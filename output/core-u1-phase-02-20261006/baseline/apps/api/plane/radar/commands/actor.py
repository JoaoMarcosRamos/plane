from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

ActorType = Literal["human", "agent", "system", "integration"]


@dataclass(frozen=True, kw_only=True)
class Actor:
    actor_type: ActorType
    actor_id: UUID
    reason: str
    source: str
    correlation_id: UUID
    run_id: UUID | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    approval_id: UUID | None = None
    confidence: float | None = None
    on_behalf_of: UUID | None = None
    metadata: dict = field(default_factory=dict)
