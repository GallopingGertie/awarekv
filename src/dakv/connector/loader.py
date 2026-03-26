import torch
from typing import Optional, Tuple, List
from dakv.codec.registry import get_codec
from dakv.common.types import (
    EncodedBlob,
    ObjectHeader,
    DeadlineConnectorMetadata,
    TransferMode
)
from dakv.transport.critical_channel import CriticalChannel
from dakv.transport.refine_channel import RefineChannel
from dakv.common.time_utils import Timer
from dakv.logging import get_logger


logger = get_logger()


class RemoteKVLoader:
    def __init__(
        self,
        critical_channel: CriticalChannel,
        refine_channel: RefineChannel,
        config
    ):
        self.critical_channel = critical_channel
        self.refine_channel = refine_channel
        self.config = config
        self.pending_refinements = {}
    
    def start_critical_load(
        self,
        metadata: DeadlineConnectorMetadata,
        device: torch.device
    ) -> Tuple[bool, Optional[List[torch.Tensor]], int]:
        request_id = metadata.request_id
        critical_object_id = metadata.critical_object_id
        
        if not critical_object_id:
            logger.warning(f"Request {request_id}: no critical object to load")
            return False, None, 0
        
        logger.info(
            f"Request {request_id}: starting critical load "
            f"(mode={metadata.plan_mode}, object={critical_object_id[:16]}...)"
        )
        
        with Timer() as timer:
            data = self.critical_channel.fetch(critical_object_id, request_id)
        
        if data is None:
            logger.error(f"Request {request_id}: critical fetch failed")
            return False, None, 0
        
        logger.info(
            f"Request {request_id}: critical data fetched in {timer.elapsed_ms():.1f}ms "
            f"({len(data)} bytes)"
        )
        
        try:
            header, layer_tensors = self._parse_and_decode_object(
                data=data,
                codec_name=metadata.critical_codec,
                num_layers=metadata.num_layers,
                device=device
            )
            
            loaded_tokens = header.matched_tokens if header else metadata.matched_tokens
            
            logger.info(
                f"Request {request_id}: critical decode complete "
                f"({len(layer_tensors)} layers, {loaded_tokens} tokens)"
            )
            
            return True, layer_tensors, loaded_tokens
        
        except Exception as e:
            logger.error(f"Request {request_id}: critical decode failed: {e}")
            return False, None, 0
    
    def start_refinement_load(
        self,
        metadata: DeadlineConnectorMetadata,
        device: torch.device
    ) -> bool:
        request_id = metadata.request_id
        refinement_object_id = metadata.refinement_object_id
        
        if not metadata.need_refinement or not refinement_object_id:
            logger.debug(f"Request {request_id}: no refinement needed")
            return False
        
        if metadata.plan_mode not in [
            TransferMode.FULL_FP16,
            TransferMode.INT8_FIRST_THEN_FP16
        ]:
            logger.debug(
                f"Request {request_id}: plan mode {metadata.plan_mode} "
                "does not use refinement"
            )
            return False
        
        logger.info(
            f"Request {request_id}: starting refinement load in background "
            f"(object={refinement_object_id[:16]}...)"
        )
        
        with Timer() as timer:
            data = self.refine_channel.fetch(refinement_object_id, request_id)
        
        if data is None:
            logger.warning(f"Request {request_id}: refinement fetch failed")
            return False
        
        logger.info(
            f"Request {request_id}: refinement data fetched in {timer.elapsed_ms():.1f}ms "
            f"({len(data)} bytes)"
        )
        
        try:
            header, layer_tensors = self._parse_and_decode_object(
                data=data,
                codec_name=metadata.refinement_codec,
                num_layers=metadata.num_layers,
                device=device
            )
            
            self.pending_refinements[request_id] = {
                "tensors": layer_tensors,
                "header": header,
                "metadata": metadata
            }
            
            logger.info(
                f"Request {request_id}: refinement decode complete, "
                "ready for apply"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Request {request_id}: refinement decode failed: {e}")
            return False
    
    def apply_refinement_if_ready(
        self,
        request_id: str,
        kv_cache_layers: List[torch.Tensor],
        allocated_block_ids: List[int]
    ) -> bool:
        refinement_data = self.pending_refinements.get(request_id)
        
        if refinement_data is None:
            return False
        
        refined_tensors = refinement_data["tensors"]
        metadata = refinement_data["metadata"]
        
        if len(refined_tensors) != len(kv_cache_layers):
            logger.error(
                f"Request {request_id}: layer count mismatch "
                f"(refined={len(refined_tensors)}, cache={len(kv_cache_layers)})"
            )
            return False
        
        logger.info(
            f"Request {request_id}: applying refinement "
            f"({len(allocated_block_ids)} blocks)"
        )
        
        try:
            with Timer() as timer:
                for layer_idx, (refined_kv, kv_cache_layer) in enumerate(
                    zip(refined_tensors, kv_cache_layers)
                ):
                    self._apply_refinement_to_layer(
                        refined_kv=refined_kv,
                        kv_cache_layer=kv_cache_layer,
                        block_ids=allocated_block_ids,
                        layer_idx=layer_idx
                    )
            
            del self.pending_refinements[request_id]
            
            logger.info(
                f"Request {request_id}: refinement applied in {timer.elapsed_ms():.1f}ms"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Request {request_id}: refinement apply failed: {e}")
            return False
    
    def _apply_refinement_to_layer(
        self,
        refined_kv: torch.Tensor,
        kv_cache_layer: torch.Tensor,
        block_ids: List[int],
        layer_idx: int
    ):
        for i, block_id in enumerate(block_ids):
            if block_id >= 0 and block_id < kv_cache_layer.shape[0]:
                if i < refined_kv.shape[0]:
                    kv_cache_layer[block_id].copy_(refined_kv[i])
        
        logger.debug(
            f"Layer {layer_idx}: applied refinement to {len(block_ids)} blocks"
        )
    
    def _parse_and_decode_object(
        self,
        data: bytes,
        codec_name: str,
        num_layers: int,
        device: torch.device
    ) -> Tuple[Optional[ObjectHeader], List[torch.Tensor]]:
        codec = get_codec(codec_name)
        
        if len(data) < 128:
            logger.warning(
                f"Object too small ({len(data)} bytes), "
                "assuming headerless legacy format"
            )
            return self._decode_legacy_format(
                data=data,
                codec=codec,
                num_layers=num_layers,
                device=device
            )
        
        try:
            header = self._try_parse_header(data[:128])
            
            if header and header.object_format_version >= 1:
                logger.debug(
                    f"Parsing object with header (version={header.object_format_version}, "
                    f"layers={header.num_layers}, tokens={header.matched_tokens})"
                )
                
                return self._decode_with_header(
                    data=data,
                    header=header,
                    codec=codec,
                    device=device
                )
        except Exception as e:
            logger.warning(f"Failed to parse header: {e}, fallback to legacy format")
        
        return self._decode_legacy_format(
            data=data,
            codec=codec,
            num_layers=num_layers,
            device=device
        )
    
    def _try_parse_header(self, header_bytes: bytes) -> Optional[ObjectHeader]:
        if len(header_bytes) < 128:
            return None
        
        magic = header_bytes[:8]
        if magic != b"DAKVOBJ\x00":
            return None
        
        import struct
        
        (
            version,
            num_layers,
            matched_tokens,
            matched_blocks,
            block_size,
            _reserved1,
            _reserved2,
            _reserved3
        ) = struct.unpack("<IIIIIIII", header_bytes[8:40])
        
        header = ObjectHeader(
            object_format_version=version,
            num_layers=num_layers,
            matched_tokens=matched_tokens,
            matched_blocks=matched_blocks,
            block_size=block_size,
            cache_dtype="float16",
            kv_layout_version=1,
            checksum=""
        )
        
        return header
    
    def _decode_with_header(
        self,
        data: bytes,
        header: ObjectHeader,
        codec,
        device: torch.device
    ) -> Tuple[ObjectHeader, List[torch.Tensor]]:
        payload_start = 128
        
        if header.num_layers == 0:
            logger.warning("Header indicates 0 layers")
            return header, []
        
        bytes_per_layer = (len(data) - payload_start) // header.num_layers
        
        layer_tensors = []
        for layer_idx in range(header.num_layers):
            layer_start = payload_start + layer_idx * bytes_per_layer
            layer_end = layer_start + bytes_per_layer
            layer_data = data[layer_start:layer_end]
            
            blob = EncodedBlob(
                codec_name=codec.name,
                data=layer_data,
                shape=None,
                dtype="int8" if "int8" in codec.name else "float16"
            )
            
            decoded_tensor = codec.decode(blob, device=device)
            layer_tensors.append(decoded_tensor)
        
        logger.debug(
            f"Decoded {len(layer_tensors)} layers from object with header"
        )
        
        return header, layer_tensors
    
    def _decode_legacy_format(
        self,
        data: bytes,
        codec,
        num_layers: int,
        device: torch.device
    ) -> Tuple[None, List[torch.Tensor]]:
        if num_layers == 0:
            logger.warning("Cannot decode legacy format with num_layers=0")
            return None, []
        
        bytes_per_layer = len(data) // num_layers
        
        layer_tensors = []
        for layer_idx in range(num_layers):
            layer_start = layer_idx * bytes_per_layer
            layer_end = layer_start + bytes_per_layer
            layer_data = data[layer_start:layer_end]
            
            blob = EncodedBlob(
                codec_name=codec.name,
                data=layer_data,
                shape=None,
                dtype="int8" if "int8" in codec.name else "float16"
            )
            
            decoded_tensor = codec.decode(blob, device=device)
            layer_tensors.append(decoded_tensor)
        
        logger.debug(
            f"Decoded {len(layer_tensors)} layers from legacy format"
        )
        
        return None, layer_tensors
    
    def has_pending_refinement(self, request_id: str) -> bool:
        return request_id in self.pending_refinements
    
    def clear_pending_refinement(self, request_id: str):
        if request_id in self.pending_refinements:
            del self.pending_refinements[request_id]
            logger.debug(f"Request {request_id}: cleared pending refinement")
