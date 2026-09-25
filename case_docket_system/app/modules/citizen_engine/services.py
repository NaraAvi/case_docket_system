"""Citizen engine service layer.

This boundary focuses on the authentication and profile workflow for citizen
actors. Docket submission and investigation functionality remain intentionally
deferred to later packs.
"""

from __future__ import annotations

from app.auth.service import TestIdentityRegistry
from app.modules.audit_engine.services import AuditTrailService
from app.modules.case_engine.services import DocketManagementService
from app.modules.escalation_engine.services import EscalationService
from app.validation.validators import CitizenDocketValidator


class CitizenAuthenticationService:
    """Authenticates a citizen using the prototype identity registry."""

    def __init__(self, identity_provider=None):
        self.identity_provider = identity_provider or TestIdentityRegistry()

    @staticmethod
    def validate_test_id(test_id):
        if test_id is None:
            return False

        value = str(test_id).strip()
        if not value.isdigit() or len(value) != 13:
            return False

        return True

    def authenticate(self, supplied_test_id):
        value = str(supplied_test_id).strip() if supplied_test_id is not None else ""
        if not self.validate_test_id(value):
            return None

        identity = self.identity_provider.verify_identity(value)
        if not identity or not identity.get("active"):
            return None

        return {
            "test_id": identity["test_id"],
            "full_name": identity["full_name"],
            "role": identity["role"],
            "active": identity["active"],
        }

    def get_profile(self, test_id):
        identity = self.identity_provider.get_identity(str(test_id))
        if not identity or not identity.get("active"):
            return None

        return {
            "test_id": identity["test_id"],
            "full_name": identity["full_name"],
            "role": identity["role"],
            "active": identity["active"],
        }


