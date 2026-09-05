"""Domain model for disciplinary case records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, Optional


@dataclass
class DisciplinaryCase:
    """Disciplinary case domain object."""

    disciplinary_case_id: Optional[str] = None
    source_case_reference: Optional[str] = None
    escalation_id: Optional[str] = None
    implicated_officer_id: Optional[str] = None
    created_by: Optional[str] = None
    created_by_role: Optional[str] = None
    status: str = "OPEN"
    reason: Optional[str] = None
    category: Optional[str] = None
    created_at: Optional[str] = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: Optional[str] = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "disciplinary_case_id": self.disciplinary_case_id,
            "source_case_reference": self.source_case_reference,
            "escalation_id": self.escalation_id,
            "implicated_officer_id": self.implicated_officer_id,
            "created_by": self.created_by,
            "created_by_role": self.created_by_role,
            "status": self.status,
            "reason": self.reason,
            "category": self.category,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
