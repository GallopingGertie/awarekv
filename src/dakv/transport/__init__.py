import struct
from typing import Dict, Any
from dataclasses import dataclass


FRAME_MAGIC = b"DAKV"
FRAME_VERSION = 1


@dataclass
class FrameHeader:
    op: str
    request_id: str
    object_id: str
    tier: str
    codec: str
    payload_nbytes: int
    checksum: str
    deadline_ms: int


def encode_frame(header: FrameHeader, payload: bytes = b"") -> bytes:
    header_dict = {
        "op": header.op,
        "request_id": header.request_id,
        "object_id": header.object_id,
        "tier": header.tier,
        "codec": header.codec,
        "checksum": header.checksum,
        "deadline_ms": header.deadline_ms
    }
    
    import json
    header_json = json.dumps(header_dict).encode("utf-8")
    header_len = len(header_json)
    payload_len = len(payload)
    
    frame = FRAME_MAGIC
    frame += struct.pack("!H", FRAME_VERSION)
    frame += struct.pack("!I", header_len)
    frame += struct.pack("!I", payload_len)
    frame += header_json
    frame += payload
    
    return frame


def decode_frame(data: bytes) -> tuple:
    if not data.startswith(FRAME_MAGIC):
        raise ValueError("Invalid frame magic")
    
    offset = len(FRAME_MAGIC)
    
    version = struct.unpack("!H", data[offset:offset+2])[0]
    offset += 2
    
    if version != FRAME_VERSION:
        raise ValueError(f"Unsupported frame version: {version}")
    
    header_len = struct.unpack("!I", data[offset:offset+4])[0]
    offset += 4
    
    payload_len = struct.unpack("!I", data[offset:offset+4])[0]
    offset += 4
    
    import json
    header_json = data[offset:offset+header_len]
    header_dict = json.loads(header_json.decode("utf-8"))
    offset += header_len
    
    payload = data[offset:offset+payload_len]
    
    header = FrameHeader(
        op=header_dict["op"],
        request_id=header_dict["request_id"],
        object_id=header_dict["object_id"],
        tier=header_dict["tier"],
        codec=header_dict["codec"],
        payload_nbytes=payload_len,
        checksum=header_dict["checksum"],
        deadline_ms=header_dict["deadline_ms"]
    )
    
    return header, payload
