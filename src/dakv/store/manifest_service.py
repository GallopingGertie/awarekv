from fastapi import FastAPI, HTTPException
from typing import Optional
import uvicorn

from dakv.store.manifest_models import (
    ManifestQueryRequest, ManifestQueryResponse,
    ManifestPutRequest, ManifestPutResponse,
    ManifestTouchRequest, ManifestTouchResponse,
    ManifestDeleteRequest, ManifestDeleteResponse,
    ManifestStatsResponse
)
from dakv.store.memory_index import MemoryIndex
from dakv.store.local_disk_backend import LocalDiskBackend
from dakv.common.types import PrefixManifest
from dakv.common.time_utils import current_time_ms
from dakv.logging import get_logger
from dakv.constants import TIER_T2_REMOTE


logger = get_logger()


class ManifestService:
    def __init__(self, storage_root: str):
        self.index = MemoryIndex()
        self.object_store = LocalDiskBackend(storage_root)
        self.app = FastAPI()
        self._setup_routes()
    
    def _setup_routes(self):
        @self.app.post("/manifest/query", response_model=ManifestQueryResponse)
        async def query_manifest(req: ManifestQueryRequest):
            manifest = self.index.get(req.prefix_key)
            
            if manifest is None:
                return ManifestQueryResponse(hit=False)
            
            self.index.touch(req.prefix_key)
            
            return ManifestQueryResponse(
                hit=True,
                manifest=self._manifest_to_dict(manifest),
                tier=TIER_T2_REMOTE
            )
        
        @self.app.post("/manifest/put", response_model=ManifestPutResponse)
        async def put_manifest(req: ManifestPutRequest):
            now = current_time_ms()
            
            manifest = PrefixManifest(
                prefix_key=req.prefix_key,
                model_id=req.model_id,
                tokenizer_id=req.tokenizer_id,
                kv_layout_version=req.kv_layout_version,
                block_size=req.block_size,
                cache_dtype=req.cache_dtype,
                matched_tokens=req.matched_tokens,
                matched_blocks=req.matched_blocks,
                num_layers=req.num_layers,
                created_at_ms=now,
                last_access_ms=now,
                ttl_s=req.ttl_s,
                critical_codec=req.critical_codec,
                critical_nbytes=req.critical_nbytes,
                critical_object_id=req.critical_object_id,
                refinement_codec=req.refinement_codec,
                refinement_nbytes=req.refinement_nbytes,
                refinement_object_id=req.refinement_object_id,
                quality_mode=req.quality_mode,
                checksum=req.checksum
            )
            
            self.index.put(manifest)
            
            return ManifestPutResponse(success=True, message="Manifest saved")
        
        @self.app.post("/manifest/touch", response_model=ManifestTouchResponse)
        async def touch_manifest(req: ManifestTouchRequest):
            success = self.index.touch(req.prefix_key)
            return ManifestTouchResponse(success=success)
        
        @self.app.post("/manifest/delete", response_model=ManifestDeleteResponse)
        async def delete_manifest(req: ManifestDeleteRequest):
            success = self.index.delete(req.prefix_key)
            return ManifestDeleteResponse(success=success)
        
        @self.app.get("/manifest/stats", response_model=ManifestStatsResponse)
        async def get_stats():
            manifests = self.index.list_all()
            total_bytes = sum(
                m.critical_nbytes + (m.refinement_nbytes or 0)
                for m in manifests
            )
            
            return ManifestStatsResponse(
                total_manifests=len(manifests),
                total_objects=len(manifests) * 2,
                total_bytes=total_bytes
            )
    
    def _manifest_to_dict(self, manifest: PrefixManifest) -> dict:
        return {
            "prefix_key": manifest.prefix_key,
            "model_id": manifest.model_id,
            "tokenizer_id": manifest.tokenizer_id,
            "kv_layout_version": manifest.kv_layout_version,
            "block_size": manifest.block_size,
            "cache_dtype": manifest.cache_dtype,
            "matched_tokens": manifest.matched_tokens,
            "matched_blocks": manifest.matched_blocks,
            "num_layers": manifest.num_layers,
            "created_at_ms": manifest.created_at_ms,
            "last_access_ms": manifest.last_access_ms,
            "ttl_s": manifest.ttl_s,
            "critical_codec": manifest.critical_codec,
            "critical_nbytes": manifest.critical_nbytes,
            "critical_object_id": manifest.critical_object_id,
            "refinement_codec": manifest.refinement_codec,
            "refinement_nbytes": manifest.refinement_nbytes,
            "refinement_object_id": manifest.refinement_object_id,
            "quality_mode": manifest.quality_mode,
            "checksum": manifest.checksum
        }
    
    def run(self, host: str = "0.0.0.0", port: int = 8081):
        logger.info(f"Starting manifest service on {host}:{port}")
        uvicorn.run(self.app, host=host, port=port)


def create_manifest_service(storage_root: str) -> ManifestService:
    return ManifestService(storage_root)
