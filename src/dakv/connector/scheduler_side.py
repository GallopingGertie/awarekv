import requests
from typing import Optional, Dict
from dakv.common.types import PrefixManifest, TransferPlan, RequestTransferState, DeadlineConnectorMetadata
from dakv.planner.deadline_planner import DeadlinePlanner
from dakv.connector.vllm_adapter import extract_request_id, extract_prompt_tokens, extract_num_computed_tokens
from dakv.connector.state import StateManager
from dakv.connector.metadata import build_metadata_from_state
from dakv.common.hashing import compute_prefix_key
from dakv.common.time_utils import current_time_ms
from dakv.logging import get_logger
from dakv.metrics import get_metrics_collector
from dakv.constants import (
    PLAN_MODE_RECOMPUTE,
    REQUEST_STATUS_INIT,
    REQUEST_STATUS_MISS,
    REQUEST_STATUS_HIT_PLANNED,
    REQUEST_STATUS_RECOMPUTE
)


logger = get_logger()


class SchedulerSide:
    """
    Scheduler-side logic for DeadlinePrefixKVConnector
    
    Responsibilities:
    - Manifest query to determine prefix availability
    - Transfer plan generation (when to load, from which tier)
    - Metadata building for worker-side operations
    - Request state tracking throughout lifecycle
    """
    
    def __init__(self, config, planner: DeadlinePlanner, manifest_url: str, state_manager: StateManager = None):
        """
        Initialize scheduler-side components
        
        Args:
            config: Connector configuration
            planner: DeadlinePlanner instance for transfer planning
            manifest_url: URL of manifest service
            state_manager: Optional StateManager (if None, creates new one)
        """
        self.config = config
        self.planner = planner
        self.manifest_url = manifest_url
        self.metrics = get_metrics_collector()
        
        # Use provided state manager or create new one
        self.state_manager = state_manager or StateManager()
        
        logger.info(f"SchedulerSide initialized (manifest_url={manifest_url})")
    
    def prepare_request_state(self, request, num_computed_tokens: int) -> Optional[tuple]:
        """
        Prepare request state by querying manifest and creating transfer plan
        
        This is called from connector's get_num_new_matched_tokens() lifecycle method.
        
        Args:
            request: vLLM request object
            num_computed_tokens: Number of tokens already computed
        
        Returns:
            Tuple[int, bool]: (num_matched_tokens, is_external_load)
            - num_matched_tokens: Number of prefix tokens that can be loaded
            - is_external_load: Always False (we use external connector, not built-in)
        """
        request_id = extract_request_id(request)
        prompt_tokens = extract_prompt_tokens(request)
        
        # Validation: no prompt tokens
        if not prompt_tokens:
            logger.debug(f"Request {request_id}: no prompt tokens")
            return (0, False)
        
        # Validation: prompt too short
        if len(prompt_tokens) < self.config.planner.min_prefix_tokens:
            logger.debug(
                f"Request {request_id}: prompt too short "
                f"({len(prompt_tokens)} < {self.config.planner.min_prefix_tokens})"
            )
            return (0, False)
        
        # Check if state already exists (e.g., from previous call)
        state = self.state_manager.get(request_id)
        if state and state.status in [REQUEST_STATUS_HIT_PLANNED, REQUEST_STATUS_RECOMPUTE]:
            # State already prepared, return cached result
            logger.debug(f"Request {request_id}: using cached state (status={state.status})")
            return (state.matched_tokens, False)
        
        # Create new state
        state = self.state_manager.create_or_get(request_id)
        state.start_time_ms = current_time_ms()
        
        # Compute prefix key
        prefix_key = compute_prefix_key(
            model_id=self.config.model_id,
            tokenizer_id=self.config.tokenizer_id,
            kv_layout_version=self.config.kv_layout_version,
            cache_dtype=self.config.cache_dtype,
            block_size=self.config.block_size,
            prompt_token_ids=prompt_tokens,
            matched_prefix_len=len(prompt_tokens)
        )
        
        state.prefix_key = prefix_key
        
        # Query manifest
        manifest = self._query_manifest(prefix_key, request_id)
        
        if manifest is None:
            # Manifest miss - will recompute
            logger.info(f"Request {request_id}: manifest miss for prefix_key {prefix_key[:16]}...")
            self.metrics.record_manifest_query(hit=False)
            
            self.state_manager.mark_manifest_miss(request_id, reason="no_match")
            state.matched_tokens = 0
            
            return (0, False)
        
        # Manifest hit - proceed with planning
        logger.info(
            f"Request {request_id}: manifest hit "
            f"({manifest.matched_tokens} tokens, {len(manifest.matched_blocks)} blocks)"
        )
        self.metrics.record_manifest_query(hit=True)
        
        self.state_manager.mark_manifest_hit(request_id, manifest)
        state.matched_tokens = manifest.matched_tokens
        state.matched_blocks = manifest.matched_blocks
        
        # Generate transfer plan
        plan = self.planner.plan(manifest, request_id, self.config.enable_refinement)
        
        if plan.mode == PLAN_MODE_RECOMPUTE:
            # Planner decided to recompute (e.g., deadline too tight)
            logger.info(
                f"Request {request_id}: planner decided to recompute "
                f"(reason: {plan.reason_code})"
            )
            self.metrics.record_recompute()
            
            self.state_manager.mark_recompute(request_id, reason=plan.reason_code)
            state.matched_tokens = 0
            
            return (0, False)
        
        # Plan accepted - will load external KV
        self.state_manager.set_plan(request_id, plan)
        
        # Calculate matched tokens accounting for already computed tokens
        matched_tokens = plan.matched_tokens - num_computed_tokens
        
        logger.info(
            f"Request {request_id}: matched {matched_tokens} tokens, "
            f"plan {plan.mode}, load_from {plan.load_from_tier}, "
            f"reason {plan.reason_code}"
        )
        
        return (max(0, matched_tokens), False)
    
    def bind_allocated_blocks(self, request_id: str, allocated_blocks: list):
        """
        Bind vLLM-allocated block IDs to request state
        
        This is called from connector's update_state_after_alloc() lifecycle method.
        
        Args:
            request_id: Request ID
            allocated_blocks: List of block IDs allocated by vLLM
        """
        state = self.state_manager.get(request_id)
        if not state:
            logger.warning(f"Request {request_id}: cannot bind blocks, state not found")
            return
        
        self.state_manager.set_allocated_blocks(request_id, allocated_blocks)
        
        logger.debug(f"Request {request_id}: bound {len(allocated_blocks)} allocated blocks")
    
    def build_request_metadata(self, request_id: str) -> Optional[DeadlineConnectorMetadata]:
        """
        Build connector metadata for worker-side operations
        
        This is called from connector's build_connector_meta() lifecycle method.
        
        Args:
            request_id: Request ID
        
        Returns:
            DeadlineConnectorMetadata or None if state not ready
        """
        state = self.state_manager.get(request_id)
        
        if not state:
            logger.debug(f"Request {request_id}: no state found for metadata building")
            return None
        
        if state.status != REQUEST_STATUS_HIT_PLANNED:
            logger.debug(
                f"Request {request_id}: state status {state.status} not ready for metadata"
            )
            return None
        
        if not state.manifest or not state.plan:
            logger.debug(f"Request {request_id}: missing manifest or plan")
            return None
        
        # Use metadata.py helper to build metadata from state
        metadata = build_metadata_from_state(state, state.allocated_block_ids)
        
        if metadata:
            logger.info(
                f"Request {request_id}: metadata built "
                f"(mode={metadata.plan_mode}, tokens={metadata.matched_tokens}, "
                f"need_refinement={metadata.need_refinement})"
            )
        
        return metadata
    
    def get_state(self, request_id: str) -> Optional[RequestTransferState]:
        """
        Get request state
        
        Args:
            request_id: Request ID
        
        Returns:
            RequestTransferState or None
        """
        return self.state_manager.get(request_id)
    
    def remove_state(self, request_id: str):
        """
        Remove request state (cleanup)
        
        Args:
            request_id: Request ID
        """
        self.state_manager.remove(request_id)
        logger.debug(f"Request {request_id}: state removed from scheduler side")
    
    def _query_manifest(self, prefix_key: str, request_id: str) -> Optional[PrefixManifest]:
        """
        Query manifest service for prefix KV availability
        
        Args:
            prefix_key: Prefix key to query
            request_id: Request ID (for logging)
        
        Returns:
            PrefixManifest or None if miss
        """
        try:
            url = f"{self.manifest_url}/manifest/query"
            payload = {
                "prefix_key": prefix_key,
                "request_id": request_id,
                "need_refinement": self.config.enable_refinement
            }
            
            response = requests.post(url, json=payload, timeout=2.0)
            
            if response.status_code != 200:
                logger.warning(
                    f"Request {request_id}: manifest query failed with status {response.status_code}"
                )
                return None
            
            data = response.json()
            
            if not data.get("hit", False):
                return None
            
            manifest_dict = data.get("manifest")
            if not manifest_dict:
                logger.warning(f"Request {request_id}: manifest response has no manifest data")
                return None
            
            manifest = PrefixManifest(**manifest_dict)
            return manifest
        
        except requests.exceptions.Timeout:
            logger.warning(f"Request {request_id}: manifest query timeout")
            return None
        
        except Exception as e:
            logger.warning(f"Request {request_id}: failed to query manifest: {e}")
            return None
