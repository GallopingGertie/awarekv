from pydantic import BaseModel
from typing import List, Optional


class ManifestQueryRequest(BaseModel):
    prefix_key: str
    request_id: str
    need_refinement: bool = True


class ManifestQueryResponse(BaseModel):
    hit: bool
    manifest: Optional[dict] = None
    tier: Optional[str] = None


class ManifestPutRequest(BaseModel):
    prefix_key: str
    model_id: str
    tokenizer_id: str
    kv_layout_version: str
    block_size: int
    cache_dtype: str
    matched_tokens: int
    matched_blocks: List[int]
    num_layers: int
    ttl_s: int = 3600
    critical_codec: str = "fp16_raw"
    critical_nbytes: int = 0
    critical_object_id: str = ""
    refinement_codec: Optional[str] = None
    refinement_nbytes: Optional[int] = None
    refinement_object_id: Optional[str] = None
    quality_mode: str = "fp16"
    checksum: str = ""


class ManifestPutResponse(BaseModel):
    success: bool
    message: str = ""


class ManifestTouchRequest(BaseModel):
    prefix_key: str


class ManifestTouchResponse(BaseModel):
    success: bool


class ManifestDeleteRequest(BaseModel):
    prefix_key: str


class ManifestDeleteResponse(BaseModel):
    success: bool


class ManifestStatsResponse(BaseModel):
    total_manifests: int
    total_objects: int
    total_bytes: int
