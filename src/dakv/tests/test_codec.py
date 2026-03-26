import pytest
import torch
from dakv.codec.fp16_raw import FP16RawCodec
from dakv.codec.int8_symm import Int8SymmetricCodec


def test_fp16_raw_codec():
    codec = FP16RawCodec()
    
    tensor = torch.randn(4, 8, 16, dtype=torch.float16)
    
    blob = codec.encode(tensor)
    
    assert blob.codec_name == "fp16_raw"
    assert blob.shape == tuple(tensor.shape)
    assert blob.nbytes > 0
    
    decoded = codec.decode(blob)
    
    assert decoded.shape == tensor.shape
    assert decoded.dtype == torch.float16
    assert torch.allclose(decoded, tensor, rtol=1e-3)


def test_int8_symmetric_codec():
    codec = Int8SymmetricCodec()
    
    tensor = torch.randn(4, 8, 16, dtype=torch.float16)
    
    blob = codec.encode(tensor)
    
    assert blob.codec_name == "int8_symm"
    assert blob.shape == tuple(tensor.shape)
    assert blob.nbytes > 0
    assert "scale" in blob.metadata
    
    decoded = codec.decode(blob)
    
    assert decoded.shape == tensor.shape
    assert decoded.dtype == torch.float16
    
    max_error = torch.abs(decoded - tensor).max().item()
    assert max_error < 1.0


def test_codec_compression_ratio():
    fp16_codec = FP16RawCodec()
    int8_codec = Int8SymmetricCodec()
    
    tensor = torch.randn(16, 32, 64, dtype=torch.float16)
    
    fp16_blob = fp16_codec.encode(tensor)
    int8_blob = int8_codec.encode(tensor)
    
    assert int8_blob.nbytes < fp16_blob.nbytes
    
    ratio = fp16_blob.nbytes / int8_blob.nbytes
    print(f"Compression ratio: {ratio:.2f}x")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
