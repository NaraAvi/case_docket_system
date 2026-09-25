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
from app.services.case_service import new_evidence_id
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

    def _assert_not_frozen(self, case_reference):
        if self.freeze_service and self.freeze_service.is_case_frozen(case_reference):
            raise ValueError("Case is frozen and operational mutation is restricted.")

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

    def _decorate_freeze_status(self, case):
        if case is None or self.freeze_service is None:
            return case
        decorated = dict(case)
        frozen = self.freeze_service.is_case_frozen(case.get("case_reference"))
        decorated["is_frozen"] = frozen
        decorated["freeze_status"] = "FROZEN" if frozen else "NOT_FROZEN"
        return decorated

    def list_dockets(self, citizen_id):
        return [self._decorate_freeze_status(item) for item in self.docket_manager.list_dockets_for_citizen(citizen_id)]

    def get_docket(self, citizen_id, case_reference):
        return self._decorate_freeze_status(self.docket_manager.get_docket_for_citizen(citizen_id, case_reference))

    def list_statements(self, citizen_id, case_reference):
        case = self._get_case(citizen_id, case_reference)
        return [dict(item) for item in case.get("statements", [])]

    def add_statement(self, citizen_id, case_reference, payload):
        case = self._get_case(citizen_id, case_reference)
        self._assert_not_frozen(case_reference)
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
        self._assert_not_frozen(case_reference)
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

    @staticmethod
    def _validate_evidence_fields(evidence_type, description, filename):
        evidence_type = str(evidence_type or "").strip()
        description = str(description or "").strip()
        filename = str(filename or "").strip()
        if not evidence_type or not description or not filename:
            raise ValueError("Evidence type, description, and filename are required.")
        return evidence_type, description, filename

    def validate_evidence_submission(self, citizen_id, case_reference, payload):
        """Validate ownership/editability before an upload is streamed."""
        case = self._get_case(citizen_id, case_reference)
        self._assert_not_frozen(case_reference)
        self._assert_evidence_editable(case)
        if not isinstance(payload, dict):
            raise ValueError("Evidence payload must be a JSON object.")
        self._validate_evidence_fields(
            payload.get("evidence_type"),
            payload.get("description"),
            payload.get("filename"),
        )
        return case

    def add_evidence(self, citizen_id, case_reference, payload, trusted_media=False):
        case = self.validate_evidence_submission(citizen_id, case_reference, payload)
        evidence_type, description, filename = self._validate_evidence_fields(
            payload.get("evidence_type"),
            payload.get("description"),
            payload.get("filename"),
        )
        media = payload if trusted_media else {}

        evidence = {
            "evidence_id": new_evidence_id(),
            "case_reference": case_reference,
            "submitted_by": citizen_id,
            "evidence_type": evidence_type,
            "description": description,
            "filename": filename,
            "storage_managed": bool(trusted_media),
            "storage_reference": media.get("storage_reference"),
            "content_type": media.get("content_type"),
            "size_bytes": media.get("size_bytes"),
            "sha256_hash": media.get("sha256_hash"),
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

    def remove_evidence(self, citizen_id, case_reference, evidence_id):
        """Remove one citizen-owned evidence record from an editable docket.

        Evidence is embedded in the docket JSON document, so removal is an
        update to that document rather than a separate repository delete.  A
        timeline and audit event preserve the fact that the item existed.
        """
        case = self._get_case(citizen_id, case_reference)
        self._assert_not_frozen(case_reference)
        self._assert_evidence_editable(case)

        evidence_records = case.get("evidence", [])
        target_index = None
        for index, record in enumerate(evidence_records):
            if str(record.get("evidence_id")) == str(evidence_id):
                target_index = index
                break

        if target_index is None:
            raise ValueError("Evidence not found.")

        target = evidence_records[target_index]
        submitted_by = target.get("submitted_by")
        if str(submitted_by or "") != str(citizen_id):
            # Do not reveal whether another actor's evidence id exists.
            raise ValueError("Evidence not found.")

        removed = evidence_records.pop(target_index)
        self._append_timeline_event(
            case,
            "evidence_removed",
            {"evidence_id": removed.get("evidence_id"), "filename": removed.get("filename")},
        )
        self.docket_manager.update_docket(case)
        self.audit_service.log(
            {
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "action": "evidence_removed",
                "case_reference": case_reference,
                "details": {
                    "evidence_id": removed.get("evidence_id"),
                    "filename": removed.get("filename"),
                },
            }
        )
        return dict(removed)

    def list_timeline(self, citizen_id, case_reference):
        case = self._get_case(citizen_id, case_reference)
        return [dict(item) for item in case.get("timeline", [])]

    def create_escalation(self, citizen_id, case_reference, payload):
        case = self._get_case(citizen_id, case_reference)
        self._assert_not_frozen(case_reference)
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
        self._assert_not_frozen(case_reference)
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
