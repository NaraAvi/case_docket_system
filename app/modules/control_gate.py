"""Reusable backend control gates for admission, freeze, and conflict checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ControlGateResult:
    """Outcome returned by a gate check.

    A gate can either allow or deny an action. Callers can use the boolean
    semantics directly or raise a ValueError once the gate result is evaluated.
    """

    allowed: bool
    gate: str
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self):
        if self.allowed:
            return "ALLOWED"
        code = str(self.code or "").upper()
        message = str(self.message or "").upper()
        if "REVIEW" in code or "REVIEW" in message:
            return "REVIEW_REQUIRED"
        return "BLOCKED"

    def __bool__(self):
        return self.allowed

    @classmethod
    def allow(cls, gate: str, code: str = "OK", message: str = "Allowed.", **details):
        return cls(True, gate, code, message, details)

    @classmethod
    def deny(cls, gate: str, code: str, message: str, **details):
        return cls(False, gate, code, message, details)

    def raise_for_block(self):
        if not self.allowed:
            raise ValueError(self.message)


class BaseControlGate:
    gate_name = "base"

    def __init__(self, freeze_service=None, conflict_service=None, assignment_service=None, audit_service=None, case_service=None):
        self.freeze_service = freeze_service
        self.conflict_service = conflict_service
        self.assignment_service = assignment_service
        self.audit_service = audit_service
        self.case_service = case_service

    @staticmethod
    def _case_reference_from_case(case):
        if isinstance(case, dict):
            return str(case.get("case_reference") or "")
        return str(case or "")

    def check(self, *args, **kwargs):
        raise NotImplementedError("Gate implementations must define check().")


class FreezeGate(BaseControlGate):
    """LEGAL_REQUIREMENT / SYSTEM_CONTROL: blocks operations when the case is under an active freeze."""

    gate_name = "freeze"

    def check(self, case_reference, actor_id=None, actor_role=None, operation="mutate"):
        case_reference = str(case_reference or "").strip()
        if not case_reference:
            return ControlGateResult.deny(self.gate_name, "CASE.MISSING", "Case reference is required.")
        if self.freeze_service is None or not self.freeze_service.is_case_frozen(case_reference):
            return ControlGateResult.allow(
                self.gate_name,
                "CASE.NOT_FROZEN",
                "Case is not frozen.",
                case_reference=case_reference,
                actor_id=actor_id,
                actor_role=actor_role,
                operation=operation,
            )
        return ControlGateResult.deny(
            self.gate_name,
            "CASE.FROZEN",
            "Case is frozen and operational mutation is restricted.",
            case_reference=case_reference,
            actor_id=actor_id,
            actor_role=actor_role,
            operation=operation,
        )


class ConflictGate(BaseControlGate):
    """LEGAL_REQUIREMENT / SYSTEM_CONTROL: wraps institutionally required recusal checks."""

    gate_name = "conflict"

    def check(self, case_reference, officer_id, operation="assignment", actor_id=None, actor_role=None):
        case_reference = str(case_reference or "").strip()
        officer_id = str(officer_id or "").strip()
        if not case_reference:
            return ControlGateResult.deny(self.gate_name, "CASE.MISSING", "Case reference is required.")
        if not officer_id:
            return ControlGateResult.deny(self.gate_name, "OFFICER.MISSING", "Officer identity is required.")
        if self.conflict_service is None:
            return ControlGateResult.allow(
                self.gate_name,
                "CONFLICT.NOT_CONFIGURED",
                "Conflict evaluation is not configured.",
                case_reference=case_reference,
                officer_id=officer_id,
                operation=operation,
            )
        try:
            evaluation = self.conflict_service.evaluate(case_reference, officer_id, operation)
        except ValueError as exc:
            return ControlGateResult.deny(self.gate_name, "CONFLICT.EVALUATION_FAILED", str(exc), case_reference=case_reference, officer_id=officer_id)

        if not evaluation.get("conflicted"):
            return ControlGateResult.allow(
                self.gate_name,
                evaluation.get("rule_code") or "CONFLICT.CLEAR",
                "Conflict check passed.",
                case_reference=case_reference,
                officer_id=officer_id,
                operation=operation,
                conflicts=[],
            )

        first_conflict = (evaluation.get("conflicts") or [{}])[0]
        message = first_conflict.get("reason") or "Conflict of interest: the officer is conflicted for this action."
        return ControlGateResult.deny(
            self.gate_name,
            first_conflict.get("rule_code") or "CASE.CONFLICT_OF_INTEREST",
            f"Conflict of interest: {message}",
            case_reference=case_reference,
            officer_id=officer_id,
            operation=operation,
            conflicts=evaluation.get("conflicts", []),
        )

    def enforce(self, case_reference, officer_id, operation="assignment", actor_id=None, actor_role=None):
        result = self.check(case_reference, officer_id, operation, actor_id, actor_role)
        result.raise_for_block()
        return result


class InterviewGate(BaseControlGate):
    """LEGAL_REQUIREMENT / SYSTEM_CONTROL: validates the interview lifecycle before registration.

    This gate enforces the controlled interview process from docket assignment to
    final registration eligibility without relying on the frontend state.
    """

    gate_name = "interview"

    @staticmethod
    def _recording_state(recording):
        if recording is None:
            return "MISSING"
        state = str(recording.get("integrity_state") or recording.get("recording_state") or recording.get("status") or "UPLOADED").upper()
        if state in {"REJECTED", "INTEGRITY_FAILURE", "FAILED", "INVALID"}:
            return "INTEGRITY_FAILURE"
        if state in {"SUBMITTED", "ACCEPTED", "VERIFIED", "UPLOADED"}:
            return state
        return state

    def check(self, interview=None, case=None, actor_id=None, actor_role=None, case_reference=None, action="validate"):
        """SYSTEM_CONTROL: authorize the interview and verify lifecycle state.

        Supported actions: start, submit_recording, register, validate.
        """
        case_reference = str(case_reference or self._case_reference_from_case(case) or (interview or {}).get("case_reference") or "").strip()
        if interview is None:
            if case is not None and case_reference:
                if self.conflict_service is not None and actor_role == "constable" and actor_id:
                    conflict_gate = ConflictGate(conflict_service=self.conflict_service)
                    conflict_result = conflict_gate.check(case_reference, actor_id, operation="open_docket", actor_id=actor_id, actor_role=actor_role)
                    if not conflict_result.allowed:
                        return conflict_result
            return ControlGateResult.deny(self.gate_name, "INTERVIEW.MISSING", "Interview not found.", case_reference=case_reference)

        interview_id = str(interview.get("interview_id") or "").strip()
        docket_case_reference = str(interview.get("case_reference") or "").strip()
        if case_reference and docket_case_reference and docket_case_reference != case_reference:
            return ControlGateResult.deny(
                self.gate_name,
                "INTERVIEW.DOCKET_MISMATCH",
                "Interview does not belong to the requested docket.",
                case_reference=case_reference,
                interview_id=interview_id,
                interview_case_reference=docket_case_reference,
            )
        if case is not None and str(case.get("case_reference") or "") and str(case.get("case_reference")) != case_reference:
            return ControlGateResult.deny(
                self.gate_name,
                "INTERVIEW.DOCKET_MISMATCH",
                "Case reference does not match the interview docket.",
                case_reference=case_reference,
                interview_id=interview_id,
            )
        if case is not None and case.get("interview_id") and interview_id and str(case.get("interview_id")) != interview_id:
            return ControlGateResult.deny(
                self.gate_name,
                "INTERVIEW.DOCKET_MISMATCH",
                "Interview is not the active interview for this docket.",
                case_reference=case_reference,
                interview_id=interview_id,
                case_interview_id=case.get("interview_id"),
            )

        if actor_id is not None and actor_role == "constable":
            if self.conflict_service is not None:
                conflict_gate = ConflictGate(conflict_service=self.conflict_service)
                conflict_result = conflict_gate.check(case_reference, actor_id, operation="open_docket", actor_id=actor_id, actor_role=actor_role)
                if not conflict_result.allowed:
                    return conflict_result
            if str(interview.get("constable_id") or "") != str(actor_id):
                return ControlGateResult.deny(
                    self.gate_name,
                    "INTERVIEW.AUTHORIZATION",
                    "Constable is not authorized for this interview.",
                    case_reference=case_reference,
                    actor_id=actor_id,
                )
        if actor_id is not None and actor_role == "citizen" and str(interview.get("citizen_id") or "") != str(actor_id):
            return ControlGateResult.deny(
                self.gate_name,
                "INTERVIEW.AUTHORIZATION",
                "Citizen is not authorized for this interview.",
                case_reference=case_reference,
                actor_id=actor_id,
            )

        if self.freeze_service and case_reference and self.freeze_service.is_case_frozen(case_reference):
            return ControlGateResult.deny(
                self.gate_name,
                "CASE.FROZEN",
                "Case is frozen and operational mutation is restricted.",
                case_reference=case_reference,
                actor_id=actor_id,
                actor_role=actor_role,
            )

        status = str(interview.get("status") or "").upper()
        if action in {"start", "submit_recording"} and status not in {"STARTED", "AWAITING_AUDIO"}:
            return ControlGateResult.deny(
                self.gate_name,
                "INTERVIEW.INVALID_STATE",
                "Interview lifecycle state is invalid for this action.",
                case_reference=case_reference,
                interview_id=interview_id,
                interview_status=status,
            )
        if action == "register" and status != "COMPLETED":
            return ControlGateResult.deny(
                self.gate_name,
                "INTERVIEW.INCOMPLETE",
                "Interview is incomplete.",
                case_reference=case_reference,
                interview_id=interview_id,
                interview_status=status,
            )

        citizen_recording = interview.get("citizen_recording")
        constable_recording = interview.get("constable_recording")

        for label, recording in (("citizen", citizen_recording), ("constable", constable_recording)):
            if recording is None:
                if action == "register":
                    return ControlGateResult.deny(
                        self.gate_name,
                        f"{label.upper()}.RECORDING.MISSING",
                        f"{label.title()} recording is missing.",
                        case_reference=case_reference,
                        interview_id=interview_id,
                    )
                continue
            if str(recording.get("case_reference") or case_reference) != case_reference:
                return ControlGateResult.deny(
                    self.gate_name,
                    f"{label.upper()}.RECORDING.DOCKET_MISMATCH",
                    f"{label.title()} recording belongs to a different docket.",
                    case_reference=case_reference,
                    interview_id=interview_id,
                    recording_case_reference=recording.get("case_reference"),
                )
            if str(recording.get("interview_id") or interview_id) != str(interview_id):
                return ControlGateResult.deny(
                    self.gate_name,
                    f"{label.upper()}.RECORDING.INTERVIEW_MISMATCH",
                    f"{label.title()} recording belongs to a different interview.",
                    case_reference=case_reference,
                    interview_id=interview_id,
                    recording_interview_id=recording.get("interview_id"),
                )
            recording_state = self._recording_state(recording)
            if recording_state == "INTEGRITY_FAILURE":
                return ControlGateResult.deny(
                    self.gate_name,
                    f"{label.upper()}.RECORDING.INTEGRITY_FAILURE",
                    f"{label.title()} recording integrity verification failed.",
                    case_reference=case_reference,
                    interview_id=interview_id,
                    recording_id=recording.get("recording_id"),
                    integrity_status=recording.get("integrity_status") or recording.get("status"),
                )
            if action == "register" and recording_state not in {"SUBMITTED", "ACCEPTED", "VERIFIED"}:
                return ControlGateResult.deny(
                    self.gate_name,
                    f"{label.upper()}.RECORDING.NOT_ACCEPTED",
                    f"{label.title()} recording is not accepted for this interview.",
                    case_reference=case_reference,
                    interview_id=interview_id,
                    recording_state=recording_state,
                )

        if action == "register":
            return ControlGateResult.allow(
                self.gate_name,
                "INTERVIEW.VALID",
                "Interview is complete and ready for registration.",
                case_reference=case_reference,
                interview_id=interview_id,
                interview_status=status,
            )

        return ControlGateResult.allow(
            self.gate_name,
            "INTERVIEW.ACTIVE",
            "Interview is active and continues within the authorized lifecycle.",
            case_reference=case_reference,
            interview_id=interview_id,
            interview_status=status,
        )


class RegistrationGate(BaseControlGate):
    """SYSTEM_CONTROL / SYSTEM_POLICY: combined gate for the registration mutation boundary."""

    gate_name = "registration"

    def check(self, case=None, interview=None, constable_id=None, actor_id=None, actor_role=None):
        case_reference = self._case_reference_from_case(case)
        if case is None:
            return ControlGateResult.deny(self.gate_name, "CASE.NOT_FOUND", "Docket not found.")

        if case.get("status") != "AWAITING_CONSTABLE_REGISTRATION":
            return ControlGateResult.deny(
                self.gate_name,
                "CASE.STATUS.INVALID",
                "Docket is not awaiting constable registration.",
                case_reference=case_reference,
                current_status=case.get("status"),
            )

        if constable_id is None:
            constable_id = actor_id
        if constable_id is None:
            return ControlGateResult.deny(self.gate_name, "OFFICER.MISSING", "Constable identity is required.")

        freeze_gate = FreezeGate(freeze_service=self.freeze_service)
        freeze_result = freeze_gate.check(case_reference, actor_id=constable_id, actor_role=actor_role or "constable", operation="register")
        if not freeze_result.allowed:
            return freeze_result

        if self.conflict_service is not None:
            conflict_gate = ConflictGate(conflict_service=self.conflict_service)
            conflict_result = conflict_gate.check(
                case_reference,
                constable_id,
                operation="open_docket",
                actor_id=constable_id,
                actor_role=actor_role or "constable",
            )
            if not conflict_result.allowed:
                return conflict_result

        if interview is None and case.get("interview_id"):
            return ControlGateResult.deny(self.gate_name, "INTERVIEW.MISSING", "Interview not found.", case_reference=case_reference)
        if interview is None:
            return ControlGateResult.deny(self.gate_name, "INTERVIEW.MISSING", "Interview not found.", case_reference=case_reference)

        interview_gate = InterviewGate(freeze_service=self.freeze_service)
        interview_result = interview_gate.check(
            interview=interview,
            case=case,
            actor_id=constable_id,
            actor_role="constable",
            case_reference=case_reference,
            action="register",
        )
        if not interview_result.allowed:
            return interview_result

        return ControlGateResult.allow(
            self.gate_name,
            "REGISTRATION.ALLOWED",
            "Registration checks passed.",
            case_reference=case_reference,
            constable_id=constable_id,
            interview_id=interview.get("interview_id"),
        )

    def enforce(self, case=None, interview=None, constable_id=None, actor_id=None, actor_role=None):
        result = self.check(case=case, interview=interview, constable_id=constable_id, actor_id=actor_id, actor_role=actor_role)
        result.raise_for_block()
        return result


class InvestigationGate(BaseControlGate):
    """SYSTEM_CONTROL: validate detective investigation admission before any mutation."""

    gate_name = "investigation"

    def check(self, case=None, case_reference=None, detective_id=None, actor_id=None, actor_role=None, action="start", investigation=None):
        case_reference = str(case_reference or self._case_reference_from_case(case) or "").strip()
        if not case_reference:
            return ControlGateResult.deny(self.gate_name, "CASE.MISSING", "Case reference is required.")

        if case is None and self.case_service is not None:
            case = self.case_service.get_case(case_reference)
        if case is None:
            return ControlGateResult.deny(self.gate_name, "CASE.NOT_FOUND", "Docket not found.", case_reference=case_reference)

        if str(case.get("status") or "").upper() != "REGISTERED":
            return ControlGateResult.deny(
                self.gate_name,
                "CASE.STATUS.INVALID",
                "Detective investigation can only start for a registered docket.",
                case_reference=case_reference,
                current_status=case.get("status"),
            )

        if actor_id is None:
            actor_id = detective_id
        if actor_id is None:
            return ControlGateResult.deny(self.gate_name, "OFFICER.MISSING", "Detective identity is required.")

        if self.assignment_service is not None:
            current_assignment = self.assignment_service.get_current_assignment_for_case(case_reference)
            if current_assignment is None or str(current_assignment.get("status") or "").upper() != "ACTIVE":
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE.ASSIGNMENT.MISSING",
                    "Detective investigation requires an active assignment to this docket.",
                    case_reference=case_reference,
                    detective_id=str(actor_id),
                )
            if str(current_assignment.get("officer_role") or "").lower() != "detective":
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE.ASSIGNMENT.ROLE_INVALID",
                    "The active assignment for this docket is not held by a detective.",
                    case_reference=case_reference,
                    detective_id=str(actor_id),
                    assigned_officer_id=current_assignment.get("officer_id"),
                    assigned_officer_role=current_assignment.get("officer_role"),
                )
            if str(current_assignment.get("officer_id") or "") != str(actor_id):
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE.ASSIGNMENT.AUTHORIZATION",
                    "Detective is not the assigned officer for this docket.",
                    case_reference=case_reference,
                    detective_id=str(actor_id),
                    assigned_officer_id=current_assignment.get("officer_id"),
                    assigned_officer_role=current_assignment.get("officer_role"),
                )

        freeze_gate = FreezeGate(freeze_service=self.freeze_service)
        freeze_result = freeze_gate.check(case_reference, actor_id=actor_id, actor_role=(actor_role or "detective"), operation="investigate")
        if not freeze_result.allowed:
            return freeze_result

        if self.conflict_service is not None:
            try:
                self.conflict_service.assert_no_conflict(
                    case_reference,
                    str(actor_id),
                    operation="open_investigation",
                    actor_id=actor_id,
                    actor_role=(actor_role or "detective"),
                )
            except ValueError as exc:
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE.CONFLICT_OF_INTEREST",
                    str(exc),
                    case_reference=case_reference,
                    detective_id=str(actor_id),
                )

        if action == "start" and investigation is not None:
            return ControlGateResult.deny(
                self.gate_name,
                "INVESTIGATION.EXISTS",
                "An active investigation already exists for this docket.",
                case_reference=case_reference,
                investigation_id=investigation.get("investigation_id"),
            )

        return ControlGateResult.allow(
            self.gate_name,
            "INVESTIGATION.ALLOWED",
            "Investigation gate checks passed.",
            case_reference=case_reference,
            detective_id=str(actor_id),
            action=action,
        )


class CaseCreationGate(BaseControlGate):
    """CONTROL_BOUNDARY: an IncidentCandidate is never auto-promoted into a procedural case.

    The gate returns the structured outcome expected by the workflow: ALLOWED,
    BLOCKED, or REVIEW_REQUIRED. Only an explicit, gate-checked conversion is
    allowed to create a CaseDocket from an incident candidate; the underlying
    case model remains the existing CaseDocket and is never replaced with a
    competing procedural model.
    """

    gate_name = "case_creation"

    def check(self, candidate=None, submission=None, actor_id=None, actor_role=None, case_reference=None, candidate_id=None, submission_id=None):
        candidate_id = str(candidate_id or (candidate or {}).get("candidate_id") or "").strip()
        submission_id = str(submission_id or (submission or {}).get("submission_id") or "").strip()
        if not candidate_id:
            return ControlGateResult.deny(
                self.gate_name,
                "CASE_CREATION.CANDIDATE_MISSING",
                "Incident candidate is required before a procedural case can be created.",
                actor_id=actor_id,
                actor_role=actor_role,
            )

        if not submission_id:
            return ControlGateResult.deny(
                self.gate_name,
                "CASE_CREATION.SUBMISSION_MISSING",
                "Source submission is required before a procedural case can be created.",
                actor_id=actor_id,
                actor_role=actor_role,
            )

        if candidate is not None:
            if str((candidate or {}).get("source_actor_id") or "").strip() and actor_id and str((candidate or {}).get("source_actor_id") or "") != str(actor_id):
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE_CREATION.AUTHORIZATION",
                    "Citizen cannot create a case from another citizen's incident candidate.",
                    candidate_id=candidate_id,
                    submission_id=submission_id,
                    actor_id=actor_id,
                    actor_role=actor_role,
                )

            if not (candidate or {}).get("source_claim_ids"):
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE_CREATION.CLAIMS_MISSING",
                    "Candidate lacks claim provenance and cannot advance to a procedural case.",
                    candidate_id=candidate_id,
                    submission_id=submission_id,
                    actor_id=actor_id,
                    actor_role=actor_role,
                )

            if not (candidate or {}).get("source_submission_ids"):
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE_CREATION.SOURCE_MISSING",
                    "Candidate is missing source submission references.",
                    candidate_id=candidate_id,
                    submission_id=submission_id,
                    actor_id=actor_id,
                    actor_role=actor_role,
                )

            candidate_status = str((candidate or {}).get("status") or "").upper()
            relationship_summary = (candidate or {}).get("deterministic_basis", {}).get("relationship_summary") or {}
            try:
                duplicate_count = int(relationship_summary.get("duplicate_count") or 0)
            except (TypeError, ValueError):
                duplicate_count = 0
            if candidate_status in {"REVIEW_REQUIRED", "BLOCKED"} or duplicate_count > 0:
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE_CREATION.REVIEW_REQUIRED",
                    "The incident candidate requires review before creation of a procedural case because it is tied to duplicate or uncertain clustering.",
                    candidate_id=candidate_id,
                    submission_id=submission_id,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    reason="duplicate_cluster_requires_review",
                    duplicate_count=duplicate_count,
                )

        if self.case_service is not None:
            existing_cases = self.case_service.get_all_cases() or []
            for case in existing_cases:
                if case is None:
                    continue
                if str(case.get("source_candidate_id") or "").strip() == candidate_id:
                    return ControlGateResult.deny(
                        self.gate_name,
                        "CASE_CREATION.ALREADY_CREATED",
                        "A procedural case already exists for this incident candidate.",
                        candidate_id=candidate_id,
                        submission_id=submission_id,
                        case_reference=case.get("case_reference"),
                        actor_id=actor_id,
                        actor_role=actor_role,
                    )
                if str(case.get("source_submission_id") or "").strip() == submission_id:
                    return ControlGateResult.deny(
                        self.gate_name,
                        "CASE_CREATION.ALREADY_CREATED",
                        "A procedural case already exists for this submission.",
                        candidate_id=candidate_id,
                        submission_id=submission_id,
                        case_reference=case.get("case_reference"),
                        actor_id=actor_id,
                        actor_role=actor_role,
                    )

        return ControlGateResult.allow(
            self.gate_name,
            "CASE_CREATION.ALLOWED",
            "Candidate met the controlled procedural-case gate requirements.",
            candidate_id=candidate_id,
            submission_id=submission_id,
            actor_id=actor_id,
            actor_role=actor_role,
            allowed_case_creation=True,
            enforcement="existing_case_docket",
        )

    def enforce(self, candidate=None, submission=None, actor_id=None, actor_role=None, case_reference=None, candidate_id=None, submission_id=None):
        result = self.check(
            candidate=candidate,
            submission=submission,
            actor_id=actor_id,
            actor_role=actor_role,
            case_reference=case_reference,
            candidate_id=candidate_id,
            submission_id=submission_id,
        )
        result.raise_for_block()
        return result


class FindingGate(BaseControlGate):
    """SYSTEM_CONTROL: finding creation requires assigned detective authority and a valid case/investigation state."""

    gate_name = "finding"

    def check(self, case=None, investigation=None, case_reference=None, detective_id=None, actor_id=None, actor_role=None, payload=None):
        case_reference = str(case_reference or self._case_reference_from_case(case) or (investigation or {}).get("case_reference") or "").strip()
        if not case_reference:
            return ControlGateResult.deny(self.gate_name, "CASE.MISSING", "Case reference is required.")

        if case is None and self.case_service is not None:
            case = self.case_service.get_case(case_reference)
        if case is None:
            return ControlGateResult.deny(self.gate_name, "CASE.NOT_FOUND", "Docket not found.", case_reference=case_reference)
        if investigation is None:
            return ControlGateResult.deny(self.gate_name, "INVESTIGATION.MISSING", "Investigation not found.", case_reference=case_reference)

        if actor_id is None:
            actor_id = detective_id
        if actor_id is None:
            return ControlGateResult.deny(self.gate_name, "OFFICER.MISSING", "Detective identity is required.")
        if str((investigation or {}).get("detective_id") or "") != str(actor_id):
            return ControlGateResult.deny(
                self.gate_name,
                "INVESTIGATION.AUTHORIZATION",
                "Detective is not authorized for this investigation.",
                case_reference=case_reference,
                detective_id=str(actor_id),
            )
        if str((case or {}).get("case_reference") or "") != case_reference:
            return ControlGateResult.deny(
                self.gate_name,
                "CASE.MISMATCH",
                "Case reference does not match the investigation docket.",
                case_reference=case_reference,
                investigation_id=(investigation or {}).get("investigation_id"),
            )
        if str((investigation or {}).get("case_reference") or "") != case_reference:
            return ControlGateResult.deny(
                self.gate_name,
                "INVESTIGATION.CASE_MISMATCH",
                "Investigation is attached to a different case.",
                case_reference=case_reference,
                investigation_id=(investigation or {}).get("investigation_id"),
            )
        if str((case or {}).get("status") or "").upper() != "REGISTERED":
            return ControlGateResult.deny(
                self.gate_name,
                "CASE.STATUS.INVALID",
                "Finding creation requires a registered docket.",
                case_reference=case_reference,
                current_status=(case or {}).get("status"),
            )
        if str((investigation or {}).get("status") or "").upper() not in {"OPEN", "IN_PROGRESS"}:
            return ControlGateResult.deny(
                self.gate_name,
                "INVESTIGATION.STATUS.INVALID",
                "Investigation is not open for new findings.",
                case_reference=case_reference,
                investigation_status=(investigation or {}).get("status"),
            )

        freeze_gate = FreezeGate(freeze_service=self.freeze_service)
        freeze_result = freeze_gate.check(case_reference, actor_id=actor_id, actor_role=(actor_role or "detective"), operation="record_finding")
        if not freeze_result.allowed:
            return freeze_result

        if self.conflict_service is not None:
            try:
                self.conflict_service.assert_no_conflict(
                    case_reference,
                    str(actor_id),
                    operation="open_investigation",
                    actor_id=actor_id,
                    actor_role=(actor_role or "detective"),
                )
            except ValueError as exc:
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE.CONFLICT_OF_INTEREST",
                    str(exc),
                    case_reference=case_reference,
                    detective_id=str(actor_id),
                )

        if self.assignment_service is not None:
            current_assignment = self.assignment_service.get_current_assignment_for_case(case_reference)
            if current_assignment is None or str(current_assignment.get("status") or "").upper() != "ACTIVE":
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE.ASSIGNMENT.MISSING",
                    "Detective finding requires an active assignment to this docket.",
                    case_reference=case_reference,
                    detective_id=str(actor_id),
                )
            if str(current_assignment.get("officer_role") or "").lower() != "detective":
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE.ASSIGNMENT.ROLE_INVALID",
                    "The active assignment for this docket is not held by a detective.",
                    case_reference=case_reference,
                    detective_id=str(actor_id),
                )
            if str(current_assignment.get("officer_id") or "") != str(actor_id):
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE.ASSIGNMENT.AUTHORIZATION",
                    "Detective is not the assigned officer for this docket.",
                    case_reference=case_reference,
                    detective_id=str(actor_id),
                )

        if payload is not None and not isinstance(payload, dict):
            return ControlGateResult.deny(self.gate_name, "FINDING.PAYLOAD.INVALID", "Finding payload must be a JSON object.")

        return ControlGateResult.allow(
            self.gate_name,
            "FINDING.ALLOWED",
            "Finding creation checks passed.",
            case_reference=case_reference,
            detective_id=str(actor_id),
            investigation_id=(investigation or {}).get("investigation_id"),
        )

    def enforce(self, case=None, investigation=None, case_reference=None, detective_id=None, actor_id=None, actor_role=None, payload=None):
        result = self.check(
            case=case,
            investigation=investigation,
            case_reference=case_reference,
            detective_id=detective_id,
            actor_id=actor_id,
            actor_role=actor_role,
            payload=payload,
        )
        result.raise_for_block()
        return result


class InvestigationCompletionGate(BaseControlGate):
    """SYSTEM_CONTROL: completion is allowed only for an authorized, active investigation in the current procedural state."""

    gate_name = "investigation_completion"

    @staticmethod
    def _as_list(value):
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, tuple):
            return [str(item) for item in value]
        if isinstance(value, set):
            return [str(item) for item in sorted(value)]
        return [str(value)]

    def check(self, case=None, investigation=None, case_reference=None, detective_id=None, actor_id=None, actor_role=None, payload=None):
        case_reference = str(case_reference or self._case_reference_from_case(case) or (investigation or {}).get("case_reference") or "").strip()
        if not case_reference:
            return ControlGateResult.deny(self.gate_name, "CASE.MISSING", "Case reference is required.")

        if case is None and self.case_service is not None:
            case = self.case_service.get_case(case_reference)
        if case is None:
            return ControlGateResult.deny(self.gate_name, "CASE.NOT_FOUND", "Docket not found.", case_reference=case_reference)
        if investigation is None:
            return ControlGateResult.deny(self.gate_name, "INVESTIGATION.MISSING", "Investigation not found.", case_reference=case_reference)

        if actor_id is None:
            actor_id = detective_id
        if actor_id is None:
            return ControlGateResult.deny(self.gate_name, "OFFICER.MISSING", "Detective identity is required.")

        if str((investigation or {}).get("detective_id") or "") != str(actor_id):
            return ControlGateResult.deny(
                self.gate_name,
                "INVESTIGATION.AUTHORIZATION",
                "Detective is not authorized for this investigation.",
                case_reference=case_reference,
                detective_id=str(actor_id),
            )

        if str((investigation or {}).get("status") or "").upper() not in {"OPEN", "IN_PROGRESS"}:
            return ControlGateResult.deny(
                self.gate_name,
                "INVESTIGATION.STATUS.INVALID",
                "Investigation is not in a completable state.",
                case_reference=case_reference,
                investigation_status=(investigation or {}).get("status"),
            )

        if str((case or {}).get("status") or "").upper() != "REGISTERED":
            return ControlGateResult.deny(
                self.gate_name,
                "CASE.STATUS.INVALID",
                "Investigation completion requires a registered docket.",
                case_reference=case_reference,
                current_status=(case or {}).get("status"),
            )

        if self.assignment_service is not None:
            current_assignment = self.assignment_service.get_current_assignment_for_case(case_reference)
            if current_assignment is None or str(current_assignment.get("status") or "").upper() != "ACTIVE":
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE.ASSIGNMENT.MISSING",
                    "Investigation completion requires an active detective assignment to this docket.",
                    case_reference=case_reference,
                    detective_id=str(actor_id),
                )
            if str(current_assignment.get("officer_role") or "").lower() != "detective":
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE.ASSIGNMENT.ROLE_INVALID",
                    "The active assignment for this docket is not held by a detective.",
                    case_reference=case_reference,
                    detective_id=str(actor_id),
                    assigned_officer_role=current_assignment.get("officer_role"),
                )
            if str(current_assignment.get("officer_id") or "") != str(actor_id):
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE.ASSIGNMENT.AUTHORIZATION",
                    "Detective is not the assigned officer for this docket.",
                    case_reference=case_reference,
                    detective_id=str(actor_id),
                    assigned_officer_id=current_assignment.get("officer_id"),
                )

        freeze_gate = FreezeGate(freeze_service=self.freeze_service)
        freeze_result = freeze_gate.check(case_reference, actor_id=actor_id, actor_role=(actor_role or "detective"), operation="complete_investigation")
        if not freeze_result.allowed:
            return freeze_result

        if self.conflict_service is not None:
            try:
                self.conflict_service.assert_no_conflict(
                    case_reference,
                    str(actor_id),
                    operation="complete_investigation",
                    actor_id=actor_id,
                    actor_role=(actor_role or "detective"),
                )
            except ValueError as exc:
                return ControlGateResult.deny(
                    self.gate_name,
                    "CASE.CONFLICT_OF_INTEREST",
                    str(exc),
                    case_reference=case_reference,
                    detective_id=str(actor_id),
                )

        if not isinstance(payload, dict):
            return ControlGateResult.deny(self.gate_name, "INVESTIGATION.PAYLOAD.INVALID", "Completion payload must be a JSON object.")

        payload = dict(payload)
        for key in {"status", "completed", "completed_at", "investigation_id", "case_reference", "case_id", "detective_id", "actor_id", "officer_id", "investigator_id", "created_at", "updated_at", "previous_state", "new_state"}:
            payload.pop(key, None)

        final_notes = str(payload.get("final_notes") or payload.get("notes") or "").strip()
        if not final_notes:
            return ControlGateResult.deny(self.gate_name, "INVESTIGATION.FINAL_REASONING_REQUIRED", "Final reasoning is required.")

        outcome = str(payload.get("outcome") or "").strip().upper()
        if not outcome:
            return ControlGateResult.deny(self.gate_name, "INVESTIGATION.OUTCOME_REQUIRED", "Outcome is required.")
        if outcome in {"GUILTY", "NOT_GUILTY"}:
            return ControlGateResult.deny(
                self.gate_name,
                "INVESTIGATION.OUTCOME.SEMANTIC_BLOCKED",
                "Criminal guilt or innocence is not a valid investigative conclusion. Use VALID, INVALID, or REVIEW_REQUIRED.",
                case_reference=case_reference,
                outcome=outcome,
            )
        if outcome not in {"VALID", "INVALID", "REVIEW_REQUIRED"}:
            return ControlGateResult.deny(
                self.gate_name,
                "INVESTIGATION.OUTCOME.INVALID",
                "Outcome is invalid. Use VALID, INVALID, or REVIEW_REQUIRED.",
                case_reference=case_reference,
                outcome=outcome,
            )

        findings = payload.get("findings") or []
        case_evidence = (case or {}).get("evidence") or []
        case_evidence_ids = {str(item.get("evidence_id")) for item in case_evidence if isinstance(item, dict) and item.get("evidence_id")}

        finding_evidence = set()
        for item in findings:
            if not isinstance(item, dict):
                continue
            for evidence_id in self._as_list(item.get("evidence_ids")):
                finding_evidence.add(str(evidence_id))

        if case_evidence_ids and not findings:
            return ControlGateResult.deny(
                self.gate_name,
                "INVESTIGATION.FINDING_REQUIRED",
                "At least one real finding is required before completion when docket evidence exists.",
                case_reference=case_reference,
                required_evidence_ids=sorted(case_evidence_ids),
            )

        if case_evidence_ids and not finding_evidence.intersection(case_evidence_ids):
            return ControlGateResult.deny(
                self.gate_name,
                "INVESTIGATION.EVIDENCE_LINKAGE_REQUIRED",
                "All docket evidence must be linked to a finding before completion.",
                case_reference=case_reference,
                required_evidence_ids=sorted(case_evidence_ids),
                linked_evidence_ids=sorted(finding_evidence),
            )

        return ControlGateResult.allow(
            self.gate_name,
            "INVESTIGATION.COMPLETION_ALLOWED",
            "Completion checks passed.",
            case_reference=case_reference,
            detective_id=str(actor_id),
            outcome=outcome,
            previous_status=(investigation or {}).get("status"),
            new_status="COMPLETED",
        )

    def enforce(self, case=None, investigation=None, case_reference=None, detective_id=None, actor_id=None, actor_role=None, payload=None):
        result = self.check(
            case=case,
            investigation=investigation,
            case_reference=case_reference,
            detective_id=detective_id,
            actor_id=actor_id,
            actor_role=actor_role,
            payload=payload,
        )
        result.raise_for_block()
        return result
