import torch
import requests
from typing import List
from dakv.codec.registry import get_codec
from dakv.transport.critical_channel import CriticalChannel
from dakv.transport.refine_channel import RefineChannel
from dakv.common.hashing import compute_object_id
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
        matched_blocks: List[int],
        num_layers: int
    ):
        logger.info(f"Saving prefix KV: {matched_tokens} tokens, {num_layers} layers")
        
        critical_codec = get_codec(self.config.critical_codec)
        
        critical_blobs = []
        for layer_idx, kv_tensor in enumerate(kv_tensors):
            blob = critical_codec.encode(kv_tensor)
            critical_blobs.append(blob)
        
        critical_data = b"".join([b.data for b in critical_blobs])
        critical_object_id = compute_object_id(prefix_key, "critical", critical_codec.name)
        
        success = self.critical_channel.store(
            critical_object_id,
            critical_data,
            critical_codec.name,
            ""
        )
        
        if not success:
            logger.error("Failed to save critical KV")
            return False
        
        refinement_object_id = None
        refinement_nbytes = 0
        
        if self.config.enable_refinement:
            refine_codec = get_codec(self.config.refinement_codec)
            refine_blobs = []
            for kv_tensor in kv_tensors:
                blob = refine_codec.encode(kv_tensor)
                refine_blobs.append(blob)
            
            refine_data = b"".join([b.data for b in refine_blobs])
            refinement_object_id = compute_object_id(prefix_key, "refinement", refine_codec.name)
            
            self.refine_channel.store(refinement_object_id, refine_data, refine_codec.name, "")
            refinement_nbytes = len(refine_data)
        
        self._update_manifest(
            prefix_key=prefix_key,
            matched_tokens=matched_tokens,
            matched_blocks=matched_blocks,
            num_layers=num_layers,
            critical_object_id=critical_object_id,
            critical_nbytes=len(critical_data),
            refinement_object_id=refinement_object_id,
            refinement_nbytes=refinement_nbytes
        )
        
        logger.info(f"Prefix KV saved: critical {len(critical_data)} bytes")
        return True
    
    def _update_manifest(
        self,
        prefix_key: str,
        matched_tokens: int,
        matched_blocks: List[int],
        num_layers: int,
        critical_object_id: str,
        critical_nbytes: int,
        refinement_object_id: str,
        refinement_nbytes: int
    ):
        try:
            url = f"{self.manifest_url}/manifest/put"
            payload = {
                "prefix_key": prefix_key,
                "model_id": self.config.model_id,
                "tokenizer_id": self.config.model_id,
                "kv_layout_version": self.config.kv_layout_version,
                "block_size": 16,
                "cache_dtype": "float16",
                "matched_tokens": matched_tokens,
                "matched_blocks": matched_blocks,
                "num_layers": num_layers,
                "ttl_s": 3600,
                "critical_codec": self.config.critical_codec,
                "critical_nbytes": critical_nbytes,
                "critical_object_id": critical_object_id,
                "refinement_codec": self.config.refinement_codec if refinement_object_id else None,
                "refinement_nbytes": refinement_nbytes if refinement_object_id else None,
                "refinement_object_id": refinement_object_id,
                "quality_mode": "int8+fp16" if refinement_object_id else "int8_only",
                "checksum": ""
            }
            
            response = requests.post(url, json=payload, timeout=2.0)
            
            if response.status_code == 200:
                logger.info(f"Manifest updated for {prefix_key[:16]}...")
            else:
                logger.warning(f"Manifest update failed: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to update manifest: {e}")
