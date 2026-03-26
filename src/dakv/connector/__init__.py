from dataclasses import dataclass
from typing import Optional
from dakv.common.types import TransferPlan


@dataclass
class ConnectorMetadata:
    request_id: str
    prefix_key: Optional[str] = None
    matched_tokens: int = 0
    plan: Optional[TransferPlan] = None
    need_remote_load: bool = False
    need_refinement: bool = False
