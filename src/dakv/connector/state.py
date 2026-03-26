import threading
from typing import Dict, Optional
from dakv.common.types import RequestTransferState
from dakv.logging import get_logger


logger = get_logger()


class StateManager:
    def __init__(self):
        self.states: Dict[str, RequestTransferState] = {}
        self.lock = threading.RLock()
    
    def get(self, request_id: str) -> Optional[RequestTransferState]:
        with self.lock:
            return self.states.get(request_id)
    
    def put(self, request_id: str, state: RequestTransferState):
        with self.lock:
            self.states[request_id] = state
    
    def update_status(self, request_id: str, status: str):
        with self.lock:
            if request_id in self.states:
                self.states[request_id].status = status
                logger.debug(f"Request {request_id} status -> {status}")
    
    def remove(self, request_id: str):
        with self.lock:
            if request_id in self.states:
                del self.states[request_id]
