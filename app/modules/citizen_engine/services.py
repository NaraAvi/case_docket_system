"""Citizen engine service layer.

This boundary focuses on the authentication and profile workflow for citizen
actors. Docket submission and investigation functionality remain intentionally
deferred to later packs.
"""

from __future__ import annotations

import hashlib

from app.auth.service import TestIdentityRegistry
from app.database.repositories.assertion_repository import AssertionRepository, ClaimRepository
from app.database.repositories.submission_repository import SubmissionEventRepository, SubmissionRepository
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


class CitizenSubmissionService:
    """Protected submission foundation for citizen-originated reporting."""

    VALID_PROVENANCE = {"CITIZEN_ASSERTED"}
    VALID_ASSESSMENT = {"CITIZEN_ASSERTED", "CORROBORATED", "CONTRADICTED", "UNSUPPORTED", "SYSTEM_OBSERVED", "EVIDENCE_DERIVED", "AUTHORITY_DETERMINED"}

    def __init__(self, repository=None, event_repository=None, audit_service=None, app=None, assertion_repository=None, claim_repository=None,
                 evidence_repository=None, correction_repository=None, withdrawal_repository=None):
        self.app = app
        self.repository = repository or SubmissionRepository(app=app)
        self.event_repository = event_repository or SubmissionEventRepository(app=app)
        self.assertion_repository = assertion_repository or AssertionRepository(app=app)
        self.claim_repository = claim_repository or ClaimRepository(app=app)
        self.evidence_repository = evidence_repository
        self.correction_repository = correction_repository
        self.withdrawal_repository = withdrawal_repository
        self.audit_service = audit_service

    @staticmethod
    def _utc_timestamp():
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat()

    @staticmethod
    def _clean_text(value, field_name):
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{field_name} is required.")
        return text

    @staticmethod
    def _validate_payload(payload):
        if not isinstance(payload, dict):
            raise ValueError("Submission payload must be a JSON object.")

        title = CitizenSubmissionService._clean_text(payload.get("title"), "Title")
        description = CitizenSubmissionService._clean_text(payload.get("description"), "Description")
        if len(title) < 3:
            raise ValueError("Title must be at least 3 characters long.")
        if len(description) < 10:
            raise ValueError("Description must be at least 10 characters long.")

        clean = {
            "title": title,
            "description": description,
            "incident_date": payload.get("incident_date"),
            "location": payload.get("location"),
        }
        if clean["incident_date"] is not None:
            clean["incident_date"] = str(clean["incident_date"]).strip() or None
        if clean["location"] is not None:
            clean["location"] = str(clean["location"]).strip() or None
        return clean

    @staticmethod
    def _build_original_content(payload):
        if not isinstance(payload, dict):
            return {}

        excluded = {
            "title",
            "description",
            "incident_date",
            "location",
            "citizen_id",
            "status",
            "provenance",
            "receipt_timestamp",
            "event_history",
            "submission_id",
            "created_at",
            "updated_at",
            "id",
        }

        original_content = {}
        for key, value in payload.items():
            if key in excluded or value is None:
                continue
            if isinstance(value, (str, int, float, bool, list, dict)):
                original_content[key] = value
            elif value is not None:
                original_content[key] = str(value)
        return original_content

    def _serialize_submission(self, submission):
        if submission is None:
            return None
        data = dict(submission)
        data.pop("id", None)
        if "original_content" not in data or not isinstance(data.get("original_content"), dict):
            data["original_content"] = {}
        if "provenance" not in data or not isinstance(data.get("provenance"), dict):
            data["provenance"] = {}
        if "event_history" not in data or not isinstance(data.get("event_history"), list):
            data["event_history"] = []
        return data

    def _next_submission_id(self):
        all_items = self.repository.list_all()
        last_number = max((int(item.get("submission_id", "").split("-")[-1]) for item in all_items if str(item.get("submission_id", "")).startswith("SUB-")), default=0)
        return f"SUB-{last_number + 1:06d}"

    def create_submission(self, citizen_id, payload):
        if not citizen_id:
            raise ValueError("Citizen identity is required.")

        sanitized = self._validate_payload(payload)
        supplied_citizen_id = payload.get("citizen_id") if isinstance(payload, dict) else None
        if supplied_citizen_id not in (None, "", citizen_id):
            sanitized.pop("citizen_id", None)

        created_at = self._utc_timestamp()
        submission_id = self._next_submission_id()
        original_content = self._build_original_content(payload)
        original_content.update({
            "title": sanitized["title"],
            "description": sanitized["description"],
            "incident_date": sanitized.get("incident_date"),
            "location": sanitized.get("location"),
        })
        provenance = {
            "actor_id": citizen_id,
            "actor_role": "citizen",
            "source": "citizen_submission",
            "created_via": "api",
            "receipt_timestamp": created_at,
        }
        event_history = [{
            "event_type": "submission_created",
            "timestamp": created_at,
            "actor_id": citizen_id,
            "actor_role": "citizen",
            "details": {"submission_id": submission_id, "status": "RECEIVED"},
        }]
        record = {
            "submission_id": submission_id,
            "citizen_id": citizen_id,
            "title": sanitized["title"],
            "description": sanitized["description"],
            "incident_date": sanitized.get("incident_date"),
            "location": sanitized.get("location"),
            "status": "RECEIVED",
            "original_content": original_content,
            "provenance": provenance,
            "receipt_timestamp": created_at,
            "event_history": event_history,
        }
        persisted = self.repository.create(record)
        self.event_repository.create(
            {
                "event_id": f"SUB-EVT-{submission_id}-0001",
                "submission_id": submission_id,
                "event_type": "submission_created",
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "timestamp": created_at,
                "details": {"status": "RECEIVED", "receipt_timestamp": created_at},
            }
        )
        if self.audit_service is not None:
            self.audit_service.log(
                {
                    "actor_id": citizen_id,
                    "actor_role": "citizen",
                    "action": "submission_created",
                    "object_type": "submission",
                    "object_id": submission_id,
                    "details": {"status": "RECEIVED", "receipt_timestamp": created_at},
                }
            )
        return self._serialize_submission(persisted)

    def _get_submission_record(self, citizen_id, submission_id):
        owned = self.repository.get_for_citizen(citizen_id, submission_id)
        if owned is not None:
            return owned

        cross_owner = self.repository.get_by_id(submission_id)
        if cross_owner is not None and str(cross_owner.get("citizen_id")) != str(citizen_id):
            raise ValueError("Forbidden: citizen cannot access another citizen's submission.")
        return None

    def list_submissions(self, citizen_id):
        items = self.repository.list_for_citizen(citizen_id)
        return [self._serialize_submission(item) for item in items]

    def get_submission(self, citizen_id, submission_id):
        try:
            return self._serialize_submission(self._get_submission_record(citizen_id, submission_id))
        except ValueError:
            raise

    def list_history(self, citizen_id, submission_id):
        submission = self.get_submission(citizen_id, submission_id)
        if submission is None:
            raise ValueError("Submission not found.")
        history = self.event_repository.list_for_submission(submission_id)
        if history:
            return history
        return list(submission.get("event_history", []))

    def update_submission(self, citizen_id, submission_id, payload):
        submission = self.get_submission(citizen_id, submission_id)
        if submission is None:
            raise ValueError("Submission not found.")
        raise ValueError("Submission content is immutable. Create a new submission for corrections.")

    @staticmethod
    def _reject_client_controlled_provenance(payload, subject_name):
        if isinstance(payload, dict):
            if "verified" in payload:
                raise ValueError(f"Client-supplied verified status is not allowed for {subject_name}.")
            if "status" in payload and str(payload.get("status")).upper() in {"VERIFIED", "SYSTEM_OBSERVED"}:
                raise ValueError(f"Client-supplied verification status is not allowed for {subject_name}.")
            if "provenance" in payload:
                raise ValueError(f"Client-supplied provenance is not allowed for {subject_name}. The backend assigns provenance.")

    def _next_assertion_id(self):
        all_items = self.assertion_repository.list_all()
        last_number = max((int(item.get("assertion_id", "").split("-")[-1]) for item in all_items if str(item.get("assertion_id", "")).startswith("AST-")), default=0)
        return f"AST-{last_number + 1:06d}"

    def _next_claim_id(self):
        all_items = self.claim_repository.list_all()
        last_number = max((int(item.get("claim_id", "").split("-")[-1]) for item in all_items if str(item.get("claim_id", "")).startswith("CLM-")), default=0)
        return f"CLM-{last_number + 1:06d}"

    def create_assertion(self, citizen_id, submission_id, payload):
        if not citizen_id:
            raise ValueError("Citizen identity is required.")
        submission = self._get_submission_record(citizen_id, submission_id)
        if submission is None:
            raise ValueError("Submission not found.")

        if not isinstance(payload, dict):
            raise ValueError("Assertion payload must be a JSON object.")
        self._reject_client_controlled_provenance(payload, "assertion")

        assertion_text = str(payload.get("assertion_text", "")).strip()
        if not assertion_text:
            raise ValueError("Assertion text is required.")

        created_at = self._utc_timestamp()
        assertion_id = self._next_assertion_id()
        record = {
            "assertion_id": assertion_id,
            "submission_id": submission_id,
            "citizen_id": citizen_id,
            "source_actor_id": citizen_id,
            "source_actor_role": "citizen",
            "provenance": "CITIZEN_ASSERTED",
            "assertion_text": assertion_text,
            "created_at": created_at,
            "source": "citizen_submission",
            "version": 1,
            "assertion_metadata": {"source_submission_id": submission_id},
        }
        persisted = self.assertion_repository.create(record)

        event_details = {
            "assertion_id": assertion_id,
            "provenance": "CITIZEN_ASSERTED",
            "source_submission_id": submission_id,
        }
        self.event_repository.create(
            {
                "event_id": f"SUB-EVT-{submission_id}-{len(self.event_repository.list_for_submission(submission_id)) + 1:04d}",
                "submission_id": submission_id,
                "event_type": "assertion_created",
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "timestamp": created_at,
                "details": event_details,
            }
        )
        if self.audit_service is not None:
            self.audit_service.log(
                {
                    "actor_id": citizen_id,
                    "actor_role": "citizen",
                    "action": "assertion_created",
                    "object_type": "assertion",
                    "object_id": assertion_id,
                    "details": event_details,
                }
            )
        return persisted

    def list_assertions(self, citizen_id, submission_id):
        submission = self._get_submission_record(citizen_id, submission_id)
        if submission is None:
            raise ValueError("Submission not found.")
        return self.assertion_repository.list_for_submission(submission_id)

    def get_assertion(self, citizen_id, submission_id, assertion_id):
        submission = self._get_submission_record(citizen_id, submission_id)
        if submission is None:
            raise ValueError("Submission not found.")
        assertion = self.assertion_repository.get_for_submission(citizen_id, submission_id, assertion_id)
        if assertion is None:
            raise ValueError("Assertion not found.")
        return assertion

    def create_claim(self, citizen_id, submission_id, assertion_id, payload=None):
        if not citizen_id:
            raise ValueError("Citizen identity is required.")
        submission = self._get_submission_record(citizen_id, submission_id)
        if submission is None:
            raise ValueError("Submission not found.")

        payload = payload or {}
        self._reject_client_controlled_provenance(payload, "claim")
        assertion = self.assertion_repository.get_for_submission(citizen_id, submission_id, assertion_id)
        if assertion is None:
            raise ValueError("Assertion not found.")

        created_at = self._utc_timestamp()
        text = assertion.get("assertion_text", "")
        claim_type = "asserted_fact"
        subject = None
        predicate = None
        object_value = None

        if "Officer" in text and "at" in text:
            subject = "officer"
            predicate = "present_at_location"
            object_value = text.split("Officer", 1)[1].split("at", 1)[0].strip()
        elif "Officer" in text:
            subject = "officer"
            predicate = "alleged_actor"
            object_value = text.split("Officer", 1)[1].strip().split(".", 1)[0].strip()
        elif "vehicle" in text.lower():
            subject = "vehicle"
            predicate = "mentioned"
            object_value = text

        if subject is None:
            subject = "report"
            predicate = "asserted"
            object_value = text

        claim_id = self._next_claim_id()
        record = {
            "claim_id": claim_id,
            "assertion_id": assertion_id,
            "submission_id": submission_id,
            "citizen_id": citizen_id,
            "source_actor_id": citizen_id,
            "source_actor_role": "citizen",
            "provenance": "CITIZEN_ASSERTED",
            "claim_type": claim_type,
            "subject": subject,
            "predicate": predicate,
            "object_value": object_value,
            "created_at": created_at,
            "source": "assertion_extraction",
            "relation_type": None,
            "source_assertion_ids": [assertion_id],
            "assessment_state": "CITIZEN_ASSERTED",
            "claim_metadata": {"source_assertion_id": assertion_id, "derived_from": "assertion_text"},
        }
        persisted = self.claim_repository.create(record)

        if self.audit_service is not None:
            self.audit_service.log(
                {
                    "actor_id": citizen_id,
                    "actor_role": "citizen",
                    "action": "claim_created",
                    "object_type": "claim",
                    "object_id": claim_id,
                    "details": {"assertion_id": assertion_id, "provenance": "CITIZEN_ASSERTED"},
                }
            )
        return [persisted]

    def create_evidence(self, citizen_id, submission_id, payload):
        if not citizen_id:
            raise ValueError("Citizen identity is required.")
        self._get_submission_record(citizen_id, submission_id)
        if not isinstance(payload, dict):
            raise ValueError("Evidence payload must be a JSON object.")

        if "source_actor_id" in payload and str(payload.get("source_actor_id") or "").strip() and str(payload.get("source_actor_id")).strip() != str(citizen_id):
            raise ValueError("Evidence source actor is server-controlled and cannot be overridden.")
        if "sha256_hash" in payload and payload.get("sha256_hash") is not None and str(payload.get("sha256_hash", "")).strip() and len(str(payload.get("sha256_hash")).strip()) != 64:
            raise ValueError("Evidence hash must be a valid SHA-256 digest generated by the server.")
        self._reject_client_controlled_provenance(payload, "evidence")

        evidence_type = str(payload.get("evidence_type") or "").strip()
        description = str(payload.get("description") or "").strip()
        if not evidence_type:
            raise ValueError("Evidence type is required.")
        if not description:
            raise ValueError("Evidence description is required.")

        storage_reference = str(payload.get("storage_reference") or "").strip()
        if not storage_reference:
            raise ValueError("Storage reference is required.")
        filename = str(payload.get("filename") or "").strip() or storage_reference.rsplit("/", 1)[-1]
        content_type = str(payload.get("content_type") or "application/octet-stream").strip() or "application/octet-stream"
        created_at = self._utc_timestamp()
        sha256_hash = str(payload.get("sha256_hash") or "").strip()
        if not sha256_hash:
            import hashlib
            sha256_hash = hashlib.sha256(f"{submission_id}:{storage_reference}:{description}".encode("utf-8")).hexdigest()

        evidence_id = f"EVD-{submission_id}-{len(self.evidence_repository.list_for_submission(submission_id)) + 1:04d}"
        record = {
            "evidence_id": evidence_id,
            "submission_id": submission_id,
            "citizen_id": citizen_id,
            "source_actor_id": citizen_id,
            "source_actor_role": "citizen",
            "evidence_type": evidence_type,
            "description": description,
            "filename": filename,
            "content_type": content_type,
            "storage_reference": storage_reference,
            "sha256_hash": sha256_hash,
            "integrity_status": "VERIFIED",
            "source": "citizen_submission",
            "original_reference": storage_reference,
            "created_at": created_at,
            "version": 1,
            "handling_history": [{"event_type": "submitted", "timestamp": created_at, "actor_id": citizen_id, "actor_role": "citizen"}],
            "metadata": {"source_submission_id": submission_id, "server_controlled": True},
        }
        persisted = self.evidence_repository.create(record)

        self.event_repository.create(
            {
                "event_id": f"SUB-EVT-{submission_id}-{len(self.event_repository.list_for_submission(submission_id)) + 1:04d}",
                "submission_id": submission_id,
                "event_type": "evidence_added",
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "timestamp": created_at,
                "details": {"evidence_id": evidence_id, "sha256_hash": sha256_hash, "integrity_status": "VERIFIED"},
            }
        )
        if self.audit_service is not None:
            self.audit_service.log({
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "action": "evidence_added",
                "object_type": "submission_evidence",
                "object_id": evidence_id,
                "details": {"submission_id": submission_id, "integrity_status": "VERIFIED"},
            })
        return persisted

    def list_evidence(self, citizen_id, submission_id):
        self._get_submission_record(citizen_id, submission_id)
        if self.evidence_repository is None:
            return []
        return self.evidence_repository.list_for_submission(submission_id)

    def create_correction(self, citizen_id, submission_id, payload):
        if not citizen_id:
            raise ValueError("Citizen identity is required.")
        self._get_submission_record(citizen_id, submission_id)
        if not isinstance(payload, dict):
            raise ValueError("Correction payload must be a JSON object.")
        assertion_id = str(payload.get("assertion_id") or "").strip()
        if not assertion_id:
            raise ValueError("Assertion id is required.")
        assertion = self.assertion_repository.get_for_submission(citizen_id, submission_id, assertion_id)
        if assertion is None:
            raise ValueError("Assertion not found.")
        assertion_text = str(payload.get("assertion_text") or "").strip()
        if not assertion_text:
            raise ValueError("Corrected assertion text is required.")

        created_at = self._utc_timestamp()
        corrected_assertion_id = f"AST-{submission_id}-{len(self.assertion_repository.list_for_submission(submission_id)) + 1:04d}"
        corrected_assertion = {
            "assertion_id": corrected_assertion_id,
            "submission_id": submission_id,
            "citizen_id": citizen_id,
            "source_actor_id": citizen_id,
            "source_actor_role": "citizen",
            "provenance": "CITIZEN_ASSERTED",
            "assertion_text": assertion_text,
            "created_at": created_at,
            "source": "citizen_submission",
            "version": 2,
            "assertion_metadata": {"correction_of": assertion_id, "source_submission_id": submission_id, "append_only": True},
        }
        self.assertion_repository.create(corrected_assertion)

        correction_id = f"COR-{submission_id}-{len(self.correction_repository.list_for_submission(submission_id)) + 1:04d}"
        record = {
            "correction_id": correction_id,
            "submission_id": submission_id,
            "citizen_id": citizen_id,
            "original_assertion_id": assertion_id,
            "corrected_assertion_id": corrected_assertion_id,
            "relationship_type": "correction_for",
            "reason": str(payload.get("reason") or "Correction requested by citizen.")[:2000],
            "created_at": created_at,
            "metadata": {"source_submission_id": submission_id, "append_only": True},
        }
        persisted = self.correction_repository.create(record)
        self.event_repository.create(
            {
                "event_id": f"SUB-EVT-{submission_id}-{len(self.event_repository.list_for_submission(submission_id)) + 1:04d}",
                "submission_id": submission_id,
                "event_type": "correction_logged",
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "timestamp": created_at,
                "details": {"assertion_id": assertion_id, "correction_id": correction_id, "corrected_assertion_id": corrected_assertion_id},
            }
        )
        return persisted

    def create_withdrawal(self, citizen_id, submission_id, payload):
        if not citizen_id:
            raise ValueError("Citizen identity is required.")
        self._get_submission_record(citizen_id, submission_id)
        if not isinstance(payload, dict):
            raise ValueError("Withdrawal payload must be a JSON object.")
        reason = str(payload.get("reason") or "").strip()
        if not reason:
            raise ValueError("Withdrawal reason is required.")

        created_at = self._utc_timestamp()
        withdrawal_id = f"WDR-{submission_id}-{len(self.withdrawal_repository.list_for_submission(submission_id)) + 1:04d}"
        record = {
            "withdrawal_id": withdrawal_id,
            "submission_id": submission_id,
            "citizen_id": citizen_id,
            "reason": reason,
            "status": "REQUESTED",
            "control_evaluation_id": None,
            "created_at": created_at,
            "metadata": {"source_submission_id": submission_id, "append_only": True},
        }
        persisted = self.withdrawal_repository.create(record)
        self.event_repository.create(
            {
                "event_id": f"SUB-EVT-{submission_id}-{len(self.event_repository.list_for_submission(submission_id)) + 1:04d}",
                "submission_id": submission_id,
                "event_type": "withdrawal_requested",
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "timestamp": created_at,
                "details": {"withdrawal_id": withdrawal_id, "reason": reason},
            }
        )
        return persisted


