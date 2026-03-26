import torch
import numpy as np
from typing import Optional, Tuple


def tensor_to_bytes(tensor: torch.Tensor) -> bytes:
    if tensor.is_cuda:
        tensor = tensor.cpu()
    numpy_array = tensor.numpy()
    return numpy_array.tobytes()


def bytes_to_tensor(
    data: bytes,
    shape: Tuple[int, ...],
    dtype: torch.dtype,
    device: Optional[torch.device] = None
) -> torch.Tensor:
    if dtype == torch.float16:
        np_dtype = np.float16
    elif dtype == torch.float32:
        np_dtype = np.float32
    elif dtype == torch.int8:
        np_dtype = np.int8
    elif dtype == torch.int32:
        np_dtype = np.int32
    elif dtype == torch.int64:
        np_dtype = np.int64
    else:
        raise ValueError(f"Unsupported dtype: {dtype}")
    
    numpy_array = np.frombuffer(data, dtype=np_dtype).reshape(shape)
    tensor = torch.from_numpy(numpy_array.copy())
    
    if device is not None:
        tensor = tensor.to(device)
    
    return tensor


def get_tensor_nbytes(shape: Tuple[int, ...], dtype: torch.dtype) -> int:
    element_size = torch.tensor([], dtype=dtype).element_size()
    numel = 1
    for dim in shape:
        numel *= dim
    return numel * element_size
