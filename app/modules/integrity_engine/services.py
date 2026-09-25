"""Actor integrity, evidence integrity, and sanction tracking for anti-corruption controls."""

from __future__ import annotations

from datetime import datetime, timezone


class IntegrityService:
    """Tracks actor integrity states without creating a criminal record against a person."""

    def __init__(self, audit_service=None, evidence_service=None):
        self.audit_service = audit_service
        self.evidence_service = evidence_service
        self._integrity_events = []
        self._evidence_index = {}

    @staticmethod
    def _utc_now():
        return datetime.now(timezone.utc).isoformat()

    def _next_event_id(self):
        return f"INT-{len(self._integrity_events) + 1:06d}"

    def record_allegation(self, actor_id, actor_role, case_reference, details=None):
        event = {
            "integrity_event_id": self._next_event_id(),
            "actor_id": actor_id,
            "actor_role": actor_role,
            "case_reference": case_reference,
            "integrity_status": "ALLEGATION",
            "timestamp": self._utc_now(),
            "details": details or {},
        }
        self._integrity_events.append(event)
        if self.audit_service is not None:
            self.audit_service.log(
                {
                    "actor_id": actor_id,
                    "actor_role": actor_role,
                    "action": "integrity_allegation_logged",
                    "case_reference": case_reference,
                    "object_type": "actor_integrity",
                    "object_id": event["integrity_event_id"],
                    "reason": "Initial integrity allegation",
                    "metadata": {"integrity_status": "ALLEGATION"},
                }
            )
        return dict(event)

    def record_review(self, actor_id, actor_role, subject_event_id, decision, details=None):
        event = {
            "integrity_event_id": self._next_event_id(),
            "subject_event_id": subject_event_id,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "integrity_status": "REVIEW",
            "timestamp": self._utc_now(),
            "decision": decision,
            "details": details or {},
        }
        self._integrity_events.append(event)
        if self.audit_service is not None:
            self.audit_service.log(
                {
                    "actor_id": actor_id,
                    "actor_role": actor_role,
                    "action": "integrity_review_recorded",
                    "object_type": "actor_integrity",
                    "object_id": event["integrity_event_id"],
                    "reason": decision,
                    "metadata": {"subject_event_id": subject_event_id, "integrity_status": "REVIEW"},
                }
            )
        return dict(event)

    def confirm_finding(self, actor_id, actor_role, subject_event_id, findings=None):
        event = {
            "integrity_event_id": self._next_event_id(),
            "subject_event_id": subject_event_id,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "integrity_status": "CONFIRMED_FINDING",
            "timestamp": self._utc_now(),
            "findings": findings or {},
        }
        self._integrity_events.append(event)
        if self.audit_service is not None:
            self.audit_service.log(
                {
                    "actor_id": actor_id,
                    "actor_role": actor_role,
                    "action": "integrity_finding_confirmed",
                    "object_type": "actor_integrity",
                    "object_id": event["integrity_event_id"],
                    "reason": "Confirmed finding",
                    "metadata": {"subject_event_id": subject_event_id, "integrity_status": "CONFIRMED_FINDING"},
                }
            )
        return dict(event)

    def apply_disciplinary_action(self, actor_id, actor_role, subject_event_id, action_type, details=None):
        event = {
            "integrity_event_id": self._next_event_id(),
            "subject_event_id": subject_event_id,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "integrity_status": "DISCIPLINARY_ACTION",
            "timestamp": self._utc_now(),
            "action_type": action_type,
            "details": details or {},
        }
        self._integrity_events.append(event)
        if self.audit_service is not None:
            self.audit_service.log(
                {
                    "actor_id": actor_id,
                    "actor_role": actor_role,
                    "action": "integrity_disciplinary_action",
                    "object_type": "actor_integrity",
                    "object_id": event["integrity_event_id"],
                    "reason": action_type,
                    "metadata": {"subject_event_id": subject_event_id, "integrity_status": "DISCIPLINARY_ACTION"},
                }
            )
        return dict(event)

    def register_evidence(self, evidence):
        if not isinstance(evidence, dict):
            raise ValueError("Evidence object must be a dictionary.")
        evidence_id = evidence.get("evidence_id") or f"EVIDENCE-{len(self._evidence_index) + 1:06d}"
        record = {
            "evidence_id": evidence_id,
            "case_reference": evidence.get("case_reference"),
            "uploaded_by": evidence.get("uploaded_by"),
            "uploaded_at": evidence.get("uploaded_at") or self._utc_now(),
            "storage_reference": evidence.get("storage_reference"),
            "content_hash": evidence.get("content_hash"),
            "integrity_status": "VERIFIED",
            "chain_of_custody_reference": evidence.get("chain_of_custody_reference") or f"COC-{evidence_id}",
            "created_at": evidence.get("created_at") or self._utc_now(),
            "updated_at": evidence.get("updated_at") or self._utc_now(),
        }
        self._evidence_index[evidence_id] = record
        if self.evidence_service is not None:
            self.evidence_service.add_evidence(record)
        return dict(record)

    def verify_evidence_integrity(self, evidence):
        original = self._evidence_index.get(evidence.get("evidence_id"))
        if original is None:
            return {"evidence_id": evidence.get("evidence_id"), "integrity_status": "INTEGRITY_FAILURE", "reason": "Evidence record not found."}
        if evidence.get("content_hash") != original.get("content_hash"):
            return {
                "evidence_id": evidence.get("evidence_id"),
                "integrity_status": "INTEGRITY_FAILURE",
                "reason": "Evidence hash mismatch detected.",
                "original_hash": original.get("content_hash"),
                "current_hash": evidence.get("content_hash"),
            }
        return {
            "evidence_id": evidence.get("evidence_id"),
            "integrity_status": "VERIFIED",
            "reason": "Evidence hash matches the original signed record.",
            "original_hash": original.get("content_hash"),
            "current_hash": evidence.get("content_hash"),
        }
