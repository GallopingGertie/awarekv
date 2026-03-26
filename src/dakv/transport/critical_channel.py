from dakv.transport.data_client import DataClient
from dakv.logging import get_logger


logger = get_logger()


class CriticalChannel:
    def __init__(self, client: DataClient, timeout_ms: int = 1000):
        self.client = client
        self.timeout_ms = timeout_ms
    
    def fetch(self, object_id: str, request_id: str = "") -> bytes:
        data = self.client.get_critical(object_id, request_id)
        
        if data is None:
            raise RuntimeError(f"Critical fetch failed for {object_id}")
        
        logger.info(f"Critical fetch success: {object_id}, {len(data)} bytes")
        return data
    
    def store(self, object_id: str, data: bytes, codec: str, request_id: str = "") -> bool:
        success = self.client.put_critical(object_id, data, codec, request_id)
        
        if not success:
            logger.error(f"Critical store failed for {object_id}")
            return False
        
        logger.info(f"Critical store success: {object_id}, {len(data)} bytes")
        return True
