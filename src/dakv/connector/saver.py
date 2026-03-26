import torch
import requests
import struct
from typing import List, Optional, Dict, Any
from dakv.codec.registry import get_codec
from dakv.transport.critical_channel import CriticalChannel
from dakv.transport.refine_channel import RefineChannel
from dakv.common.hashing import compute_object_id
from dakv.common.types import ObjectHeader
from dakv.common.time_utils import Timer
from dakv.logging import get_logger


logger = get_logger()


class KVSaver:
    def __init__(
        self,
        critical_channel: CriticalChannel,
        refine_channel: RefineChannel,
        manifest_url: str,
        config
    ):
        self.critical_channel = critical_channel
        self.refine_channel = refine_channel
        self.manifest_url = manifest_url
        self.config = config
    
    def save_prefix_kv(
        self,
        prefix_key: str,
        kv_tensors: List[torch.Tensor],
        matched_tokens: int,
        matched_blocks: int,
        request_id: str = ""
    ) -> bool:
        num_layers = len(kv_tensors)
        
        logger.info(
            f"Request {request_id}: saving prefix KV "
            f"(key={prefix_key[:16]}..., tokens={matched_tokens}, "
            f"blocks={matched_blocks}, layers={num_layers})"
        )
        
        if num_layers == 0:
            logger.error(f"Request {request_id}: no layers to save")
            return False
        
        critical_success = self._save_critical_tier(
            prefix_key=prefix_key,
            kv_tensors=kv_tensors,
            matched_tokens=matched_tokens,
            matched_blocks=matched_blocks,
            num_layers=num_layers,
            request_id=request_id
        )
        
        if not critical_success:
            logger.error(f"Request {request_id}: critical save failed")
            return False
        
        refinement_success = False
        refinement_object_id = None
        refinement_nbytes = 0
        refinement_codec_name = None
        
        if self.config.enable_refinement:
            refinement_success, refinement_object_id, refinement_nbytes, refinement_codec_name = self._save_refinement_tier(
                prefix_key=prefix_key,
                kv_tensors=kv_tensors,
                matched_tokens=matched_tokens,
                matched_blocks=matched_blocks,
                num_layers=num_layers,
                request_id=request_id
            )
        
        critical_object_id = compute_object_id(
            prefix_key=prefix_key,
            tier="critical",
            codec_name=self.config.critical_codec,
            object_format_version=self.config.object_format_version
        )
        
        manifest_success = self._update_manifest(
            prefix_key=prefix_key,
            matched_tokens=matched_tokens,
            matched_blocks=matched_blocks,
            num_layers=num_layers,
            critical_object_id=critical_object_id,
            critical_codec=self.config.critical_codec,
            critical_nbytes=self._estimate_critical_size(kv_tensors),
            refinement_object_id=refinement_object_id if refinement_success else None,
            refinement_codec=refinement_codec_name if refinement_success else None,
            refinement_nbytes=refinement_nbytes if refinement_success else 0,
            request_id=request_id
        )
        
        if not manifest_success:
            logger.warning(f"Request {request_id}: manifest update failed")
        
        logger.info(
            f"Request {request_id}: prefix KV save complete "
            f"(critical=OK, refinement={refinement_success}, manifest={manifest_success})"
        )
        
        return critical_success and manifest_success
    
    def _save_critical_tier(
        self,
        prefix_key: str,
        kv_tensors: List[torch.Tensor],
        matched_tokens: int,
        matched_blocks: int,
        num_layers: int,
        request_id: str
    ) -> bool:
        critical_codec = get_codec(self.config.critical_codec)
        
        logger.debug(
            f"Request {request_id}: encoding {num_layers} layers with {critical_codec.name}"
        )
        
        with Timer() as encode_timer:
            encoded_layers = []
            for layer_idx, kv_tensor in enumerate(kv_tensors):
                blob = critical_codec.encode(kv_tensor)
                encoded_layers.append(blob.data)
                logger.debug(
                    f"Request {request_id}: layer {layer_idx} encoded "
                    f"({len(blob.data)} bytes)"
                )
        
        logger.info(
            f"Request {request_id}: critical encoding complete in {encode_timer.elapsed_ms():.1f}ms"
        )
        
        header = self._build_object_header(
            num_layers=num_layers,
            matched_tokens=matched_tokens,
            matched_blocks=matched_blocks,
            block_size=self.config.block_size,
            cache_dtype=self.config.cache_dtype,
            kv_layout_version=self.config.kv_layout_version
        )
        
        critical_object = self._build_object_with_header(header, encoded_layers)
        
        critical_object_id = compute_object_id(
            prefix_key=prefix_key,
            tier="critical",
            codec_name=critical_codec.name,
            object_format_version=self.config.object_format_version
        )
        
        with Timer() as store_timer:
            success = self.critical_channel.store(
                critical_object_id,
                critical_object,
                critical_codec.name,
                request_id
            )
        
        if success:
            logger.info(
                f"Request {request_id}: critical object stored in {store_timer.elapsed_ms():.1f}ms "
                f"({len(critical_object)} bytes, object={critical_object_id[:16]}...)"
            )
        else:
            logger.error(
                f"Request {request_id}: critical object store failed "
                f"(object={critical_object_id[:16]}...)"
            )
        
        return success
    
    def _save_refinement_tier(
        self,
        prefix_key: str,
        kv_tensors: List[torch.Tensor],
        matched_tokens: int,
        matched_blocks: int,
        num_layers: int,
        request_id: str
    ) -> tuple[bool, Optional[str], int, Optional[str]]:
        refinement_codec = get_codec(self.config.refinement_codec)
        
        logger.debug(
            f"Request {request_id}: encoding {num_layers} layers with {refinement_codec.name} "
            "for refinement"
        )
        
        with Timer() as encode_timer:
            encoded_layers = []
            for layer_idx, kv_tensor in enumerate(kv_tensors):
                blob = refinement_codec.encode(kv_tensor)
                encoded_layers.append(blob.data)
                logger.debug(
                    f"Request {request_id}: refinement layer {layer_idx} encoded "
                    f"({len(blob.data)} bytes)"
                )
        
        logger.info(
            f"Request {request_id}: refinement encoding complete in {encode_timer.elapsed_ms():.1f}ms"
        )
        
        header = self._build_object_header(
            num_layers=num_layers,
            matched_tokens=matched_tokens,
            matched_blocks=matched_blocks,
            block_size=self.config.block_size,
            cache_dtype=self.config.cache_dtype,
            kv_layout_version=self.config.kv_layout_version
        )
        
        refinement_object = self._build_object_with_header(header, encoded_layers)
        
        refinement_object_id = compute_object_id(
            prefix_key=prefix_key,
            tier="refinement",
            codec_name=refinement_codec.name,
            object_format_version=self.config.object_format_version
        )
        
        with Timer() as store_timer:
            success = self.refine_channel.store(
                refinement_object_id,
                refinement_object,
                refinement_codec.name,
                request_id
            )
        
        if success:
            logger.info(
                f"Request {request_id}: refinement object stored in {store_timer.elapsed_ms():.1f}ms "
                f"({len(refinement_object)} bytes, object={refinement_object_id[:16]}...)"
            )
            return True, refinement_object_id, len(refinement_object), refinement_codec.name
        else:
            logger.error(
                f"Request {request_id}: refinement object store failed "
                f"(object={refinement_object_id[:16]}...)"
            )
            return False, None, 0, None
    
    def _build_object_header(
        self,
        num_layers: int,
        matched_tokens: int,
        matched_blocks: int,
        block_size: int,
        cache_dtype: str,
        kv_layout_version: int
    ) -> ObjectHeader:
        return ObjectHeader(
            object_format_version=self.config.object_format_version,
            num_layers=num_layers,
            matched_tokens=matched_tokens,
            matched_blocks=matched_blocks,
            block_size=block_size,
            cache_dtype=cache_dtype,
            kv_layout_version=kv_layout_version,
            checksum=""
        )
    
    def _build_object_with_header(
        self,
        header: ObjectHeader,
        layer_data_list: List[bytes]
    ) -> bytes:
        header_bytes = self._serialize_header(header)
        
        payload = b"".join(layer_data_list)
        
        full_object = header_bytes + payload
        
        logger.debug(
            f"Built object: header={len(header_bytes)}B, payload={len(payload)}B, "
            f"total={len(full_object)}B"
        )
        
        return full_object
    
    def _serialize_header(self, header: ObjectHeader) -> bytes:
        magic = b"DAKVOBJ\x00"
        
        packed = struct.pack(
            "<IIIIIIII",
            header.object_format_version,
            header.num_layers,
            header.matched_tokens,
            header.matched_blocks,
            header.block_size,
            0,
            0,
            0
        )
        
        header_bytes = magic + packed
        
        header_bytes = header_bytes.ljust(128, b"\x00")
        
        return header_bytes
    
    def _estimate_critical_size(self, kv_tensors: List[torch.Tensor]) -> int:
        codec = get_codec(self.config.critical_codec)
        
        if len(kv_tensors) == 0:
            return 0
        
        sample_blob = codec.encode(kv_tensors[0])
        bytes_per_layer = len(sample_blob.data)
        
        total_bytes = bytes_per_layer * len(kv_tensors) + 128
        
        return total_bytes
    
    def _update_manifest(
        self,
        prefix_key: str,
        matched_tokens: int,
        matched_blocks: int,
        num_layers: int,
        critical_object_id: str,
        critical_codec: str,
        critical_nbytes: int,
        refinement_object_id: Optional[str],
        refinement_codec: Optional[str],
        refinement_nbytes: int,
        request_id: str
    ) -> bool:
        try:
            url = f"{self.manifest_url}/manifest/put"
            
            if refinement_object_id:
                quality_mode = "int8+fp16"
            else:
                quality_mode = "int8_only"
            
            payload = {
                "prefix_key": prefix_key,
                "model_id": self.config.model_id,
                "tokenizer_id": getattr(self.config, "tokenizer_id", self.config.model_id),
                "kv_layout_version": self.config.kv_layout_version,
                "object_format_version": self.config.object_format_version,
                "block_size": self.config.block_size,
                "cache_dtype": self.config.cache_dtype,
                "matched_tokens": matched_tokens,
                "matched_blocks": matched_blocks,
                "num_layers": num_layers,
                "ttl_s": 3600,
                "critical_codec": critical_codec,
                "critical_nbytes": critical_nbytes,
                "critical_object_id": critical_object_id,
                "refinement_codec": refinement_codec,
                "refinement_nbytes": refinement_nbytes if refinement_nbytes > 0 else None,
                "refinement_object_id": refinement_object_id,
                "quality_mode": quality_mode,
                "checksum": "",
                "request_id": request_id
            }
            
            logger.debug(
                f"Request {request_id}: updating manifest "
                f"(key={prefix_key[:16]}..., tokens={matched_tokens}, "
                f"quality={quality_mode})"
            )
            
            with Timer() as timer:
                response = requests.post(url, json=payload, timeout=5.0)
            
            if response.status_code == 200:
                logger.info(
                    f"Request {request_id}: manifest updated in {timer.elapsed_ms():.1f}ms "
                    f"(key={prefix_key[:16]}...)"
                )
                return True
            else:
                logger.warning(
                    f"Request {request_id}: manifest update failed "
                    f"(status={response.status_code}, key={prefix_key[:16]}...)"
                )
                return False
        
        except requests.Timeout:
            logger.error(
                f"Request {request_id}: manifest update timeout "
                f"(key={prefix_key[:16]}...)"
            )
            return False
        
        except Exception as e:
            logger.error(
                f"Request {request_id}: manifest update error: {e} "
                f"(key={prefix_key[:16]}...)"
            )
            return False
