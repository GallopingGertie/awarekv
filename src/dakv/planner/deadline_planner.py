import uuid
from typing import List
from dakv.common.types import TransferPlan, PrefixManifest, NetworkEstimate
from dakv.planner.estimator import BandwidthEstimator
from dakv.logging import get_logger
from dakv.constants import (
    PLAN_MODE_FULL_FP16,
    PLAN_MODE_CRITICAL_INT8_ONLY,
    PLAN_MODE_CRITICAL_INT8_THEN_FP16,
    PLAN_MODE_RECOMPUTE,
    TIER_T1_HOST,
    TIER_T2_REMOTE
)


logger = get_logger()


class DeadlinePlanner:
    def __init__(
        self,
        estimator: BandwidthEstimator,
        ttft_slo_ms: int,
        alpha: float = 0.8,
        min_prefix_tokens: int = 128
    ):
        self.estimator = estimator
        self.ttft_slo_ms = ttft_slo_ms
        self.alpha = alpha
        self.min_prefix_tokens = min_prefix_tokens
    
    def plan(
        self,
        manifest: PrefixManifest,
        request_id: str,
        enable_refinement: bool = True
    ) -> TransferPlan:
        if manifest.matched_tokens < self.min_prefix_tokens:
            return self._recompute_plan(
                manifest.matched_tokens,
                manifest.matched_blocks,
                "prefix_too_short"
            )
        
        net_est = self.estimator.get_estimate()
        
        critical_nbytes = manifest.critical_nbytes
        refine_nbytes = manifest.refinement_nbytes or 0
        
        ttft_budget_ms = self.ttft_slo_ms * self.alpha
        
        fp16_time_ms = net_est.rtt_ms + (critical_nbytes * 8 * 1000.0) / net_est.bandwidth_bps
        
        if fp16_time_ms < ttft_budget_ms:
            logger.info(f"Plan: FULL_FP16 (est {fp16_time_ms:.1f}ms < {ttft_budget_ms:.1f}ms)")
            return TransferPlan(
                plan_id=str(uuid.uuid4()),
                matched_tokens=manifest.matched_tokens,
                matched_blocks=manifest.matched_blocks,
                mode=PLAN_MODE_FULL_FP16,
                critical_deadline_ms=int(ttft_budget_ms),
                refine_budget_ms=0,
                load_from_tier=TIER_T2_REMOTE,
                allow_refine_drop=False,
                reason_code="full_fp16_within_budget",
                estimated_critical_bytes=critical_nbytes,
                estimated_refine_bytes=0
            )
        
        int8_nbytes = critical_nbytes // 2
        int8_time_ms = net_est.rtt_ms + (int8_nbytes * 8 * 1000.0) / net_est.bandwidth_bps
        
        if int8_time_ms >= ttft_budget_ms:
            logger.warning(f"Plan: RECOMPUTE (int8 {int8_time_ms:.1f}ms >= {ttft_budget_ms:.1f}ms)")
            return self._recompute_plan(
                manifest.matched_tokens,
                manifest.matched_blocks,
                "deadline_miss_even_with_int8"
            )
        
        if not enable_refinement or refine_nbytes == 0:
            logger.info(f"Plan: CRITICAL_INT8_ONLY (refinement disabled)")
            return TransferPlan(
                plan_id=str(uuid.uuid4()),
                matched_tokens=manifest.matched_tokens,
                matched_blocks=manifest.matched_blocks,
                mode=PLAN_MODE_CRITICAL_INT8_ONLY,
                critical_deadline_ms=int(ttft_budget_ms),
                refine_budget_ms=0,
                load_from_tier=TIER_T2_REMOTE,
                allow_refine_drop=True,
                reason_code="int8_only_no_refinement",
                estimated_critical_bytes=int8_nbytes,
                estimated_refine_bytes=0
            )
        
        refine_budget_ms = max(100, int(self.ttft_slo_ms * 0.3))
        
        logger.info(f"Plan: CRITICAL_INT8_THEN_FP16 (critical {int8_time_ms:.1f}ms, refine budget {refine_budget_ms}ms)")
        return TransferPlan(
            plan_id=str(uuid.uuid4()),
            matched_tokens=manifest.matched_tokens,
            matched_blocks=manifest.matched_blocks,
            mode=PLAN_MODE_CRITICAL_INT8_THEN_FP16,
            critical_deadline_ms=int(ttft_budget_ms),
            refine_budget_ms=refine_budget_ms,
            load_from_tier=TIER_T2_REMOTE,
            allow_refine_drop=True,
            reason_code="fallback_to_int8_for_ttft",
            estimated_critical_bytes=int8_nbytes,
            estimated_refine_bytes=refine_nbytes
        )
    
    def _recompute_plan(self, matched_tokens: int, matched_blocks: List[int], reason: str) -> TransferPlan:
        return TransferPlan(
            plan_id=str(uuid.uuid4()),
            matched_tokens=0,
            matched_blocks=[],
            mode=PLAN_MODE_RECOMPUTE,
            critical_deadline_ms=0,
            refine_budget_ms=0,
            load_from_tier=TIER_T2_REMOTE,
            allow_refine_drop=True,
            reason_code=reason,
            estimated_critical_bytes=0,
            estimated_refine_bytes=0
        )
