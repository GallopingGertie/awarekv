from abc import ABC, abstractmethod
from typing import Optional


class ObjectStore(ABC):
    @abstractmethod
    def get(self, object_id: str) -> Optional[bytes]:
        pass
    
    @abstractmethod
    def put(self, object_id: str, data: bytes) -> bool:
        pass
    
    @abstractmethod
    def delete(self, object_id: str) -> bool:
        pass
    
    @abstractmethod
    def exists(self, object_id: str) -> bool:
        pass
    
    @abstractmethod
    def size(self, object_id: str) -> int:
        pass
