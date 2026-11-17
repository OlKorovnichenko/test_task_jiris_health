from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class OutboxClaim:
    event_id: UUID
    token: UUID
    payload: dict[str, Any]
