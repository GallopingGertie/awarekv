from typing import Optional, Any, List, Dict
from concurrent.futures import ThreadPoolExecutor
from dakv.config import DeadlineKVConfig
from dakv.planner.deadline_planner import DeadlinePlanner
from dakv.planner.estimator import BandwidthEstimator
from dakv.connector.scheduler_side import SchedulerSide
from dakv.connector.worker_side import WorkerSide
from dakv.connector.state import StateManager
from dakv.connector.vllm_adapter import (
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


class DeadlinePrefixKVConnector:
    @property
    def prefer_cross_layer_blocks(self) -> bool:
        return True
    
    def __init__(self, vllm_config, role: str, kv_cache_config=None):
        logger.info(f"Initializing DeadlinePrefixKVConnector with role={role}")
        
        if not validate_connector_role(role):
            raise ValueError(f"Invalid connector role: {role}")
        
        extra_config = getattr(vllm_config, 'kv_connector_extra_config', {})
        
        if isinstance(extra_config, dict):
            self.config = DeadlineKVConfig.from_dict(extra_config)
        else:
            self.config = DeadlineKVConfig()
        
        set_log_level(self.config.metrics.log_level)
        
        self.role = role
        self.vllm_config = vllm_config
        self.kv_cache_config = kv_cache_config
        
        self.state_manager = StateManager()
        self.metrics = get_metrics_collector()
        
        self.estimator = BandwidthEstimator(alpha=self.config.planner.alpha)
        
        self.planner = DeadlinePlanner(
            estimator=self.estimator,
            ttft_slo_ms=self.config.ttft_slo_ms,
            alpha=self.config.planner.alpha,
            min_prefix_tokens=self.config.planner.min_prefix_tokens
        )
        
        self.scheduler_side: Optional[SchedulerSide] = None
        self.worker_side: Optional[WorkerSide] = None
        
        self.pending_metadata: Dict[str, DeadlineConnectorMetadata] = {}
        self.worker_results: Dict[str, WorkerLoadResult] = {}
        
        if role in ["kv_both", "kv_consumer"]:
            self.scheduler_side = SchedulerSide(
                config=self.config,
                planner=self.planner,
                manifest_url=self.config.manifest_url
            )
            
            self.worker_side = WorkerSide(
                config=self.config,
                data_host=self.config.data_host,
                data_port=self.config.data_port
            )
        
        if self.config.metrics.enable_prometheus:
            try:
                start_metrics_server(self.config.metrics.prometheus_port)
            except Exception as e:
                logger.warning(f"Failed to start metrics server: {e}")
        
        logger.info("DeadlinePrefixKVConnector initialized successfully")
    
    def get_num_new_matched_tokens(self, request, num_computed_tokens: int):
        if self.scheduler_side is None:
            return (0, False)
        
        return self.scheduler_side.prepare_request_state(request, num_computed_tokens)
    
    def update_state_after_alloc(self, request, scheduler_output):
        if self.scheduler_side is None:
            return
        
        request_id = extract_request_id(request)
        
        try:
            allocated_blocks = extract_allocated_blocks(scheduler_output, request_id)
            
            if allocated_blocks:
                self.scheduler_side.bind_allocated_blocks(request_id, allocated_blocks)
                logger.debug(f"Request {request_id}: bound {len(allocated_blocks)} allocated blocks")
        except Exception as e:
            logger.error(f"Failed to update state after alloc for {request_id}: {e}")
    
    def build_connector_meta(self, request):
        if self.scheduler_side is None:
            return None
        
        request_id = extract_request_id(request)
        
        metadata = self.scheduler_side.build_request_metadata(request_id)
        
        if metadata:
            self.pending_metadata[request_id] = metadata
            logger.debug(f"Request {request_id}: metadata prepared for worker")
        
        return metadata
    
    def build_connector_worker_meta(self, request, metadata):
        return metadata
    
    def update_connector_output(self, request_id: str, result: WorkerLoadResult):
        if result:
            self.worker_results[request_id] = result
            logger.debug(f"Request {request_id}: worker result received, success={result.success}")
    
    def request_finished(self, request_id: str):
        if self.scheduler_side:
            state = self.scheduler_side.get_state(request_id)
            if state:
                state.status = REQUEST_STATUS_DONE
                state.request_finished = True
        
        if request_id in self.pending_metadata:
            del self.pending_metadata[request_id]
        
        if request_id in self.worker_results:
            del self.worker_results[request_id]
        
        if self.worker_side:
            self.worker_side.request_finished(request_id)
        
        logger.debug(f"Request {request_id} finished and cleaned up")
    
    def take_events(self):
        return []
    
    def start_load_kv(self, forward_context, **kwargs):
        if self.worker_side is None:
            return
        
        request_id = kwargs.get("request_id")
        if not request_id:
            logger.warning("start_load_kv called without request_id")
            return
        
        metadata = self.pending_metadata.get(request_id)
        if not metadata:
            logger.warning(f"Request {request_id}: no metadata found for loading")
            return
        
        try:
            self.worker_side.start_load_kv(forward_context, metadata)
        except Exception as e:
            logger.error(f"Request {request_id}: failed to start load: {e}")
            result = WorkerLoadResult(
                request_id=request_id,
                success=False,
                error_code="load_start_failed",
                error_message=str(e)
            )
            self.update_connector_output(request_id, result)
    
    def wait_for_layer_load(self, layer_name: str):
        if self.worker_side is None:
            return None
        
        return self.worker_side.wait_for_layer_load(layer_name)
    
    def save_kv_layer(self, layer_name: str, kv_layer, attn_metadata, **kwargs):
        if self.worker_side is None:
            return
        
        request_id = kwargs.get("request_id")
        if not request_id:
            logger.warning("save_kv_layer called without request_id")
            return
        
        try:
            self.worker_side.save_kv_layer(layer_name, kv_layer, attn_metadata, request_id)
        except Exception as e:
            logger.error(f"Request {request_id}: failed to save layer {layer_name}: {e}")
    
    def wait_for_save(self):
        if self.worker_side is None:
            return
        
        self.worker_side.wait_for_save()
    
    def get_finished(self):
        return []
