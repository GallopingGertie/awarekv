from typing import Dict, Any


class PlannerPolicies:
    @staticmethod
    def rule_based_config() -> Dict[str, Any]:
        return {
            "policy_type": "rule_based",
            "alpha": 0.8,
            "min_prefix_tokens": 128,
            "refine_slack_ratio": 0.3
        }
