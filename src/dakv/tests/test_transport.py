import pytest
from dakv.transport.protocol import FrameHeader, encode_frame, decode_frame
from dakv.constants import FRAME_OP_GET_CRITICAL


def test_frame_encoding_decoding():
    header = FrameHeader(
        op=FRAME_OP_GET_CRITICAL,
        request_id="req_123",
        object_id="obj_456",
        tier="T2",
        codec="int8_symm",
        payload_nbytes=100,
        checksum="abc123",
        deadline_ms=500
    )
    
    payload = b"test payload data"
    
    frame = encode_frame(header, payload)
    
    assert frame.startswith(b"DAKV")
    assert len(frame) > len(payload)
    
    decoded_header, decoded_payload = decode_frame(frame)
    
    assert decoded_header.op == header.op
    assert decoded_header.request_id == header.request_id
    assert decoded_header.object_id == header.object_id
    assert decoded_payload == payload


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
