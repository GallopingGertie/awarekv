from dataclasses import dataclass, field
from typing import List, Optional, Literal, Dict, Any
from enum import Enum


@dataclass
class EncodedBlob:
    codec_name: str
    data: bytes
    shape: tuple
    dtype: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    nbytes: int = 0
    
    def __post_init__(self):
        if self.nbytes == 0:
            self.nbytes = len(self.data)


@dataclass
class PrefixManifest:
    prefix_key: str
    model_id: str
    tokenizer_id: str
    kv_layout_version: str
    block_size: int
    cache_dtype: str
    matched_tokens: int
    matched_blocks: List[int]
    num_layers: int
    created_at_ms: int
    last_access_ms: int
    ttl_s: int
    critical_codec: str
    critical_nbytes: int
    critical_object_id: str
    refinement_codec: Optional[str] = None
    refinement_nbytes: Optional[int] = None
    refinement_object_id: Optional[str] = None
    quality_mode: Literal["fp16", "int8+fp16", "int8_only"] = "fp16"
    checksum: str = ""
    object_format_version: str = "v1"


@dataclass
class TransferPlan:
    plan_id: str
    matched_tokens: int
    matched_blocks: List[int]
    mode: Literal[
        "FULL_FP16",
        "CRITICAL_INT8_ONLY",
        "CRITICAL_INT8_THEN_FP16",
        "RECOMPUTE"
    ]
    critical_deadline_ms: int
    refine_budget_ms: int
    load_from_tier: Literal["T1", "T2"]
    allow_refine_drop: bool
    reason_code: str = ""
    estimated_critical_bytes: int = 0
    estimated_refine_bytes: int = 0


@dataclass
class DeadlineConnectorMetadata:
    request_id: str
    prefix_key: Optional[str] = None
    plan_mode: str = ""
    matched_tokens: int = 0
    matched_blocks: List[int] = field(default_factory=list)
    num_layers: int = 32
    critical_object_id: str = ""
    critical_codec: str = ""
    critical_nbytes: int = 0
    refinement_object_id: Optional[str] = None
    refinement_codec: Optional[str] = None
    refinement_nbytes: Optional[int] = None
    need_refinement: bool = False
    load_deadline_ms: int = 0
    allocated_block_ids: List[int] = field(default_factory=list)
    load_from_tier: str = "T2"


@dataclass
class RequestTransferState:
    request_id: str
    prefix_key: Optional[str] = None
    matched_tokens: int = 0
    matched_blocks: List[int] = field(default_factory=list)
    plan: Optional[TransferPlan] = None
    manifest: Optional[PrefixManifest] = None
    status: Literal[
        "INIT",
        "MISS",
        "HIT_PLANNED",
        "CRITICAL_LOADING",
        "CRITICAL_READY",
        "REFINING",
        "DONE",
        "FAILED",
        "RECOMPUTE"
    ] = "INIT"
    last_error: Optional[str] = None
    start_time_ms: int = 0
    critical_load_time_ms: float = 0
    refine_load_time_ms: float = 0
    allocated_block_ids: List[int] = field(default_factory=list)
    critical_done: bool = False
    refinement_done: bool = False
    request_finished: bool = False
    fallback_reason: Optional[str] = None


@dataclass
class WorkerLoadResult:
    request_id: str
    success: bool
    loaded_tokens: int = 0
    loaded_blocks: int = 0
    critical_load_done: bool = False
    refinement_load_done: bool = False
    critical_bytes: int = 0
    refinement_bytes: int = 0
    critical_load_ms: float = 0.0
    refinement_load_ms: float = 0.0
    error_code: str = ""
    error_message: str = ""


@dataclass
class WorkerSaveResult:
    request_id: str
    success: bool
    saved_tokens: int = 0
    saved_blocks: List[int] = field(default_factory=list)
    critical_bytes: int = 0
    refinement_bytes: int = 0
    error_code: str = ""
    error_message: str = ""
    save_time_ms: float = 0


@dataclass
class WorkerLoadTask:
    request_id: str
    layer_name: str
    block_ids: List[int]
    critical_future: Optional[Any] = None
    refine_future: Optional[Any] = None
    critical_ready: bool = False
    refine_ready: bool = False
    applied_refine_version: int = 0


@dataclass
class NetworkEstimate:
    bandwidth_bps: float
    rtt_ms: float
    loss_rate: float = 0.0
    last_update_ms: int = 0


@dataclass
class RequestMetrics:
    request_id: str
    prefix_key: Optional[str] = None
    prefix_hit: bool = False
    matched_tokens: int = 0
    plan_mode: str = ""
    load_tier: str = ""
    critical_bytes: int = 0
    refine_bytes: int = 0
    critical_load_ms: float = 0
    refine_load_ms: float = 0
    critical_apply_ms: float = 0
    refine_apply_ms: float = 0
    ttft_ms: float = 0
    tpot_ms: float = 0
    fallback: bool = False
    fallback_reason: Optional[str] = None
    degraded: bool = False
    timestamp_ms: int = 0


@dataclass
class ObjectHeader:
    format_version: str
    num_layers: int
    block_size: int
    cache_dtype: str
    codec_name: str
    total_bytes: int
    layer_offsets: List[int]
    layer_shapes: List[tuple]
    checksum: str = ""
