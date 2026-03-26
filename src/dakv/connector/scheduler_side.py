import requests
from typing import Optional
from dakv.common.types import PrefixManifest, TransferPlan
from dakv.planner.deadline_planner import DeadlinePlanner
from dakv.connector.vllm_adapter import extract_request_id, extract_prompt_tokens
from dakv.common.hashing import compute_prefix_key
from dakv.logging import get_logger
from dakv.metrics import get_metrics_collector
from dakv.constants import PLAN_MODE_RECOMPUTE


logger = get_logger()


class SchedulerSide:
    def __init__(self, config, planner: DeadlinePlanner, manifest_url: str):
        self.config = config
        self.planner = planner
        self.manifest_url = manifest_url
        self.metrics = get_metrics_collector()
    
    def get_num_matched_tokens(self, request, num_computed_tokens: int) -> tuple:
        request_id = extract_request_id(request)
        prompt_tokens = extract_prompt_tokens(request)
        
        if not prompt_tokens or len(prompt_tokens) < self.config.planner.min_prefix_tokens:
            logger.debug(f"Request {request_id}: prompt too short, no prefix matching")
            return (0, False)
        
        prefix_key = compute_prefix_key(
            model_id=self.config.model_id,
            tokenizer_id=self.config.model_id,
            kv_layout_version=self.config.kv_layout_version,
            cache_dtype="float16",
            block_size=16,
            prompt_token_ids=prompt_tokens,
            matched_prefix_len=len(prompt_tokens)
        )
        
        manifest = self._query_manifest(prefix_key, request_id)
        
        if manifest is None:
            logger.info(f"Request {request_id}: manifest miss for prefix_key {prefix_key[:16]}...")
            self.metrics.record_manifest_query(hit=False)
            return (0, False)
        
        self.metrics.record_manifest_query(hit=True)
        
        plan = self.planner.plan(manifest, request_id, self.config.enable_refinement)
        
        if plan.mode == PLAN_MODE_RECOMPUTE:
            logger.info(f"Request {request_id}: planner decided to recompute")
            self.metrics.record_recompute()
            return (0, False)
        
        matched_tokens = plan.matched_tokens - num_computed_tokens
        
        logger.info(f"Request {request_id}: matched {matched_tokens} tokens, plan {plan.mode}")
        
        return (max(0, matched_tokens), False)
    
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
