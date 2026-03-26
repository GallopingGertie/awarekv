import requests
from typing import Optional, Dict
from dakv.common.types import PrefixManifest, TransferPlan, RequestTransferState, DeadlineConnectorMetadata
from dakv.planner.deadline_planner import DeadlinePlanner
from dakv.connector.vllm_adapter import extract_request_id, extract_prompt_tokens, extract_num_computed_tokens
from dakv.common.hashing import compute_prefix_key
from dakv.common.time_utils import current_time_ms
from dakv.logging import get_logger
from dakv.metrics import get_metrics_collector
from dakv.constants import PLAN_MODE_RECOMPUTE, REQUEST_STATUS_INIT, REQUEST_STATUS_MISS, REQUEST_STATUS_HIT_PLANNED, REQUEST_STATUS_RECOMPUTE


logger = get_logger()


class SchedulerSide:
    def __init__(self, config, planner: DeadlinePlanner, manifest_url: str):
        self.config = config
        self.planner = planner
        self.manifest_url = manifest_url
        self.metrics = get_metrics_collector()
        self.request_states: Dict[str, RequestTransferState] = {}
    
    def prepare_request_state(self, request, num_computed_tokens: int) -> Optional[tuple]:
        request_id = extract_request_id(request)
        prompt_tokens = extract_prompt_tokens(request)
        
        if not prompt_tokens:
            logger.debug(f"Request {request_id}: no prompt tokens")
            return (0, False)
        
        if len(prompt_tokens) < self.config.planner.min_prefix_tokens:
            logger.debug(f"Request {request_id}: prompt too short ({len(prompt_tokens)} < {self.config.planner.min_prefix_tokens})")
            return (0, False)
        
        if request_id in self.request_states:
            state = self.request_states[request_id]
            if state.status in [REQUEST_STATUS_HIT_PLANNED, REQUEST_STATUS_RECOMPUTE]:
                return (state.matched_tokens, False)
        
        prefix_key = compute_prefix_key(
            model_id=self.config.model_id,
            tokenizer_id=self.config.tokenizer_id,
            kv_layout_version=self.config.kv_layout_version,
            cache_dtype=self.config.cache_dtype,
            block_size=self.config.block_size,
            prompt_token_ids=prompt_tokens,
            matched_prefix_len=len(prompt_tokens)
        )
        
        manifest = self._query_manifest(prefix_key, request_id)
        
        state = RequestTransferState(
            request_id=request_id,
            prefix_key=prefix_key,
            status=REQUEST_STATUS_INIT,
            start_time_ms=current_time_ms()
        )
        
        if manifest is None:
            logger.info(f"Request {request_id}: manifest miss for prefix_key {prefix_key[:16]}...")
            self.metrics.record_manifest_query(hit=False)
            state.status = REQUEST_STATUS_MISS
            state.matched_tokens = 0
            self.request_states[request_id] = state
            return (0, False)
        
        self.metrics.record_manifest_query(hit=True)
        state.manifest = manifest
        state.matched_tokens = manifest.matched_tokens
        state.matched_blocks = manifest.matched_blocks
        
        plan = self.planner.plan(manifest, request_id, self.config.enable_refinement)
        state.plan = plan
        
        if plan.mode == PLAN_MODE_RECOMPUTE:
            logger.info(f"Request {request_id}: planner decided to recompute (reason: {plan.reason_code})")
            self.metrics.record_recompute()
            state.status = REQUEST_STATUS_RECOMPUTE
            state.fallback_reason = plan.reason_code
            self.request_states[request_id] = state
            return (0, False)
        
        state.status = REQUEST_STATUS_HIT_PLANNED
        self.request_states[request_id] = state
        
        matched_tokens = plan.matched_tokens - num_computed_tokens
        
        logger.info(f"Request {request_id}: matched {matched_tokens} tokens, plan {plan.mode}, reason {plan.reason_code}")
        
        return (max(0, matched_tokens), False)
    
    def bind_allocated_blocks(self, request_id: str, allocated_blocks: list):
        if request_id in self.request_states:
            state = self.request_states[request_id]
            state.allocated_block_ids = allocated_blocks
            logger.debug(f"Request {request_id}: bound {len(allocated_blocks)} allocated blocks")
    
    def build_request_metadata(self, request_id: str) -> Optional[DeadlineConnectorMetadata]:
        if request_id not in self.request_states:
            return None
        
        state = self.request_states[request_id]
        
        if state.status != REQUEST_STATUS_HIT_PLANNED:
            return None
        
        if state.manifest is None or state.plan is None:
            return None
        
        metadata = DeadlineConnectorMetadata(
            request_id=request_id,
            prefix_key=state.prefix_key,
            plan_mode=state.plan.mode,
            matched_tokens=state.matched_tokens,
            matched_blocks=state.matched_blocks,
            num_layers=state.manifest.num_layers,
            critical_object_id=state.manifest.critical_object_id,
            critical_codec=state.manifest.critical_codec,
            critical_nbytes=state.manifest.critical_nbytes,
            refinement_object_id=state.manifest.refinement_object_id,
            refinement_codec=state.manifest.refinement_codec,
            refinement_nbytes=state.manifest.refinement_nbytes,
            need_refinement=self.config.enable_refinement and state.manifest.refinement_object_id is not None,
            load_deadline_ms=state.plan.critical_deadline_ms,
            allocated_block_ids=state.allocated_block_ids,
            load_from_tier=state.plan.load_from_tier
        )
        
        return metadata
    
    def get_state(self, request_id: str) -> Optional[RequestTransferState]:
        return self.request_states.get(request_id)
    
    def remove_state(self, request_id: str):
        if request_id in self.request_states:
            del self.request_states[request_id]
            logger.debug(f"Request {request_id}: state removed")
    
    def _query_manifest(self, prefix_key: str, request_id: str) -> Optional[PrefixManifest]:
        try:
            url = f"{self.manifest_url}/manifest/query"
            payload = {
                "prefix_key": prefix_key,
                "request_id": request_id,
                "need_refinement": self.config.enable_refinement
            }
            
            response = requests.post(url, json=payload, timeout=2.0)
            
            if response.status_code != 200:
                logger.warning(f"Manifest query failed: {response.status_code}")
                return None
            
            data = response.json()
            
            if not data.get("hit", False):
                return None
            
            manifest_dict = data.get("manifest")
            if not manifest_dict:
                return None
            
            manifest = PrefixManifest(**manifest_dict)
            return manifest
        except Exception as e:
            logger.warning(f"Failed to query manifest: {e}")
            return None
