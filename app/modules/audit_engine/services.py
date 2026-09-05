"""Audit engine service layer."""

from __future__ import annotations

from datetime import datetime, timezone


class AuditTrailService:
    """Boundary for operational tracing and accountability events."""

    _shared_entries = []
    _event_counter = 0

    def __init__(self):
        self._entries = self.__class__._shared_entries

    @classmethod
    def _next_event_id(cls):
        cls._event_counter += 1
        return f"AUDIT-{cls._event_counter:06d}"

    def log(self, entry):
        event = {
            "event_id": entry.get("event_id") or self._next_event_id(),
            "timestamp": entry.get("timestamp") or datetime.now(timezone.utc).isoformat(),
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
        self._entries.append(event)
        return event

    def update_event(self, event_id, updates):
        raise ValueError("Audit event history is immutable and append-only.")

    def list_entries(self):
        return [dict(entry) for entry in self._entries]

    def get_events_by_actor(self, actor_id):
        return [
            dict(entry)
            for entry in self._entries
            if str(entry.get("actor_id")) == str(actor_id)
        ]

    def get_for_case(self, case_reference):
        return [
            dict(entry)
            for entry in self._entries
            if entry.get("case_reference") == case_reference
        ]
