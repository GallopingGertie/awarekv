import hashlib
import json
from typing import List, Optional, Any, Dict


def compute_prefix_key(
    model_id: str,
    tokenizer_id: str,
    kv_layout_version: str,
    cache_dtype: str,
    block_size: int,
    prompt_token_ids: List[int],
    matched_prefix_len: int,
    mm_hashes: Optional[List[str]] = None
) -> str:
    data = {
        "model_id": model_id,
        "tokenizer_id": tokenizer_id,
        "kv_layout_version": kv_layout_version,
        "cache_dtype": cache_dtype,
        "block_size": block_size,
        "prompt_tokens": prompt_token_ids[:matched_prefix_len],
        "mm_hashes": mm_hashes or []
    }
    
    json_str = json.dumps(data, sort_keys=True)
    hash_obj = hashlib.sha256(json_str.encode("utf-8"))
    return hash_obj.hexdigest()


def compute_object_id(
    prefix_key: str,
    tier: str,
    codec: str,
    object_format_version: str = "v1"
) -> str:
    data = f"{prefix_key}:{tier}:{codec}:{object_format_version}"
    hash_obj = hashlib.sha256(data.encode("utf-8"))
    return hash_obj.hexdigest()


def compute_layout_fingerprint(kv_layout_version: str, config: Dict[str, Any]) -> str:
    data = {
        "kv_layout_version": kv_layout_version,
        "config": config
    }
    json_str = json.dumps(data, sort_keys=True)
    hash_obj = hashlib.sha256(json_str.encode("utf-8"))
    return hash_obj.hexdigest()


def verify_prefix_key_consistency(
    prefix_key: str,
    model_id: str,
    tokenizer_id: str,
    kv_layout_version: str,
    cache_dtype: str,
    block_size: int,
    prompt_token_ids: List[int],
    matched_prefix_len: int
) -> bool:
    recomputed = compute_prefix_key(
        model_id=model_id,
        tokenizer_id=tokenizer_id,
        kv_layout_version=kv_layout_version,
        cache_dtype=cache_dtype,
        block_size=block_size,
        prompt_token_ids=prompt_token_ids,
        matched_prefix_len=matched_prefix_len
    )
    return recomputed == prefix_key
