"""
Metadata building utilities for DeadlinePrefixKVConnector

This module provides helper functions to build connector metadata from
scheduler-side state and transfer plans.
"""

from typing import Optional
from dakv.common.types import (
    DeadlineConnectorMetadata,
    WorkerLoadResult,
    WorkerSaveResult,
    RequestTransferState,
    TransferPlan,
    PrefixManifest
)
from dakv.logging import get_logger


logger = get_logger()


def build_metadata_from_state(
    state: RequestTransferState,
    allocated_block_ids: Optional[list] = None
) -> Optional[DeadlineConnectorMetadata]:
    """
    Build DeadlineConnectorMetadata from RequestTransferState
    
    Args:
        state: Request transfer state from scheduler
        allocated_block_ids: Block IDs allocated by vLLM (if available)
    
    Returns:
        DeadlineConnectorMetadata or None if state is not ready
    """
    if not state.manifest or not state.plan:
        logger.debug(f"Request {state.request_id}: state not ready for metadata building")
        return None
    
    manifest = state.manifest
    plan = state.plan
    
    # Determine if refinement is needed
    need_refinement = (
        plan.mode in ["CRITICAL_INT8_THEN_FP16", "FULL_FP16"] and
        manifest.refinement_object_id is not None
    )
    
    metadata = DeadlineConnectorMetadata(
        request_id=state.request_id,
        prefix_key=state.prefix_key or manifest.prefix_key,
        plan_mode=plan.mode,
        matched_tokens=manifest.matched_tokens,
        matched_blocks=manifest.matched_blocks,
        num_layers=manifest.num_layers,
        critical_object_id=manifest.critical_object_id,
        critical_codec=manifest.critical_codec,
        critical_nbytes=manifest.critical_nbytes,
        refinement_object_id=manifest.refinement_object_id if need_refinement else None,
        refinement_codec=manifest.refinement_codec if need_refinement else None,
        refinement_nbytes=manifest.refinement_nbytes if need_refinement else None,
        need_refinement=need_refinement,
        load_deadline_ms=plan.critical_deadline_ms,
        allocated_block_ids=allocated_block_ids or state.allocated_block_ids,
        load_from_tier=plan.load_from_tier
    )
    
    logger.debug(
        f"Request {state.request_id}: built metadata "
        f"(mode={metadata.plan_mode}, tokens={metadata.matched_tokens}, "
        f"refinement={metadata.need_refinement})"
    )
    
    return metadata


def create_load_result(
    request_id: str,
    success: bool,
    critical_done: bool = False,
    refinement_done: bool = False,
    loaded_tokens: int = 0,
    loaded_blocks: int = 0,
    critical_bytes: int = 0,
    refinement_bytes: int = 0,
    critical_load_ms: float = 0.0,
    refinement_load_ms: float = 0.0,
    error_code: str = "",
    error_message: str = ""
) -> WorkerLoadResult:
    """
    Create a WorkerLoadResult
    
    Args:
        request_id: Request ID
        success: Whether load succeeded
        critical_done: Whether critical load finished
        refinement_done: Whether refinement load finished
        loaded_tokens: Number of tokens loaded
        loaded_blocks: Number of blocks loaded
        critical_bytes: Bytes transferred for critical
        refinement_bytes: Bytes transferred for refinement
        critical_load_ms: Time taken for critical load
        refinement_load_ms: Time taken for refinement load
        error_code: Error code if failed
        error_message: Error message if failed
    
    Returns:
        WorkerLoadResult
    """
    return WorkerLoadResult(
        request_id=request_id,
        success=success,
        loaded_tokens=loaded_tokens,
        loaded_blocks=loaded_blocks,
        critical_load_done=critical_done,
        refinement_load_done=refinement_done,
        critical_bytes=critical_bytes,
        refinement_bytes=refinement_bytes,
        critical_load_ms=critical_load_ms,
        refinement_load_ms=refinement_load_ms,
        error_code=error_code,
        error_message=error_message
    )


def create_save_result(
    request_id: str,
    success: bool,
    saved_tokens: int = 0,
    saved_blocks: int = 0,
    critical_bytes: int = 0,
    refinement_bytes: int = 0,
    save_ms: float = 0.0,
    manifest_updated: bool = False,
    error_code: str = "",
    error_message: str = ""
) -> WorkerSaveResult:
    """
    Create a WorkerSaveResult
    
    Args:
        request_id: Request ID
        success: Whether save succeeded
        saved_tokens: Number of tokens saved
        saved_blocks: Number of blocks saved
        critical_bytes: Bytes saved for critical
        refinement_bytes: Bytes saved for refinement
        save_ms: Time taken for save
        manifest_updated: Whether manifest was updated
        error_code: Error code if failed
        error_message: Error message if failed
    
    Returns:
        WorkerSaveResult
    """
    return WorkerSaveResult(
        request_id=request_id,
        success=success,
        saved_tokens=saved_tokens,
        saved_blocks=saved_blocks,
        critical_bytes=critical_bytes,
        refinement_bytes=refinement_bytes,
        save_ms=save_ms,
        manifest_updated=manifest_updated,
        error_code=error_code,
        error_message=error_message
    )


def validate_metadata(metadata: DeadlineConnectorMetadata) -> tuple[bool, str]:
    """
    Validate connector metadata
    
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    if not metadata.request_id:
        return False, "request_id is required"
    
    if not metadata.prefix_key:
        return False, "prefix_key is required"
    
    if metadata.matched_tokens <= 0:
        return False, "matched_tokens must be positive"
    
    if not metadata.critical_object_id:
        return False, "critical_object_id is required"
    
    if metadata.need_refinement and not metadata.refinement_object_id:
        return False, "refinement_object_id required when need_refinement=True"
    
    return True, ""
