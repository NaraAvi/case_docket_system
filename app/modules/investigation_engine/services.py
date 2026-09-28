"""Investigation engine service layer."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from app.database.repositories.flag_repository import FlagRepository
from app.database.repositories.investigation_action_repository import InvestigationActionRepository
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
    VALID_INTERVIEW_TYPES = {"INITIAL", "FOLLOW_UP", "FORMAL", "OTHER"}
    VALID_EVIDENCE_TYPES = {"PHOTO", "VIDEO", "DOCUMENT", "AUDIO", "WITNESS_STATEMENT", "OTHER"}
    REQUIRED_ACTION_SEQUENCE = [
        "INTERVIEW",
        "EVIDENCE_REVIEW",
        "EVIDENCE_COLLECTION",
        "RECORD_REQUEST",
        "WITNESS_CONTACT",
        "SCENE_REVIEW",
    ]

    def __init__(
        self,
        case_service=None,
        audit_service=None,
        repository=None,
        constable_service=None,
        finding_repository=None,
        note_repository=None,
        action_repository=None,
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
        self.citizen_submission_service = None
        self.incident_candidate_service = None
        if app is not None and hasattr(app, "extensions"):
            self.citizen_submission_service = app.extensions.get("citizen_submission_service")
            self.incident_candidate_service = app.extensions.get("incident_candidate_service")
        self.finding_repository = finding_repository or InvestigationFindingRepository(app=app)
        self.note_repository = note_repository or InvestigationNoteRepository(app=app)
        self.action_repository = action_repository or InvestigationActionRepository(app=app)
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

    @staticmethod
    def _generate_action_id(sequence):
        return f"ACT-{sequence:06d}"

    @classmethod
    def _normalize_action_type(cls, action_type):
        return str(action_type or "").strip().upper()

    def _completed_required_actions(self, investigation_id):
        if self.action_repository is None:
            return []
        completed = []
        for action in self.action_repository.list_for_investigation(investigation_id):
            if not isinstance(action, dict):
                continue
            normalized = self._normalize_action_type(action.get("action_type"))
            if normalized in self.REQUIRED_ACTION_SEQUENCE and normalized not in completed:
                completed.append(normalized)
        return completed

    def _require_all_required_actions(self, investigation_id):
        completed = self._completed_required_actions(investigation_id)
        if len(completed) == len(self.REQUIRED_ACTION_SEQUENCE):
            return
        remaining = [item for item in self.REQUIRED_ACTION_SEQUENCE if item not in completed]
        raise ValueError(
            f"Required investigative actions are incomplete. {len(completed)} of {len(self.REQUIRED_ACTION_SEQUENCE)} are complete; findings remain blocked until all six required actions are complete. Remaining: {', '.join(remaining)}."
        )

    def _assert_required_action_not_duplicate(self, investigation_id, action_type):
        normalized = self._normalize_action_type(action_type)
        if normalized not in self.REQUIRED_ACTION_SEQUENCE:
            raise ValueError(
                "Only the required investigative actions are permitted for this investigation: "
                + ", ".join(self.REQUIRED_ACTION_SEQUENCE)
                + "."
            )

        # Repeated action records remain valid for the same required action category.
        # The completion gate is category-based and counts whether each required
        # action type has been covered at least once, not whether a single record was
        # recorded only once.
        return

    def _get_case(self, case_reference):
        if not case_reference:
            return None
        for case in self.case_service.get_all_cases():
            if case.get("case_reference") == case_reference:
                return case
        return None

    def _collect_authoritative_case_evidence(self, case):
        if case is None:
            return []

        protected_context = self._resolve_protected_submission_context(case)
        evidence_items = []
        for source in (case.get("evidence") or [], protected_context.get("citizen_evidence") or []):
            if not isinstance(source, list):
                continue
            evidence_items.extend(source)

        ordered = []
        seen = set()
        for item in evidence_items:
            if not isinstance(item, dict):
                continue
            evidence_id = str(item.get("evidence_id") or "").strip()
            if not evidence_id or evidence_id in seen:
                continue
            ordered.append(item)
            seen.add(evidence_id)
        return ordered

    def _get_procedure_service(self):
        if self.app is not None and hasattr(self.app, "extensions"):
            return self.app.extensions.get("detective_procedure_service") or self.app.extensions.get("procedure_service")
        return None

    def _enforce_procedure_gate(self, case_reference, detective_id, action):
        procedure_service = self._get_procedure_service()
        if procedure_service is None:
            return
        result = procedure_service.evaluate_case(
            case_reference,
            actor_id=detective_id,
            actor_role="detective",
            action=action,
        )
        if not result.get("allowed"):
            raise ValueError(result.get("blocking_reason") or result.get("message") or "Procedure requirements are not yet satisfied for this action.")

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

    def _resolve_protected_submission_context(self, case):
        """Return the authoritative citizen submission and evidence chain for a procedural case."""
        if case is None:
            return {
                "citizen_submission": None,
                "citizen_assertions": [],
                "citizen_claims": [],
                "incident_candidate": None,
                "relationships": [],
                "citizen_evidence": [],
            }

        if self.citizen_submission_service is None and self.app is not None and hasattr(self.app, "extensions"):
            self.citizen_submission_service = self.app.extensions.get("citizen_submission_service")
        if self.incident_candidate_service is None and self.app is not None and hasattr(self.app, "extensions"):
            self.incident_candidate_service = self.app.extensions.get("incident_candidate_service")

        submission_id = case.get("source_submission_id")
        candidate_id = case.get("source_candidate_id")

        citizen_submission = None
        assertions = []
        claims = []
        candidate = None
        relationships = []
        evidence = []

        if submission_id and self.citizen_submission_service is not None:
            repository = getattr(self.citizen_submission_service, "repository", None)
            if repository is not None:
                citizen_submission = repository.get_by_id(submission_id)
            assertion_repository = getattr(self.citizen_submission_service, "assertion_repository", None)
            if assertion_repository is not None:
                assertions = assertion_repository.list_for_submission(submission_id)
            claim_repository = getattr(self.citizen_submission_service, "claim_repository", None)
            if claim_repository is not None:
                claims = claim_repository.list_for_submission(submission_id)
            evidence_repository = getattr(self.citizen_submission_service, "evidence_repository", None)
            if evidence_repository is not None:
                evidence = evidence_repository.list_for_submission(submission_id)

        if candidate_id and self.incident_candidate_service is not None:
            candidate_repository = getattr(self.incident_candidate_service, "candidate_repository", None)
            if candidate_repository is not None:
                candidate = candidate_repository.get_by_id(candidate_id)

        if self.incident_candidate_service is not None:
            relationship_repository = getattr(self.incident_candidate_service, "relationship_repository", None)
            if relationship_repository is not None:
                relationships = relationship_repository.list_for_submission(submission_id) if submission_id else []
                if candidate_id:
                    relationships = [
                        item
                        for item in relationships
                        if str(item.get("candidate_id") or "") == str(candidate_id) or str(item.get("source_submission_id") or "") == str(submission_id)
                    ]

        if candidate is None and submission_id and self.incident_candidate_service is not None:
            candidate_repository = getattr(self.incident_candidate_service, "candidate_repository", None)
            if candidate_repository is not None:
                candidates = candidate_repository.list_for_submission(submission_id)
                if candidates:
                    candidate = candidates[0]

        return {
            "citizen_submission": citizen_submission,
            "citizen_assertions": assertions,
            "citizen_claims": claims,
            "incident_candidate": candidate,
            "relationships": relationships,
            "citizen_evidence": evidence,
        }

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
        sanitized = {
            "evidence_id": evidence.get("evidence_id"),
            "evidence_type": evidence.get("evidence_type"),
            "description": evidence.get("description"),
            "source": source,
            "submission_timestamp": evidence.get("created_at") or evidence.get("submitted_at"),
            "status": evidence.get("status") or "SUBMITTED",
        }
        if evidence.get("storage_reference"):
            sanitized["storage_reference"] = evidence.get("storage_reference")
        if evidence.get("sha256_hash") not in (None, ""):
            sanitized["sha256_hash"] = str(evidence.get("sha256_hash"))
        if evidence.get("filename"):
            sanitized["filename"] = evidence.get("filename")
        if evidence.get("content_type"):
            sanitized["content_type"] = evidence.get("content_type")
        if evidence.get("size_bytes") is not None:
            sanitized["size_bytes"] = evidence.get("size_bytes")
        return sanitized

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

    def _assert_active_detective_assignment(self, case_reference, detective_id):
        if detective_id is None:
            raise ValueError("Detective identity is required.")
        if self.assignment_service is None:
            return

        current_assignment = self.assignment_service.get_current_assignment_for_case(case_reference)
        if current_assignment is None or str(current_assignment.get("status") or "").upper() != "ACTIVE":
            raise ValueError("Detective access requires an active assignment to this docket.")
        if str(current_assignment.get("officer_role") or "").lower() != "detective":
            raise ValueError("The active assignment for this docket is not held by a detective.")
        if str(current_assignment.get("officer_id") or "") != str(detective_id):
            raise ValueError("Detective is not the assigned officer for this docket.")

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

    def get_docket_for_detective(self, case_reference, detective_id=None):
        case = self._get_case(case_reference)
        if case is None:
            raise ValueError("Docket not found.")
        if case.get("status") != "REGISTERED":
            raise ValueError("Detective access is limited to registered dockets.")
        if detective_id is not None:
            self._assert_active_detective_assignment(case_reference, detective_id)
        freeze = self.freeze_service.get_current_freeze(case_reference) if self.freeze_service else None
        if freeze is not None:
            # IPID custody blocks a detective from viewing the case content
            # at all -- not just from mutating it -- while it's frozen. Only
            # enough is returned for the workspace to render the "Case
            # Frozen" notice.
            return self._frozen_notice(case, freeze)

        protected_context = self._resolve_protected_submission_context(case)
        source_submission = protected_context.get("citizen_submission") or {}
        source_evidence = protected_context.get("citizen_evidence") or []
        evidence_items = case.get("evidence") or source_evidence
        source_submission_id = case.get("source_submission_id")
        if not source_submission_id and isinstance(source_submission, dict):
            source_submission_id = source_submission.get("submission_id")

        if detective_id is not None:
            presented_evidence_ids = [
                str(item.get("evidence_id") or "")
                for item in source_evidence
                if isinstance(item, dict) and str(item.get("evidence_id") or "").strip()
            ]
            self.audit_service.log(
                {
                    "actor_id": detective_id,
                    "actor_role": "detective",
                    "action": "detective_case_accessed",
                    "case_reference": case_reference,
                    "object_type": "case_docket",
                    "object_id": case_reference,
                    "previous_state": "REGISTERED",
                    "new_state": "CASE_PRESENTED",
                    "reason": "Assigned detective accessed the protected case source and evidence for review before investigation start.",
                    "details": {
                        "source_submission_id": source_submission_id,
                        "source_candidate_id": case.get("source_candidate_id"),
                        "presented_evidence_ids": presented_evidence_ids,
                    },
                }
            )

        procedural_assessment = case.get("procedural_assessment") if isinstance(case.get("procedural_assessment"), dict) else {}
        persisted_case_facts_verification = (
            case.get("case_facts_verification")
            if isinstance(case.get("case_facts_verification"), dict)
            else procedural_assessment.get("case_facts_verification")
            if isinstance(procedural_assessment.get("case_facts_verification"), dict)
            else {}
        )

        return {
            "id": case.get("id"),
            "case_reference": case.get("case_reference"),
            "title": case.get("title"),
            "description": case.get("description"),
            "citizen_id": case.get("citizen_id"),
            "status": case.get("status"),
            "incident_date": case.get("incident_date"),
            "location": case.get("location"),
            "source_submission_id": source_submission_id,
            "source_candidate_id": case.get("source_candidate_id"),
            "case_origin": case.get("case_origin"),
            "gate_decision": case.get("gate_decision"),
            "statement_count": len(case.get("statements", [])),
            "statements": case.get("statements", []),
            "evidence": [self._sanitize_evidence(item) for item in evidence_items],
            "timeline": case.get("timeline", []),
            "interview_id": case.get("interview_id"),
            "investigation": self._get_latest_investigation_by_case(case_reference),
            "is_frozen": False,
            "freeze_status": "NOT_FROZEN",
            "freeze_reason": None,
            "procedural_assessment": procedural_assessment,
            "case_facts_verification": persisted_case_facts_verification,
            "citizen_submission": protected_context["citizen_submission"],
            "citizen_assertions": protected_context["citizen_assertions"],
            "citizen_claims": protected_context["citizen_claims"],
            "incident_candidate": protected_context["incident_candidate"],
            "relationships": protected_context["relationships"],
            "citizen_evidence": [self._sanitize_evidence(item) for item in source_evidence],
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
        self._assert_active_detective_assignment(case_reference, detective_id)
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
        self._enforce_procedure_gate(case_reference, detective_id, "start_investigation")
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
        procedure_service = self._get_procedure_service()
        if procedure_service is not None and hasattr(procedure_service, "reconcile_investigation_state"):
            procedure_service.reconcile_investigation_state(case_reference, actor_id=detective_id, actor_role="detective", investigation=investigation)
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
        procedure_service = self._get_procedure_service()
        if procedure_service is not None and hasattr(procedure_service, "reconcile_investigation_state"):
            procedure_service.reconcile_investigation_state(
                investigation.get("case_reference"),
                actor_id=detective_id,
                actor_role="detective",
                investigation=investigation,
            )
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
        self._assert_active_detective_assignment(investigation.get("case_reference"), detective_id)

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

        protected_context = self._resolve_protected_submission_context(case)
        evidence_items = case.get("evidence") or protected_context.get("citizen_evidence") or []

        return {
            "investigation_id": investigation.get("investigation_id"),
            "case_reference": case.get("case_reference"),
            "case_status": case.get("status"),
            "title": case.get("title"),
            "description": case.get("description"),
            "incident_date": case.get("incident_date"),
            "location": case.get("location"),
            "source_submission_id": case.get("source_submission_id"),
            "source_candidate_id": case.get("source_candidate_id"),
            "citizen_submission": {
                "original_statement": (
                    case.get("statements", [{}])[-1].get("statement_text")
                    if case.get("statements")
                    else None
                ),
                "statements": [self._sanitize_statement(item) for item in case.get("statements", [])],
                "evidence": [self._sanitize_evidence(item) for item in evidence_items],
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
        self._assert_active_detective_assignment(investigation.get("case_reference"), detective_id)

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
        self._assert_active_detective_assignment(investigation.get("case_reference"), detective_id)

        case = self._get_case(investigation.get("case_reference"))
        if case is None:
            raise ValueError("Docket not found.")

        protected_context = self._resolve_protected_submission_context(case)
        evidence_items = [self._sanitize_evidence(item) for item in (case.get("evidence") or protected_context.get("citizen_evidence") or [])]
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
        self._assert_active_detective_assignment(investigation.get("case_reference"), detective_id)

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
        self._assert_active_detective_assignment(investigation.get("case_reference"), detective_id)

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

        raw_finding_type = payload.get("finding_type", payload.get("type"))
        finding_type = str(raw_finding_type or "").strip().upper() if raw_finding_type is not None and str(raw_finding_type).strip() else None
        if finding_type in self.REJECTED_ADJUDICATIVE_VALUES:
            finding_type = None
        elif finding_type is not None and finding_type not in self.VALID_FINDING_TYPES:
            finding_type = None

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
        action_ids = self._normalize_string_list(payload.get("action_ids"))
        if action_ids:
            valid_action_ids = {str(item.get("action_id")) for item in self.action_repository.list_for_investigation(investigation_id) if isinstance(item, dict) and item.get("action_id")}
            invalid_action_ids = [action_id for action_id in action_ids if action_id not in valid_action_ids]
            if invalid_action_ids:
                raise ValueError("Investigation record references must match action records on this investigation.")
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

        explicit_basis = bool(structured_evidence_ids or action_ids or claim_ids or supporting_material or contradicting_material)
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

        self._require_all_required_actions(investigation_id)

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
            "action_ids": action_ids,
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

    @staticmethod
    def _as_bool(value):
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    @classmethod
    def _normalize_evidence_type(cls, value):
        if value is None:
            return ""
        return str(value).strip().upper().replace("-", "_").replace(" ", "_")

    @staticmethod
    def _as_list(value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, str):
            return [value] if value.strip() else []
        return [value]

    @staticmethod
    def _extract_evidence_id(item):
        if not isinstance(item, dict):
            return ""
        for key in ("evidence_id", "evidenceId", "id", "reference_id", "referenceId"):
            value = item.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    def _resolve_case_evidence_ids(self, case):
        ids = set()
        for item in self._collect_authoritative_case_evidence(case):
            evidence_id = self._extract_evidence_id(item)
            if evidence_id:
                ids.add(evidence_id)
        return ids

    @staticmethod
    def _coerce_recording_entries(value):
        entries = []
        raw_values = []
        if value is None:
            return entries
        if isinstance(value, dict):
            raw_values = [value]
        else:
            raw_values = list(value)

        for index, item in enumerate(raw_values, start=1):
            if isinstance(item, dict):
                record = dict(item)
            else:
                record = {"storage_reference": str(item).strip() if item is not None else ""}

            if not any(str(record.get(key) or "").strip() for key in ("filename", "storage_reference", "recording_id", "recording_reference", "name")):
                continue

            normalized = {}
            for key in ("filename", "storage_reference", "recording_id", "recording_reference", "recording_type", "mime_type"):
                candidate = record.get(key)
                if candidate not in (None, ""):
                    normalized[key] = candidate

            if "filename" not in normalized:
                candidate = normalized.get("storage_reference") or normalized.get("recording_reference") or normalized.get("recording_id")
                if candidate:
                    normalized["filename"] = str(candidate).split("/")[-1]
            if "storage_reference" not in normalized:
                candidate = record.get("storage_reference") or record.get("recording_reference") or record.get("filename")
                if candidate:
                    normalized["storage_reference"] = candidate
            if "recording_type" not in normalized:
                normalized["recording_type"] = "audio"
            normalized["recording_number"] = index
            entries.append(normalized)
        return entries

    def _next_interview_number(self, investigation_id):
        current_count = 0
        for action in self.action_repository.list_for_investigation(investigation_id):
            if isinstance(action, dict) and self._normalize_action_type(action.get("action_type")) == "INTERVIEW":
                current_count += 1
        return current_count + 1

    def _clean_record_payload(self, payload):
        forbidden = {
            "action_id",
            "investigation_id",
            "case_reference",
            "detective_id",
            "actor_id",
            "created_at",
            "updated_at",
            "performed_at",
            "timestamp",
            "provenance",
            "audit_actor",
            "purpose",
            "evidence_id",
        }
        data = {}
        for key, value in dict(payload).items():
            if key in forbidden or key == "action_type":
                continue
            if key == "record_data":
                if isinstance(value, dict):
                    data.update(value)
                continue
            data[key] = value
        return data

    def _validate_investigation_action_contract(self, action_type, payload, case):
        case_evidence_ids = self._resolve_case_evidence_ids(case)
        data = self._clean_record_payload(payload)
        legacy_payload_present = any(key in payload for key in {"purpose", "description", "result", "result_observation"})
        legacy_summary = str(payload.get("purpose") or "").strip()
        legacy_description = str(payload.get("description") or "").strip()
        legacy_result = str(payload.get("result_observation") or payload.get("result") or "").strip()

        def require(value, message):
            if value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, (list, tuple, set)) and not value):
                raise ValueError(message)
            return value

        def legacy_record_data(summary=None, detail=None, outcome=None):
            record = {}
            if summary:
                record["legacy_summary"] = summary
            if detail:
                record["legacy_description"] = detail
            if outcome:
                record["legacy_result"] = outcome
            return record

        if action_type == "WITNESS_CONTACT":
            if not any(key in data for key in {"witness_name", "relationship_to_incident", "contact_date", "contact_time", "contact_method", "information_obtained", "lead_generated", "lead_description", "explanation"}) and legacy_payload_present:
                return legacy_record_data(legacy_summary or None, legacy_description or None, legacy_result or None)
            witness_name = str(data.get("witness_name") or data.get("witness") or "").strip()
            relationship = str(data.get("relationship_to_incident") or "").strip()
            contact_date = str(data.get("contact_date") or "").strip()
            contact_time = str(data.get("contact_time") or "").strip()
            contact_method = str(data.get("contact_method") or data.get("method") or "").strip().upper()
            result = str(data.get("result") or "").strip().upper()
            information = str(data.get("information_obtained") or "").strip()
            lead_generated = self._as_bool(data.get("lead_generated") or data.get("generated_lead"))
            lead_description = str(data.get("lead_description") or "").strip()
            explanation = str(data.get("explanation") or data.get("reason") or "").strip()
            require(witness_name, "Witness name is required.")
            require(relationship, "Witness relationship to the incident is required.")
            require(contact_date, "Witness contact date is required.")
            require(contact_time, "Witness contact time is required.")
            require(contact_method, "Witness contact method is required.")
            require(result, "Witness contact result is required.")
            require(information, "Information obtained is required.")
            if result not in {"PROVIDED_INFORMATION", "AGREED_TO_INTERVIEW", "UNAVAILABLE", "DECLINED", "NO_RELEVANT_INFORMATION", "REFERRED_TO_PERSON_OR_EVIDENCE", "OTHER"}:
                raise ValueError("Witness contact result is not recognised.")
            if lead_generated and not lead_description:
                raise ValueError("Lead description is required when a witness lead was generated.")
            if result in {"UNAVAILABLE", "DECLINED", "NO_RELEVANT_INFORMATION", "REFERRED_TO_PERSON_OR_EVIDENCE", "OTHER"} and not explanation:
                raise ValueError("An explanation is required for unsuccessful or unavailable witness contact outcomes.")
            return {
                "witness_name": witness_name,
                "relationship_to_incident": relationship,
                "known_contact_information": str(data.get("known_contact_information") or "").strip() or None,
                "how_witness_was_identified": str(data.get("how_witness_was_identified") or data.get("identification_method") or "").strip() or None,
                "contact_date": contact_date,
                "contact_time": contact_time,
                "contact_method": contact_method,
                "result": result,
                "information_obtained": information,
                "lead_generated": lead_generated,
                "lead_description": lead_description or None,
                "explanation": explanation or None,
            }

        if action_type == "INTERVIEW":
            if not any(key in data for key in {"person_name", "interviewee_name", "person_interviewed", "role", "interview_date", "interview_time", "location_method", "interview_type", "recording_uploads", "recordings", "interview_notes_uploads", "information_obtained", "contradictions", "follow_up_lead", "lead_description"}) and legacy_payload_present:
                return legacy_record_data(legacy_summary or None, legacy_description or None, legacy_result or None)
            person_name = str(data.get("person_name") or data.get("interviewee_name") or data.get("person_interviewed") or "").strip()
            role = str(data.get("role") or "").strip().upper()
            interview_date = str(data.get("interview_date") or data.get("date") or "").strip()
            interview_time = str(data.get("interview_time") or data.get("time") or "").strip()
            location_method = str(data.get("location_method") or data.get("location") or "").strip()
            interview_type = str(data.get("interview_type") or "").strip().upper()
            recording_uploads = self._coerce_recording_entries(data.get("recordings") or data.get("recording_uploads") or data.get("recording_upload"))
            note_uploads = self._as_list(data.get("interview_notes_uploads") or data.get("notes_uploads") or data.get("document_uploads") or data.get("interview_notes"))
            information = str(data.get("information_obtained") or "").strip()
            contradictions = str(data.get("contradictions") or "").strip().upper()
            contradiction_explanation = str(data.get("contradiction_explanation") or data.get("contradictions_explanation") or data.get("explanation") or "").strip()
            follow_up_lead = self._as_bool(data.get("follow_up_lead") or data.get("lead_generated"))
            lead_description = str(data.get("lead_description") or "").strip()
            outcome = str(data.get("outcome") or "").strip().upper()
            outcome_explanation = str(data.get("outcome_explanation") or data.get("explanation") or "").strip()
            require(person_name, "Interviewee name is required.")
            require(role, "Interviewee role is required.")
            require(interview_date, "Interview date is required.")
            require(interview_time, "Interview time is required.")
            require(location_method, "Interview location or method is required.")
            require(interview_type, "Interview type is required.")
            if interview_type not in self.VALID_INTERVIEW_TYPES:
                raise ValueError("Interview type is not recognised.")
            if not recording_uploads and not note_uploads:
                raise ValueError("An interview must include at least one recording upload or interview notes/document upload.")
            require(information, "Information obtained from the interview is required.")
            require(contradictions, "Contradictions or inconsistencies status is required.")
            if contradictions == "IDENTIFIED" and not contradiction_explanation:
                raise ValueError("Contradictions or inconsistencies require an explanation when identified.")
            if follow_up_lead and not lead_description:
                raise ValueError("Lead description is required when a follow-up lead is generated.")
            require(outcome, "Interview outcome is required.")
            if outcome in {"NO_MATERIAL_INFORMATION", "PERSON_DISPUTED_ALLEGATION", "INTERVIEW_UNSUCCESSFUL", "OTHER"} and not outcome_explanation:
                raise ValueError("An explanation is required for unsuccessful or materially unhelpful interview outcomes.")
            return {
                "person_name": person_name,
                "role": role,
                "interview_date": interview_date,
                "interview_time": interview_time,
                "location_method": location_method,
                "interview_type": interview_type,
                "recordings": recording_uploads,
                "recording_uploads": [item.get("storage_reference") or item.get("filename") or "" for item in recording_uploads if item.get("storage_reference") or item.get("filename")],
                "interview_notes_uploads": note_uploads,
                "information_obtained": information,
                "contradictions": contradictions,
                "contradiction_explanation": contradiction_explanation or None,
                "follow_up_lead": follow_up_lead,
                "lead_description": lead_description or None,
                "outcome": outcome,
                "outcome_explanation": outcome_explanation or None,
            }

        if action_type == "EVIDENCE_REVIEW":
            if not any(key in data for key in {"selected_evidence_ids", "evidence_ids", "selected_evidence", "observation", "interpretation", "unknown_limitation", "consistency", "related_evidence_ids"}) and legacy_payload_present:
                evidence_reference = str(payload.get("evidence_id") or "").strip()
                if evidence_reference and evidence_reference not in case_evidence_ids:
                    raise ValueError("Evidence reference does not match any evidence item on this case.")
                return legacy_record_data(legacy_summary or None, legacy_description or None, legacy_result or None)
            raw_evidence_ids = self._as_list(data.get("selected_evidence_ids") or data.get("evidence_ids") or data.get("selected_evidence"))
            evidence_ids = []
            for item in raw_evidence_ids:
                if isinstance(item, dict):
                    normalized = self._extract_evidence_id(item)
                    if normalized:
                        evidence_ids.append(normalized)
                    continue
                text = str(item).strip()
                if text:
                    evidence_ids.append(text)
            evidence_ids = list(dict.fromkeys(evidence_ids))
            if not evidence_ids:
                raise ValueError("At least one existing evidence item must be selected for evidence review.")
            invalid = [item for item in evidence_ids if item not in case_evidence_ids]
            if invalid:
                raise ValueError("Evidence reference does not match any evidence item on this case.")
            observation = str(data.get("observation") or "").strip()
            interpretation = str(data.get("interpretation") or "").strip()
            unknown_limitation = str(data.get("unknown_limitation") or data.get("unknown") or data.get("limitations") or "").strip()
            consistency = str(data.get("consistency") or "").strip().upper()
            require(observation, "Observation is required.")
            require(interpretation, "Interpretation is required.")
            require(unknown_limitation, "Unknown or limitation is required.")
            require(consistency, "Evidence consistency status is required.")
            if consistency not in {"SUPPORTS_EXISTING_INFORMATION", "CONTRADICTS_EXISTING_INFORMATION", "PROVIDES_NEW_INFORMATION", "INCONCLUSIVE"}:
                raise ValueError("Evidence consistency value is not recognised.")
            return {
                "selected_evidence_ids": evidence_ids,
                "observation": observation,
                "interpretation": interpretation,
                "unknown_limitation": unknown_limitation,
                "consistency": consistency,
                "related_evidence_ids": [str(item).strip() for item in self._as_list(data.get("related_evidence_ids") or data.get("related_evidence")) if str(item).strip()],
            }

        if action_type == "EVIDENCE_COLLECTION":
            if not any(key in data for key in {"evidence_type", "source", "where_obtained", "date_time_obtained", "provider", "collection_method", "explanation", "uploads", "collected_evidence_items"}) and legacy_payload_present:
                return legacy_record_data(legacy_summary or None, legacy_description or None, legacy_result or None)

            collected_items = self._as_list(data.get("collected_evidence_items") or data.get("evidence_items") or data.get("items"))
            if collected_items:
                normalized_items = []
                for item in collected_items:
                    if not isinstance(item, dict):
                        continue
                    evidence_type = self._normalize_evidence_type(item.get("evidence_type") or data.get("evidence_type") or "")
                    description = str(item.get("description") or data.get("description") or "").strip()
                    source = str(item.get("source") or data.get("source") or "").strip()
                    date_time_obtained = str(item.get("date_time_obtained") or item.get("obtained_at") or data.get("date_time_obtained") or "").strip()
                    provider = str(item.get("provider") or item.get("person_institution_providing_it") or data.get("provider") or "").strip()
                    collection_method = str(item.get("collection_method") or data.get("collection_method") or "").strip().upper()
                    result = str(item.get("result") or data.get("result") or "").strip().upper()
                    explanation = str(item.get("explanation") or item.get("reason") or data.get("explanation") or "").strip()
                    single_upload = self._as_list(item.get("upload") or item.get("uploads") or data.get("uploads"))
                    require(evidence_type, "Evidence type is required.")
                    if evidence_type not in self.VALID_EVIDENCE_TYPES:
                        raise ValueError("Evidence type must be one of: PHOTO, VIDEO, DOCUMENT, AUDIO, WITNESS_STATEMENT, OTHER.")
                    require(description, "Evidence description is required.")
                    require(source, "Evidence source is required.")
                    require(date_time_obtained, "Date and time obtained is required.")
                    require(provider, "Person or institution providing the evidence is required.")
                    require(collection_method, "Collection method is required.")
                    require(result, "Collection result is required.")
                    if result not in {"OBTAINED", "PARTIALLY_OBTAINED", "REQUESTED_BUT_UNAVAILABLE", "REFUSED", "NO_LONGER_AVAILABLE", "OTHER"}:
                        raise ValueError("Collection result is not recognised.")
                    if result in {"PARTIALLY_OBTAINED", "REQUESTED_BUT_UNAVAILABLE", "REFUSED", "NO_LONGER_AVAILABLE", "OTHER"} and not explanation:
                        raise ValueError("An explanation is required when the evidence was not fully obtained.")
                    normalized_items.append(
                        {
                            "description": description,
                            "evidence_type": evidence_type,
                            "source": source,
                            "date_time_obtained": date_time_obtained,
                            "provider": provider,
                            "collection_method": collection_method,
                            "result": result,
                            "explanation": explanation or None,
                            "upload": single_upload[0] if single_upload else None,
                            "uploads": single_upload,
                        }
                    )
                if normalized_items:
                    return {
                        "collected_evidence_items": normalized_items,
                        "evidence_type": normalized_items[0]["evidence_type"],
                        "description": normalized_items[0]["description"],
                        "source": normalized_items[0]["source"],
                        "date_time_obtained": normalized_items[0]["date_time_obtained"],
                        "provider": normalized_items[0]["provider"],
                        "collection_method": normalized_items[0]["collection_method"],
                        "result": normalized_items[0]["result"],
                        "explanation": normalized_items[0]["explanation"],
                        "uploads": self._as_list(normalized_items[0].get("uploads") or normalized_items[0].get("upload")),
                    }

            evidence_type = self._normalize_evidence_type(data.get("evidence_type") or "")
            description = str(data.get("description") or "").strip()
            source = str(data.get("source") or "").strip()
            where_obtained = str(data.get("where_obtained") or "").strip()
            date_time_obtained = str(data.get("date_time_obtained") or data.get("obtained_at") or "").strip()
            provider = str(data.get("provider") or data.get("person_institution_providing_it") or "").strip()
            collection_method = str(data.get("collection_method") or "").strip().upper()
            result = str(data.get("result") or "").strip().upper()
            explanation = str(data.get("explanation") or data.get("reason") or "").strip()
            require(evidence_type, "Evidence type is required.")
            if evidence_type not in self.VALID_EVIDENCE_TYPES:
                raise ValueError("Evidence type must be one of: PHOTO, VIDEO, DOCUMENT, AUDIO, WITNESS_STATEMENT, OTHER.")
            require(description, "Evidence description is required.")
            require(source, "Evidence source is required.")
            require(where_obtained or date_time_obtained, "Where the evidence was obtained is required.")
            require(date_time_obtained, "Date and time obtained is required.")
            require(provider, "Person or institution providing the evidence is required.")
            require(collection_method, "Collection method is required.")
            require(result, "Collection result is required.")
            if result not in {"OBTAINED", "PARTIALLY_OBTAINED", "REQUESTED_BUT_UNAVAILABLE", "REFUSED", "NO_LONGER_AVAILABLE", "OTHER"}:
                raise ValueError("Collection result is not recognised.")
            if result in {"PARTIALLY_OBTAINED", "REQUESTED_BUT_UNAVAILABLE", "REFUSED", "NO_LONGER_AVAILABLE", "OTHER"} and not explanation:
                raise ValueError("An explanation is required when the evidence was not fully obtained.")
            return {
                "evidence_type": evidence_type,
                "description": description,
                "source": source,
                "where_obtained": where_obtained,
                "date_time_obtained": date_time_obtained,
                "provider": provider,
                "collection_method": collection_method,
                "result": result,
                "explanation": explanation or None,
                "uploads": self._as_list(data.get("uploads") or data.get("evidence_uploads") or data.get("uploaded_files") or data.get("upload")),
            }

        if action_type == "RECORD_REQUEST":
            if not any(key in data for key in {"record_type", "record_holder", "specific_record_requested", "date_range_from", "date_range_to", "reason_relevant", "date_requested", "request_reference", "request_method", "response_explanation"}) and legacy_payload_present:
                return legacy_record_data(legacy_summary or None, legacy_description or None, legacy_result or None)
            record_type = str(data.get("record_type") or "").strip()
            record_holder = str(data.get("record_holder") or data.get("record_holder_organisation") or "").strip()
            specific_record_requested = str(data.get("specific_record_requested") or data.get("specific_record") or "").strip()
            date_range_from = str(data.get("date_range_from") or "").strip()
            date_range_to = str(data.get("date_range_to") or "").strip()
            reason_relevant = str(data.get("reason_relevant") or "").strip()
            date_requested = str(data.get("date_requested") or "").strip()
            request_reference = str(data.get("request_reference") or data.get("request_ref") or "").strip()
            request_method = str(data.get("request_method") or "").strip().upper()
            response = str(data.get("response") or "").strip().upper()
            explanation = str(data.get("explanation") or data.get("response_explanation") or "").strip()
            require(record_type, "Requested record type is required.")
            require(record_holder, "Record holder or organisation is required.")
            require(specific_record_requested, "Specific record requested is required.")
            require(date_range_from or date_range_to, "A relevant date or date range is required.")
            require(reason_relevant, "The record's relevance is required.")
            require(date_requested, "Date requested is required.")
            require(request_reference, "Request reference number is required.")
            require(request_method, "Request method is required.")
            require(response, "Record request response status is required.")
            if response in {"NO_RESPONSE", "REFUSED", "UNAVAILABLE"} and not explanation:
                raise ValueError("An explanation is required when the record request has no response, is refused, or unavailable.")
            return {
                "record_type": record_type,
                "record_holder": record_holder,
                "specific_record_requested": specific_record_requested,
                "date_range_from": date_range_from or None,
                "date_range_to": date_range_to or None,
                "reason_relevant": reason_relevant,
                "date_requested": date_requested,
                "request_reference": request_reference,
                "request_method": request_method,
                "response": response,
                "response_explanation": explanation or None,
                "uploaded_records": self._as_list(data.get("uploaded_records") or data.get("response_uploads") or data.get("documents")),
            }

        if action_type == "SCENE_REVIEW":
            if not any(key in data for key in {"location", "scene_date", "scene_time", "persons_present", "scene_condition", "observations", "consistent_with_incident", "differed", "not_established", "visibility", "lighting", "access_points", "distances", "obstructions", "limitations"}) and legacy_payload_present:
                return legacy_record_data(legacy_summary or None, legacy_description or None, legacy_result or None)
            location = str(data.get("location") or "").strip()
            scene_date = str(data.get("scene_date") or data.get("date") or "").strip()
            scene_time = str(data.get("scene_time") or data.get("time") or "").strip()
            persons_present = str(data.get("persons_present") or "").strip()
            scene_condition = str(data.get("scene_condition") or "").strip()
            observations = str(data.get("observations") or "").strip()
            consistent_with_incident = str(data.get("consistent_with_incident") or "").strip()
            differed = str(data.get("differed") or "").strip()
            not_established = str(data.get("not_established") or data.get("what_could_not_be_established") or "").strip()
            visibility = str(data.get("visibility") or "").strip()
            lighting = str(data.get("lighting") or "").strip()
            access_points = str(data.get("access_points") or "").strip()
            distances = str(data.get("distances") or "").strip()
            obstructions = str(data.get("obstructions") or "").strip()
            limitations = str(data.get("limitations") or "").strip()
            require(location, "Scene location is required.")
            require(scene_date, "Scene date is required.")
            require(scene_time, "Scene time is required.")
            require(persons_present, "Persons present are required.")
            require(scene_condition, "Scene condition is required.")
            require(observations, "Observations are required.")
            require(consistent_with_incident, "What was consistent with the reported incident is required.")
            require(differed, "What differed is required.")
            require(not_established, "What could not be established is required.")
            require(visibility, "Visibility is required.")
            require(lighting, "Lighting is required.")
            require(access_points, "Access points are required.")
            require(distances, "Distances are required.")
            require(obstructions, "Obstructions are required.")
            require(limitations, "Limitations are required.")
            return {
                "location": location,
                "scene_date": scene_date,
                "scene_time": scene_time,
                "persons_present": persons_present,
                "scene_condition": scene_condition,
                "observations": observations,
                "consistent_with_incident": consistent_with_incident,
                "differed": differed,
                "not_established": not_established,
                "scene_material": self._as_list(data.get("scene_material") or data.get("material") or data.get("attachments")),
                "visibility": visibility,
                "lighting": lighting,
                "access_points": access_points,
                "distances": distances,
                "obstructions": obstructions,
                "limitations": limitations,
            }

        raise ValueError(f"Unsupported action type '{action_type}'.")

    def create_action(self, investigation_id, detective_id, payload=None):
        investigation = self.get_investigation(investigation_id)
        if investigation is None:
            raise ValueError("Investigation not found.")
        self._assert_authorized_detective(investigation, detective_id)
        self._assert_active_detective_assignment(investigation.get("case_reference"), detective_id)

        if investigation.get("status") not in {"OPEN", "IN_PROGRESS"}:
            raise ValueError("Investigation is not open for recordable actions.")
        if self.freeze_service and self.freeze_service.is_case_frozen(investigation.get("case_reference")):
            raise ValueError("Case is frozen and operational mutation is restricted.")

        if not isinstance(payload, dict):
            raise ValueError("Action payload must be a JSON object.")

        forbidden = {
            "action_id",
            "investigation_id",
            "case_reference",
            "detective_id",
            "actor_id",
            "created_at",
            "updated_at",
            "performed_at",
            "timestamp",
            "provenance",
            "audit_actor",
        }
        if forbidden.intersection(payload):
            raise ValueError("Action provenance and identity are server-controlled and cannot be overridden.")

        action_type = self._normalize_action_type(payload.get("action_type"))
        if not action_type:
            raise ValueError("Action type is required.")

        case = self._get_case(investigation.get("case_reference"))
        if case is None:
            raise ValueError("Docket not found.")

        evidence_id = payload.get("evidence_id")
        evidence_reference = None
        if evidence_id not in (None, ""):
            evidence_reference = str(evidence_id).strip()
            case_evidence_ids = {
                str(item.get("evidence_id"))
                for item in self._collect_authoritative_case_evidence(case)
                if isinstance(item, dict) and item.get("evidence_id")
            }
            if evidence_reference not in case_evidence_ids:
                raise ValueError("Evidence reference does not match any evidence item on this case.")

        record_data = self._validate_investigation_action_contract(action_type, payload, case)
        self._assert_required_action_not_duplicate(investigation_id, action_type)
        if action_type == "INTERVIEW":
            interview_number = self._next_interview_number(investigation_id)
            record_data["interview_number"] = interview_number
            record_data["interview_title"] = f"Interview {interview_number}"
            for index, entry in enumerate(record_data.get("recordings") or [], start=1):
                entry["recording_number"] = index
            if "recording_uploads" in record_data and not record_data.get("recordings"):
                record_data["recordings"] = self._coerce_recording_entries(record_data.get("recording_uploads"))
        purpose = str(payload.get("purpose") or "").strip() or self._build_action_summary(action_type, record_data)
        description = str(payload.get("description") or "").strip() or purpose
        raw_result = payload.get("result_observation")
        if raw_result is None:
            raw_result = payload.get("result")
        result = str(raw_result or "").strip() or self._build_action_result(action_type, record_data)

        now = self._utc_now()
        action = {
            "action_id": self._generate_action_id(len(self.action_repository.list()) + 1),
            "investigation_id": investigation.get("investigation_id"),
            "case_reference": investigation.get("case_reference"),
            "detective_id": detective_id,
            "action_type": action_type,
            "purpose": purpose,
            "description": description,
            "result": result,
            "record_data": record_data,
            "evidence_id": evidence_reference,
            "provenance": {
                "actor_id": str(detective_id),
                "actor_role": "detective",
                "source": "investigative_action",
                "performed_at": now,
                "created_at": now,
            },
            "performed_at": now,
            "created_at": now,
            "updated_at": now,
        }
        created = self.action_repository.create(action)
        serialized = dict(created)
        serialized["result_observation"] = serialized.get("result")
        if "record_data" not in serialized:
            serialized["record_data"] = record_data
        self.audit_service.log(
            {
                "actor_id": detective_id,
                "actor_role": "detective",
                "action": "investigative_action_created",
                "case_reference": investigation.get("case_reference"),
                "object_type": "investigation_action",
                "object_id": created.get("action_id"),
                "details": {
                    "investigation_id": investigation.get("investigation_id"),
                    "action_type": action_type,
                    "evidence_id": evidence_reference,
                },
            }
        )
        return serialized

    @staticmethod
    def _build_action_summary(action_type, record):
        if action_type == "WITNESS_CONTACT":
            witness = record.get("witness_name") or "Witness"
            outcome = record.get("result") or "contact recorded"
            return f"Contact {witness} and document the {outcome.lower()} outcome."
        if action_type == "INTERVIEW":
            person = record.get("person_name") or "relevant person"
            return f"Interview {person} and preserve the substantive account."
        if action_type == "EVIDENCE_REVIEW":
            items = record.get("selected_evidence_ids") or []
            ref = items[0] if items else "evidence"
            return f"Review existing evidence item {ref} for observation and interpretation."
        if action_type == "EVIDENCE_COLLECTION":
            return f"Collect new {record.get('evidence_type', 'evidence')} material under controlled chain-of-custody."
        if action_type == "RECORD_REQUEST":
            return f"Request {record.get('record_type', 'record')} from {record.get('record_holder', 'the relevant holder')}."
        if action_type == "SCENE_REVIEW":
            return f"Review the scene at {record.get('location', 'the relevant location')} for contextual observations and limitations."
        return f"Record the {action_type.lower().replace('_', ' ')} investigative action."

    @staticmethod
    def _build_action_result(action_type, record):
        if action_type == "WITNESS_CONTACT":
            return str(record.get("result") or "CONTACT_RECORDED")
        if action_type == "INTERVIEW":
            return str(record.get("outcome") or "INTERVIEW_RECORDED")
        if action_type == "EVIDENCE_REVIEW":
            return str(record.get("consistency") or "EVIDENCE_REVIEWED")
        if action_type == "EVIDENCE_COLLECTION":
            return str(record.get("result") or "EVIDENCE_COLLECTED")
        if action_type == "RECORD_REQUEST":
            return str(record.get("response") or "REQUEST_RECORDED")
        if action_type == "SCENE_REVIEW":
            return "SCENE_REVIEW_RECORDED"
        return "RECORD_CREATED"

    def list_actions_for_investigation(self, investigation_id, detective_id):
        investigation = self.get_investigation(investigation_id)
        self._assert_authorized_detective(investigation, detective_id)
        actions = []
        for item in self.action_repository.list_for_investigation(investigation_id):
            serialized = dict(item)
            if "result_observation" not in serialized and "result" in serialized:
                serialized["result_observation"] = serialized.get("result")
            if "record_data" not in serialized:
                serialized["record_data"] = {}
            actions.append(serialized)
        return actions

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

        outcome = str(payload.get("outcome") or "").strip().upper()
        if outcome in self.REJECTED_ADJUDICATIVE_VALUES:
            raise ValueError("Criminal guilt or innocence is not a valid investigative conclusion. Use VALID, INVALID, or REVIEW_REQUIRED.")
        if outcome not in self.VALID_OUTCOMES:
            raise ValueError("Outcome is invalid. Use VALID, INVALID, or REVIEW_REQUIRED.")

        final_notes = str(payload.get("final_notes") or payload.get("notes") or "").strip()
        if not final_notes:
            raise ValueError("Final reasoning is required.")

        existing_findings = [dict(item) for item in self.finding_repository.list_for_investigation(investigation_id)]
        case_evidence_ids = {str(item.get("evidence_id")) for item in (case.get("evidence") or []) if isinstance(item, dict) and item.get("evidence_id")}
        if not existing_findings and case_evidence_ids:
            raise ValueError("A real finding is required before the investigation can be completed when docket evidence exists.")

        referenced_finding_ids = self._normalize_string_list(payload.get("finding_ids"))
        if referenced_finding_ids:
            existing_finding_ids = {str(item.get("finding_id")) for item in existing_findings if isinstance(item, dict) and item.get("finding_id")}
            invalid_finding_ids = [finding_id for finding_id in referenced_finding_ids if finding_id not in existing_finding_ids]
            if invalid_finding_ids:
                raise ValueError("Finding references must match findings recorded for this investigation.")

        payload_with_findings = dict(payload)
        payload_with_findings["findings"] = existing_findings
        completion_gate = self._completion_gate()

        self._enforce_procedure_gate(investigation.get("case_reference"), detective_id, "complete_investigation")

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
                        "requested_outcome": outcome,
                        "findings_count": len(existing_findings),
                    },
                }
            )
            raise ValueError(completion_result.message)

        if existing_findings or case_evidence_ids:
            self._require_all_required_actions(investigation_id)

        final_finding = {
            "finding_id": self._generate_finding_id(len(self.finding_repository.list()) + 1),
            "investigation_id": investigation.get("investigation_id"),
            "case_reference": investigation.get("case_reference"),
            "detective_id": detective_id,
            "finding_type": outcome,
            "notes": final_notes,
            "reasoning": final_notes,
            "evidence_ids": [
                str(item)
                for finding in existing_findings
                for item in (finding.get("evidence_ids") or [])
            ],
            "action_ids": [
                str(item)
                for finding in existing_findings
                for item in (finding.get("action_ids") or [])
            ],
            "referenced_finding_ids": referenced_finding_ids,
            "claim_ids": [
                str(item)
                for finding in existing_findings
                for item in (finding.get("claim_ids") or [])
            ],
            "supporting_material": [
                item for finding in existing_findings for item in (finding.get("supporting_material") or [])
            ],
            "contradicting_material": [
                item for finding in existing_findings for item in (finding.get("contradicting_material") or [])
            ],
            "status": "SUBMITTED",
            "version": 1,
            "created_at": self._utc_now(),
            "updated_at": self._utc_now(),
            "is_final_outcome": True,
        }
        created_final_finding = self.finding_repository.create(final_finding)

        investigation["status"] = "COMPLETED"
        investigation["outcome"] = outcome
        investigation["final_notes"] = final_notes
        investigation["referenced_finding_ids"] = referenced_finding_ids
        investigation["completed_at"] = self._utc_now()
        investigation["updated_at"] = investigation["completed_at"]
        self.repository.update(investigation["id"], investigation)
        procedure_service = self._get_procedure_service()
        if procedure_service is not None and hasattr(procedure_service, "reconcile_investigation_state"):
            procedure_service.reconcile_investigation_state(
                investigation.get("case_reference"),
                actor_id=detective_id,
                actor_role="detective",
                investigation=investigation,
            )
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
                if procedure_service is not None and hasattr(procedure_service, "reconcile_investigation_state"):
                    procedure_service.reconcile_investigation_state(
                        saved.get("case_reference"),
                        actor_id=detective_id,
                        actor_role="detective",
                        investigation=saved,
                    )
            raise
        return dict(investigation)

    def add_findings(self, payload):
        return payload
