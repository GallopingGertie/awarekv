import torch
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, Future
from dakv.transport.data_client import DataClient
from dakv.transport.critical_channel import CriticalChannel
from dakv.transport.refine_channel import RefineChannel
from dakv.codec.registry import get_codec
from dakv.tier.host_cache import HostCache
from dakv.common.types import EncodedBlob
from dakv.common.time_utils import Timer
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
        
        self.current_request_id: Optional[str] = None
        self.current_object_id: Optional[str] = None
    
    def start_load_kv(self, request_id: str, object_id: str, codec_name: str, num_layers: int):
        self.current_request_id = request_id
        self.current_object_id = object_id
        
        logger.info(f"Starting KV load for request {request_id}, object {object_id[:16]}...")
    
    def wait_for_layer_load(self, layer_idx: int) -> torch.Tensor:
        if self.current_object_id is None:
            raise RuntimeError("No active load operation")
        
        with Timer() as timer:
            critical_data = self.critical_channel.fetch(self.current_object_id, self.current_request_id)
        
        codec = get_codec(self.config.critical_codec)
        
        blob = EncodedBlob(
            codec_name=codec.name,
            data=critical_data,
            shape=(1, 16, 128),
            dtype="int8"
        )
        
        decoded = codec.decode(blob, device=torch.device("cuda" if torch.cuda.is_available() else "cpu"))
        
        self.metrics.record_critical_bytes(len(critical_data))
        
        logger.info(f"Layer {layer_idx} loaded in {timer.elapsed_ms():.1f}ms")
        
        return decoded
    
    def save_kv_layer(self, layer_idx: int, kv_tensor: torch.Tensor, object_id: str):
        logger.info(f"Saving layer {layer_idx} KV, shape {kv_tensor.shape}")
        
        codec = get_codec(self.config.critical_codec)
        blob = codec.encode(kv_tensor)
        
        success = self.critical_channel.store(object_id, blob.data, codec.name, "")
        
        if success:
            logger.info(f"Layer {layer_idx} saved successfully")
        else:
            logger.error(f"Layer {layer_idx} save failed")
        
        return success
