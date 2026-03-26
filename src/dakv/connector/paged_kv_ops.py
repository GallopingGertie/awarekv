import torch
from typing import List, Optional
from dakv.logging import get_logger


logger = get_logger()


def extract_prefix_kv_from_layer(
    kv_layer: torch.Tensor,
    slot_mapping: Optional[torch.Tensor],
    matched_blocks: List[int],
    matched_tokens: int,
    attn_metadata=None
) -> torch.Tensor:
    try:
        if slot_mapping is not None and len(slot_mapping) > 0:
            valid_slots = slot_mapping[slot_mapping >= 0]
            if len(valid_slots) > 0:
                return kv_layer[valid_slots[:matched_tokens]]
        
        if len(matched_blocks) > 0:
            block_tensors = []
            for block_id in matched_blocks:
                if block_id >= 0 and block_id < kv_layer.shape[0]:
                    block_tensors.append(kv_layer[block_id:block_id+1])
            if block_tensors:
                return torch.cat(block_tensors, dim=0)
        
        return kv_layer[:matched_tokens]
    
    except Exception as e:
        logger.error(f"Failed to extract prefix KV: {e}")
        return kv_layer[:min(matched_tokens, kv_layer.shape[0])]


def inject_prefix_kv_into_layer(
    dst_kv_cache_layer: torch.Tensor,
    src_kv_tensor: torch.Tensor,
    slot_mapping: Optional[torch.Tensor],
    matched_blocks: List[int],
    attn_metadata=None
) -> bool:
    try:
        if src_kv_tensor.device != dst_kv_cache_layer.device:
            src_kv_tensor = src_kv_tensor.to(dst_kv_cache_layer.device)
        
        if src_kv_tensor.dtype != dst_kv_cache_layer.dtype:
            src_kv_tensor = src_kv_tensor.to(dst_kv_cache_layer.dtype)
        
        if slot_mapping is not None and len(slot_mapping) > 0:
            num_tokens = min(src_kv_tensor.shape[0], len(slot_mapping))
            for i in range(num_tokens):
                slot_idx = slot_mapping[i].item()
                if slot_idx >= 0 and slot_idx < dst_kv_cache_layer.shape[0]:
                    dst_kv_cache_layer[slot_idx] = src_kv_tensor[i]
            logger.debug(f"Injected {num_tokens} tokens via slot_mapping")
            return True
        
        if len(matched_blocks) > 0:
            src_idx = 0
            for block_id in matched_blocks:
                if block_id >= 0 and block_id < dst_kv_cache_layer.shape[0]:
                    if src_idx < src_kv_tensor.shape[0]:
                        dst_kv_cache_layer[block_id] = src_kv_tensor[src_idx]
                        src_idx += 1
            logger.debug(f"Injected {src_idx} blocks via matched_blocks")
            return True
        
        num_tokens = min(src_kv_tensor.shape[0], dst_kv_cache_layer.shape[0])
        dst_kv_cache_layer[:num_tokens] = src_kv_tensor[:num_tokens]
        logger.debug(f"Injected {num_tokens} tokens directly")
        return True
    
    except Exception as e:
        logger.error(f"Failed to inject prefix KV: {e}")
        return False


def validate_kv_shape_compatibility(
    src_shape: tuple,
    dst_shape: tuple,
    matched_tokens: int
) -> bool:
    if len(src_shape) != len(dst_shape):
        return False
    
    if src_shape[0] < matched_tokens:
        return False
    
    for i in range(1, len(src_shape)):
        if src_shape[i] != dst_shape[i]:
            return False
    
    return True
