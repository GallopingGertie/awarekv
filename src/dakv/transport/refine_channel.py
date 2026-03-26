from dakv.transport.data_client import DataClient
from dakv.logging import get_logger
from typing import Optional


logger = get_logger()


class RefineChannel:
    def __init__(self, client: DataClient, timeout_ms: int = 500):
        self.client = client
        self.timeout_ms = timeout_ms
    
    def fetch(self, object_id: str, request_id: str = "") -> Optional[bytes]:
        try:
            data = self.client.get_refinement(object_id, request_id)
            
            if data is None:
                logger.warning(f"Refinement fetch failed for {object_id}, dropping")
                return None
            
            logger.info(f"Refinement fetch success: {object_id}, {len(data)} bytes")
            return data
        except Exception as e:
            logger.warning(f"Refinement fetch error for {object_id}: {e}, dropping")
            return None
    
    def store(self, object_id: str, data: bytes, codec: str, request_id: str = "") -> bool:
        try:
            success = self.client.put_refinement(object_id, data, codec, request_id)
            
            if not success:
                logger.warning(f"Refinement store failed for {object_id}")
                return False
            
            logger.info(f"Refinement store success: {object_id}, {len(data)} bytes")
            return True
        except Exception as e:
            logger.warning(f"Refinement store error for {object_id}: {e}")
            return False
