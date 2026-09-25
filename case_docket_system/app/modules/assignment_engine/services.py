"""Assignment engine service layer.

This engine owns assignment state, current assignment lookup, reassignment
lifecycle, and history while remaining reusable outside Station Commander
authority. The caller/service layer remains responsible for enforcing who is
allowed to perform a reassignment.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.auth.service import TestIdentityRegistry
from app.database.repositories.assignment_repository import AssignmentRepository
from app.modules.audit_engine.services import AuditTrailService
from app.modules.freeze_engine.services import FreezeService
from app.services.case_service import CaseService


class AssignmentService:
    """Shared operational assignment service for case-to-officer responsibility."""

    VALID_OFFICER_ROLES = {"constable", "detective"}

    def __init__(self, repository=None, case_service=None, identity_registry=None, audit_service=None, freeze_service=None):
        self.repository = repository or AssignmentRepository()
        self.case_service = case_service or CaseService()
        self.identity_registry = identity_registry or TestIdentityRegistry()
        self.audit_service = audit_service or AuditTrailService()
        self.freeze_service = freeze_service or FreezeService(case_service=self.case_service, audit_service=self.audit_service)

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _get_case(self, case_reference):
        if not case_reference:
            return None
        for case in self.case_service.get_all_cases():
            if case.get("case_reference") == case_reference:
                return case
        return None

    def _resolve_target_officer(self, officer_id, officer_role=None):
        if officer_id is None:
            raise ValueError("Target officer identity is required.")

        identity = self.identity_registry.get_identity(str(officer_id))
        if identity is None or not identity.get("active"):
            raise ValueError("Target officer not found.")
        if str(identity.get("access_state", "ACTIVE")).upper() == "REVOKED":
            raise ValueError("Target officer access has been revoked.")

        resolved_role = str(officer_role or identity.get("role") or "").lower()
        if resolved_role not in self.VALID_OFFICER_ROLES:
            raise ValueError("Target officer is not an eligible operational officer.")
        return resolved_role

    def _assert_assignable_status(self, case, resolved_role):
        status = case.get("status")
        if status == "REGISTERED":
            return
        if status == "AWAITING_CONSTABLE_REGISTRATION" and resolved_role == "constable":
            # A station commander can hand an unregistered docket to a specific
            # constable to take hold of before triage/registration happens.
            return
        raise ValueError(
            "Assignment requires a registered case, or a constable assignment to a docket still awaiting constable registration."
        )

    def get_current_assignment_for_case(self, case_reference):
        return self.repository.get_current_assignment_for_case(case_reference)

    def get_assignment_history_for_case(self, case_reference):
        return self.repository.get_history_for_case(case_reference)

    def query_assignments_by_officer(self, officer_id):
        return self.repository.query_by_officer(officer_id)

    def end_assignment(self, assignment_id, ended_by=None, ended_by_role=None, reason=None):
        assignment = self.repository.get_by_id(assignment_id)
        if assignment is None:
            raise ValueError("Assignment not found.")

        ended = self.repository.end_assignment(
            assignment_id,
            ended_by=ended_by,
            ended_by_role=ended_by_role,
            reason=reason,
        )
        if ended is not None:
            self.audit_service.log(
                {
                    "actor_id": ended_by,
                    "actor_role": ended_by_role,
                    "action": "assignment_ended",
                    "case_reference": ended.get("case_reference"),
                    "details": {
                        "assignment_id": ended.get("assignment_id"),
                        "officer_id": ended.get("officer_id"),
                        "officer_role": ended.get("officer_role"),
                        "previous_assignment_id": ended.get("previous_assignment_id"),
                        "reason": reason,
                    },
                }
            )
        return ended

    def create_assignment(
        self,
        case_reference,
        officer_id,
        officer_role=None,
        assigned_by=None,
        assigned_by_role=None,
        reason=None,
        override_authority=False,
    ):
        case = self._get_case(case_reference)
        if case is None:
            raise ValueError("Case not found.")
        if self.freeze_service and self.freeze_service.is_case_frozen(case_reference):
            raise ValueError("Case is frozen and operational mutation is restricted.")

        resolved_role = self._resolve_target_officer(officer_id, officer_role)
        self._assert_assignable_status(case, resolved_role)

        current = self.get_current_assignment_for_case(case_reference)
        if current and current.get("status") == "ACTIVE":
            if str(current.get("officer_id")) == str(officer_id):
                raise ValueError("This case is already assigned to this officer.")
            raise ValueError("An active assignment already exists for this case. Use create_replacement_assignment.")

        trusted_assigner = assigned_by if override_authority else None
        trusted_assigner_role = assigned_by_role if override_authority else None

        assignment = self.repository.create(
            {
                "case_reference": case_reference,
                "officer_id": str(officer_id),
                "officer_role": resolved_role,
                "assigned_by": trusted_assigner,
                "assigned_by_role": trusted_assigner_role,
                "assigned_at": self._utc_now(),
                "status": "ACTIVE",
                "reason": reason,
                "previous_assignment_id": None,
            }
        )
        self.audit_service.log(
            {
                "actor_id": trusted_assigner,
                "actor_role": trusted_assigner_role,
                "action": "assignment_created",
                "case_reference": case_reference,
                "details": {
                    "assignment_id": assignment.get("assignment_id"),
                    "officer_id": assignment.get("officer_id"),
                    "officer_role": assignment.get("officer_role"),
                    "assigned_by": trusted_assigner,
                    "assigned_by_role": trusted_assigner_role,
                    "reason": reason,
                },
            }
        )
        return assignment

    def create_replacement_assignment(
        self,
        case_reference,
        officer_id,
        officer_role=None,
        assigned_by=None,
        assigned_by_role=None,
        previous_assignment_id=None,
        reason=None,
        override_authority=False,
    ):
        case = self._get_case(case_reference)
        if case is None:
            raise ValueError("Case not found.")
        if self.freeze_service and self.freeze_service.is_case_frozen(case_reference):
            raise ValueError("Case is frozen and operational mutation is restricted.")

        resolved_role = self._resolve_target_officer(officer_id, officer_role)
        self._assert_assignable_status(case, resolved_role)

        current = self.get_current_assignment_for_case(case_reference)
        if current and current.get("status") == "ACTIVE":
            if str(current.get("officer_id")) == str(officer_id):
                raise ValueError("The case is already assigned to this officer.")
            previous_assignment_id = previous_assignment_id or current.get("assignment_id")

        trusted_assigner = assigned_by if override_authority else None
        trusted_assigner_role = assigned_by_role if override_authority else None

        if previous_assignment_id:
            self.end_assignment(
                previous_assignment_id,
                ended_by=trusted_assigner,
                ended_by_role=trusted_assigner_role,
                reason=reason or "Reassignment",
            )

        replacement = self.repository.create(
            {
                "case_reference": case_reference,
                "officer_id": str(officer_id),
                "officer_role": resolved_role,
                "assigned_by": trusted_assigner,
                "assigned_by_role": trusted_assigner_role,
                "assigned_at": self._utc_now(),
                "status": "ACTIVE",
                "reason": reason,
                "previous_assignment_id": previous_assignment_id,
            }
        )
        self.audit_service.log(
            {
                "actor_id": trusted_assigner,
                "actor_role": trusted_assigner_role,
                "action": "assignment_created",
                "case_reference": case_reference,
                "details": {
                    "assignment_id": replacement.get("assignment_id"),
                    "officer_id": replacement.get("officer_id"),
                    "officer_role": replacement.get("officer_role"),
                    "assigned_by": trusted_assigner,
                    "assigned_by_role": trusted_assigner_role,
                    "previous_assignment_id": previous_assignment_id,
                    "reason": reason,
                },
            }
        )
        return replacement
