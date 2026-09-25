"""Constable engine service layer."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.flag_repository import FlagRepository
from app.database.repositories.related_case_repository import RelatedCaseRepository
from app.infrastructure.storage.media_manager import MediaManager
from app.modules.audit_engine.services import AuditTrailService
from app.modules.evidence_engine.services import EvidenceManagementService
from app.services.case_service import CaseService


class ConstableRegistrationService:
    """Boundary for docket registration and interview workflows."""

    _shared_interviews = {}
    _shared_recordings = {}
    VALID_FLAG_CATEGORIES = {
        "INCONSISTENT_INFORMATION",
        "INSUFFICIENT_INFORMATION",
        "CONFLICTING_ACCOUNT",
        "DUPLICATE_OR_RELATED_REPORT",
        "OTHER",
    }
    VALID_FLAG_STATUSES = {"OPEN", "RESOLVED", "DISMISSED"}
    VALID_RELATIONSHIP_TYPES = {"RELATED_CASE"}

    def __init__(
        self,
        case_service=None,
        audit_service=None,
        media_manager=None,
        evidence_service=None,
        flag_repository=None,
        related_case_repository=None,
        freeze_service=None,
    ):
        self.case_service = case_service or CaseService()
        self.audit_service = audit_service or AuditTrailService()
        self.media_manager = media_manager or MediaManager()
        self.evidence_service = evidence_service or EvidenceManagementService()
        self.flag_repository = flag_repository or FlagRepository()
        self.related_case_repository = related_case_repository or RelatedCaseRepository()
        self.freeze_service = freeze_service
        self._interviews = self.__class__._shared_interviews
        self._recordings = self.__class__._shared_recordings

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _normalize_recording_type(value):
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized == "citizen_recording":
            return "citizen_recording"
        if normalized == "constable_recording":
            return "constable_recording"
        return None

    def _get_docket_by_reference(self, case_reference):
        if not case_reference:
            return None
        for case in self.case_service.get_all_cases():
            if case.get("case_reference") == case_reference:
                return case
        return None

    def _assert_not_frozen(self, case_reference):
        if self.freeze_service and self.freeze_service.is_case_frozen(case_reference):
            raise ValueError("Case is frozen and operational mutation is restricted.")

    def _append_timeline_event(self, case, event_type, actor_id, actor_role, details=None):
        if case is None:
            return None
        timeline = case.setdefault("timeline", [])
        event = {
            "event_type": event_type,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "timestamp": self._utc_now(),
            "details": details or {},
        }
        timeline.append(event)
        return event

    def list_unregistered_dockets(self):
        return [
            {
                "case_reference": case.get("case_reference"),
                "title": case.get("title"),
                "description": case.get("description"),
                "citizen_id": case.get("citizen_id"),
                "status": case.get("status"),
                "incident_date": case.get("incident_date"),
                "location": case.get("location"),
            }
            for case in self.case_service.get_all_cases()
            if case.get("status") == "AWAITING_CONSTABLE_REGISTRATION"
        ]

    def get_docket(self, case_reference):
        case = self._get_docket_by_reference(case_reference)
        if case is None:
            return None
        return {
            "id": case.get("id"),
            "case_reference": case.get("case_reference"),
            "citizen_id": case.get("citizen_id"),
            "title": case.get("title"),
            "description": case.get("description"),
            "incident_date": case.get("incident_date"),
            "location": case.get("location"),
            "status": case.get("status"),
            "statement_count": len(case.get("statements", [])),
            "evidence": case.get("evidence", []),
            "statements": case.get("statements", []),
            "timeline": case.get("timeline", []),
            "interview_id": case.get("interview_id"),
        }

    def open_docket(self, case_reference, constable_id):
        case = self._get_docket_by_reference(case_reference)
        if case is None:
            raise ValueError("Docket not found.")
        self._assert_not_frozen(case_reference)
        if case.get("status") != "AWAITING_CONSTABLE_REGISTRATION":
            raise ValueError("Docket is not awaiting constable registration.")
        if case.get("citizen_id") == constable_id:
            raise ValueError("Constable cannot open a citizen-owned docket for registration.")
        self.audit_service.log(
            {
                "actor_id": constable_id,
                "actor_role": "constable",
                "action": "docket_opened",
                "case_reference": case_reference,
                "details": {"status": case.get("status")},
            }
        )
        return self.get_docket(case_reference)

    def create_flag(self, case_reference, constable_id, payload=None):
        case = self._get_docket_by_reference(case_reference)
        if case is None:
            raise ValueError("Docket not found.")
        if self.freeze_service and self.freeze_service.is_case_frozen(case_reference):
            raise ValueError("Case is frozen and operational mutation is restricted.")

        if not isinstance(payload, dict):
            raise ValueError("Flag payload must be provided as a JSON object.")

        category = str(payload.get("category") or "").strip().upper()
        if category not in self.VALID_FLAG_CATEGORIES:
            raise ValueError("Flag category is invalid.")

        notes = str(payload.get("notes") or "").strip()
        if not notes:
            raise ValueError("Flag notes are required.")

        status = str(payload.get("status") or "OPEN").strip().upper()
        if status not in self.VALID_FLAG_STATUSES:
            raise ValueError("Flag status is invalid.")

        flag_id = f"FLG-{case_reference}-{len(self.flag_repository.list()) + 1:04d}"
        flag = {
            "id": len(self.flag_repository.list()) + 1,
            "flag_id": flag_id,
            "case_reference": case_reference,
            "created_by": constable_id,
            "created_by_role": "constable",
            "created_at": self._utc_now(),
            "updated_at": self._utc_now(),
            "category": category,
            "notes": notes,
            "status": status,
        }
        self.flag_repository.create(flag)
        self.audit_service.log(
            {
                "actor_id": constable_id,
                "actor_role": "constable",
                "action": "potential_invalidity_flag_created",
                "case_reference": case_reference,
                "details": {"flag_id": flag_id, "category": category, "status": status},
            }
        )
        return dict(flag)

    def list_flags_for_case(self, case_reference):
        return [dict(flag) for flag in self.flag_repository.list_for_case(case_reference)]

    def update_flag(self, flag_id, constable_id, payload=None):
        flag = self.flag_repository.get_for_flag_id(flag_id)
        if flag is None:
            raise ValueError("Flag not found.")

        if not isinstance(payload, dict):
            raise ValueError("Flag update payload must be a JSON object.")

        if "category" in payload:
            category = str(payload.get("category") or "").strip().upper()
            if category not in self.VALID_FLAG_CATEGORIES:
                raise ValueError("Flag category is invalid.")
            flag["category"] = category

        if "notes" in payload:
            notes = str(payload.get("notes") or "").strip()
            if not notes:
                raise ValueError("Flag notes are required.")
            flag["notes"] = notes

        if "status" in payload:
            status = str(payload.get("status") or "").strip().upper()
            if status not in self.VALID_FLAG_STATUSES:
                raise ValueError("Flag status is invalid.")
            flag["status"] = status

        flag["updated_at"] = self._utc_now()
        self.flag_repository.update(flag["flag_id"], flag)
        self.audit_service.log(
            {
                "actor_id": constable_id,
                "actor_role": "constable",
                "action": "potential_invalidity_flag_updated",
                "case_reference": flag.get("case_reference"),
                "details": {"flag_id": flag.get("flag_id"), "status": flag.get("status")},
            }
        )
        return dict(flag)

    def search_dockets(self, search_text=None):
        query = str(search_text or "").strip().lower()
        results = []
        for case in self.case_service.get_all_cases():
            searchable = " ".join(
                [
                    str(case.get("case_reference") or ""),
                    str(case.get("title") or ""),
                    str(case.get("description") or ""),
                    str(case.get("location") or ""),
                    str(case.get("incident_date") or ""),
                ]
            ).lower()
            if query and query not in searchable:
                continue
            results.append(
                {
                    "case_reference": case.get("case_reference"),
                    "title": case.get("title"),
                    "description": case.get("description"),
                    "location": case.get("location"),
                    "incident_date": case.get("incident_date"),
                    "status": case.get("status"),
                }
            )
        return results

    def create_related_case_link(self, source_case_reference, constable_id, payload=None):
        if not isinstance(payload, dict):
            raise ValueError("Related case payload must be a JSON object.")

        source_case = self._get_docket_by_reference(source_case_reference)
        if source_case is None:
            raise ValueError("Source case not found.")

        related_case_reference = str(payload.get("related_case_reference") or "").strip()
        if not related_case_reference:
            raise ValueError("Related case reference is required.")

        related_case = self._get_docket_by_reference(related_case_reference)
        if related_case is None:
            raise ValueError("Related case not found.")

        if source_case_reference == related_case_reference:
            raise ValueError("A case cannot be related to itself.")

        if self.related_case_repository.get_duplicate_relationship(source_case_reference, related_case_reference):
            raise ValueError("Relationship already exists.")

        relationship_type = str(payload.get("relationship_type") or "").strip().upper()
        if relationship_type not in self.VALID_RELATIONSHIP_TYPES:
            raise ValueError("Relationship type is invalid.")

        notes = str(payload.get("notes") or "").strip()
        relationship_id = f"REL-{source_case_reference}-{related_case_reference}-{len(self.related_case_repository.list()) + 1:04d}"
        relationship = {
            "id": len(self.related_case_repository.list()) + 1,
            "relationship_id": relationship_id,
            "source_case_reference": source_case_reference,
            "related_case_reference": related_case_reference,
            "relationship_type": relationship_type,
            "created_by": constable_id,
            "created_by_role": "constable",
            "created_at": self._utc_now(),
            "notes": notes,
        }
        self.related_case_repository.create(relationship)
        self.audit_service.log(
            {
                "actor_id": constable_id,
                "actor_role": "constable",
                "action": "related_case_link_created",
                "case_reference": source_case_reference,
                "details": {
                    "source_case_reference": source_case_reference,
                    "related_case_reference": related_case_reference,
                    "relationship_type": relationship_type,
                },
            }
        )
        return dict(relationship)

    def list_related_cases(self, case_reference):
        relationships = self.related_case_repository.list_for_case(case_reference)
        normalized = []
        for relationship in relationships:
            source = relationship.get("source_case_reference")
            related = relationship.get("related_case_reference")
            if source == case_reference or related == case_reference:
                normalized.append(dict(relationship))
        return normalized

    def get_case_detail_for_constable(self, case_reference):
        case = self._get_docket_by_reference(case_reference)
        if case is None:
            return None
        if case.get("status") != "AWAITING_CONSTABLE_REGISTRATION":
            return None
        return {
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
        }

    def get_flags_for_case(self, case_reference):
        return self.list_flags_for_case(case_reference)

    def get_related_cases_for_case(self, case_reference):
        return self.list_related_cases(case_reference)

    def start_interview(self, case_reference, constable_id, payload=None):
        case = self._get_docket_by_reference(case_reference)
        if case is None:
            raise ValueError("Docket not found.")
        self._assert_not_frozen(case_reference)
        if case.get("status") != "AWAITING_CONSTABLE_REGISTRATION":
            raise ValueError("Docket is not awaiting constable registration.")

        for interview in self._interviews.values():
            if interview.get("case_reference") == case_reference:
                return interview

        interview_id = f"INT-{case_reference}-{len(self._interviews) + 1:04d}"
        interview = {
            "interview_id": interview_id,
            "case_reference": case_reference,
            "citizen_id": case.get("citizen_id"),
            "constable_id": constable_id,
            "status": "STARTED",
            "start_timestamp": self._utc_now(),
            "completion_timestamp": None,
            "citizen_recording": None,
            "constable_recording": None,
            "created_at": self._utc_now(),
            "updated_at": self._utc_now(),
        }
        self._interviews[interview_id] = interview
        case["interview_id"] = interview_id
        self.case_service.update_case(case)
        self._append_timeline_event(
            case,
            "constable_registration_interview_started",
            constable_id,
            "constable",
            {"interview_id": interview_id},
        )
        self.audit_service.log(
            {
                "actor_id": constable_id,
                "actor_role": "constable",
                "action": "interview_started",
                "case_reference": case_reference,
                "details": {"interview_id": interview_id},
            }
        )
        return dict(interview)

    def get_interview_by_id(self, interview_id):
        interview = self._interviews.get(interview_id)
        if interview is None:
            return None
        return dict(interview)

    def get_interview_for_citizen(self, citizen_id, interview_id):
        interview = self._interviews.get(interview_id)
        if interview is None:
            return None
        if interview.get("citizen_id") != citizen_id:
            return None
        return dict(interview)

    def get_interview_for_constable(self, constable_id, interview_id):
        interview = self._interviews.get(interview_id)
        if interview is None:
            return None
        if interview.get("constable_id") != constable_id:
            return None
        return dict(interview)

    def _ensure_interview_complete(self, interview):
        citizen_recording = interview.get("citizen_recording")
        constable_recording = interview.get("constable_recording")
        if citizen_recording is None or constable_recording is None:
            interview["status"] = "AWAITING_AUDIO"
            return False
        if citizen_recording.get("status") != "SUBMITTED" or constable_recording.get("status") != "SUBMITTED":
            interview["status"] = "AWAITING_AUDIO"
            return False
        interview["status"] = "COMPLETED"
        interview["completion_timestamp"] = self._utc_now()
        return True

    def submit_recording(self, actor_id, actor_role, interview_id, payload):
        interview = self._interviews.get(interview_id)
        if interview is None:
            raise ValueError("Interview not found.")

        if actor_role == "citizen":
            if interview.get("citizen_id") != actor_id:
                raise ValueError("Citizen is not authorized for this interview.")
            recording_type = "citizen_recording"
        elif actor_role == "constable":
            if interview.get("constable_id") != actor_id:
                raise ValueError("Constable is not authorized for this interview.")
            recording_type = "constable_recording"
        else:
            raise ValueError("Unsupported actor role.")

        normalized_type = self._normalize_recording_type(payload.get("recording_type")) if isinstance(payload, dict) else None
        if normalized_type is None:
            normalized_type = recording_type
        if normalized_type != recording_type:
            raise ValueError("Recording type does not match actor role.")

        case = self._get_docket_by_reference(interview.get("case_reference"))
        if case is None:
            raise ValueError("Docket not found.")
        self._assert_not_frozen(interview.get("case_reference"))

        filename = (payload.get("filename") if isinstance(payload, dict) else None) or f"{recording_type}.wav"
        storage_reference = payload.get("storage_reference") if isinstance(payload, dict) else None
        if storage_reference is None:
            storage_reference = filename

        media = self.media_manager.register_file(filename, {"storage_reference": storage_reference, "recording_type": recording_type})
        recording = {
            "recording_id": f"REC-{interview_id}-{len(self._recordings) + 1:04d}",
            "interview_id": interview_id,
            "case_reference": interview.get("case_reference"),
            "recorder_id": actor_id,
            "recorder_role": actor_role,
            "recording_type": recording_type,
            "status": "SUBMITTED",
            "filename": media["filename"],
            "storage_reference": media["storage_reference"],
            "created_at": self._utc_now(),
            "submitted_at": self._utc_now(),
        }

        interview[f"{recording_type}"] = recording
        interview["updated_at"] = self._utc_now()
        self._recordings[recording["recording_id"]] = recording

        if self._ensure_interview_complete(interview):
            self._append_timeline_event(
                case,
                "interview_completed",
                actor_id,
                actor_role,
                {"interview_id": interview_id},
            )
            self.audit_service.log(
                {
                    "actor_id": actor_id,
                    "actor_role": actor_role,
                    "action": "interview_completed",
                    "case_reference": interview.get("case_reference"),
                    "details": {"interview_id": interview_id},
                }
            )
        else:
            self._append_timeline_event(
                case,
                f"{recording_type}_submitted",
                actor_id,
                actor_role,
                {"recording_id": recording["recording_id"], "interview_id": interview_id},
            )

        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": actor_role,
                "action": f"{recording_type}_submitted",
                "case_reference": interview.get("case_reference"),
                "details": {"recording_id": recording["recording_id"], "interview_id": interview_id},
            }
        )
        case["interview_id"] = interview_id
        self.case_service.update_case(case)
        self.evidence_service.add_recording(recording)
        return recording

    def register_docket(self, interview_id, constable_id):
        interview = self._interviews.get(interview_id)
        if interview is None:
            raise ValueError("Interview not found.")
        if interview.get("constable_id") != constable_id:
            raise ValueError("Constable is not authorized for this interview.")

        case = self._get_docket_by_reference(interview.get("case_reference"))
        if case is None:
            raise ValueError("Docket not found.")
        self._assert_not_frozen(interview.get("case_reference"))
        if case.get("status") != "AWAITING_CONSTABLE_REGISTRATION":
            raise ValueError("Docket is not awaiting constable registration.")
        if interview.get("status") != "COMPLETED":
            raise ValueError("Interview is incomplete.")
        if interview.get("citizen_recording") is None or interview.get("constable_recording") is None:
            raise ValueError("Both recordings are required before registration.")
        if interview["citizen_recording"].get("status") != "SUBMITTED":
            raise ValueError("Citizen recording is missing.")
        if interview["constable_recording"].get("status") != "SUBMITTED":
            raise ValueError("Constable recording is missing.")

        case["status"] = "REGISTERED"
        case["registered_at"] = self._utc_now()
        self._append_timeline_event(
            case,
            "docket_registered",
            constable_id,
            "constable",
            {"interview_id": interview_id},
        )
        self.audit_service.log(
            {
                "actor_id": constable_id,
                "actor_role": "constable",
                "action": "docket_registered",
                "case_reference": case.get("case_reference"),
                "details": {"interview_id": interview_id, "status": "REGISTERED"},
            }
        )
        self.case_service.update_case(case)
        return dict(case)

    def get_case_detail_for_constable(self, case_reference):
        case = self._get_docket_by_reference(case_reference)
        if case is None:
            return None
        if case.get("status") != "AWAITING_CONSTABLE_REGISTRATION":
            return None
        return {
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
        }
