import torch
from typing import List
from dakv.logging import get_logger


logger = get_logger()


def apply_kv_to_cache(
    kv_tensor: torch.Tensor,
    kv_cache: torch.Tensor,
    slot_mapping: torch.Tensor,
    layer_idx: int
):
    try:
        if slot_mapping is None or len(slot_mapping) == 0:
            logger.warning(f"Empty slot_mapping for layer {layer_idx}")
            return
        
        num_tokens = kv_tensor.shape[0]
        
        for i in range(min(num_tokens, len(slot_mapping))):
            slot_idx = slot_mapping[i].item()
            if slot_idx >= 0 and slot_idx < kv_cache.shape[0]:
                kv_cache[slot_idx] = kv_tensor[i]
        
        logger.debug(f"Applied {num_tokens} tokens to layer {layer_idx}")
    except Exception as e:
        logger.error(f"Error applying KV to cache at layer {layer_idx}: {e}")
        raise


def apply_critical_kv(
    decoded_kv: torch.Tensor,
    kv_cache: torch.Tensor,
    block_ids: List[int],
    layer_idx: int
):
    try:
        for i, block_id in enumerate(block_ids):
            if block_id >= 0 and block_id < kv_cache.shape[0]:
                kv_cache[block_id] = decoded_kv[i]
        
        logger.debug(f"Applied critical KV for {len(block_ids)} blocks at layer {layer_idx}")
    except Exception as e:
        logger.error(f"Error applying critical KV at layer {layer_idx}: {e}")
        raise


def apply_refinement_kv(
    refined_kv: torch.Tensor,
    kv_cache: torch.Tensor,
    block_ids: List[int],
    layer_idx: int
):
    try:
        for i, block_id in enumerate(block_ids):
            if block_id >= 0 and block_id < kv_cache.shape[0]:
                kv_cache[block_id] = refined_kv[i]
        
        logger.debug(f"Applied refinement KV for {len(block_ids)} blocks at layer {layer_idx}")
    except Exception as e:
        logger.error(f"Error applying refinement KV at layer {layer_idx}: {e}")
        raise
