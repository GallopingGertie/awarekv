from typing import Protocol
import torch
from dakv.common.types import EncodedBlob


class KVCodec(Protocol):
    name: str

    def encode(self, tensor: torch.Tensor) -> EncodedBlob:
        ...

    def decode_to(self, blob: EncodedBlob, dst: torch.Tensor) -> None:
        ...

    def decode(self, blob: EncodedBlob, device: torch.device = None) -> torch.Tensor:
        ...
