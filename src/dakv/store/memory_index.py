from typing import Dict, Optional
import threading
from dakv.common.types import PrefixManifest
from dakv.common.time_utils import current_time_ms


class MemoryIndex:
    def __init__(self):
        self._index: Dict[str, PrefixManifest] = {}
        self._lock = threading.RLock()
    
    def get(self, prefix_key: str) -> Optional[PrefixManifest]:
        with self._lock:
            manifest = self._index.get(prefix_key)
            if manifest is not None:
                if self._is_expired(manifest):
                    del self._index[prefix_key]
                    return None
            return manifest
    
    def put(self, manifest: PrefixManifest):
        with self._lock:
            self._index[manifest.prefix_key] = manifest
    
    def delete(self, prefix_key: str) -> bool:
        with self._lock:
            if prefix_key in self._index:
                del self._index[prefix_key]
                return True
            return False
    
    def touch(self, prefix_key: str) -> bool:
        with self._lock:
            if prefix_key in self._index:
                self._index[prefix_key].last_access_ms = current_time_ms()
                return True
            return False
    
    def list_all(self) -> list:
        with self._lock:
            return list(self._index.values())
    
    def _is_expired(self, manifest: PrefixManifest) -> bool:
        if manifest.ttl_s <= 0:
            return False
        now = current_time_ms()
        age_ms = now - manifest.created_at_ms
        return age_ms > (manifest.ttl_s * 1000)
    
    def evict_expired(self) -> int:
        with self._lock:
            expired_keys = []
            for key, manifest in self._index.items():
                if self._is_expired(manifest):
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._index[key]
            
            return len(expired_keys)
