import torch
from typing import Dict, List, Optional
from dataclasses import dataclass
from dakv.logging import get_logger


logger = get_logger()


@dataclass
class LayerKVData:
    layer_idx: int
    layer_name: str
    kv_tensor: torch.Tensor
    shape: tuple
    dtype: str


class SaveSession:
    def __init__(
        self,
        request_id: str,
        prefix_key: str,
        matched_tokens: int,
        matched_blocks: List[int],
        num_layers: int
    ):
        self.request_id = request_id
        self.prefix_key = prefix_key
        self.matched_tokens = matched_tokens
        self.matched_blocks = matched_blocks
        self.num_layers = num_layers
        
        self.layer_data: Dict[int, LayerKVData] = {}
        self.completed = False
        self.aborted = False
        self.abort_reason: Optional[str] = None
        
        logger.info(f"SaveSession created for request {request_id}, {num_layers} layers expected")
    
    def add_layer(
        self,
        layer_name: str,
        kv_tensor: torch.Tensor,
        attn_metadata=None,
        slot_mapping=None
    ) -> bool:
        if self.completed or self.aborted:
            logger.warning(f"SaveSession {self.request_id}: cannot add layer, session closed")
            return False
        
        try:
            layer_idx = int(layer_name.split("_")[-1]) if "_" in layer_name else len(self.layer_data)
        except:
            layer_idx = len(self.layer_data)
        
        if layer_idx >= self.num_layers:
            logger.warning(f"SaveSession {self.request_id}: layer_idx {layer_idx} >= {self.num_layers}")
            return False
        
        if layer_idx in self.layer_data:
            logger.warning(f"SaveSession {self.request_id}: layer {layer_idx} already added, skipping")
            return False
        
        if kv_tensor.is_cuda:
            kv_tensor = kv_tensor.cpu()
        
        kv_tensor = kv_tensor.clone()
        
        layer_data = LayerKVData(
            layer_idx=layer_idx,
            layer_name=layer_name,
            kv_tensor=kv_tensor,
            shape=tuple(kv_tensor.shape),
            dtype=str(kv_tensor.dtype)
        )
        
        self.layer_data[layer_idx] = layer_data
        
        logger.debug(f"SaveSession {self.request_id}: added layer {layer_idx}, shape {kv_tensor.shape}, {len(self.layer_data)}/{self.num_layers}")
        
        return True
    
    def is_complete(self) -> bool:
        return len(self.layer_data) >= self.num_layers
    
    def abort(self, reason: str):
        self.aborted = True
        self.abort_reason = reason
        logger.warning(f"SaveSession {self.request_id}: aborted, reason: {reason}")
    
    def get_all_layers(self) -> List[LayerKVData]:
        return [self.layer_data[i] for i in sorted(self.layer_data.keys())]
    
    def mark_completed(self):
        self.completed = True
        logger.info(f"SaveSession {self.request_id}: marked completed, {len(self.layer_data)} layers saved")
