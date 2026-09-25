"""Investigation engine service layer."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from app.database.repositories.flag_repository import FlagRepository
from app.database.repositories.investigation_finding_repository import InvestigationFindingRepository
from app.database.repositories.investigation_note_repository import InvestigationNoteRepository
from app.database.repositories.investigation_repository import InvestigationRepository
from app.database.repositories.related_case_repository import RelatedCaseRepository
from app.modules.audit_engine.services import AuditTrailService
from app.modules.control_gate import InvestigationCompletionGate, InvestigationGate
from app.services.case_service import CaseService


class InvestigationService:
    """Boundary for detective caseload, investigation lifecycle, and operational review."""

    VALID_STATUSES = {"OPEN", "IN_PROGRESS", "COMPLETED"}
    VALID_FINDING_TYPES = {"VALID", "INVALID", "REVIEW_REQUIRED"}
    VALID_INVESTIGATIVE_CONCLUSIONS = {"VALID", "INVALID", "REVIEW_REQUIRED"}
    VALID_OUTCOMES = VALID_INVESTIGATIVE_CONCLUSIONS
    REJECTED_ADJUDICATIVE_VALUES = {"GUILTY", "NOT_GUILTY"}

    def __init__(
        self,
        case_service=None,
        audit_service=None,
        repository=None,
        constable_service=None,
        finding_repository=None,
        note_repository=None,
        flag_repository=None,
        related_case_repository=None,
        freeze_service=None,
        assignment_service=None,
        app=None,
    ):
        self.app = app
        self.case_service = case_service or CaseService(app=app)
        self.audit_service = audit_service or AuditTrailService()
        self.repository = repository or InvestigationRepository(app=app)
        self.constable_service = constable_service
        self.finding_repository = finding_repository or InvestigationFindingRepository(app=app)
        self.note_repository = note_repository or InvestigationNoteRepository(app=app)
        self.flag_repository = flag_repository or FlagRepository(app=app)
        self.related_case_repository = related_case_repository or RelatedCaseRepository(app=app)
        self.freeze_service = freeze_service
        self.assignment_service = assignment_service
        if self.assignment_service is None and app is not None and hasattr(app, "extensions"):
            self.assignment_service = app.extensions.get("assignment_service")
        # M4.4: wired after construction (see ConflictOfInterestService).
        self.conflict_service = None

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _generate_investigation_id(sequence):
        return f"INV-{sequence:06d}"

    @staticmethod
    def _generate_finding_id(sequence):
        return f"FND-{sequence:06d}"

    def _get_case(self, case_reference):
        if not case_reference:
            return None
        for case in self.case_service.get_all_cases():
            if case.get("case_reference") == case_reference:
                return case
        return None

    def _get_investigation_by_case(self, case_reference):
        investigations = self.repository.list_for_case(case_reference)
        for investigation in investigations:
            if investigation.get("status") in {"OPEN", "IN_PROGRESS"}:
                return investigation
        return None

    def _get_latest_investigation_by_case(self, case_reference):
        """Like `_get_investigation_by_case`, but also returns a COMPLETED
        investigation so the detective workspace can still display its
        findings/notes/outcome after completion, instead of the page
        reverting to "no investigation has been started" the moment one is
        completed (the actual completion is unaffected either way -- this is
        display-only; `_get_investigation_by_case` still governs whether a
        new investigation may be opened)."""
        active = self._get_investigation_by_case(case_reference)
        if active is not None:
            return active
        investigations = self.repository.list_for_case(case_reference)
        return investigations[-1] if investigations else None

    def _get_interview_for_case(self, case_reference):
        if self.constable_service is None:
            return None
        case = self._get_case(case_reference)
        if case is None:
            return None
        interview_id = case.get("interview_id")
        if not interview_id:
            return None
        return self.constable_service.get_interview_by_id(interview_id)

    @staticmethod
    def _normalize_string_list(value):
        if value is None:
            return []
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, (list, tuple, set)):
            items = list(value)
        else:
            items = [value]
        normalized = []
        for item in items:
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized

    def _normalize_basis_material(self, basis_items, case, case_evidence_ids, case_statement_ids, valid_claim_ids):
        if basis_items is None:
            return []
        if isinstance(basis_items, dict):
            basis_items = [basis_items]
        if not isinstance(basis_items, list):
            raise ValueError("Finding basis material must be a list of support or contradiction references.")

        normalized = []
        for item in basis_items:
            if not isinstance(item, dict):
                raise ValueError("Each finding basis item must be an object with kind, id, and relationship.")
            kind = str(item.get("kind") or item.get("type") or "").strip().upper()
            relationship = str(item.get("relationship") or item.get("relation") or "").strip().upper()
            if not kind:
                raise ValueError("Each finding basis item requires a kind such as evidence, statement, or claim.")
            if relationship not in {"SUPPORTS", "CONTRADICTS", "CONTEXT"}:
                raise ValueError("Basis relationships must be SUPPORTS, CONTRADICTS, or CONTEXT.")

            item_id = str(item.get("id") or item.get("evidence_id") or item.get("statement_id") or item.get("claim_id") or item.get("reference_id") or "").strip()
            if not item_id:
                raise ValueError("Each finding basis item requires an id reference.")

            if kind in {"EVIDENCE", "EVIDENCE_ID"}:
                if item_id not in case_evidence_ids:
                    raise ValueError("Evidence basis must be linked to evidence on this case.")
                normalized.append({"kind": "evidence", "id": item_id, "relationship": relationship})
                continue
            if kind in {"CLAIM", "CLAIM_ID"}:
                if item_id not in valid_claim_ids:
                    raise ValueError("Claim basis is not valid for this case.")
                normalized.append({"kind": "claim", "id": item_id, "relationship": relationship})
                continue
            if kind in {"STATEMENT", "STATEMENT_ID"}:
                if item_id not in case_statement_ids:
                    raise ValueError("Statement basis must match a statement in this case.")
                normalized.append({"kind": "statement", "id": item_id, "relationship": relationship})
                continue
            if kind in {"INVESTIGATION", "INVESTIGATION_ID"}:
                normalized.append({"kind": "investigation", "id": item_id, "relationship": relationship})
                continue
            raise ValueError("Unsupported basis kind for finding.")
        return normalized

    def _sanitize_statement(self, statement):
        if not isinstance(statement, dict):
            return {}
        statement_content = statement.get("statement_text") or statement.get("statement_content")
        return {
            "statement_id": statement.get("statement_id"),
            "case_reference": statement.get("case_reference"),
            "statement_type": statement.get("statement_type") or "citizen_statement",
            "statement_content": statement_content,
            "created_at": statement.get("created_at"),
            "actor_role": statement.get("actor_role") or "citizen",
        }

    def _sanitize_evidence(self, evidence):
        if not isinstance(evidence, dict):
            return {}
        source = evidence.get("source")
        if not source:
            source = evidence.get("submitted_by") and "citizen" or evidence.get("recorder_role") or "citizen"
        return {
            "evidence_id": evidence.get("evidence_id"),
            "evidence_type": evidence.get("evidence_type"),
            "description": evidence.get("description"),
            "source": source,
            "submission_timestamp": evidence.get("created_at") or evidence.get("submitted_at"),
            "status": evidence.get("status") or "SUBMITTED",
        }

    def _sanitize_flag(self, flag):
        if not isinstance(flag, dict):
            return {}
        return {
            "flag_id": flag.get("flag_id"),
            "category": flag.get("category"),
            "notes": flag.get("notes"),
            "status": flag.get("status"),
            "created_by_role": flag.get("created_by_role") or "constable",
            "created_at": flag.get("created_at"),
            "resolution_information": flag.get("resolution_information"),
        }

    def _sanitize_related_case(self, relationship):
        if not isinstance(relationship, dict):
            return {}
        return {
            "relationship_id": relationship.get("relationship_id"),
            "source_case_reference": relationship.get("source_case_reference"),
            "related_case_reference": relationship.get("related_case_reference"),
            "relationship_type": relationship.get("relationship_type"),
            "created_by_role": relationship.get("created_by_role") or "constable",
            "notes": relationship.get("notes"),
            "created_at": relationship.get("created_at"),
        }

    def _assert_authorized_detective(self, investigation, detective_id):
        if investigation.get("detective_id") != detective_id:
            raise ValueError("Detective is not authorized for this investigation.")

    def _investigation_gate(self):
        return InvestigationGate(
            freeze_service=self.freeze_service,
            conflict_service=self.conflict_service,
            assignment_service=self.assignment_service,
            case_service=self.case_service,
        )

    def _completion_gate(self):
        return InvestigationCompletionGate(
            freeze_service=self.freeze_service,
            conflict_service=self.conflict_service,
            case_service=self.case_service,
        )

    def get_docket_for_detective(self, case_reference):
        case = self._get_case(case_reference)
        if case is None:
            raise ValueError("Docket not found.")
        if case.get("status") != "REGISTERED":
            raise ValueError("Detective access is limited to registered dockets.")
        freeze = self.freeze_service.get_current_freeze(case_reference) if self.freeze_service else None
        if freeze is not None:
            # IPID custody blocks a detective from viewing the case content
            # at all -- not just from mutating it -- while it's frozen. Only
            # enough is returned for the workspace to render the "Case
            # Frozen" notice.
            return self._frozen_notice(case, freeze)
        return {
            "id": case.get("id"),
            "case_reference": case.get("case_reference"),
            "title": case.get("title"),
            "description": case.get("description"),
            "citizen_id": case.get("citizen_id"),
            "status": case.get("status"),
            "incident_date": case.get("incident_date"),
            "location": case.get("location"),
            "statements": case.get("statements", []),
            "evidence": case.get("evidence", []),
            "timeline": case.get("timeline", []),
            "interview_id": case.get("interview_id"),
            "investigation": self._get_latest_investigation_by_case(case_reference),
            "is_frozen": False,
            "freeze_status": "NOT_FROZEN",
            "freeze_reason": None,
        }

    @staticmethod
    def _frozen_notice(case, freeze):
        return {
            "case_reference": case.get("case_reference"),
            "status": case.get("status"),
            "is_frozen": True,
            "freeze_status": "FROZEN",
            "freeze_reason": freeze.get("reason"),
            "frozen_at": freeze.get("frozen_at"),
            "frozen_by": freeze.get("actor_id"),
        }

    def add_statement(self, case_reference, detective_id, payload=None):
        """Let a detective record an additional victim/witness statement on
        the case docket, visible to every role that already reads
        `docket.statements` (citizen, constable, station commander, IPID) --
        distinct from the citizen's own self-authored statement, which stays
        editable only by them while still DRAFT."""
        case = self._get_case(case_reference)
        if case is None:
            raise ValueError("Docket not found.")
        if case.get("status") != "REGISTERED":
            raise ValueError("Detective access is limited to registered dockets.")
        if self.freeze_service and self.freeze_service.is_case_frozen(case_reference):
            raise ValueError("Case is frozen and operational mutation is restricted.")

        if not isinstance(payload, dict):
            raise ValueError("Statement payload must be a JSON object.")
        forbidden = {"statement_id", "case_reference", "citizen_id", "recorded_by", "recorded_by_role", "created_at", "updated_at", "provenance", "content_hash", "sha256_hash"}
        if forbidden.intersection(payload):
            raise ValueError("Statement provenance and identity are server-controlled and cannot be overridden.")

        statement_text = str(payload.get("statement_text") or "").strip()
        if not statement_text:
            raise ValueError("Statement text is required.")

        created_at = self._utc_now()
        statement = {
            "statement_id": len(case.get("statements", [])) + 1,
            "case_reference": case_reference,
            "citizen_id": case.get("citizen_id"),
            "statement_text": statement_text,
            "recorded_by": detective_id,
            "recorded_by_role": "detective",
            "created_at": created_at,
            "content_hash": hashlib.sha256(statement_text.encode("utf-8")).hexdigest(),
            "provenance": {
                "actor_id": str(detective_id),
                "actor_role": "detective",
                "source": "detective_statement",
                "created_at": created_at,
                "statement_version": 1,
            },
        }
        case.setdefault("statements", []).append(statement)
        case.setdefault("timeline", []).append(
            {
                "event_type": "statement_added_by_detective",
                "actor_id": detective_id,
                "actor_role": "detective",
                "timestamp": self._utc_now(),
                "details": {"statement_id": statement["statement_id"]},
            }
        )
        self.case_service.update_case(case)
        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "statement_added_by_detective",
                "case_reference": case_reference,
                "details": {"statement_id": statement["statement_id"]},
            }
        )
        return dict(statement)

    def create_investigation(self, case_reference, detective_id, payload=None):
        case = self._get_case(case_reference)
        if case is None:
            raise ValueError("Docket not found.")

        if self.assignment_service is not None:
            current_assignment = self.assignment_service.get_current_assignment_for_case(case_reference)
            if current_assignment is None or str(current_assignment.get("status") or "").upper() != "ACTIVE":
                raise ValueError("Detective investigation requires an active assignment to this docket.")
            if str(current_assignment.get("officer_role") or "").lower() != "detective":
                raise ValueError("The active assignment for this docket is not held by a detective.")
            if str(current_assignment.get("officer_id") or "") != str(detective_id):
                raise ValueError("Detective is not the assigned officer for this docket.")

        existing = self._get_investigation_by_case(case_reference)
        gate = self._investigation_gate()
        gate_result = gate.check(
            case=case,
            case_reference=case_reference,
            detective_id=detective_id,
            actor_id=detective_id,
            actor_role="detective",
            action="start",
            investigation=existing,
        )
        gate_result.raise_for_block()

        payload = payload or {}
        if not isinstance(payload, dict):
            raise ValueError("Investigation payload must be a JSON object.")

        notes = str(payload.get("notes") or "").strip()
        if not notes:
            raise ValueError("Investigation notes are required.")

        investigation_id = self._generate_investigation_id(len(self.repository.list()) + 1)
        investigation = {
            "id": len(self.repository.list()) + 1,
            "investigation_id": investigation_id,
            "case_reference": case_reference,
            "detective_id": detective_id,
            "status": "OPEN",
            "notes": notes,
            "created_at": self._utc_now(),
            "updated_at": self._utc_now(),
            "timeline": [
                {
                    "event_type": "investigation_opened",
                    "actor_id": detective_id,
                    "actor_role": "detective",
                    "timestamp": self._utc_now(),
                    "details": {"notes": notes},
                }
            ],
        }
        self.repository.create(investigation)
        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "investigation_created",
                "case_reference": case_reference,
                "details": {"investigation_id": investigation_id, "status": "OPEN"},
            }
        )

        case.setdefault("timeline", []).append(
            CaseService._timeline_event(
                "investigation_opened",
                detective_id,
                "detective",
                {"investigation_id": investigation_id},
            )
        )
        self.case_service.update_case(case)

        return dict(investigation)

    def get_investigation(self, investigation_id):
        investigation = self.repository.get_by_investigation_id(investigation_id)
        if investigation is None:
            raise ValueError("Investigation not found.")
        return dict(investigation)

    def update_status(self, investigation_id, detective_id, payload=None):
        investigation = self.repository.get_by_investigation_id(investigation_id)
        if investigation is None:
            raise ValueError("Investigation not found.")
        if investigation.get("detective_id") != detective_id:
            raise ValueError("Detective is not authorized for this investigation.")

        if not isinstance(payload, dict):
            raise ValueError("Status update payload must be a JSON object.")

        next_status = str(payload.get("status") or "").strip().upper()
        if next_status == "COMPLETED":
            raise ValueError("Investigation completion is controlled by the dedicated completion endpoint and cannot be forced via generic status mutation.")
        if next_status not in self.VALID_STATUSES:
            raise ValueError("Status is invalid.")

        current_status = str(investigation.get("status") or "").strip().upper()
        if current_status == "COMPLETED":
            raise ValueError("A completed investigation cannot be reopened.")
        if next_status == current_status:
            return dict(investigation)

        allowed_transitions = {
            "OPEN": {"IN_PROGRESS"},
            "IN_PROGRESS": set(),
        }
        if next_status not in allowed_transitions.get(current_status, set()):
            raise ValueError("Invalid status transition.")

        investigation["status"] = next_status
        investigation["updated_at"] = self._utc_now()
        investigation.setdefault("timeline", []).append(
            {
                "event_type": "investigation_status_updated",
                "actor_id": detective_id,
                "actor_role": "detective",
                "timestamp": self._utc_now(),
                "details": {"status": next_status},
            }
        )
        self.repository.update(investigation["id"], investigation)
        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "investigation_status_updated",
                "case_reference": investigation.get("case_reference"),
                "details": {"investigation_id": investigation_id, "status": next_status},
            }
        )
        return dict(investigation)

    def reassign_active_investigation(self, case_reference, new_detective_id, actor_id, reason=None):
        """Transfer ownership of a case's active investigation (if one exists)
        to a newly assigned detective. Called when a station commander or IPID
        reviewer force-reassigns a case that already has an OPEN/IN_PROGRESS
        investigation, so the new detective isn't denied access to it."""
        investigation = self._get_investigation_by_case(case_reference)
        if investigation is None or investigation.get("detective_id") == new_detective_id:
            return investigation

        previous_detective_id = investigation.get("detective_id")
        investigation["detective_id"] = new_detective_id
        investigation["updated_at"] = self._utc_now()
        investigation.setdefault("timeline", []).append(
            {
                "event_type": "investigation_reassigned",
                "actor_id": actor_id,
                "actor_role": "station_commander",
                "timestamp": self._utc_now(),
                "details": {"previous_detective_id": previous_detective_id, "new_detective_id": new_detective_id, "reason": reason},
            }
        )
        self.repository.update(investigation["id"], investigation)
        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": "station_commander",
                "action": "investigation_reassigned",
                "case_reference": case_reference,
                "details": {
                    "investigation_id": investigation.get("investigation_id"),
                    "previous_detective_id": previous_detective_id,
                    "new_detective_id": new_detective_id,
                    "reason": reason,
                },
            }
        )
        return dict(investigation)

    def update_notes(self, investigation_id, detective_id, payload=None):
        investigation = self.repository.get_by_investigation_id(investigation_id)
        if investigation is None:
            raise ValueError("Investigation not found.")
        if investigation.get("detective_id") != detective_id:
            raise ValueError("Detective is not authorized for this investigation.")
        if investigation.get("status") == "COMPLETED":
            raise ValueError("A completed investigation's notes cannot be edited.")

        if not isinstance(payload, dict):
            raise ValueError("Notes payload must be a JSON object.")

        notes = str(payload.get("notes") or "").strip()
        if not notes:
            raise ValueError("Investigation notes are required.")

        investigation["notes"] = notes
        investigation["updated_at"] = self._utc_now()
        investigation.setdefault("timeline", []).append(
            {
                "event_type": "investigation_notes_updated",
                "actor_id": detective_id,
                "actor_role": "detective",
                "timestamp": self._utc_now(),
                "details": {},
            }
        )
        self.repository.update(investigation["id"], investigation)
        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "investigation_notes_updated",
                "case_reference": investigation.get("case_reference"),
                "details": {"investigation_id": investigation_id},
            }
        )
        return dict(investigation)

    def get_case_view_for_detective(self, investigation_id, detective_id):
        investigation = self.get_investigation(investigation_id)
        self._assert_authorized_detective(investigation, detective_id)

        case = self._get_case(investigation.get("case_reference"))
        if case is None:
            raise ValueError("Docket not found.")

        interview = self._get_interview_for_case(case.get("case_reference"))
        flags = self.flag_repository.list_for_case(case.get("case_reference"))
        related = self.related_case_repository.list_for_case(case.get("case_reference"))

        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "detective_investigation_viewed",
                "case_reference": case.get("case_reference"),
                "details": {"investigation_id": investigation_id},
            }
        )

        return {
            "investigation_id": investigation.get("investigation_id"),
            "case_reference": case.get("case_reference"),
            "case_status": case.get("status"),
            "title": case.get("title"),
            "description": case.get("description"),
            "incident_date": case.get("incident_date"),
            "location": case.get("location"),
            "citizen_submission": {
                "original_statement": (
                    case.get("statements", [{}])[-1].get("statement_text")
                    if case.get("statements")
                    else None
                ),
                "statements": [self._sanitize_statement(item) for item in case.get("statements", [])],
                "evidence": [self._sanitize_evidence(item) for item in case.get("evidence", [])],
            },
            "constable_information": {
                "registration_information": {
                    "status": case.get("status"),
                    "registered_at": case.get("registered_at"),
                },
                "interview_information": interview,
                "citizen_recording_metadata": interview.get("citizen_recording") if interview else None,
                "constable_recording_metadata": interview.get("constable_recording") if interview else None,
                "potential_invalidity_flags": [self._sanitize_flag(item) for item in flags],
            },
            "related_cases": [self._sanitize_related_case(item) for item in related],
            "timeline": case.get("timeline", []),
        }

    def get_case_statements_for_detective(self, investigation_id, detective_id):
        investigation = self.get_investigation(investigation_id)
        self._assert_authorized_detective(investigation, detective_id)

        case = self._get_case(investigation.get("case_reference"))
        if case is None:
            raise ValueError("Docket not found.")

        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "detective_statement_reviewed",
                "case_reference": case.get("case_reference"),
                "details": {"investigation_id": investigation_id},
            }
        )
        return [self._sanitize_statement(item) for item in case.get("statements", [])]

    def get_case_evidence_for_detective(self, investigation_id, detective_id):
        investigation = self.get_investigation(investigation_id)
        self._assert_authorized_detective(investigation, detective_id)

        case = self._get_case(investigation.get("case_reference"))
        if case is None:
            raise ValueError("Docket not found.")

        evidence_items = [self._sanitize_evidence(item) for item in case.get("evidence", [])]
        interview = self._get_interview_for_case(case.get("case_reference"))
        if interview:
            for key in ("citizen_recording", "constable_recording"):
                recording = interview.get(key)
                if recording:
                    evidence_items.append(
                        {
                            "evidence_id": recording.get("recording_id"),
                            "evidence_type": recording.get("recording_type"),
                            "description": f"{key.replace('_', ' ')} recording",
                            "source": recording.get("recorder_role") or key.replace("_recording", ""),
                            "submission_timestamp": recording.get("submitted_at") or recording.get("created_at"),
                            "status": recording.get("status") or "SUBMITTED",
                        }
                    )

        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "detective_evidence_reviewed",
                "case_reference": case.get("case_reference"),
                "details": {"investigation_id": investigation_id},
            }
        )
        return evidence_items

    def get_case_flags_for_detective(self, investigation_id, detective_id):
        investigation = self.get_investigation(investigation_id)
        self._assert_authorized_detective(investigation, detective_id)

        case = self._get_case(investigation.get("case_reference"))
        if case is None:
            raise ValueError("Docket not found.")

        flags = self.flag_repository.list_for_case(case.get("case_reference"))
        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "detective_flag_reviewed",
                "case_reference": case.get("case_reference"),
                "details": {"investigation_id": investigation_id},
            }
        )
        return [self._sanitize_flag(item) for item in flags]

    def get_case_related_for_detective(self, investigation_id, detective_id):
        investigation = self.get_investigation(investigation_id)
        self._assert_authorized_detective(investigation, detective_id)

        case = self._get_case(investigation.get("case_reference"))
        if case is None:
            raise ValueError("Docket not found.")

        relationships = self.related_case_repository.list_for_case(case.get("case_reference"))
        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "detective_related_cases_reviewed",
                "case_reference": case.get("case_reference"),
                "details": {"investigation_id": investigation_id},
            }
        )
        return [self._sanitize_related_case(item) for item in relationships]

    def create_finding(self, investigation_id, detective_id, payload=None):
        investigation = self.get_investigation(investigation_id)
        if not isinstance(payload, dict):
            raise ValueError("Finding payload must be a JSON object.")

        payload = dict(payload)
        forbidden = {
            "finding_id",
            "investigation_id",
            "case_reference",
            "case_id",
            "detective_id",
            "author_id",
            "officer_id",
            "investigator_id",
            "created_at",
            "updated_at",
            "status",
            "version",
            "actor_id",
        }
        for key in forbidden:
            payload.pop(key, None)

        case = self._get_case(investigation.get("case_reference"))
        finding_gate = self._finding_gate()
        gate_result = finding_gate.check(
            case=case,
            investigation=investigation,
            case_reference=investigation.get("case_reference"),
            detective_id=detective_id,
            actor_id=detective_id,
            actor_role="detective",
            payload=payload,
        )
        gate_result.raise_for_block()

        if investigation.get("status") == "COMPLETED":
            raise ValueError("Completed investigations cannot receive new findings.")

        finding_type = str(payload.get("finding_type") or "").strip().upper()
        if finding_type in self.REJECTED_ADJUDICATIVE_VALUES:
            raise ValueError("Criminal guilt or innocence is not a valid finding type. Use VALID, INVALID, or REVIEW_REQUIRED.")
        if finding_type not in self.VALID_FINDING_TYPES:
            raise ValueError("Finding type is invalid. Use VALID, INVALID, or REVIEW_REQUIRED.")

        notes = str(payload.get("notes") or payload.get("finding") or payload.get("finding_text") or "").strip()
        if not notes:
            raise ValueError("Finding notes are required.")

        case_evidence = case.get("evidence", []) if case else []
        case_evidence_ids = {str(item.get("evidence_id")) for item in case_evidence if isinstance(item, dict) and item.get("evidence_id")}
        case_statements = case.get("statements", []) if case else []
        case_statement_ids = {str(item.get("statement_id")) for item in case_statements if isinstance(item, dict) and item.get("statement_id")}
        available_claim_ids = set()
        if self.app is not None and hasattr(self.app, "extensions"):
            claim_repo = self.app.extensions.get("claim_repository")
            if claim_repo is not None:
                for claim in claim_repo.list_all():
                    if claim is None:
                        continue
                    if case and str(claim.get("submission_id") or "") == str(case.get("source_submission_id") or ""):
                        available_claim_ids.add(str(claim.get("claim_id") or ""))
                    elif case and case.get("source_submission_id") is None and str(claim.get("citizen_id") or "") == str(case.get("citizen_id") or ""):
                        available_claim_ids.add(str(claim.get("claim_id") or ""))
        available_claim_ids = {claim_id for claim_id in available_claim_ids if claim_id}

        structured_evidence_ids = self._normalize_string_list(payload.get("evidence_ids"))
        claim_ids = self._normalize_string_list(payload.get("claim_ids"))
        supporting_material = self._normalize_basis_material(
            payload.get("supporting_material"),
            case,
            case_evidence_ids,
            case_statement_ids,
            available_claim_ids,
        )
        contradicting_material = self._normalize_basis_material(
            payload.get("contradicting_material"),
            case,
            case_evidence_ids,
            case_statement_ids,
            available_claim_ids,
        )

        explicit_basis = bool(structured_evidence_ids or claim_ids or supporting_material or contradicting_material)
        case_has_statement_basis = bool(case_statement_ids)
        case_has_evidence_basis = bool(case_evidence_ids)

        if case_has_evidence_basis and not explicit_basis:
            raise ValueError("Evidence linkage is required before a finding can be recorded for this docket.")
        if case_has_evidence_basis and structured_evidence_ids and not set(structured_evidence_ids).issubset(case_evidence_ids):
            raise ValueError("Evidence linkage must reference evidence on the same case.")
        if not case_has_evidence_basis and not explicit_basis and not case_has_statement_basis:
            raise ValueError("Finding requires explicit evidence, claim, or traceable case basis.")
        unknown_claims = [claim_id for claim_id in claim_ids if claim_id not in available_claim_ids]
        if unknown_claims:
            raise ValueError("Claim basis is not valid for this case.")

        reasoning = str(payload.get("reasoning") or payload.get("reasoning_text") or notes or "").strip()
        finding = {
            "finding_id": self._generate_finding_id(len(self.finding_repository.list()) + 1),
            "investigation_id": investigation.get("investigation_id"),
            "case_reference": investigation.get("case_reference"),
            "detective_id": detective_id,
            "finding_type": finding_type,
            "notes": notes,
            "reasoning": reasoning,
            "evidence_ids": structured_evidence_ids,
            "claim_ids": claim_ids,
            "supporting_material": supporting_material,
            "contradicting_material": contradicting_material,
            "status": "SUBMITTED",
            "version": 1,
            "created_at": self._utc_now(),
            "updated_at": self._utc_now(),
            "is_final_outcome": False,
        }
        created = self.finding_repository.create(finding)
        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "detective_finding_created",
                "case_reference": investigation.get("case_reference"),
                "details": {"investigation_id": investigation_id, "finding_type": finding_type, "evidence_ids": structured_evidence_ids, "claim_ids": claim_ids},
            }
        )
        return dict(created)

    def _finding_gate(self):
        from app.modules.control_gate import FindingGate
        return FindingGate(
            freeze_service=self.freeze_service,
            conflict_service=self.conflict_service,
            assignment_service=self.assignment_service,
            case_service=self.case_service,
        )

    def amend_finding(self, investigation_id, detective_id, finding_id, payload=None):
        investigation = self.get_investigation(investigation_id)
        self._assert_authorized_detective(investigation, detective_id)
        if not finding_id:
            raise ValueError("A finding identifier is required.")
        existing = self.finding_repository.get_for_finding_id(finding_id)
        if not existing:
            raise ValueError("Finding not found.")
        raise ValueError("Finding amendments are blocked to preserve the original finding history and version lineage.")

    def list_findings_for_investigation(self, investigation_id, detective_id):
        investigation = self.get_investigation(investigation_id)
        self._assert_authorized_detective(investigation, detective_id)
        return [dict(item) for item in self.finding_repository.list_for_investigation(investigation_id)]

    def add_note(self, investigation_id, detective_id, payload=None):
        investigation = self.get_investigation(investigation_id)
        self._assert_authorized_detective(investigation, detective_id)
        if investigation.get("status") == "COMPLETED":
            raise ValueError("Completed investigations cannot receive new notes.")
        if not isinstance(payload, dict):
            raise ValueError("Note payload must be a JSON object.")

        note_text = str(payload.get("note_text") or payload.get("notes") or "").strip()
        if not note_text:
            raise ValueError("Note text is required.")

        evidence_reference = payload.get("evidence_reference")
        if evidence_reference not in (None, ""):
            evidence_reference = str(evidence_reference)
            case = self._get_case(investigation.get("case_reference"))
            case_evidence = case.get("evidence", []) if case else []
            if not any(str(item.get("evidence_id")) == evidence_reference for item in case_evidence):
                raise ValueError("Evidence reference does not match any evidence item on this case.")
        else:
            evidence_reference = None

        note = {
            "investigation_id": investigation.get("investigation_id"),
            "case_reference": investigation.get("case_reference"),
            "detective_id": detective_id,
            "evidence_reference": evidence_reference,
            "note_text": note_text,
            "created_at": self._utc_now(),
        }
        created = self.note_repository.create(note)
        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "investigation_note_added",
                "case_reference": investigation.get("case_reference"),
                "details": {"investigation_id": investigation_id, "note_id": created.get("note_id"), "evidence_reference": evidence_reference},
            }
        )
        return dict(created)

    def list_notes(self, investigation_id, detective_id):
        investigation = self.get_investigation(investigation_id)
        self._assert_authorized_detective(investigation, detective_id)
        return [dict(item) for item in self.note_repository.list_for_investigation(investigation_id)]

    def complete_investigation(self, investigation_id, detective_id, payload=None):
        investigation = self.get_investigation(investigation_id)
        self._assert_authorized_detective(investigation, detective_id)

        previous_status = str(investigation.get("status") or "").upper()
        if previous_status == "COMPLETED":
            raise ValueError("Investigation is already completed.")
        if not isinstance(payload, dict):
            raise ValueError("Completion payload must be a JSON object.")

        payload = dict(payload)
        for key in {"status", "completed", "completed_at", "investigation_id", "case_reference", "case_id", "detective_id", "actor_id", "officer_id", "investigator_id", "created_at", "updated_at", "previous_state", "new_state"}:
            payload.pop(key, None)

        case = self._get_case(investigation.get("case_reference"))
        if case is None:
            raise ValueError("Docket not found.")

        existing_findings = [dict(item) for item in self.finding_repository.list_for_investigation(investigation_id)]
        payload_with_findings = dict(payload)
        payload_with_findings["findings"] = existing_findings
        completion_gate = self._completion_gate()
        completion_result = completion_gate.check(
            case=case,
            investigation=investigation,
            case_reference=investigation.get("case_reference"),
            detective_id=detective_id,
            actor_id=detective_id,
            actor_role="detective",
            payload=payload_with_findings,
        )
        if not completion_result.allowed:
            self.audit_service.log(
                {
                    "actor_id": detective_id,
                    "actor_role": "detective",
                    "action": "investigation_completion_blocked",
                    "case_reference": investigation.get("case_reference"),
                    "object_type": "investigation",
                    "object_id": investigation_id,
                    "previous_state": previous_status,
                    "new_state": previous_status,
                    "reason": completion_result.message,
                    "rule_code": completion_result.code,
                    "details": {
                        "investigation_id": investigation_id,
                        "requested_outcome": str(payload.get("outcome") or "").strip().upper(),
                        "findings_count": len(existing_findings),
                    },
                }
            )
            raise ValueError(completion_result.message)

        outcome = str(payload.get("outcome") or "").strip().upper()
        if outcome in self.REJECTED_ADJUDICATIVE_VALUES:
            raise ValueError("Criminal guilt or innocence is not a valid investigative conclusion. Use VALID, INVALID, or REVIEW_REQUIRED.")
        if outcome not in self.VALID_OUTCOMES:
            raise ValueError("Outcome is invalid. Use VALID, INVALID, or REVIEW_REQUIRED.")

        final_notes = str(payload.get("final_notes") or payload.get("notes") or "").strip()
        if not final_notes:
            raise ValueError("Final reasoning is required.")

        final_finding = {
            "finding_id": self._generate_finding_id(len(self.finding_repository.list()) + 1),
            "investigation_id": investigation.get("investigation_id"),
            "case_reference": investigation.get("case_reference"),
            "detective_id": detective_id,
            "finding_type": outcome,
            "notes": final_notes,
            "evidence_ids": [
                str(item)
                for finding in existing_findings
                for item in (finding.get("evidence_ids") or [])
            ],
            "created_at": self._utc_now(),
            "updated_at": self._utc_now(),
            "is_final_outcome": True,
        }
        created_final_finding = self.finding_repository.create(final_finding)

        investigation["status"] = "COMPLETED"
        investigation["outcome"] = outcome
        investigation["final_notes"] = final_notes
        investigation["completed_at"] = self._utc_now()
        investigation["updated_at"] = investigation["completed_at"]
        self.repository.update(investigation["id"], investigation)
        try:
            self.audit_service.log(
                {
                    "actor_id": detective_id,
                    "actor_role": "detective",
                    "action": "detective_investigation_completed",
                    "case_reference": investigation.get("case_reference"),
                    "object_type": "investigation",
                    "object_id": investigation_id,
                    "previous_state": previous_status,
                    "new_state": "COMPLETED",
                    "reason": final_notes,
                    "rule_code": completion_result.code,
                    "details": {
                        "investigation_id": investigation_id,
                        "outcome": outcome,
                        "finding_id": created_final_finding.get("finding_id"),
                    },
                }
            )
        except Exception:
            saved = self.repository.get_by_investigation_id(investigation_id)
            if saved is not None and str(saved.get("status") or "").upper() == "COMPLETED":
                saved["status"] = previous_status
                saved["outcome"] = None
                saved["final_notes"] = None
                saved["completed_at"] = None
                saved["updated_at"] = self._utc_now()
                self.repository.update(saved["id"], saved)
            raise
        return dict(investigation)

    def add_findings(self, payload):
        return payload
