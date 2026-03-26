import torch
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, Future
from dakv.transport.data_client import DataClient
from dakv.transport.critical_channel import CriticalChannel
from dakv.transport.refine_channel import RefineChannel
from dakv.codec.registry import get_codec
from dakv.tier.host_cache import HostCache
from dakv.connector.save_session import SaveSession
from dakv.connector.paged_kv_ops import extract_prefix_kv_from_layer, inject_prefix_kv_into_layer
from dakv.connector.vllm_adapter import extract_slot_mapping, extract_attention_metadata
from dakv.connector.metadata import create_load_result
from dakv.common.types import DeadlineConnectorMetadata, WorkerLoadResult, EncodedBlob
from dakv.common.time_utils import Timer, current_time_ms
from dakv.logging import get_logger
from dakv.metrics import get_metrics_collector


logger = get_logger()


class WorkerSide:
    """
    Worker-side logic for DeadlinePrefixKVConnector
    
    Responsibilities:
    - Load remote KV cache (critical + optional refinement)
    - Decode and inject KV into vLLM's layer processing
    - Save request KV to remote storage
    - Manage worker-side request lifecycle
    """
    
    def __init__(self, config, data_host: str, data_port: int):
        """
        Initialize worker-side components
        
        Args:
            config: Connector configuration
            data_host: Data server host
            data_port: Data server port
        """
        self.config = config
        
        # Initialize network client
        self.client = DataClient(data_host, data_port, timeout_ms=config.network_timeout_ms)
        
        # Initialize channels for critical and refinement transfers
        self.critical_channel = CriticalChannel(
            self.client,
            timeout_ms=config.network_timeout_ms
        )
        self.refine_channel = RefineChannel(
            self.client,
            timeout_ms=config.refine_timeout_ms
        )
        
        # Initialize host cache (Tier-1) if enabled
        self.host_cache: Optional[HostCache] = None
        if config.enable_tier1_host_cache:
            self.host_cache = HostCache(config.max_host_cache_bytes)
            logger.info(f"Host cache enabled (max {config.max_host_cache_bytes} bytes)")
        
        # Thread pool for async operations
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Metrics collector
        self.metrics = get_metrics_collector()
        
        # Request-scoped load state
        self.active_loads: Dict[str, DeadlineConnectorMetadata] = {}
        self.loaded_kvs: Dict[str, List[torch.Tensor]] = {}
        self.load_futures: Dict[str, Future] = {}
        
        # Request-scoped save state
        self.save_sessions: Dict[str, SaveSession] = {}
        
        logger.info(f"WorkerSide initialized (data_host={data_host}:{data_port})")
    
    def start_load_kv(
        self,
        forward_context,
        metadata: DeadlineConnectorMetadata
    ) -> Optional[WorkerLoadResult]:
        """
        Start loading external KV for this request
        
        This is called from connector's start_load_kv() lifecycle method,
        before the first forward pass.
        
        Args:
            forward_context: vLLM forward context (may contain device info)
            metadata: Connector metadata with load instructions
        
        Returns:
            WorkerLoadResult indicating success/failure
        """
        request_id = metadata.request_id
        
        # Track active load
        self.active_loads[request_id] = metadata
        
        logger.info(
            f"Request {request_id}: starting KV load "
            f"(mode={metadata.plan_mode}, "
            f"critical_object={metadata.critical_object_id[:16]}..., "
            f"need_refinement={metadata.need_refinement})"
        )
        
        try:
            # Load critical KV (synchronous for now)
            with Timer() as timer:
                critical_data = self._fetch_critical_kv(metadata)
            
            if critical_data is None:
                raise RuntimeError("Critical KV fetch failed")
            
            logger.info(
                f"Request {request_id}: critical KV fetched in {timer.elapsed_ms():.1f}ms "
                f"({len(critical_data)} bytes)"
            )
            
            self.metrics.record_critical_bytes(len(critical_data))
            
            # Decode critical KV
            per_layer_kvs = self._decode_critical_kv(
                critical_data,
                metadata.critical_codec,
                metadata.num_layers
            )
            
            # Store loaded KVs for layer retrieval
            self.loaded_kvs[request_id] = per_layer_kvs
            
            logger.info(
                f"Request {request_id}: critical KV loaded successfully "
                f"({len(per_layer_kvs)} layers, total {timer.elapsed_ms():.1f}ms)"
            )
            
            # Schedule refinement load if needed (async)
            if metadata.need_refinement and metadata.refinement_object_id:
                logger.info(f"Request {request_id}: scheduling refinement load")
                self._schedule_refinement_load(metadata)
            
            # Create success result
            result = create_load_result(
                request_id=request_id,
                success=True,
                critical_done=True,
                refinement_done=False,
                loaded_tokens=metadata.matched_tokens,
                loaded_blocks=len(metadata.matched_blocks),
                critical_bytes=len(critical_data),
                critical_load_ms=timer.elapsed_ms()
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Request {request_id}: KV load failed: {e}", exc_info=True)
            
            # Clean up on failure
            if request_id in self.active_loads:
                del self.active_loads[request_id]
            
            # Create failure result
            result = create_load_result(
                request_id=request_id,
                success=False,
                critical_done=False,
                error_code="load_failed",
                error_message=str(e)
            )
            
            return result
    
    def wait_for_layer_load(self, layer_name: str) -> Optional[torch.Tensor]:
        """
        Wait for and return loaded KV for specific layer
        
        This is called from connector's wait_for_layer_load() lifecycle method,
        before processing each layer.
        
        Args:
            layer_name: Layer name (e.g., "layer_0", "layer_1", ...)
        
        Returns:
            Loaded KV tensor for this layer, or None if not loaded
        """
        try:
            layer_idx = self._extract_layer_idx(layer_name)
        except ValueError:
            logger.warning(f"Cannot extract layer index from {layer_name}")
            return None
        
        # Find request with loaded KV for this layer
        for request_id, kvs in self.loaded_kvs.items():
            if layer_idx < len(kvs):
                kv_tensor = kvs[layer_idx]
                logger.debug(
                    f"Request {request_id}: returning loaded KV for {layer_name}, "
                    f"shape {kv_tensor.shape}"
                )
                return kv_tensor
        
        logger.debug(f"No loaded KV found for {layer_name}")
        return None
    
    def save_kv_layer(
        self,
        layer_name: str,
        kv_layer: torch.Tensor,
        attn_metadata,
        request_id: str
    ):
        """
        Save a layer's KV to save session (for later flush to remote)
        
        This is called from connector's save_kv_layer() lifecycle method,
        after each layer's forward pass.
        
        Args:
            layer_name: Layer name
            kv_layer: KV tensor for this layer
            attn_metadata: Attention metadata (contains slot mapping)
            request_id: Request ID
        """
        # Ensure save session exists
        if request_id not in self.save_sessions:
            logger.warning(f"Request {request_id}: no save session, creating default one")
            self.save_sessions[request_id] = SaveSession(
                request_id=request_id,
                prefix_key="temp_key",
                matched_tokens=0,
                matched_blocks=[],
                num_layers=self.config.num_layers
            )
        
        session = self.save_sessions[request_id]
        
        try:
            # Extract slot mapping from attention metadata
            slot_mapping = extract_slot_mapping(attn_metadata) if attn_metadata else None
            
            # Extract prefix KV from layer
            prefix_kv = extract_prefix_kv_from_layer(
                kv_layer=kv_layer,
                slot_mapping=slot_mapping,
                matched_blocks=session.matched_blocks,
                matched_tokens=session.matched_tokens,
                attn_metadata=attn_metadata
            )
            
            # Add to save session
            session.add_layer(layer_name, prefix_kv, attn_metadata, slot_mapping)
            
            logger.debug(
                f"Request {request_id}: saved layer {layer_name}, "
                f"shape {prefix_kv.shape}"
            )
        
        except Exception as e:
            logger.error(f"Request {request_id}: failed to save layer {layer_name}: {e}")
            session.abort(str(e))
    
    def wait_for_save(self):
        """
        Wait for all pending save operations to complete
        
        This is called from connector's wait_for_save() lifecycle method.
        """
        if not self.save_sessions:
            logger.debug("wait_for_save: no active save sessions")
            return
        
        logger.info(f"wait_for_save: waiting for {len(self.save_sessions)} save sessions")
        
        # In current implementation, saves are synchronous
        # Future implementation could flush sessions to saver here
        logger.debug("wait_for_save: all saves complete (synchronous mode)")
    
    def request_finished(self, request_id: str):
        """
        Cleanup worker-side state when request finishes
        
        This is called from connector's request_finished() lifecycle method.
        
        Args:
            request_id: Request ID
        """
        logger.info(f"Request {request_id}: worker-side cleanup starting")
        
        # Cleanup active loads
        if request_id in self.active_loads:
            del self.active_loads[request_id]
            logger.debug(f"Request {request_id}: removed active load")
        
        # Cleanup loaded KVs
        if request_id in self.loaded_kvs:
            # Free GPU memory
            for kv_tensor in self.loaded_kvs[request_id]:
                del kv_tensor
            del self.loaded_kvs[request_id]
            logger.debug(f"Request {request_id}: freed loaded KV tensors")
        
        # Cleanup load futures
        if request_id in self.load_futures:
            future = self.load_futures[request_id]
            if not future.done():
                future.cancel()
            del self.load_futures[request_id]
            logger.debug(f"Request {request_id}: cancelled load future")
        
        # Cleanup save session
        if request_id in self.save_sessions:
            session = self.save_sessions[request_id]
            
            if session.is_complete() and not session.aborted:
                logger.info(f"Request {request_id}: save session complete, would flush to saver")
                # TODO: Flush to saver service
            elif session.aborted:
                logger.warning(
                    f"Request {request_id}: save session aborted, "
                    f"reason: {session.abort_reason}"
                )
            else:
                logger.warning(f"Request {request_id}: save session incomplete")
            
            del self.save_sessions[request_id]
            logger.debug(f"Request {request_id}: removed save session")
        
        logger.info(f"Request {request_id}: worker-side cleanup complete")
    
    # ========== Private Helper Methods ==========
    
    def _fetch_critical_kv(self, metadata: DeadlineConnectorMetadata) -> Optional[bytes]:
        """
        Fetch critical KV from data server
        
        Args:
            metadata: Connector metadata
        
        Returns:
            Raw critical KV bytes or None on failure
        """
        try:
            critical_data = self.critical_channel.fetch(
                metadata.critical_object_id,
                metadata.request_id
            )
            
            if critical_data is None:
                logger.error(
                    f"Request {metadata.request_id}: critical channel returned None"
                )
                return None
            
            return critical_data
        
        except Exception as e:
            logger.error(
                f"Request {metadata.request_id}: failed to fetch critical KV: {e}"
            )
            return None
    
    def _decode_critical_kv(
        self,
        data: bytes,
        codec_name: str,
        num_layers: int
    ) -> List[torch.Tensor]:
        """
        Decode critical KV data into per-layer tensors
        
        Args:
            data: Raw encoded KV bytes
            codec_name: Codec name for decoding
            num_layers: Number of layers
        
        Returns:
            List of decoded KV tensors (one per layer)
        """
        codec = get_codec(codec_name)
        
        layers = []
        chunk_size = len(data) // num_layers
        
        for i in range(num_layers):
            start = i * chunk_size
            end = start + chunk_size if i < num_layers - 1 else len(data)
            layer_data = data[start:end]
            
            # Infer shape from data size and config
            # For now, use a reasonable default that matches common models
            # Shape: (num_blocks, block_size, num_kv_heads, head_size)
            # Simplified: assume we can infer from data size
            block_size = self.config.block_size
            
            # Estimate shape from byte size
            # int8: 1 byte per element, fp16: 2 bytes per element
            bytes_per_element = 1 if "int8" in codec_name else 2
            total_elements = len(layer_data) // bytes_per_element
            
            # Reasonable default: (1, block_size, 32, 128) for num_blocks=1
            # This will be overridden by actual decoded tensor shape
            estimated_shape = (1, block_size, 32, 128)
            
            # Create encoded blob with estimated shape
            # The codec will decode and return actual shape
            blob = EncodedBlob(
                codec_name=codec.name,
                data=layer_data,
                shape=estimated_shape,
                dtype="int8" if "int8" in codec.name else "float16"
            )
            
            # Decode - codec will handle actual shape
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            decoded = codec.decode(blob, device=device)
            
            layers.append(decoded)
        
        return layers
    
    def _schedule_refinement_load(self, metadata: DeadlineConnectorMetadata):
        """
        Schedule asynchronous refinement load
        
        Args:
            metadata: Connector metadata with refinement info
        """
        request_id = metadata.request_id
        
        def _load_refinement():
            try:
                logger.info(f"Request {request_id}: starting refinement load")
                
                refine_data = self.refine_channel.fetch(
                    metadata.refinement_object_id,
                    request_id
                )
                
                if refine_data:
                    logger.info(
                        f"Request {request_id}: refinement loaded "
                        f"({len(refine_data)} bytes)"
                    )
                    self.metrics.record_refinement_bytes(len(refine_data))
                    # TODO: Apply refinement to loaded KVs
                else:
                    logger.warning(f"Request {request_id}: refinement load failed")
            
            except Exception as e:
                logger.error(f"Request {request_id}: refinement load error: {e}")
        
        # Submit to thread pool
        future = self.executor.submit(_load_refinement)
        self.load_futures[request_id] = future
    
    @staticmethod
    def _extract_layer_idx(layer_name: str) -> int:
        """
        Extract layer index from layer name
        
        Args:
            layer_name: Layer name (e.g., "layer_0", "layer_1")
        
        Returns:
            Layer index
        
        Raises:
            ValueError: If layer name format is invalid
        """
        if "_" in layer_name:
            parts = layer_name.split("_")
            return int(parts[-1])
        else:
            return int(layer_name)