class CitizenDocketService:
    """Boundary for citizen-facing submission and status flows."""

    def __init__(self, docket_manager=None, audit_service=None, escalation_service=None, freeze_service=None, app=None):
        self.app = app
        self._submissions = []
        self.docket_manager = docket_manager or DocketManagementService(app=app)
        self.audit_service = audit_service or AuditTrailService()
        self.escalation_service = escalation_service or EscalationService(audit_service=self.audit_service, app=app)
        self.freeze_service = freeze_service
        # M4.3: wired after construction; screens newly logged allegations for
        # IPID Act s28(1) matters and enforces the mandatory referral.
        self.referral_service = None

    @staticmethod
    def _utc_timestamp():
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat()

    def _get_case(self, citizen_id, case_reference):
        case = self.get_docket(citizen_id, case_reference)
        if case is None:
            raise ValueError("Docket not found.")
        return case

    def _statement_snapshot(self, case_data):
        return [
            {
                "statement_id": item.get("statement_id"),
                "citizen_id": item.get("citizen_id"),
                "statement_text": item.get("statement_text"),
                "created_at": item.get("created_at"),
            }
            for item in case_data.get("statements", [])
        ]

    def _assert_draft(self, case_data):
        if case_data.get("status") != "DRAFT":
            raise ValueError("This docket is no longer editable by the citizen.")

    def _assert_statement_history_locked(self, case_data):
        """PROTOTYPE_CODIFICATION: lock the historical submitted statement set
        until a later statement-versioning system is added; direct replacement is
        rejected to prevent silent overwrites during or after interview flow."""
        if case_data.get("submitted_statement_snapshot") is not None:
            current = self._statement_snapshot(case_data)
            if current != case_data.get("submitted_statement_snapshot"):
                raise ValueError("Submitted statement history is locked and cannot be silently replaced.")

    def _assert_evidence_editable(self, case_data):
        if case_data.get("status") not in {"DRAFT", "AWAITING_CONSTABLE_REGISTRATION", "REGISTERED"}:
            raise ValueError("This docket is no longer editable by the citizen.")

    @staticmethod
    def _reject_client_controlled_statement_fields(payload):
        if not isinstance(payload, dict):
            return
        forbidden = {
            "statement_id",
            "case_reference",
            "citizen_id",
            "recorded_by",
            "recorded_by_role",
            "created_at",
            "updated_at",
            "provenance",
            "content_hash",
            "sha256_hash",
            "integrity_status",
        }
        if forbidden.intersection(payload):
            raise ValueError("Statement provenance and identity are server-controlled and cannot be overridden.")

    @staticmethod
    def _reject_client_controlled_evidence_fields(payload):
        if not isinstance(payload, dict):
            return
        forbidden = {
            "evidence_id",
            "case_reference",
            "submitted_by",
            "submitted_by_role",
            "created_at",
            "updated_at",
            "provenance",
            "content_hash",
            "integrity_status",
            "chain_of_custody_reference",
        }
        if forbidden.intersection(payload):
            raise ValueError("Evidence case binding, submitter, and provenance are server-controlled and cannot be overridden.")
        candidate_hash = payload.get("sha256_hash")
        if candidate_hash is not None:
            candidate_hash = str(candidate_hash).strip()
            if candidate_hash and len(candidate_hash) != 64:
                raise ValueError("Evidence hash must be a valid SHA-256 digest generated by the server.")

    @staticmethod
    def _statement_provenance(actor_id, actor_role, created_at):
        return {
            "actor_id": str(actor_id),
            "actor_role": actor_role,
            "source": "case_statement",
            "created_at": created_at,
            "statement_version": 1,
        }

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
        raise ValueError("Citizen docket creation is retired. Use the protected submission workflow instead.")

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
        self._assert_statement_history_locked(case)
        self._reject_client_controlled_statement_fields(payload)

        statement_text = payload.get("statement_text") if isinstance(payload, dict) else None
        if statement_text is None or str(statement_text).strip() == "":
            raise ValueError("Statement text is required.")

        statement_text = str(statement_text).strip()
        created_at = self._utc_timestamp()
        statement = {
            "statement_id": len(case.get("statements", [])) + 1,
            "case_reference": case_reference,
            "citizen_id": citizen_id,
            "statement_text": statement_text,
            "created_at": created_at,
            "content_hash": hashlib.sha256(statement_text.encode("utf-8")).hexdigest(),
            "provenance": self._statement_provenance(citizen_id, "citizen", created_at),
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
        self._assert_statement_history_locked(case)

        if payload is not None:
            self._reject_client_controlled_statement_fields(payload)

        raise ValueError("Statement content is immutable and append-only. Create a new statement instead.")

    def list_evidence(self, citizen_id, case_reference):
        case = self._get_case(citizen_id, case_reference)
        return [dict(item) for item in case.get("evidence", [])]

    def add_evidence(self, citizen_id, case_reference, payload):
        case = self._get_case(citizen_id, case_reference)
        self._assert_evidence_editable(case)

        if not isinstance(payload, dict):
            raise ValueError("Evidence payload must be a JSON object.")

        payload_case_reference = payload.get("case_reference")
        if payload_case_reference is not None and str(payload_case_reference).strip() and str(payload_case_reference).strip() != str(case_reference):
            raise ValueError("Evidence case binding is server-controlled and cannot be overridden.")
        if payload.get("submitted_by") is not None and str(payload.get("submitted_by")).strip() and str(payload.get("submitted_by")).strip() != str(citizen_id):
            raise ValueError("Evidence submitter is server-controlled and cannot be overridden.")
        self._reject_client_controlled_evidence_fields(payload)

        evidence_type = (payload.get("evidence_type") or "").strip()
        description = (payload.get("description") or "").strip()
        filename = (payload.get("filename") or "").strip()

        if not evidence_type or not description or not filename:
            raise ValueError("Evidence type, description, and filename are required.")

        candidate_hash = str(payload.get("sha256_hash") or "").strip() if payload.get("sha256_hash") is not None else ""
        content_hash = candidate_hash if candidate_hash else None
        if payload.get("content_hash") is not None:
            declared_hash = str(payload.get("content_hash")).strip()
            if declared_hash and content_hash and declared_hash != content_hash:
                raise ValueError("Evidence content hash is server-controlled and cannot be tampered with.")
            content_hash = content_hash or declared_hash or None
        if content_hash and len(content_hash) != 64:
            raise ValueError("Evidence hash must be a valid SHA-256 digest generated by the server.")

        created_at = self._utc_timestamp()
        evidence = {
            "evidence_id": len(case.get("evidence", [])) + 1,
            "case_reference": case_reference,
            "submitted_by": citizen_id,
            "submitted_by_role": "citizen",
            "evidence_type": evidence_type,
            "description": description,
            "filename": filename,
            "storage_reference": payload.get("storage_reference"),
            "content_type": payload.get("content_type"),
            "size_bytes": payload.get("size_bytes"),
            "sha256_hash": content_hash,
            "content_hash": content_hash,
            "integrity_status": "VERIFIED" if content_hash else "UNHASHED",
            "provenance": {
                "actor_id": str(citizen_id),
                "actor_role": "citizen",
                "source": "citizen_evidence",
                "created_at": created_at,
                "server_controlled": True,
            },
            "created_at": created_at,
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

        # M4.3: screened only *after* the docket write above, so the referral's
        # own timeline entry is not overwritten by this method's stale copy.
        if self.referral_service is not None:
            referral = self.referral_service.screen_citizen_escalation(case_reference, escalation, citizen_id)
            if referral.get("referred"):
                escalation = dict(referral["escalation"])
                escalation["statutory_referral"] = True
        return escalation

    def list_escalations(self, citizen_id, case_reference):
        case = self._get_case(citizen_id, case_reference)
        escalations = self.escalation_service.list_for_case(case_reference)
        enriched = []
        for item in escalations:
            # A citizen sees the escalations they filed and any statutory
            # referral the system raised on their own docket (M4.3).
            is_own = str(item.get("created_by")) == str(citizen_id)
            is_statutory_on_own_docket = item.get("source") == EscalationService.SOURCE_STATUTORY
            if not (is_own or is_statutory_on_own_docket):
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
                    "source": item.get("source") or EscalationService.SOURCE_MANUAL,
                    "statutory_basis": item.get("statutory_basis"),
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
        case["submitted_statement_snapshot"] = self._statement_snapshot(case)
        case["statement_lock_status"] = "LOCKED"
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

        # M4.3: the whole docket text is screened once, at submission.
        referral = None
        if self.referral_service is not None:
            referral = self.referral_service.screen_docket_submission(case_reference, citizen_id)

        docket = self.get_docket(citizen_id, case_reference)
        if referral and referral.get("referred") and docket is not None:
            docket = dict(docket)
            docket["statutory_referral"] = {
                "escalation_id": referral["escalation"].get("escalation_id"),
                "freeze_id": referral["freeze"].get("freeze_id"),
                "statutory_basis": referral["triage"]["statutory_basis"],
            }
        return docket

    def submit_docket_payload(self, payload):
        self._submissions.append(payload)
        return payload
