from typing import List, Optional
from collections import OrderedDict
import threading


class LRUEvictionPolicy:
    def __init__(self, max_items: int = 100):
        self.max_items = max_items
        self.cache = OrderedDict()
        self.lock = threading.Lock()
    
    def touch(self, key: str):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
    
    def add(self, key: str, size: int):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            else:
                self.cache[key] = size
                if len(self.cache) > self.max_items:
                    self.cache.popitem(last=False)
    
    def remove(self, key: str):
        with self.lock:
            if key in self.cache:
                del self.cache[key]
    
    def get_eviction_candidates(self, target_count: int) -> List[str]:
        with self.lock:
            candidates = list(self.cache.keys())[:target_count]
            return candidates
