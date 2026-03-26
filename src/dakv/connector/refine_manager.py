import threading
from typing import Dict, Optional, Any
import torch
from dakv.common.types import DeadlineConnectorMetadata
from dakv.logging import get_logger


logger = get_logger()


class RefineManager:
    def __init__(self):
        self.pending_refinements: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
    
    def add_pending(
        self,
        request_id: str,
        refined_kv: torch.Tensor,
        metadata: Optional[DeadlineConnectorMetadata] = None
    ):
        with self.lock:
            self.pending_refinements[request_id] = {
                "refined_kv": refined_kv,
                "metadata": metadata,
                "timestamp": self._current_timestamp()
            }
            logger.debug(
                f"Request {request_id}: added pending refinement "
                f"(shape={refined_kv.shape if refined_kv is not None else None})"
            )
    
    def get_pending(self, request_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            refinement_data = self.pending_refinements.pop(request_id, None)
            
            if refinement_data:
                logger.debug(
                    f"Request {request_id}: retrieved pending refinement"
                )
            
            return refinement_data
    
    def has_pending(self, request_id: str) -> bool:
        with self.lock:
            return request_id in self.pending_refinements
    
    def clear_pending(self, request_id: str):
        with self.lock:
            if request_id in self.pending_refinements:
                del self.pending_refinements[request_id]
                logger.debug(
                    f"Request {request_id}: cleared pending refinement"
                )
    
    def clear_all(self):
        with self.lock:
            count = len(self.pending_refinements)
            self.pending_refinements.clear()
            logger.info(f"Cleared all {count} pending refinements")
    
    def get_all_pending_requests(self) -> list[str]:
        with self.lock:
            return list(self.pending_refinements.keys())
    
    def cleanup_stale(self, max_age_seconds: float = 300.0):
        with self.lock:
            current_time = self._current_timestamp()
            stale_requests = []
            
            for request_id, data in self.pending_refinements.items():
                age = current_time - data.get("timestamp", 0)
                if age > max_age_seconds:
                    stale_requests.append(request_id)
            
            for request_id in stale_requests:
                del self.pending_refinements[request_id]
                logger.warning(
                    f"Request {request_id}: removed stale refinement "
                    f"(age > {max_age_seconds}s)"
                )
            
            if stale_requests:
                logger.info(
                    f"Cleaned up {len(stale_requests)} stale refinements"
                )
    
    def _current_timestamp(self) -> float:
        import time
        return time.time()
