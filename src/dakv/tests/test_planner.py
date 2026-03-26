import pytest
from dakv.planner.estimator import BandwidthEstimator
from dakv.planner.deadline_planner import DeadlinePlanner
from dakv.common.types import PrefixManifest
from dakv.common.time_utils import current_time_ms
from dakv.constants import PLAN_MODE_FULL_FP16, PLAN_MODE_CRITICAL_INT8_THEN_FP16, PLAN_MODE_RECOMPUTE


def test_bandwidth_estimator():
    estimator = BandwidthEstimator(alpha=0.3)
    
    estimator.update(nbytes=1_000_000, duration_ms=10.0, rtt_ms=5.0)
    
    estimate = estimator.get_estimate()
    
    assert estimate.bandwidth_bps > 0
    assert estimate.rtt_ms > 0


def test_deadline_planner_full_fp16():
    estimator = BandwidthEstimator()
    estimator.update(nbytes=10_000_000, duration_ms=10.0)
    
    planner = DeadlinePlanner(
        estimator=estimator,
        ttft_slo_ms=500,
        alpha=0.8,
        min_prefix_tokens=128
    )
    
    manifest = PrefixManifest(
        prefix_key="test_key",
        model_id="test_model",
        tokenizer_id="test_tokenizer",
        kv_layout_version="v1",
        block_size=16,
        cache_dtype="float16",
        matched_tokens=256,
        matched_blocks=list(range(16)),
        num_layers=32,
        created_at_ms=current_time_ms(),
        last_access_ms=current_time_ms(),
        ttl_s=3600,
        critical_codec="int8_symm",
        critical_nbytes=1_000_000,
        critical_object_id="obj_123",
        refinement_codec="fp16_raw",
        refinement_nbytes=2_000_000,
        refinement_object_id="obj_456"
    )
    
    plan = planner.plan(manifest, "req_1", enable_refinement=True)
    
    assert plan.matched_tokens == 256
    assert plan.mode in [PLAN_MODE_FULL_FP16, PLAN_MODE_CRITICAL_INT8_THEN_FP16]


def test_deadline_planner_recompute_short_prefix():
    estimator = BandwidthEstimator()
    
    planner = DeadlinePlanner(
        estimator=estimator,
        ttft_slo_ms=500,
        alpha=0.8,
        min_prefix_tokens=128
    )
    
    manifest = PrefixManifest(
        prefix_key="test_key",
        model_id="test_model",
        tokenizer_id="test_tokenizer",
        kv_layout_version="v1",
        block_size=16,
        cache_dtype="float16",
        matched_tokens=64,
        matched_blocks=list(range(4)),
        num_layers=32,
        created_at_ms=current_time_ms(),
        last_access_ms=current_time_ms(),
        ttl_s=3600,
        critical_codec="int8_symm",
        critical_nbytes=100_000,
        critical_object_id="obj_123"
    )
    
    plan = planner.plan(manifest, "req_1", enable_refinement=True)
    
    assert plan.mode == PLAN_MODE_RECOMPUTE
    assert plan.matched_tokens == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
