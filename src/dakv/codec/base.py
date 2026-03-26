from abc import ABC, abstractmethod
import torch
from dakv.common.types import EncodedBlob


class BaseCodec(ABC):
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def encode(self, tensor: torch.Tensor) -> EncodedBlob:
        pass
    
    @abstractmethod
    def decode_to(self, blob: EncodedBlob, dst: torch.Tensor) -> None:
        pass
    
    @abstractmethod
    def decode(self, blob: EncodedBlob, device: torch.device = None) -> torch.Tensor:
        pass
