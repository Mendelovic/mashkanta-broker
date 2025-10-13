"""Intake storage primitives built around validated interview records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from ..domain.schemas import IntakeSubmission, InterviewRecord


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class IntakeRevision:
    """A single confirmed intake snapshot."""

    version: int
    record: InterviewRecord
    confirmed_at: datetime
    confirmation_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "confirmed_at": self.confirmed_at.isoformat(),
            "record": self.record.model_dump(),
            "confirmation_notes": list(self.confirmation_notes),
        }


@dataclass
class IntakeStore:
    """Maintains the versioned history of intake submissions for a session."""

    _revisions: List[IntakeRevision] = field(default_factory=list)

    def clear(self) -> None:
        self._revisions.clear()

    def is_empty(self) -> bool:
        return not self._revisions

    def current(self) -> Optional[IntakeRevision]:
        if not self._revisions:
            return None
        return self._revisions[-1]

    def revisions(self) -> List[IntakeRevision]:
        return list(self._revisions)

    def submit(self, submission: IntakeSubmission) -> IntakeRevision:
        version = self._revisions[-1].version + 1 if self._revisions else 1
        record = submission.record.model_copy(deep=True)
        notes = list(submission.confirmation_notes or [])
        revision = IntakeRevision(
            version=version,
            record=record,
            confirmed_at=_utcnow(),
            confirmation_notes=notes,
        )
        self._revisions.append(revision)
        return revision

    def append_note(self, note: str) -> Optional[IntakeRevision]:
        if not self._revisions:
            return None
        trimmed = note.strip()
        if not trimmed:
            return self._revisions[-1]
        latest = self._revisions[-1]
        updated_notes = list(latest.confirmation_notes)
        updated_notes.append(trimmed)
        revised = IntakeRevision(
            version=latest.version,
            record=latest.record,
            confirmed_at=latest.confirmed_at,
            confirmation_notes=updated_notes,
        )
        self._revisions[-1] = revised
        return revised

    def extend_notes(self, notes: Iterable[str]) -> Optional[IntakeRevision]:
        if not self._revisions:
            return None
        filtered = [
            note.strip() for note in notes if isinstance(note, str) and note.strip()
        ]
        if not filtered:
            return self._revisions[-1]
        latest = self._revisions[-1]
        updated_notes = list(latest.confirmation_notes)
        updated_notes.extend(filtered)
        revised = IntakeRevision(
            version=latest.version,
            record=latest.record,
            confirmed_at=latest.confirmed_at,
            confirmation_notes=updated_notes,
        )
        self._revisions[-1] = revised
        return revised

    def to_dict(self) -> dict:
        current_revision = self.current()
        return {
            "current": current_revision.to_dict() if current_revision else None,
            "history": [rev.to_dict() for rev in self._revisions],
        }


__all__ = ["IntakeRevision", "IntakeStore"]
