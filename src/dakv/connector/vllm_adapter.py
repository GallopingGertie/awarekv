from typing import List, Optional, Any, Dict
from dakv.logging import get_logger


logger = get_logger()


# vLLM Version-Specific Imports
# This module centralizes all vLLM version-dependent imports to facilitate version upgrades

try:
    from vllm.v1.connector.base import KVConnectorBase_V1
    _VLLM_CONNECTOR_AVAILABLE = True
except ImportError:
    try:
        from vllm.connector.base import KVConnectorBase_V1
        _VLLM_CONNECTOR_AVAILABLE = True
    except ImportError:
        logger.warning("KVConnectorBase_V1 not found, creating fallback base class")
        _VLLM_CONNECTOR_AVAILABLE = False
        
        class KVConnectorBase_V1:
            @property
            def prefer_cross_layer_blocks(self) -> bool:
                return True
            
            def __init__(self, vllm_config, role: str, kv_cache_config=None):
                pass


def is_vllm_connector_available() -> bool:
    return _VLLM_CONNECTOR_AVAILABLE


# Request and Scheduler Output Extraction Functions

def extract_request_id(request) -> str:
    if hasattr(request, 'request_id'):
        return request.request_id
    elif hasattr(request, 'id'):
        return request.id
    else:
        return str(id(request))


def extract_prompt_tokens(request) -> List[int]:
    if hasattr(request, 'prompt_token_ids'):
        return list(request.prompt_token_ids)
    elif hasattr(request, 'inputs') and hasattr(request.inputs, 'prompt_token_ids'):
        return list(request.inputs.prompt_token_ids)
    elif hasattr(request, 'tokens'):
        return list(request.tokens)
    else:
        logger.warning(f"Cannot extract prompt tokens from request {extract_request_id(request)}")
        return []


def extract_num_computed_tokens(request) -> int:
    if hasattr(request, 'num_computed_tokens'):
        return request.num_computed_tokens
    elif hasattr(request, 'computed_tokens'):
        return request.computed_tokens
    else:
        return 0


def extract_model_id(vllm_config) -> str:
    if hasattr(vllm_config, 'model'):
        return vllm_config.model
    elif hasattr(vllm_config, 'model_config') and hasattr(vllm_config.model_config, 'model'):
        return vllm_config.model_config.model
    else:
        return "unknown_model"


def extract_allocated_blocks(scheduler_output, request_id: str) -> List[int]:
    try:
        # Try direct blocks attribute
        if hasattr(scheduler_output, 'blocks'):
            return list(scheduler_output.blocks)
        
        # Try scheduled_seq_groups
        if hasattr(scheduler_output, 'scheduled_seq_groups'):
            for seq_group in scheduler_output.scheduled_seq_groups:
                if hasattr(seq_group, 'seq_group') and extract_request_id(seq_group.seq_group) == request_id:
                    if hasattr(seq_group, 'block_table'):
                        return list(seq_group.block_table)
        
        # Try seq_group_metadata_list
        if hasattr(scheduler_output, 'seq_group_metadata_list'):
            for seq_group_meta in scheduler_output.seq_group_metadata_list:
                if hasattr(seq_group_meta, 'request_id') and seq_group_meta.request_id == request_id:
                    if hasattr(seq_group_meta, 'block_tables'):
                        # block_tables is usually a dict of seq_id -> block_table
                        for block_table in seq_group_meta.block_tables.values():
                            return list(block_table)
                    elif hasattr(seq_group_meta, 'block_table'):
                        return list(seq_group_meta.block_table)
        
        return []
    except Exception as e:
        logger.warning(f"Failed to extract allocated blocks for {request_id}: {e}")
        return []


def extract_slot_mapping(forward_context) -> Optional[Any]:
    try:
        if hasattr(forward_context, 'slot_mapping'):
            return forward_context.slot_mapping
        if hasattr(forward_context, 'attn_metadata') and hasattr(forward_context.attn_metadata, 'slot_mapping'):
            return forward_context.attn_metadata.slot_mapping
        return None
    except Exception as e:
        logger.warning(f"Failed to extract slot_mapping: {e}")
        return None


