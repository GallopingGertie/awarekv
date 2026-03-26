import socket
from typing import Optional
from dakv.transport.protocol import encode_frame, decode_frame, FrameHeader
from dakv.common.checksum import verify_checksum, compute_checksum
from dakv.logging import get_logger
from dakv.constants import (
    FRAME_OP_GET_CRITICAL, FRAME_OP_GET_REFINEMENT,
    FRAME_OP_PUT_CRITICAL, FRAME_OP_PUT_REFINEMENT,
    FRAME_OP_RESPONSE, FRAME_OP_ERROR
)


logger = get_logger()


class DataClient:
    def __init__(self, host: str, port: int, timeout_ms: int = 5000):
        self.host = host
        self.port = port
        self.timeout_s = timeout_ms / 1000.0
    
    def get_critical(self, object_id: str, request_id: str = "") -> Optional[bytes]:
        return self._get(object_id, "critical", request_id)
    
    def get_refinement(self, object_id: str, request_id: str = "") -> Optional[bytes]:
        return self._get(object_id, "refinement", request_id)
    
    def put_critical(self, object_id: str, data: bytes, codec: str, request_id: str = "") -> bool:
        return self._put(object_id, data, "critical", codec, request_id)
    
    def put_refinement(self, object_id: str, data: bytes, codec: str, request_id: str = "") -> bool:
        return self._put(object_id, data, "refinement", codec, request_id)
    
    def _get(self, object_id: str, tier: str, request_id: str) -> Optional[bytes]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout_s)
            sock.connect((self.host, self.port))
            
            op = FRAME_OP_GET_CRITICAL if tier == "critical" else FRAME_OP_GET_REFINEMENT
            
            header = FrameHeader(
                op=op,
                request_id=request_id,
                object_id=object_id,
                tier=tier,
                codec="",
                payload_nbytes=0,
                checksum="",
                deadline_ms=0
            )
            
            frame = encode_frame(header)
            sock.sendall(frame)
            
            response_data = self._recv_frame(sock)
            sock.close()
            
            if not response_data:
                logger.error(f"Failed to receive response for {object_id}")
                return None
            
            response_header, payload = decode_frame(response_data)
            
            if response_header.op == FRAME_OP_ERROR:
                logger.error(f"Server error: {payload.decode('utf-8')}")
                return None
            
            if response_header.checksum and not verify_checksum(payload, response_header.checksum):
                logger.error(f"Checksum mismatch for {object_id}")
                return None
            
            return payload
        except Exception as e:
            logger.error(f"Error getting object {object_id}: {e}")
            return None
    
    def _put(self, object_id: str, data: bytes, tier: str, codec: str, request_id: str) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout_s)
            sock.connect((self.host, self.port))
            
            op = FRAME_OP_PUT_CRITICAL if tier == "critical" else FRAME_OP_PUT_REFINEMENT
            
            checksum = compute_checksum(data)
            
            header = FrameHeader(
                op=op,
                request_id=request_id,
                object_id=object_id,
                tier=tier,
                codec=codec,
                payload_nbytes=len(data),
                checksum=checksum,
                deadline_ms=0
            )
            
            frame = encode_frame(header, data)
            sock.sendall(frame)
            
            response_data = self._recv_frame(sock)
            sock.close()
            
            if not response_data:
                logger.error(f"Failed to receive response for PUT {object_id}")
                return False
            
            response_header, payload = decode_frame(response_data)
            
            if response_header.op == FRAME_OP_ERROR:
                logger.error(f"Server error: {payload.decode('utf-8')}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Error putting object {object_id}: {e}")
            return False
    
    def _recv_frame(self, sock: socket.socket) -> Optional[bytes]:
        try:
            header = sock.recv(14)
            if len(header) < 14:
                return None
            
            import struct
            header_len = struct.unpack("!I", header[6:10])[0]
            payload_len = struct.unpack("!I", header[10:14])[0]
            
            total_len = 14 + header_len + payload_len
            frame_data = header
            
            while len(frame_data) < total_len:
                chunk = sock.recv(min(4096, total_len - len(frame_data)))
                if not chunk:
                    return None
                frame_data += chunk
            
            return frame_data
        except Exception as e:
            logger.error(f"Error receiving frame: {e}")
            return None
