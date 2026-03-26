import threading
from typing import Dict, Optional
import torch
from dakv.logging import get_logger


logger = get_logger()


class RefineManager:
    def __init__(self):
        self.pending_refinements: Dict[str, torch.Tensor] = {}
        self.lock = threading.Lock()
    
    def add_pending(self, request_id: str, refined_kv: torch.Tensor):
        with self.lock:
            self.pending_refinements[request_id] = refined_kv
            logger.debug(f"Added pending refinement for request {request_id}")
    
    def get_pending(self, request_id: str) -> Optional[torch.Tensor]:
        with self.lock:
            return self.pending_refinements.pop(request_id, None)
    
    def has_pending(self, request_id: str) -> bool:
        with self.lock:
            return request_id in self.pending_refinements
    
    def clear_pending(self, request_id: str):
        with self.lock:
            if request_id in self.pending_refinements:
                del self.pending_refinements[request_id]
                logger.debug(f"Cleared pending refinement for request {request_id}")
