"""Timeline domain models."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class TimelineEventStatus(str, Enum):
    """Allowed timeline status values."""

    COMPLETED = "completed"
    ACTIVE = "active"
    PENDING = "pending"


class TimelineEventType(str, Enum):
    """Event categories used by the UI."""

    CONSULTATION = "consultation"
    DOCUMENT = "document"
    ELIGIBILITY = "eligibility"
    LENDER_OUTREACH = "lender-outreach"
    BANK_OFFER = "bank-offer"
    NEGOTIATION = "negotiation"
    APPROVAL = "approval"
    UPDATE = "update"


class TimelineStage(str, Enum):
    """Primary stages of the mortgage workflow."""

    CONSULTATION = "consultation"
    DOCUMENTS = "documents"
    ELIGIBILITY = "eligibility"
    OFFERS = "offers"
    NEGOTIATION = "negotiation"
    APPROVAL = "approval"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TimelineDetail:
    label: str
    value: str

    def to_dict(self) -> Dict[str, str]:
        return {"label": self.label, "value": self.value}


@dataclass
class TimelineEvent:
    id: str
    type: TimelineEventType
    title: str
    stage: TimelineStage
    status: TimelineEventStatus = TimelineEventStatus.PENDING
    description: Optional[str] = None
    bank_name: Optional[str] = None
    timestamp: datetime = field(default_factory=_utcnow)
    details: List[TimelineDetail] = field(default_factory=list)

    def to_frontend_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["type"] = self.type.value
        data["stage"] = self.stage.value
        data["status"] = self.status.value
        data["timestamp"] = self.timestamp.isoformat()
        data["details"] = [detail.to_dict() for detail in self.details]
        if self.bank_name:
            data["bankName"] = self.bank_name
        return data


@dataclass
class TimelineState:
    events: List[TimelineEvent] = field(default_factory=list)
    current_stage: Optional[TimelineStage] = None
    version: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "events": [event.to_frontend_dict() for event in self.events],
            "current_stage": self.current_stage.value if self.current_stage else None,
            "version": self.version,
        }

    def _touch(self) -> None:
        self.version += 1

    def clear(self) -> None:
        self.events.clear()
        self.current_stage = None
        self.version = 0

    def upsert_event(self, event: TimelineEvent) -> TimelineEvent:
        index = next(
            (i for i, existing in enumerate(self.events) if existing.id == event.id),
            None,
        )

        if event.status == TimelineEventStatus.ACTIVE:
            for existing in self.events:
                if existing.status == TimelineEventStatus.ACTIVE:
                    existing.status = TimelineEventStatus.COMPLETED
            self.current_stage = event.stage

        if index is not None:
            self.events[index] = event
        else:
            self.events.append(event)

        self._touch()
        return event


__all__ = [
    "TimelineDetail",
    "TimelineEvent",
    "TimelineEventStatus",
    "TimelineEventType",
    "TimelineStage",
    "TimelineState",
]
