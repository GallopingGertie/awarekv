from typing import Optional, Any, List, Dict
from concurrent.futures import ThreadPoolExecutor
from dakv.config import DeadlineKVConfig
from dakv.planner.deadline_planner import DeadlinePlanner
from dakv.planner.estimator import BandwidthEstimator
from dakv.connector.scheduler_side import SchedulerSide
from dakv.connector.worker_side import WorkerSide
from dakv.connector.state import StateManager
from dakv.connector.vllm_adapter import (
    KVConnectorBase_V1,
    is_vllm_connector_available,
    extract_request_id,
    extract_prompt_tokens,
    extract_num_computed_tokens,
    extract_allocated_blocks,
    validate_connector_role
)
from dakv.common.types import DeadlineConnectorMetadata, RequestTransferState, WorkerLoadResult
from dakv.metrics import start_metrics_server, get_metrics_collector
from dakv.logging import get_logger, set_log_level
from dakv.constants import REQUEST_STATUS_DONE

logger = get_logger()


class DeadlinePrefixKVConnector(KVConnectorBase_V1):
    """
    Deadline-Aware Prefix KV Connector for vLLM
    
    This connector implements the vLLM KVConnectorBase_V1 interface to provide
    deadline-aware, tiered remote KV cache loading and saving.
    
    Key features:
    - Scheduler-side: Manifest query, transfer planning, metadata generation
    - Worker-side: Remote KV load/save, codec operations
    - Request-scoped state management for concurrent requests
    - Deadline-aware progressive transfer (critical + refinement)
    """
    
    @property
    def prefer_cross_layer_blocks(self) -> bool:
        """Request vLLM to allocate blocks that span across all layers for a request"""
        return True
    
    def __init__(self, vllm_config, role: str, kv_cache_config=None):
        """
        Initialize the connector
        
        Args:
            vllm_config: vLLM configuration object
            role: Connector role ("kv_producer", "kv_consumer", or "kv_both")
            kv_cache_config: KV cache configuration (optional)
        """
        logger.info(f"Initializing DeadlinePrefixKVConnector with role={role}")
        
        # Call parent constructor
        super().__init__(vllm_config, role, kv_cache_config)
        
        # Validate role
        if not validate_connector_role(role):
            raise ValueError(f"Invalid connector role: {role}. Must be one of: kv_producer, kv_consumer, kv_both")
        
        # Extract configuration
        extra_config = getattr(vllm_config, 'kv_connector_extra_config', {})
        
        if isinstance(extra_config, dict):
            self.config = DeadlineKVConfig.from_dict(extra_config)
        else:
            self.config = DeadlineKVConfig()
        
        set_log_level(self.config.metrics.log_level)
        
        # Store vLLM config
        self.role = role
        self.vllm_config = vllm_config
        self.kv_cache_config = kv_cache_config
        
        # Initialize core components
        self.state_manager = StateManager()
        self.metrics = get_metrics_collector()
        
        # Initialize planner components
        self.estimator = BandwidthEstimator(alpha=self.config.planner.alpha)
        
        self.planner = DeadlinePlanner(
            estimator=self.estimator,
            ttft_slo_ms=self.config.ttft_slo_ms,
            alpha=self.config.planner.alpha,
            min_prefix_tokens=self.config.planner.min_prefix_tokens
        )
        
        # Initialize role-specific components
        self.scheduler_side: Optional[SchedulerSide] = None
        self.worker_side: Optional[WorkerSide] = None
        
        # Request-scoped state
        self.pending_metadata: Dict[str, DeadlineConnectorMetadata] = {}
        self.worker_results: Dict[str, WorkerLoadResult] = {}
        self.finished_requests: List[str] = []
        
        # Initialize components based on role
        if role in ["kv_both", "kv_consumer"]:
            logger.info("Initializing scheduler-side components")
            self.scheduler_side = SchedulerSide(
                config=self.config,
                planner=self.planner,
                manifest_url=self.config.manifest_url,
                state_manager=self.state_manager
            )
            
            logger.info("Initializing worker-side components")
            self.worker_side = WorkerSide(
                config=self.config,
                data_host=self.config.data_host,
                data_port=self.config.data_port
            )
        
        # Start metrics server if enabled
        if self.config.metrics.enable_prometheus:
            try:
                start_metrics_server(self.config.metrics.prometheus_port)
                logger.info(f"Metrics server started on port {self.config.metrics.prometheus_port}")
            except Exception as e:
                logger.warning(f"Failed to start metrics server: {e}")
        
        logger.info("DeadlinePrefixKVConnector initialized successfully")
        logger.info(f"vLLM Connector Base available: {is_vllm_connector_available()}")
    
    # ========== Scheduler-Side Lifecycle Methods ==========
    
    def get_num_new_matched_tokens(self, request, num_computed_tokens: int):
        """
        Scheduler-side: Query manifest and determine how many prefix tokens can be loaded
        
        Returns:
            Tuple[int, bool]: (num_matched_tokens, is_external_load)
        """
        if self.scheduler_side is None:
            logger.debug("Scheduler side not initialized, returning 0 matched tokens")
            return (0, False)
        
        try:
            result = self.scheduler_side.prepare_request_state(request, num_computed_tokens)
            
            request_id = extract_request_id(request)
            if result[0] > 0:
                logger.info(f"Request {request_id}: {result[0]} prefix tokens matched (external={result[1]})")
            else:
                logger.debug(f"Request {request_id}: no prefix match")
            
            return result
        
        except Exception as e:
            request_id = extract_request_id(request)
            logger.error(f"Request {request_id}: error in get_num_new_matched_tokens: {e}")
            return (0, False)
    
    def update_state_after_alloc(self, request, scheduler_output):
        """
        Scheduler-side: Update state after vLLM allocates blocks for this request
        
        This is called after block allocation, giving us access to the allocated block IDs.
        """
        if self.scheduler_side is None:
            return
        
        request_id = extract_request_id(request)
        
        try:
            allocated_blocks = extract_allocated_blocks(scheduler_output, request_id)
            
            if allocated_blocks:
                self.scheduler_side.bind_allocated_blocks(request_id, allocated_blocks)
                logger.debug(f"Request {request_id}: bound {len(allocated_blocks)} allocated blocks")
            else:
                logger.debug(f"Request {request_id}: no allocated blocks found")
        
        except Exception as e:
            logger.error(f"Request {request_id}: failed to update state after alloc: {e}")
    
    def build_connector_meta(self, request):
        """
        Scheduler-side: Build metadata to pass to worker
        
        This metadata contains all information worker needs to perform remote load,
        including object IDs, codecs, matched blocks, etc.
        
        Returns:
            DeadlineConnectorMetadata or None
        """
        if self.scheduler_side is None:
            return None
        
        request_id = extract_request_id(request)
        
        try:
            metadata = self.scheduler_side.build_request_metadata(request_id)
            
            if metadata:
                self.pending_metadata[request_id] = metadata
                logger.info(
                    f"Request {request_id}: metadata built "
                    f"(mode={metadata.plan_mode}, tokens={metadata.matched_tokens})"
                )
            else:
                logger.debug(f"Request {request_id}: no metadata to build (likely manifest miss)")
            
            return metadata
        
        except Exception as e:
            logger.error(f"Request {request_id}: failed to build connector meta: {e}")
            return None
    
    def build_connector_worker_meta(self, request, metadata):
        """
        Scheduler-side: Transform scheduler metadata to worker metadata
        
        In our case, metadata structure is the same for both sides.
        """
        return metadata
    
    def update_connector_output(self, request_id: str, result: WorkerLoadResult):
        """
        Scheduler-side: Receive worker load/save results
        
        This is called by vLLM to notify scheduler of worker-side completion.
        """
        if result:
            self.worker_results[request_id] = result
            
            if result.success:
                logger.info(
                    f"Request {request_id}: worker operation succeeded "
                    f"(critical_done={result.critical_load_done})"
                )
            else:
                logger.warning(
                    f"Request {request_id}: worker operation failed "
                    f"(error={result.error_code}: {result.error_message})"
                )
        else:
            logger.warning(f"Request {request_id}: received None worker result")
    
    def request_finished(self, request_id: str):
        """
        Scheduler-side: Cleanup when request is complete
        
        This is called when a request fully completes (all tokens generated).
        """
        logger.info(f"Request {request_id}: request finished, starting cleanup")
        
        # Update scheduler-side state
        if self.scheduler_side:
            state = self.scheduler_side.get_state(request_id)
            if state:
                state.status = REQUEST_STATUS_DONE
                state.request_finished = True
        
        # Cleanup pending metadata
        if request_id in self.pending_metadata:
            del self.pending_metadata[request_id]
            logger.debug(f"Request {request_id}: removed pending metadata")
        
        # Cleanup worker results
        if request_id in self.worker_results:
            del self.worker_results[request_id]
            logger.debug(f"Request {request_id}: removed worker results")
        
        # Notify worker side for cleanup (e.g., save sessions)
        if self.worker_side:
            self.worker_side.request_finished(request_id)
        
        # Track finished requests for get_finished()
        self.finished_requests.append(request_id)
        
        logger.info(f"Request {request_id}: cleanup complete")
    
    def take_events(self):
        """
        Scheduler-side: Return any pending events to vLLM
        
        Currently we don't use events mechanism, return empty list.
        """
        return []
    
    def get_finished(self):
        """
        Scheduler-side: Return list of finished request IDs
        
        This allows vLLM to know which requests have completed their connector lifecycle.
        """
        finished = self.finished_requests.copy()
        self.finished_requests.clear()
        
        if finished:
            logger.debug(f"Returning {len(finished)} finished requests: {finished}")
        
        return finished
    
    # ========== Worker-Side Lifecycle Methods ==========
    
    def start_load_kv(self, forward_context, **kwargs):
        """
        Worker-side: Start loading external KV for this request
        
        This is called before the first forward pass for a request.
        """
        if self.worker_side is None:
            logger.warning("Worker side not initialized, cannot start load")
            return
        
        request_id = kwargs.get("request_id")
        if not request_id:
            logger.warning("start_load_kv called without request_id in kwargs")
            return
        
        # Get metadata from scheduler
        metadata = self.pending_metadata.get(request_id)
        if not metadata:
            logger.debug(f"Request {request_id}: no metadata found, skipping external load")
            return
        
        try:
            logger.info(f"Request {request_id}: starting KV load (mode={metadata.plan_mode})")
            self.worker_side.start_load_kv(forward_context, metadata)
        
        except Exception as e:
            logger.error(f"Request {request_id}: failed to start load: {e}", exc_info=True)
            
            # Report failure to scheduler
            result = WorkerLoadResult(
                request_id=request_id,
                success=False,
                critical_load_done=False,
                error_code="load_start_failed",
                error_message=str(e)
            )
            self.update_connector_output(request_id, result)
    
    def wait_for_layer_load(self, layer_name: str):
        """
        Worker-side: Wait for a specific layer's KV to be loaded
        
        This is called by vLLM before processing each layer.
        Returns the loaded KV tensor for this layer (or None if not loaded).
        """
        if self.worker_side is None:
            return None
        
        try:
            return self.worker_side.wait_for_layer_load(layer_name)
        
        except Exception as e:
            logger.error(f"Failed to wait for layer {layer_name} load: {e}")
            return None
    
    def save_kv_layer(self, layer_name: str, kv_layer, attn_metadata, **kwargs):
        """
        Worker-side: Save a layer's KV to remote storage
        
        This is called after each layer's forward pass for a request we want to save.
        """
        if self.worker_side is None:
            logger.warning("Worker side not initialized, cannot save KV")
            return
        
        request_id = kwargs.get("request_id")
        if not request_id:
            logger.warning(f"save_kv_layer called without request_id for layer {layer_name}")
            return
        
        try:
            self.worker_side.save_kv_layer(layer_name, kv_layer, attn_metadata, request_id)
        
        except Exception as e:
            logger.error(f"Request {request_id}: failed to save layer {layer_name}: {e}")
    
    def wait_for_save(self):
        """
        Worker-side: Wait for all pending save operations to complete
        
        This is called when vLLM wants to ensure all saves are flushed.
        """
        if self.worker_side is None:
            return
        
        try:
            logger.debug("Waiting for all save operations to complete")
            self.worker_side.wait_for_save()
            logger.debug("All save operations complete")
        
        except Exception as e:
            logger.error(f"Failed to wait for save: {e}")
