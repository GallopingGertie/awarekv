from typing import Optional, Any
from dakv.config import DeadlineKVConfig
from dakv.planner.deadline_planner import DeadlinePlanner
from dakv.planner.estimator import BandwidthEstimator
from dakv.connector.scheduler_side import SchedulerSide
from dakv.connector.worker_side import WorkerSide
from dakv.connector.state import StateManager
from dakv.metrics import start_metrics_server
from dakv.logging import get_logger, set_log_level


logger = get_logger()


class DeadlinePrefixKVConnector:
    @property
    def prefer_cross_layer_blocks(self) -> bool:
        return True
    
    def __init__(self, vllm_config, role: str, kv_cache_config=None):
        logger.info(f"Initializing DeadlinePrefixKVConnector with role={role}")
        
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
        
        self.estimator = BandwidthEstimator(alpha=self.config.planner.alpha)
        
        self.planner = DeadlinePlanner(
            estimator=self.estimator,
            ttft_slo_ms=self.config.ttft_slo_ms,
            alpha=self.config.planner.alpha,
            min_prefix_tokens=self.config.planner.min_prefix_tokens
        )
        
        self.scheduler_side: Optional[SchedulerSide] = None
        self.worker_side: Optional[WorkerSide] = None
        
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
            start_metrics_server(self.config.metrics.prometheus_port)
        
        logger.info("DeadlinePrefixKVConnector initialized successfully")
    
    def get_num_new_matched_tokens(self, request, num_computed_tokens: int):
        if self.scheduler_side is None:
            return (0, False)
        
        return self.scheduler_side.get_num_matched_tokens(request, num_computed_tokens)
    
    def update_state_after_alloc(self, *args, **kwargs):
        pass
    
    def update_connector_output(self, *args, **kwargs):
        pass
    
    def request_finished(self, request_id: str):
        self.state_manager.remove(request_id)
        logger.debug(f"Request {request_id} finished")
    
    def take_events(self):
        return []
    
    def start_load_kv(self, forward_context, **kwargs):
        if self.worker_side is None:
            return
        
        request_id = kwargs.get("request_id", "unknown")
        object_id = kwargs.get("object_id", "")
        codec_name = kwargs.get("codec_name", self.config.critical_codec)
        num_layers = kwargs.get("num_layers", 32)
        
        self.worker_side.start_load_kv(request_id, object_id, codec_name, num_layers)
    
    def wait_for_layer_load(self, layer_name: str):
        if self.worker_side is None:
            return None
        
        layer_idx = int(layer_name.split("_")[-1]) if "_" in layer_name else 0
        
        return self.worker_side.wait_for_layer_load(layer_idx)
    
    def save_kv_layer(self, layer_name: str, kv_layer, attn_metadata, **kwargs):
        if self.worker_side is None:
            return
        
        layer_idx = int(layer_name.split("_")[-1]) if "_" in layer_name else 0
        object_id = kwargs.get("object_id", "")
        
        self.worker_side.save_kv_layer(layer_idx, kv_layer, object_id)
    
    def wait_for_save(self):
        pass
    
    def build_connector_worker_meta(self, *args, **kwargs):
        return {}
    
    def get_finished(self):
        return []