class CitizenDocketService:
    """Boundary for citizen-facing submission and status flows."""

    def __init__(self, docket_manager=None, audit_service=None, escalation_service=None, freeze_service=None):
        self._submissions = []
        self.docket_manager = docket_manager or DocketManagementService()
        self.audit_service = audit_service or AuditTrailService()
        self.escalation_service = escalation_service or EscalationService(audit_service=self.audit_service)
        self.freeze_service = freeze_service

    @staticmethod
    def _utc_timestamp():
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat()

    def _get_case(self, citizen_id, case_reference):
        case = self.get_docket(citizen_id, case_reference)
        if case is None:
            raise ValueError("Docket not found.")
        return case

    def _assert_draft(self, case_data):
        if case_data.get("status") != "DRAFT":
            raise ValueError("This docket is no longer editable by the citizen.")

    def _assert_evidence_editable(self, case_data):
        if case_data.get("status") not in {"DRAFT", "AWAITING_CONSTABLE_REGISTRATION", "REGISTERED"}:
            raise ValueError("This docket is no longer editable by the citizen.")

    def _append_timeline_event(self, case_data, event_type, details=None):
        timeline = case_data.setdefault("timeline", [])
        event = {
            "event_type": event_type,
            "actor_id": case_data.get("citizen_id"),
            "actor_role": "citizen",
            "timestamp": self._utc_timestamp(),
            "details": details or {},
        }
        timeline.append(event)
        return event

    def create_docket(self, citizen_id, payload):
        validated_payload = CitizenDocketValidator.validate(payload)
        docket = self.docket_manager.create_docket(citizen_id, validated_payload)
        self.audit_service.log(
            {
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "action": "case_created",
                "case_reference": docket.get("case_reference"),
                "details": {
                    "title": docket.get("title"),
                    "status": docket.get("status"),
                },
            }
        )
        return docket

    def list_dockets(self, citizen_id):
        return self.docket_manager.list_dockets_for_citizen(citizen_id)

    def get_docket(self, citizen_id, case_reference):
        return self.docket_manager.get_docket_for_citizen(citizen_id, case_reference)

    def get_docket_with_freeze_status(self, citizen_id, case_reference):
        """Read-only enrichment for the citizen docket-detail endpoint --
        a citizen can't mutate a frozen docket anyway (post-registration
        edits are already blocked by `_assert_draft`/`_assert_evidence_editable`),
        but they should still be able to see that IPID has taken custody of
        it. Deliberately separate from `get_docket`/`_get_case`, which every
        mutation method reuses, so this display-only field never has to flow
        through a write path."""
        docket = self.get_docket(citizen_id, case_reference)
        if docket is None or self.freeze_service is None:
            return docket
        docket = dict(docket)
        freeze = self.freeze_service.get_current_freeze(case_reference)
        docket["is_frozen"] = freeze is not None
        docket["freeze_status"] = "FROZEN" if freeze else "NOT_FROZEN"
        docket["freeze_reason"] = freeze.get("reason") if freeze else None
        return docket

    def list_statements(self, citizen_id, case_reference):
        case = self._get_case(citizen_id, case_reference)
        return [dict(item) for item in case.get("statements", [])]

    def add_statement(self, citizen_id, case_reference, payload):
        case = self._get_case(citizen_id, case_reference)
        self._assert_draft(case)

        statement_text = payload.get("statement_text") if isinstance(payload, dict) else None
        if statement_text is None or str(statement_text).strip() == "":
            raise ValueError("Statement text is required.")

        statement = {
            "statement_id": len(case.get("statements", [])) + 1,
            "case_reference": case_reference,
            "citizen_id": citizen_id,
            "statement_text": str(statement_text).strip(),
            "created_at": self._utc_timestamp(),
        }
        case.setdefault("statements", []).append(statement)
        self._append_timeline_event(case, "statement_added", {"statement_id": statement["statement_id"]})
        self.docket_manager.update_docket(case)
        self.audit_service.log(
            {
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "action": "statement_added",
                "case_reference": case_reference,
                "details": {"statement_id": statement["statement_id"]},
            }
        )
        return statement

    def update_statement(self, citizen_id, case_reference, statement_id, payload):
        case = self._get_case(citizen_id, case_reference)
        self._assert_draft(case)

        statements = case.get("statements", [])
        if not statements:
            raise ValueError("No statement found to update.")

        target = None
        if statement_id is None:
            target = statements[-1]
        else:
            for statement in statements:
                if str(statement.get("statement_id")) == str(statement_id):
                    target = statement
                    break

        if target is None or target.get("citizen_id") != citizen_id:
            raise ValueError("Statement not found.")

        new_text = payload.get("statement_text") if isinstance(payload, dict) else None
        if new_text is None or str(new_text).strip() == "":
            raise ValueError("Statement text is required.")

        target["statement_text"] = str(new_text).strip()
        target["updated_at"] = self._utc_timestamp()
        self._append_timeline_event(case, "statement_updated", {"statement_id": target["statement_id"]})
        self.docket_manager.update_docket(case)
        self.audit_service.log(
            {
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "action": "statement_updated",
                "case_reference": case_reference,
                "details": {"statement_id": target["statement_id"]},
            }
        )
        return target

    def list_evidence(self, citizen_id, case_reference):
        case = self._get_case(citizen_id, case_reference)
        return [dict(item) for item in case.get("evidence", [])]

    def add_evidence(self, citizen_id, case_reference, payload):
        case = self._get_case(citizen_id, case_reference)
        self._assert_evidence_editable(case)

        if not isinstance(payload, dict):
            raise ValueError("Evidence payload must be a JSON object.")

        evidence_type = (payload.get("evidence_type") or "").strip()
        description = (payload.get("description") or "").strip()
        filename = (payload.get("filename") or "").strip()

        if not evidence_type or not description or not filename:
            raise ValueError("Evidence type, description, and filename are required.")

        evidence = {
            "evidence_id": len(case.get("evidence", [])) + 1,
            "case_reference": case_reference,
            "submitted_by": citizen_id,
            "evidence_type": evidence_type,
            "description": description,
            "filename": filename,
            "storage_reference": payload.get("storage_reference"),
            "content_type": payload.get("content_type"),
            "size_bytes": payload.get("size_bytes"),
            "sha256_hash": payload.get("sha256_hash"),
            "created_at": self._utc_timestamp(),
        }
        case.setdefault("evidence", []).append(evidence)
        self._append_timeline_event(case, "evidence_added", {"evidence_id": evidence["evidence_id"]})
        self.docket_manager.update_docket(case)
        self.audit_service.log(
            {
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "action": "evidence_added",
                "case_reference": case_reference,
                "details": {"evidence_id": evidence["evidence_id"], "filename": filename},
            }
        )
        return evidence

    def list_timeline(self, citizen_id, case_reference):
        case = self._get_case(citizen_id, case_reference)
        return [dict(item) for item in case.get("timeline", [])]

    def create_escalation(self, citizen_id, case_reference, payload):
        case = self._get_case(citizen_id, case_reference)
        if not isinstance(payload, dict):
            raise ValueError("Escalation payload must be a JSON object.")
        if any(key in payload for key in {"created_by", "created_by_role", "status", "reviewer_id", "reviewer_role"}):
            raise ValueError("Escalation identity and status are server-controlled.")

        category = str(payload.get("category") or "").strip()
        description = str(payload.get("description") or "").strip()
        if not category:
            raise ValueError("Escalation category is required.")
        if len(description) < 10:
            raise ValueError("Escalation description is too short.")

        escalation = self.escalation_service.create_escalation(
            case_reference,
            citizen_id,
            "citizen",
            category,
            description,
        )
        self._append_timeline_event(case, "citizen_escalation_submitted", {"escalation_id": escalation["escalation_id"], "category": category})
        self.docket_manager.update_docket(case)
        return escalation

    def list_escalations(self, citizen_id, case_reference):
        case = self._get_case(citizen_id, case_reference)
        escalations = self.escalation_service.list_for_case(case_reference)
        enriched = []
        for item in escalations:
            if str(item.get("created_by")) != str(citizen_id):
                continue
            enriched.append(
                {
                    "escalation_id": item.get("escalation_id"),
                    "case_reference": item.get("case_reference"),
                    "category": item.get("category"),
                    "description": item.get("description"),
                    "status": item.get("status"),
                    "decision": item.get("decision"),
                    "decision_reason": item.get("decision_reason"),
                    "decision_at": item.get("decision_at"),
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                }
            )
        return enriched

    def submit_docket(self, citizen_id, case_reference):
        case = self._get_case(citizen_id, case_reference)
        self._assert_draft(case)

        if not case.get("statements"):
            raise ValueError("A docket requires at least one statement before submission.")

        case["status"] = "AWAITING_CONSTABLE_REGISTRATION"
        case["submitted_at"] = self._utc_timestamp()
        self._append_timeline_event(case, "docket_submitted", {"status": case["status"]})
        self.docket_manager.update_docket(case)
        self.audit_service.log(
            {
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "action": "docket_submitted",
                "case_reference": case_reference,
                "details": {"status": case["status"]},
            }
        )
        return self.get_docket(citizen_id, case_reference)

    def submit_docket_payload(self, payload):
        self._submissions.append(payload)
        return payload
