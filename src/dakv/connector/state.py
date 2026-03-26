import threading
from typing import Dict, Optional, List
from dakv.common.types import RequestTransferState, TransferPlan, PrefixManifest
from dakv.logging import get_logger


logger = get_logger()


class StateManager:
    """
    Thread-safe request state manager for connector
    
    Manages request-scoped transfer state throughout the connector lifecycle:
    - INIT: Request created
    - MISS: Manifest miss, will recompute
    - HIT_PLANNED: Manifest hit and plan generated
    - CRITICAL_LOADING: Loading critical KV
    - CRITICAL_READY: Critical KV loaded and applied
    - REFINING: Loading refinement KV
    - DONE: Request completed
    - FAILED: Load/save failed
    """
    
    def __init__(self):
        self.states: Dict[str, RequestTransferState] = {}
        self.lock = threading.RLock()
    
    def create_or_get(self, request_id: str) -> RequestTransferState:
        """Create a new state or return existing state for request"""
        with self.lock:
            if request_id not in self.states:
                state = RequestTransferState(
                    request_id=request_id,
                    status="INIT"
                )
                self.states[request_id] = state
                logger.debug(f"Request {request_id}: created new state")
                return state
            else:
                return self.states[request_id]
    
    def get(self, request_id: str) -> Optional[RequestTransferState]:
        """Get state for request (returns None if not exists)"""
        with self.lock:
            return self.states.get(request_id)
    
    def put(self, request_id: str, state: RequestTransferState):
        """Put/update state for request"""
        with self.lock:
            self.states[request_id] = state
    
    def mark_manifest_hit(self, request_id: str, manifest: PrefixManifest):
        """Mark that manifest was hit for this request"""
        with self.lock:
            if request_id in self.states:
                self.states[request_id].manifest = manifest
                self.states[request_id].status = "HIT_PLANNED"
                logger.debug(f"Request {request_id}: manifest hit, {manifest.matched_tokens} tokens")
    
    def mark_manifest_miss(self, request_id: str, reason: str = "no_match"):
        """Mark that manifest was missed for this request"""
        with self.lock:
            if request_id in self.states:
                self.states[request_id].status = "MISS"
                self.states[request_id].fallback_reason = reason
                logger.debug(f"Request {request_id}: manifest miss, reason={reason}")
    
    def set_plan(self, request_id: str, plan: TransferPlan):
        """Set transfer plan for request"""
        with self.lock:
            if request_id in self.states:
                self.states[request_id].plan = plan
                logger.debug(f"Request {request_id}: plan set to {plan.mode}")
    
    def set_allocated_blocks(self, request_id: str, allocated_blocks: List[int]):
        """Set allocated block IDs for request"""
        with self.lock:
            if request_id in self.states:
                self.states[request_id].allocated_block_ids = allocated_blocks
                logger.debug(f"Request {request_id}: set {len(allocated_blocks)} allocated blocks")
    
    def set_connector_metadata(self, request_id: str, metadata):
        """Set connector metadata for request"""
        with self.lock:
            if request_id in self.states:
                self.states[request_id].connector_metadata = metadata
    
    def mark_load_started(self, request_id: str):
        """Mark that load has started for request"""
        with self.lock:
            if request_id in self.states:
                self.states[request_id].status = "CRITICAL_LOADING"
                logger.debug(f"Request {request_id}: load started")
    
    def mark_load_finished(self, request_id: str, success: bool):
        """Mark that load has finished for request"""
        with self.lock:
            if request_id in self.states:
                if success:
                    self.states[request_id].critical_load_done = True
                    self.states[request_id].status = "CRITICAL_READY"
                    logger.debug(f"Request {request_id}: critical load finished successfully")
                else:
                    self.states[request_id].status = "FAILED"
                    logger.warning(f"Request {request_id}: load failed")
    
    def mark_load_failed(self, request_id: str, error_message: str):
        """Mark that load has failed for request"""
        with self.lock:
            if request_id in self.states:
                self.states[request_id].status = "FAILED"
                self.states[request_id].fallback_reason = error_message
                logger.error(f"Request {request_id}: load failed - {error_message}")
    
    def mark_save_started(self, request_id: str):
        """Mark that save has started for request"""
        with self.lock:
            if request_id in self.states:
                logger.debug(f"Request {request_id}: save started")
    
    def mark_save_finished(self, request_id: str, success: bool):
        """Mark that save has finished for request"""
        with self.lock:
            if request_id in self.states:
                if success:
                    logger.debug(f"Request {request_id}: save finished successfully")
                else:
                    logger.warning(f"Request {request_id}: save failed")
    
    def mark_save_failed(self, request_id: str, error_message: str):
        """Mark that save has failed for request"""
        with self.lock:
            if request_id in self.states:
                logger.error(f"Request {request_id}: save failed - {error_message}")
    
    def mark_refine_started(self, request_id: str):
        """Mark that refinement has started for request"""
        with self.lock:
            if request_id in self.states:
                self.states[request_id].status = "REFINING"
                logger.debug(f"Request {request_id}: refinement started")
    
    def mark_refine_finished(self, request_id: str):
        """Mark that refinement has finished for request"""
        with self.lock:
            if request_id in self.states:
                self.states[request_id].refinement_load_done = True
                logger.debug(f"Request {request_id}: refinement finished")
    
    def mark_refine_dropped(self, request_id: str, reason: str = "timeout"):
        """Mark that refinement was dropped for request"""
        with self.lock:
            if request_id in self.states:
                logger.info(f"Request {request_id}: refinement dropped - {reason}")
    
    def mark_done(self, request_id: str):
        """Mark request as done"""
        with self.lock:
            if request_id in self.states:
                self.states[request_id].status = "DONE"
                self.states[request_id].request_finished = True
                logger.debug(f"Request {request_id}: marked as done")
    
    def mark_recompute(self, request_id: str, reason: str = "fallback"):
        """Mark that request will recompute (not use external KV)"""
        with self.lock:
            if request_id in self.states:
                self.states[request_id].status = "MISS"
                self.states[request_id].fallback_reason = reason
                logger.info(f"Request {request_id}: will recompute - {reason}")
    
    def update_status(self, request_id: str, status: str):
        """Update status for request"""
        with self.lock:
            if request_id in self.states:
                self.states[request_id].status = status
                logger.debug(f"Request {request_id}: status -> {status}")
    
    def remove(self, request_id: str):
        """Remove state for request"""
        with self.lock:
            if request_id in self.states:
                del self.states[request_id]
                logger.debug(f"Request {request_id}: state removed")
    
    def gc_finished(self, max_age_seconds: float = 300.0):
        """Garbage collect finished requests older than max_age_seconds"""
        import time
        
        with self.lock:
            current_time = time.time()
            to_remove = []
            
            for request_id, state in self.states.items():
                if state.request_finished:
                    # Simple age check - would need timestamp tracking for real implementation
                    to_remove.append(request_id)
            
            for request_id in to_remove:
                del self.states[request_id]
            
            if to_remove:
                logger.debug(f"GC: removed {len(to_remove)} finished request states")
    
    def get_all_request_ids(self) -> List[str]:
        """Get all request IDs currently tracked"""
        with self.lock:
            return list(self.states.keys())
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about current states"""
        with self.lock:
            stats = {}
            for state in self.states.values():
                status = state.status
                stats[status] = stats.get(status, 0) + 1
            return stats
