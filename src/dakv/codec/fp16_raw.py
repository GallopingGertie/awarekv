import torch
import numpy as np
from dakv.codec.base import BaseCodec
from dakv.common.types import EncodedBlob
from dakv.common.tensor_io import tensor_to_bytes, bytes_to_tensor


class FP16RawCodec(BaseCodec):
    def __init__(self):
        super().__init__("fp16_raw")
    
    def encode(self, tensor: torch.Tensor) -> EncodedBlob:
        if tensor.dtype != torch.float16:
            tensor = tensor.to(torch.float16)
        
        data = tensor_to_bytes(tensor)
        
        return EncodedBlob(
            codec_name=self.name,
            data=data,
            shape=tuple(tensor.shape),
            dtype=str(tensor.dtype),
            metadata={},
            nbytes=len(data)
        )
    
    def decode_to(self, blob: EncodedBlob, dst: torch.Tensor) -> None:
        if blob.codec_name != self.name:
            raise ValueError(f"Codec mismatch: expected {self.name}, got {blob.codec_name}")
        
        device = dst.device
        decoded = bytes_to_tensor(blob.data, blob.shape, torch.float16, device=device)
        
        dst.copy_(decoded)
    
    def decode(self, blob: EncodedBlob, device: torch.device = None) -> torch.Tensor:
        if blob.codec_name != self.name:
            raise ValueError(f"Codec mismatch: expected {self.name}, got {blob.codec_name}")
        
        if device is None:
            device = torch.device("cpu")
        
        return bytes_to_tensor(blob.data, blob.shape, torch.float16, device=device)
