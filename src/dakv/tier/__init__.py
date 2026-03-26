import torch
import threading
from typing import Dict, Optional
from collections import OrderedDict
from dakv.logging import get_logger


logger = get_logger()


class HostCache:
    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        self.current_bytes = 0
        self.cache: OrderedDict = OrderedDict()
        self.lock = threading.RLock()
        
        logger.info(f"HostCache initialized with max {max_bytes / 1e9:.2f} GB")
    
    def get(self, key: str) -> Optional[torch.Tensor]:
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                tensor, nbytes = self.cache[key]
                logger.debug(f"HostCache hit: {key}")
                return tensor
            logger.debug(f"HostCache miss: {key}")
            return None
    
    def put(self, key: str, tensor: torch.Tensor):
        with self.lock:
            if tensor.is_cuda:
                tensor = tensor.cpu()
            
            tensor = tensor.pin_memory()
            
            nbytes = tensor.element_size() * tensor.numel()
            
            if key in self.cache:
                old_tensor, old_nbytes = self.cache[key]
                self.current_bytes -= old_nbytes
                del self.cache[key]
            
            while self.current_bytes + nbytes > self.max_bytes and len(self.cache) > 0:
                evict_key, (evict_tensor, evict_nbytes) = self.cache.popitem(last=False)
                self.current_bytes -= evict_nbytes
                logger.debug(f"HostCache evicted: {evict_key}")
            
            if nbytes <= self.max_bytes:
                self.cache[key] = (tensor, nbytes)
                self.current_bytes += nbytes
                logger.debug(f"HostCache put: {key}, {nbytes / 1e6:.2f} MB")
    
    def delete(self, key: str):
        with self.lock:
            if key in self.cache:
                tensor, nbytes = self.cache[key]
                del self.cache[key]
                self.current_bytes -= nbytes
                logger.debug(f"HostCache delete: {key}")
    
    def clear(self):
        with self.lock:
            self.cache.clear()
            self.current_bytes = 0
            logger.info("HostCache cleared")
