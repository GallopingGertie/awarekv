from typing import List, Optional, Any, Dict
from dakv.logging import get_logger


logger = get_logger()


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
        if hasattr(scheduler_output, 'blocks'):
            return list(scheduler_output.blocks)
        if hasattr(scheduler_output, 'scheduled_seq_groups'):
            for seq_group in scheduler_output.scheduled_seq_groups:
                if hasattr(seq_group, 'seq_group') and extract_request_id(seq_group.seq_group) == request_id:
                    if hasattr(seq_group, 'block_table'):
                        return list(seq_group.block_table)
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


def extract_layer_name(layer_idx: int) -> str:
    return f"layer_{layer_idx}"


def extract_num_layers(model_config) -> int:
    if hasattr(model_config, 'num_hidden_layers'):
        return model_config.num_hidden_layers
    elif hasattr(model_config, 'num_layers'):
        return model_config.num_layers
    else:
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
