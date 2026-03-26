import torch
import numpy as np
import struct
from dakv.codec.base import BaseCodec
from dakv.common.types import EncodedBlob


class Int8SymmetricCodec(BaseCodec):
    def __init__(self):
        super().__init__("int8_symm")
    
    def encode(self, tensor: torch.Tensor) -> EncodedBlob:
        if tensor.is_cuda:
            tensor = tensor.cpu()
        
        if tensor.dtype != torch.float16:
            tensor = tensor.to(torch.float16)
        
        tensor_np = tensor.numpy().astype(np.float32)
        
        abs_max = np.abs(tensor_np).max()
        if abs_max == 0:
            abs_max = 1.0
        
        scale = abs_max / 127.0
        
        quantized = np.round(tensor_np / scale).astype(np.int8)
        
        scale_bytes = struct.pack('f', scale)
        quantized_bytes = quantized.tobytes()
        data = scale_bytes + quantized_bytes
        
        return EncodedBlob(
            codec_name=self.name,
            data=data,
            shape=tuple(tensor.shape),
            dtype="int8",
            metadata={"scale": float(scale)},
            nbytes=len(data)
        )
    
    def decode_to(self, blob: EncodedBlob, dst: torch.Tensor) -> None:
        if blob.codec_name != self.name:
            raise ValueError(f"Codec mismatch: expected {self.name}, got {blob.codec_name}")
        
        decoded = self.decode(blob, device=dst.device)
        dst.copy_(decoded.to(dst.dtype))
    
    def decode(self, blob: EncodedBlob, device: torch.device = None) -> torch.Tensor:
        if blob.codec_name != self.name:
            raise ValueError(f"Codec mismatch: expected {self.name}, got {blob.codec_name}")
        
        if device is None:
            device = torch.device("cpu")
        
        scale_bytes = blob.data[:4]
        quantized_bytes = blob.data[4:]
        
        scale = struct.unpack('f', scale_bytes)[0]
        
        quantized_np = np.frombuffer(quantized_bytes, dtype=np.int8).reshape(blob.shape)
        
        dequantized_np = quantized_np.astype(np.float32) * scale
        
        tensor = torch.from_numpy(dequantized_np).to(torch.float16)
        
        if device.type != "cpu":
            tensor = tensor.to(device)
        
        return tensor
