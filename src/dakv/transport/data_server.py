import socket
import threading
from typing import Optional
from dakv.transport.protocol import decode_frame, encode_frame, FrameHeader
from dakv.store.local_disk_backend import LocalDiskBackend
from dakv.common.checksum import verify_checksum
from dakv.logging import get_logger
from dakv.constants import (
    FRAME_OP_GET_CRITICAL, FRAME_OP_GET_REFINEMENT,
    FRAME_OP_PUT_CRITICAL, FRAME_OP_PUT_REFINEMENT,
    FRAME_OP_DELETE, FRAME_OP_RESPONSE, FRAME_OP_ERROR
)


logger = get_logger()


class DataServer:
    def __init__(self, host: str, port: int, object_store: LocalDiskBackend):
        self.host = host
        self.port = port
        self.object_store = object_store
        self.server_socket: Optional[socket.socket] = None
        self.running = False
    
    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(10)
        self.running = True
        
        logger.info(f"Data server listening on {self.host}:{self.port}")
        
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                logger.info(f"New connection from {addr}")
                
                thread = threading.Thread(target=self._handle_client, args=(client_socket,))
                thread.daemon = True
                thread.start()
            except Exception as e:
                if self.running:
                    logger.error(f"Error accepting connection: {e}")
    
    def _handle_client(self, client_socket: socket.socket):
        try:
            while True:
                frame_data = self._recv_frame(client_socket)
                if not frame_data:
                    break
                
                header, payload = decode_frame(frame_data)
                
                response_data = self._process_request(header, payload)
                
                if response_data:
                    client_socket.sendall(response_data)
        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            client_socket.close()
    
    def _recv_frame(self, sock: socket.socket) -> Optional[bytes]:
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
    
    def _process_request(self, header: FrameHeader, payload: bytes) -> Optional[bytes]:
        try:
            if header.op == FRAME_OP_GET_CRITICAL:
                return self._handle_get(header, "critical")
            elif header.op == FRAME_OP_GET_REFINEMENT:
                return self._handle_get(header, "refinement")
            elif header.op == FRAME_OP_PUT_CRITICAL:
                return self._handle_put(header, payload, "critical")
            elif header.op == FRAME_OP_PUT_REFINEMENT:
                return self._handle_put(header, payload, "refinement")
            elif header.op == FRAME_OP_DELETE:
                return self._handle_delete(header)
            else:
                return self._error_response(header, f"Unknown op: {header.op}")
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            return self._error_response(header, str(e))
    
    def _handle_get(self, header: FrameHeader, tier: str) -> bytes:
        data = self.object_store.get(header.object_id, tier=tier)
        
        if data is None:
            return self._error_response(header, "Object not found")
        
        from dakv.common.checksum import compute_checksum
        checksum = compute_checksum(data)
        
        response_header = FrameHeader(
            op=FRAME_OP_RESPONSE,
            request_id=header.request_id,
            object_id=header.object_id,
            tier=tier,
            codec=header.codec,
            payload_nbytes=len(data),
            checksum=checksum,
            deadline_ms=0
        )
        
        return encode_frame(response_header, data)
    
    def _handle_put(self, header: FrameHeader, payload: bytes, tier: str) -> bytes:
        if header.checksum and not verify_checksum(payload, header.checksum):
            return self._error_response(header, "Checksum mismatch")
        
        success = self.object_store.put(header.object_id, payload, tier=tier)
        
        if not success:
            return self._error_response(header, "Failed to store object")
        
        response_header = FrameHeader(
            op=FRAME_OP_RESPONSE,
            request_id=header.request_id,
            object_id=header.object_id,
            tier=tier,
            codec=header.codec,
            payload_nbytes=0,
            checksum="",
            deadline_ms=0
        )
        
        return encode_frame(response_header, b"OK")
    
    def _handle_delete(self, header: FrameHeader) -> bytes:
        self.object_store.delete(header.object_id, tier="critical")
        self.object_store.delete(header.object_id, tier="refinement")
        
        response_header = FrameHeader(
            op=FRAME_OP_RESPONSE,
            request_id=header.request_id,
            object_id=header.object_id,
            tier="",
            codec="",
            payload_nbytes=0,
            checksum="",
            deadline_ms=0
        )
        
        return encode_frame(response_header, b"OK")
    
    def _error_response(self, header: FrameHeader, error_msg: str) -> bytes:
        error_header = FrameHeader(
            op=FRAME_OP_ERROR,
            request_id=header.request_id,
            object_id=header.object_id,
            tier="",
            codec="",
            payload_nbytes=len(error_msg),
            checksum="",
            deadline_ms=0
        )
        
        return encode_frame(error_header, error_msg.encode("utf-8"))
    
    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()
