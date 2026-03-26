from typing import List
from dakv.constants import TIER_T0_GPU, TIER_T1_HOST, TIER_T2_REMOTE


class PlacementPolicy:
    @staticmethod
    def should_cache_to_t1(object_size: int, available_space: int) -> bool:
        return object_size < available_space
    
    @staticmethod
    def select_tier(
        have_t1_cache: bool,
        t1_hit: bool,
        t2_available: bool
    ) -> str:
        if have_t1_cache and t1_hit:
            return TIER_T1_HOST
        
        if t2_available:
            return TIER_T2_REMOTE
        
        return TIER_T2_REMOTE
