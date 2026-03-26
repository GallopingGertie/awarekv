def extract_request_id(request) -> str:
    if hasattr(request, 'request_id'):
        return request.request_id
    elif hasattr(request, 'id'):
        return request.id
    else:
        return str(id(request))


def extract_prompt_tokens(request) -> list:
    if hasattr(request, 'prompt_token_ids'):
        return request.prompt_token_ids
    elif hasattr(request, 'inputs') and hasattr(request.inputs, 'prompt_token_ids'):
        return request.inputs.prompt_token_ids
    else:
        return []


def extract_layer_name(layer_idx: int) -> str:
    return f"layer_{layer_idx}"


def can_use_cross_layer_blocks() -> bool:
    return True