def extract_attention_metadata(forward_context):
    if hasattr(forward_context, 'attn_metadata'):
        return forward_context.attn_metadata
    elif hasattr(forward_context, 'attention_metadata'):
        return forward_context.attention_metadata
    return None


def extract_layer_kv_cache(forward_context, layer_name: str):
    try:
        # Try to get layer from no_compile_layers or kv_caches
        if hasattr(forward_context, 'no_compile_layers'):
            if layer_name in forward_context.no_compile_layers:
                return forward_context.no_compile_layers[layer_name]
        
        if hasattr(forward_context, 'kv_caches'):
            # kv_caches might be a list indexed by layer_idx
            if isinstance(forward_context.kv_caches, (list, tuple)):
                try:
                    layer_idx = int(layer_name.replace('layer_', ''))
                    if layer_idx < len(forward_context.kv_caches):
                        return forward_context.kv_caches[layer_idx]
                except (ValueError, IndexError):
                    pass
            # or a dict indexed by layer_name
            elif isinstance(forward_context.kv_caches, dict):
                if layer_name in forward_context.kv_caches:
                    return forward_context.kv_caches[layer_name]
        
        return None
    except Exception as e:
        logger.warning(f"Failed to extract KV cache for layer {layer_name}: {e}")
        return None


def extract_layer_name(layer_idx: int) -> str:
    return f\"layer_{layer_idx}\"


def extract_num_layers(model_config) -> int:
    if hasattr(model_config, 'num_hidden_layers'):
        return model_config.num_hidden_layers
    elif hasattr(model_config, 'num_layers'):
        return model_config.num_layers
    else:
        logger.warning("Cannot determine num_layers, using default 32")
        return 32


def can_use_cross_layer_blocks() -> bool:
    return True


def extract_kv_cache_layer(kv_cache, layer_idx: int):
    if isinstance(kv_cache, (list, tuple)):
        if layer_idx < len(kv_cache):
            return kv_cache[layer_idx]
    return None


def validate_connector_role(role: str) -> bool:
    valid_roles = ["kv_producer", "kv_consumer", "kv_both"]
    return role in valid_roles


def get_block_size_from_config(vllm_config) -> int:
    if hasattr(vllm_config, 'block_size'):
        return vllm_config.block_size
    if hasattr(vllm_config, 'cache_config') and hasattr(vllm_config.cache_config, 'block_size'):
        return vllm_config.cache_config.block_size
    return 16


def extract_num_kv_heads(model_config) -> int:
    if hasattr(model_config, 'num_key_value_heads'):
        return model_config.num_key_value_heads
    elif hasattr(model_config, 'num_kv_heads'):
        return model_config.num_kv_heads
    elif hasattr(model_config, 'num_attention_heads'):
        # Fallback: assume GQA with num_kv_heads = num_attention_heads
        return model_config.num_attention_heads
    else:
        logger.warning("Cannot determine num_kv_heads, using default 32")
        return 32


def extract_head_size(model_config) -> int:
    if hasattr(model_config, 'head_size'):
        return model_config.head_size
    elif hasattr(model_config, 'head_dim'):
        return model_config.head_dim
    elif hasattr(model_config, 'hidden_size') and hasattr(model_config, 'num_attention_heads'):
        return model_config.hidden_size // model_config.num_attention_heads
    else:
        logger.warning("Cannot determine head_size, using default 128")
        return 128


def is_store_request(forward_context) -> bool:
    """Determine if this is a request that should store KV"""
    # This is a heuristic - adjust based on actual vLLM behavior
    if hasattr(forward_context, 'is_prefill'):
        return forward_context.is_prefill
    
    attn_metadata = extract_attention_metadata(forward_context)
    if attn_metadata:
        # If we're in prefill phase, we should store
        if hasattr(attn_metadata, 'is_prompt'):
            return attn_metadata.is_prompt
        if hasattr(attn_metadata, 'prefill_metadata'):
            return attn_metadata.prefill_metadata is not None
    
    return False


def is_load_request(forward_context) -> bool:
    """Determine if this is a request that should load external KV"""
    # This should be set by scheduler metadata
    # We'll rely on metadata passed through kwargs
    return True  # Will be determined by metadata existence
