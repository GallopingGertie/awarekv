import torch
from typing import List
from dakv.codec.registry import get_codec
from dakv.common.types import EncodedBlob
from dakv.transport.data_client import DataClient
from dakv.transport.critical_channel import CriticalChannel
from dakv.transport.refine_channel import RefineChannel
from dakv.common.time_utils import Timer
from dakv.logging import get_logger


logger = get_logger()


class RemoteKVLoader:
    def __init__(self, critical_channel: CriticalChannel, refine_channel: RefineChannel):
        self.critical_channel = critical_channel
        self.refine_channel = refine_channel
    
    def load_critical(
        self,
        object_id: str,
        codec_name: str,
        shape: tuple,
        device: torch.device,
        request_id: str = ""
    ) -> torch.Tensor:
        with Timer() as timer:
            data = self.critical_channel.fetch(object_id, request_id)
        
        codec = get_codec(codec_name)
        
        blob = EncodedBlob(
            codec_name=codec_name,
            data=data,
            shape=shape,
            dtype="int8"
        )
        
        decoded = codec.decode(blob, device=device)
        
        logger.info(f"Critical loaded in {timer.elapsed_ms():.1f}ms, {len(data)} bytes")
        
        return decoded
    
    def load_refinement(
        self,
        object_id: str,
        codec_name: str,
        shape: tuple,
        device: torch.device,
        request_id: str = ""
    ) -> torch.Tensor:
        with Timer() as timer:
            data = self.refine_channel.fetch(object_id, request_id)
        
        if data is None:
            logger.warning("Refinement fetch failed, skipping")
            return None
        
        codec = get_codec(codec_name)
        
        blob = EncodedBlob(
            codec_name=codec_name,
            data=data,
            shape=shape,
            dtype="float16"
        )
        
        decoded = codec.decode(blob, device=device)
        
        logger.info(f"Refinement loaded in {timer.elapsed_ms():.1f}ms, {len(data)} bytes")
        
        return decoded
    
    def apply_pending_refinement(self, kv_cache: torch.Tensor, refined_kv: torch.Tensor, block_ids: List[int]):
        if refined_kv is None:
            return
        
        for i, block_id in enumerate(block_ids):
            if block_id >= 0 and block_id < kv_cache.shape[0]:
                kv_cache[block_id] = refined_kv[i]
        
        logger.debug(f"Applied refinement to {len(block_ids)} blocks")
