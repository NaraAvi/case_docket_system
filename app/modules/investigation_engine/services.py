"""Investigation engine service layer."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.flag_repository import FlagRepository
from app.database.repositories.investigation_finding_repository import InvestigationFindingRepository
from app.database.repositories.investigation_note_repository import InvestigationNoteRepository
from app.database.repositories.investigation_repository import InvestigationRepository
from app.database.repositories.related_case_repository import RelatedCaseRepository
from app.modules.audit_engine.services import AuditTrailService
from app.services.case_service import CaseService


class InvestigationService:
    """Boundary for detective caseload, investigation lifecycle, and operational review."""

    VALID_STATUSES = {"OPEN", "IN_PROGRESS", "COMPLETED"}
    VALID_FINDING_TYPES = {"VALID", "INVALID", "GUILTY", "NOT_GUILTY"}
    VALID_OUTCOMES = VALID_FINDING_TYPES

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
    ):
        self.case_service = case_service or CaseService()
        self.audit_service = audit_service or AuditTrailService()
        self.repository = repository or InvestigationRepository()
        self.constable_service = constable_service
        self.finding_repository = finding_repository or InvestigationFindingRepository()
        self.note_repository = note_repository or InvestigationNoteRepository()
        self.flag_repository = flag_repository or FlagRepository()
        self.related_case_repository = related_case_repository or RelatedCaseRepository()
        self.freeze_service = freeze_service

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
        statement_text = str(payload.get("statement_text") or "").strip()
        if not statement_text:
            raise ValueError("Statement text is required.")

        statement = {
            "statement_id": len(case.get("statements", [])) + 1,
            "case_reference": case_reference,
            "citizen_id": case.get("citizen_id"),
            "statement_text": statement_text,
            "recorded_by": detective_id,
            "recorded_by_role": "detective",
            "created_at": self._utc_now(),
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
        if case.get("status") != "REGISTERED":
            raise ValueError("Detective investigation can only start for a registered docket.")
        if self.freeze_service and self.freeze_service.is_case_frozen(case_reference):
            raise ValueError("Case is frozen and operational mutation is restricted.")

        existing = self._get_investigation_by_case(case_reference)
        if existing is not None:
            raise ValueError("An active investigation already exists for this docket.")

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
        if next_status not in self.VALID_STATUSES:
            raise ValueError("Status is invalid.")

        current_status = str(investigation.get("status") or "").strip().upper()
        if current_status == "COMPLETED":
            raise ValueError("A completed investigation cannot be reopened.")
        if next_status == current_status:
            return dict(investigation)

        allowed_transitions = {
            "OPEN": {"IN_PROGRESS"},
            "IN_PROGRESS": {"COMPLETED"},
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
        self._assert_authorized_detective(investigation, detective_id)
        if investigation.get("status") == "COMPLETED":
            raise ValueError("Completed investigations cannot receive new findings.")
        if not isinstance(payload, dict):
            raise ValueError("Finding payload must be a JSON object.")

        finding_type = str(payload.get("finding_type") or "").strip().upper()
        if finding_type not in self.VALID_FINDING_TYPES:
            raise ValueError("Finding type is invalid.")

        notes = str(payload.get("notes") or "").strip()
        if not notes:
            raise ValueError("Finding notes are required.")

        finding = {
            "finding_id": self._generate_finding_id(len(self.finding_repository.list()) + 1),
            "investigation_id": investigation.get("investigation_id"),
            "case_reference": investigation.get("case_reference"),
            "detective_id": detective_id,
            "finding_type": finding_type,
            "notes": notes,
            "created_at": self._utc_now(),
            "updated_at": self._utc_now(),
        }
        self.finding_repository.create(finding)
        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "detective_finding_created",
                "case_reference": investigation.get("case_reference"),
                "details": {"investigation_id": investigation_id, "finding_type": finding_type},
            }
        )
        return dict(finding)

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

        if investigation.get("status") == "COMPLETED":
            raise ValueError("Investigation is already completed.")
        if not isinstance(payload, dict):
            raise ValueError("Completion payload must be a JSON object.")

        outcome = str(payload.get("outcome") or "").strip().upper()
        if outcome not in self.VALID_OUTCOMES:
            raise ValueError("Outcome is invalid.")

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
            "created_at": self._utc_now(),
            "updated_at": self._utc_now(),
            "is_final_outcome": True,
        }
        self.finding_repository.create(final_finding)

        investigation["status"] = "COMPLETED"
        investigation["outcome"] = outcome
        investigation["final_notes"] = final_notes
        investigation["completed_at"] = self._utc_now()
        investigation["updated_at"] = investigation["completed_at"]
        self.repository.update(investigation["id"], investigation)
        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "detective_investigation_completed",
                "case_reference": investigation.get("case_reference"),
                "details": {"investigation_id": investigation_id, "outcome": outcome},
            }
        )
        return dict(investigation)

    def add_findings(self, payload):
        return payload
