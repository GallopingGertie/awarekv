import pytest
from dakv.common.types import PrefixManifest
from dakv.common.time_utils import current_time_ms


def test_manifest_creation():
    manifest = PrefixManifest(
        prefix_key="test_key_123",
        model_id="test_model",
        tokenizer_id="test_tokenizer",
        kv_layout_version="v1",
        block_size=16,
        cache_dtype="float16",
        matched_tokens=100,
        matched_blocks=[0, 1, 2],
        num_layers=32,
        created_at_ms=current_time_ms(),
        last_access_ms=current_time_ms(),
        ttl_s=3600,
        critical_codec="int8_symm",
        critical_nbytes=1024,
        critical_object_id="obj_123",
        refinement_codec="fp16_raw",
        refinement_nbytes=2048,
        refinement_object_id="obj_456",
        quality_mode="int8+fp16",
        checksum="abc123"
    )
    
    assert manifest.prefix_key == "test_key_123"
    assert manifest.matched_tokens == 100
    assert len(manifest.matched_blocks) == 3
    assert manifest.quality_mode == "int8+fp16"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
