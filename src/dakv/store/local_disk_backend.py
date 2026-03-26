import os
from typing import Optional
from dakv.store.object_store import ObjectStore
from dakv.logging import get_logger


logger = get_logger()


class LocalDiskBackend(ObjectStore):
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.critical_dir = os.path.join(root_dir, "objects", "critical")
        self.refinement_dir = os.path.join(root_dir, "objects", "refinement")
        
        os.makedirs(self.critical_dir, exist_ok=True)
        os.makedirs(self.refinement_dir, exist_ok=True)
        
        logger.info(f"LocalDiskBackend initialized at {root_dir}")
    
    def _get_path(self, object_id: str, tier: str = "critical") -> str:
        if tier == "refinement":
            return os.path.join(self.refinement_dir, object_id)
        else:
            return os.path.join(self.critical_dir, object_id)
    
    def get(self, object_id: str, tier: str = "critical") -> Optional[bytes]:
        path = self._get_path(object_id, tier)
        try:
            with open(path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error reading object {object_id}: {e}")
            return None
    
    def put(self, object_id: str, data: bytes, tier: str = "critical") -> bool:
        path = self._get_path(object_id, tier)
        try:
            with open(path, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            logger.error(f"Error writing object {object_id}: {e}")
            return False
    
    def delete(self, object_id: str, tier: str = "critical") -> bool:
        path = self._get_path(object_id, tier)
        try:
            if os.path.exists(path):
                os.remove(path)
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting object {object_id}: {e}")
            return False
    
    def exists(self, object_id: str, tier: str = "critical") -> bool:
        path = self._get_path(object_id, tier)
        return os.path.exists(path)
    
    def size(self, object_id: str, tier: str = "critical") -> int:
        path = self._get_path(object_id, tier)
        try:
            return os.path.getsize(path)
        except:
            return 0
