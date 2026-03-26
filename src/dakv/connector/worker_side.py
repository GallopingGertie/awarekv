import torch
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor
from dakv.transport.data_client import DataClient
from dakv.transport.critical_channel import CriticalChannel
from dakv.transport.refine_channel import RefineChannel
from dakv.codec.registry import get_codec
from dakv.tier.host_cache import HostCache
from dakv.connector.save_session import SaveSession
from dakv.connector.paged_kv_ops import extract_prefix_kv_from_layer, inject_prefix_kv_into_layer
from dakv.connector.vllm_adapter import extract_slot_mapping, extract_attention_metadata
from dakv.common.types import DeadlineConnectorMetadata, WorkerLoadResult
from dakv.common.time_utils import Timer, current_time_ms
from dakv.logging import get_logger
from dakv.metrics import get_metrics_collector


logger = get_logger()


class WorkerSide:
    def __init__(self, config, data_host: str, data_port: int):
        self.config = config
        self.client = DataClient(data_host, data_port, timeout_ms=config.network_timeout_ms)
        self.critical_channel = CriticalChannel(self.client, timeout_ms=config.network_timeout_ms)
        self.refine_channel = RefineChannel(self.client, timeout_ms=config.refine_timeout_ms)
        
        self.host_cache: Optional[HostCache] = None
        if config.enable_tier1_host_cache:
            self.host_cache = HostCache(config.max_host_cache_bytes)
        
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.metrics = get_metrics_collector()
        
        self.active_loads: Dict[str, DeadlineConnectorMetadata] = {}
        self.loaded_kvs: Dict[str, List[torch.Tensor]] = {}
        
        self.save_sessions: Dict[str, SaveSession] = {}
        
        logger.info("WorkerSide initialized")
    
    def start_load_kv(self, forward_context, metadata: DeadlineConnectorMetadata):
        request_id = metadata.request_id
        
        self.active_loads[request_id] = metadata
        
        logger.info(f"Request {request_id}: starting KV load, mode={metadata.plan_mode}, critical_object={metadata.critical_object_id[:16]}...")
        
        try:
            with Timer() as timer:
                critical_data = self.critical_channel.fetch(
                    metadata.critical_object_id,
                    request_id
                )
            
            if critical_data is None:
                raise RuntimeError("Critical fetch failed")
            
            self.metrics.record_critical_bytes(len(critical_data))
            
            codec = get_codec(metadata.critical_codec)
            
            per_layer_kvs = self._parse_and_decode_object(
                critical_data,
                codec,
                metadata.num_layers
            )
            
            self.loaded_kvs[request_id] = per_layer_kvs
            
            logger.info(f"Request {request_id}: critical KV loaded in {timer.elapsed_ms():.1f}ms, {len(per_layer_kvs)} layers")
            
            if metadata.need_refinement and metadata.refinement_object_id:
                logger.info(f"Request {request_id}: scheduling refinement load")
        
        except Exception as e:
            logger.error(f"Request {request_id}: load failed: {e}")
            raise
    
    def wait_for_layer_load(self, layer_name: str) -> Optional[torch.Tensor]:
        try:
            layer_idx = int(layer_name.split("_")[-1]) if "_" in layer_name else 0
        except:
            layer_idx = 0
        
        for request_id, kvs in self.loaded_kvs.items():
            if layer_idx < len(kvs):
                kv_tensor = kvs[layer_idx]
                logger.debug(f"Layer {layer_name}: returning loaded KV, shape {kv_tensor.shape}")
                return kv_tensor
        
        return None
    
    def save_kv_layer(self, layer_name: str, kv_layer: torch.Tensor, attn_metadata, request_id: str):
        if request_id not in self.save_sessions:
            logger.warning(f"Request {request_id}: no save session, creating one")
            self.save_sessions[request_id] = SaveSession(
                request_id=request_id,
                prefix_key="temp_key",
                matched_tokens=0,
                matched_blocks=[],
                num_layers=self.config.num_layers
            )
        
        session = self.save_sessions[request_id]
        
        try:
            slot_mapping = extract_slot_mapping(attn_metadata) if attn_metadata else None
            
            prefix_kv = extract_prefix_kv_from_layer(
                kv_layer=kv_layer,
                slot_mapping=slot_mapping,
                matched_blocks=session.matched_blocks,
                matched_tokens=session.matched_tokens,
                attn_metadata=attn_metadata
            )
            
            session.add_layer(layer_name, prefix_kv, attn_metadata, slot_mapping)
            
            logger.debug(f"Request {request_id}: saved layer {layer_name}, shape {prefix_kv.shape}")
        
        except Exception as e:
            logger.error(f"Request {request_id}: failed to save layer {layer_name}: {e}")
            session.abort(str(e))
    
    def wait_for_save(self):
        logger.debug("wait_for_save called")
    
    def request_finished(self, request_id: str):
        if request_id in self.active_loads:
            del self.active_loads[request_id]
        
        if request_id in self.loaded_kvs:
            del self.loaded_kvs[request_id]
        
        if request_id in self.save_sessions:
            session = self.save_sessions[request_id]
            if session.is_complete() and not session.aborted:
                logger.info(f"Request {request_id}: save session complete, would flush to saver")
            del self.save_sessions[request_id]
        
        logger.debug(f"Request {request_id}: worker-side cleanup done")
    
    def _parse_and_decode_object(self, data: bytes, codec, num_layers: int) -> List[torch.Tensor]:
        layers = []
        
        offset = 0
        chunk_size = len(data) // num_layers
        
        for i in range(num_layers):
            start = i * chunk_size
            end = start + chunk_size if i < num_layers - 1 else len(data)
            layer_data = data[start:end]
            
            from dakv.common.types import EncodedBlob
            blob = EncodedBlob(
                codec_name=codec.name,
                data=layer_data,
                shape=(1, 16, 128),
                dtype="int8" if "int8" in codec.name else "float16"
            )
            
            decoded = codec.decode(blob, device=torch.device("cuda" if torch.cuda.is_available() else "cpu"))
            layers.append(decoded)
        
        return layers
