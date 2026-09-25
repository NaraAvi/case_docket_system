"""Audit engine service layer."""

from __future__ import annotations

from datetime import datetime, timezone


class AuditTrailService:
    """Boundary for operational tracing and accountability events."""

    def __init__(self, repository=None):
        self.repository = repository
        self._entries = []
        self._event_counter = 0

    def _next_event_id(self):
        self._event_counter += 1
        return f"AUDIT-{self._event_counter:06d}"

    def log(self, entry):
        payload = {
            "event_id": entry.get("event_id"),
            "timestamp": entry.get("timestamp"),
            "actor_id": entry.get("actor_id"),
            "actor_role": entry.get("actor_role"),
            "action": entry.get("action"),
            "case_reference": entry.get("case_reference"),
            "object_type": entry.get("object_type"),
            "object_id": entry.get("object_id"),
            "previous_state": entry.get("previous_state"),
            "new_state": entry.get("new_state"),
            "reason": entry.get("reason"),
            "authorization_context": entry.get("authorization_context"),
            "rule_code": entry.get("rule_code"),
            "legal_reference": entry.get("legal_reference"),
            "metadata": entry.get("metadata", {}),
            "details": entry.get("details", {}),
        }

        if self.repository is not None:
            return self.repository.create(payload)

        payload["event_id"] = payload["event_id"] or self._next_event_id()
        payload["timestamp"] = payload["timestamp"] or datetime.now(timezone.utc).isoformat()
        self._entries.append(payload)
        return payload

    def update_event(self, event_id, updates):
        raise ValueError("Audit event history is immutable and append-only.")

    def list_entries(self):
        if self.repository is not None:
            return self.repository.list()
        return [dict(entry) for entry in self._entries]

    def get_events_by_actor(self, actor_id):
        if self.repository is not None:
            return self.repository.list_for_actor(actor_id)
        return [
            dict(entry)
            for entry in self._entries
            if str(entry.get("actor_id")) == str(actor_id)
        ]

    def get_for_case(self, case_reference):
        if self.repository is not None:
            return self.repository.list_for_case(case_reference)
        return [
            dict(entry)
            for entry in self._entries
            if entry.get("case_reference") == case_reference
        ]
