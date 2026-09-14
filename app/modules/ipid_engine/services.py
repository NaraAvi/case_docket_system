"""IPID orchestration service layer."""

from __future__ import annotations

from datetime import UTC, datetime

from app.auth.service import TestIdentityRegistry
from app.database.repositories.review_finding_repository import ReviewFindingRepository
from app.database.repositories.review_note_repository import ReviewNoteRepository
from app.modules.audit_engine.services import AuditTrailService
from app.modules.discipline_engine.services import DisciplinaryCaseService
from app.modules.escalation_engine.services import EscalationService
from app.services.case_service import CaseService


class IPIDReviewService:
    """Boundary for escalation review and read-only case context checks."""

    def __init__(
        self,
        case_service=None,
        audit_service=None,
        escalation_service=None,
        assignment_service=None,
        freeze_service=None,
        constable_service=None,
        investigation_service=None,
        review_note_repository=None,
        review_finding_repository=None,
        identity_registry=None,
        disciplinary_service=None,
    ):
        self.case_service = case_service or CaseService()
        self.audit_service = audit_service or AuditTrailService()
        self.escalation_service = escalation_service or EscalationService(audit_service=self.audit_service)
        self.assignment_service = assignment_service
        self.freeze_service = freeze_service
        self.constable_service = constable_service
        self.investigation_service = investigation_service
        self.review_note_repository = review_note_repository or ReviewNoteRepository()
        self.review_finding_repository = review_finding_repository or ReviewFindingRepository()
        self.identity_registry = identity_registry or TestIdentityRegistry()
        self.disciplinary_service = disciplinary_service or DisciplinaryCaseService(audit_service=self.audit_service)

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _get_case_summary(self, case_reference):
        if not case_reference:
            return None
        for case in self.case_service.get_all_cases():
            if case.get("case_reference") == case_reference:
                return dict(case)
        return None

    def _build_case_context(self, case_reference):
        case_summary = self._get_case_summary(case_reference)
        if case_summary is None:
            return {}

        context = {
            "case_reference": case_reference,
            "citizen_id": case_summary.get("citizen_id"),
            "title": case_summary.get("title"),
            "description": case_summary.get("description"),
            "status": case_summary.get("status"),
            "incident_date": case_summary.get("incident_date"),
            "location": case_summary.get("location"),
            "statements": list(case_summary.get("statements", [])),
            "evidence": list(case_summary.get("evidence", [])),
            "timeline": list(case_summary.get("timeline", [])),
            "interview_id": case_summary.get("interview_id"),
        }

        if self.assignment_service is not None:
            current_assignment = self.assignment_service.get_current_assignment_for_case(case_reference)
            context["current_assignment"] = current_assignment
            if current_assignment:
                context["assigned_officer_id"] = current_assignment.get("officer_id")
                context["assigned_officer_role"] = current_assignment.get("officer_role")
            context["assignment_history"] = self.assignment_service.get_assignment_history_for_case(case_reference)

        if self.freeze_service is not None:
            freeze_record = self.freeze_service.get_current_freeze(case_reference)
            context["freeze_record"] = freeze_record
            context["freeze_status"] = "FROZEN" if freeze_record else "NOT_FROZEN"
            context["is_frozen"] = bool(freeze_record)

        if self.constable_service is not None:
            context["flags"] = self.constable_service.list_flags_for_case(case_reference)
            context["related_cases"] = self.constable_service.list_related_cases(case_reference)

        if self.investigation_service is not None:
            investigations = self.investigation_service.repository.list_for_case(case_reference)
            context["investigations"] = investigations
            context["latest_investigation"] = investigations[-1] if investigations else None

        return context

    def list_queue(self, status=None):
        escalations = self.escalation_service.list_queue(status=status)
        return self.escalation_service.public_list(escalations)

    def get_escalation_detail(self, escalation_id):
        escalation = self.escalation_service.get_by_id(escalation_id)
        if escalation is None:
            raise ValueError("Escalation not found.")

        case_reference = escalation.get("case_reference")
        case_summary = self._get_case_summary(case_reference)

        summary = dict(escalation)
        summary["case_status"] = case_summary.get("status") if case_summary else None
        summary["assigned_officer_id"] = None
        summary["assigned_officer_role"] = None
        summary["freeze_status"] = "NOT_FROZEN"
        summary["audit_summary"] = []

        if case_summary and self.assignment_service is not None:
            assignment = self.assignment_service.get_current_assignment_for_case(case_reference)
            if assignment:
                summary["assigned_officer_id"] = assignment.get("officer_id")
                summary["assigned_officer_role"] = assignment.get("officer_role")
                summary["assignment_history"] = self.assignment_service.get_assignment_history_for_case(case_reference)

        if case_reference and self.freeze_service is not None:
            summary["freeze_status"] = "FROZEN" if self.freeze_service.is_case_frozen(case_reference) else "NOT_FROZEN"
            summary["freeze_record"] = self.freeze_service.get_current_freeze(case_reference)

        if case_reference:
            summary["audit_summary"] = self.audit_service.get_for_case(case_reference)[:10]

        return summary

    def list_review_notes(self, escalation_id):
        return [dict(item) for item in self.review_note_repository.list_for_escalation(escalation_id)]

    def add_review_note(self, escalation_id, actor_id, payload=None):
        escalation = self.escalation_service.get_by_id(escalation_id)
        if escalation is None:
            raise ValueError("Escalation not found.")

        if not isinstance(payload, dict):
            raise ValueError("Review note payload must be a JSON object.")

        note_text = str(payload.get("note") or payload.get("note_text") or "").strip()
        if not note_text:
            raise ValueError("Review note is required.")

        note = {
            "escalation_id": escalation_id,
            "case_reference": escalation.get("case_reference"),
            "author_id": actor_id,
            "author_role": "ipid",
            "note_text": note_text,
        }
        created = self.review_note_repository.create(note)
        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": "ipid",
                "action": "ipid_review_note_added",
                "case_reference": escalation.get("case_reference"),
                "details": {"escalation_id": escalation_id, "note_id": created.get("note_id")},
            }
        )
        return dict(created)

    def list_review_findings(self, escalation_id):
        return [dict(item) for item in self.review_finding_repository.list_for_escalation(escalation_id)]

    def add_review_finding(self, escalation_id, actor_id, payload=None):
        escalation = self.escalation_service.get_by_id(escalation_id)
        if escalation is None:
            raise ValueError("Escalation not found.")

        if not isinstance(payload, dict):
            raise ValueError("Review finding payload must be a JSON object.")

        finding_type = str(payload.get("finding_type") or payload.get("type") or "").strip().upper()
        if not finding_type:
            raise ValueError("Finding type is required.")

        summary = str(payload.get("summary") or "").strip()
        if not summary:
            raise ValueError("Finding summary is required.")

        finding = {
            "escalation_id": escalation_id,
            "case_reference": escalation.get("case_reference"),
            "author_id": actor_id,
            "author_role": "ipid",
            "finding_type": finding_type,
            "summary": summary,
        }
        created = self.review_finding_repository.create(finding)
        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": "ipid",
                "action": "ipid_review_finding_added",
                "case_reference": escalation.get("case_reference"),
                "details": {"escalation_id": escalation_id, "finding_id": created.get("finding_id")},
            }
        )
        return dict(created)

    def get_review_workspace(self, escalation_id):
        escalation = self.escalation_service.get_by_id(escalation_id)
        if escalation is None:
            raise ValueError("Escalation not found.")

        case_reference = escalation.get("case_reference")
        case_context = self._build_case_context(case_reference)
        readiness = {
            "status": "READY_FOR_REVIEW",
            "summary": "Escalation context and internal review notes are available for IPID review.",
        }
        if case_context.get("is_frozen"):
            readiness = {
                "status": "VIEW_ONLY_FROZEN",
                "summary": "This docket is frozen; the review workspace is read-only until the underlying case state is released.",
            }

        workspace = {
            "escalation_id": escalation.get("escalation_id"),
            "case_reference": case_reference,
            "category": escalation.get("category"),
            "description": escalation.get("description"),
            "status": escalation.get("status"),
            "created_at": escalation.get("created_at"),
            "updated_at": escalation.get("updated_at"),
            "case_context": case_context,
            "readiness": readiness,
            "audit_history": self.audit_service.get_for_case(case_reference) if case_reference else [],
            "review_notes": self.list_review_notes(escalation_id),
            "review_findings": self.list_review_findings(escalation_id),
        }
        return workspace

    def dismiss_escalation(self, escalation_id, actor_id, payload=None):
        escalation = self.escalation_service.get_by_id(escalation_id)
        if escalation is None:
            raise ValueError("Escalation not found.")

        decision_payload = payload or {}
        if not isinstance(decision_payload, dict):
            raise ValueError("Decision payload must be a JSON object.")
        reason = str(decision_payload.get("reason") or "").strip()
        if not reason:
            raise ValueError("Dismissal reason is required.")

        reviewed = self.escalation_service.dismiss_escalation(escalation_id, actor_id, "ipid", reason=reason)
        case_reference = escalation.get("case_reference")
        if self.freeze_service and case_reference:
            freeze = self.freeze_service.get_related_ipid_freeze(case_reference, escalation_id)
            if freeze is not None:
                self.freeze_service.unfreeze_case(
                    case_reference,
                    actor_id,
                    "ipid",
                    reason=f"Escalation dismissed: {reason}",
                    freeze_id=freeze.get("freeze_id"),
                )
                self.audit_service.log(
                    {
                        "actor_id": actor_id,
                        "actor_role": "ipid",
                        "action": "ipid_docket_unfrozen",
                        "case_reference": case_reference,
                        "details": {
                            "escalation_id": escalation_id,
                            "freeze_id": freeze.get("freeze_id"),
                            "reason": reason,
                        },
                    }
                )

        reviewed["decision"] = "DISMISSED"
        reviewed["decision_by"] = actor_id
        reviewed["decision_reason"] = reason
        return reviewed

    def uphold_escalation(self, escalation_id, actor_id, payload=None):
        escalation = self.escalation_service.get_by_id(escalation_id)
        if escalation is None:
            raise ValueError("Escalation not found.")

        decision_payload = payload or {}
        if not isinstance(decision_payload, dict):
            raise ValueError("Decision payload must be a JSON object.")
        reason = str(decision_payload.get("reason") or "").strip()
        if not reason:
            raise ValueError("Uphold reason is required.")

        case_reference = escalation.get("case_reference")

        # Resolve and validate the implicated officer *before* mutating
        # anything (resolving the escalation, freezing the docket) -- doing
        # this after those side effects (as this method used to) left a real
        # stuck state when no active assignment existed: the escalation was
        # already RESOLVED/UPHELD and the docket already frozen by the time
        # the ValueError below fired, with no officer revoked and no
        # disciplinary case created, and no UI path to recover (dismiss
        # requires UNDER_REVIEW, uphold requires not-already-resolved).
        implicated_officer_id = None
        if self.assignment_service is not None and case_reference:
            assignment = self.assignment_service.get_current_assignment_for_case(case_reference)
            if assignment:
                implicated_officer_id = assignment.get("officer_id")

        if implicated_officer_id is None:
            raise ValueError("No active officer assignment is available to revoke for this uphold decision.")

        officer = self.identity_registry.get_identity(str(implicated_officer_id))
        if officer is None:
            raise ValueError("Implicated officer identity not found.")
        if str(officer.get("role") or "").lower() == "ipid":
            raise ValueError("IPID reviewer cannot be revoked as an operational officer.")

        # Same reasoning as above: check freeze-ability up front too, so a
        # freeze failure can't happen after the escalation is already
        # resolved either.
        if self.freeze_service and case_reference:
            case_summary = self._get_case_summary(case_reference)
            if case_summary is None:
                raise ValueError("Case not found.")
            if case_summary.get("status") != "REGISTERED":
                raise ValueError("Freeze requires a registered case.")
            if self.freeze_service.is_case_frozen(case_reference):
                raise ValueError("Case is already frozen.")

        reviewed = self.escalation_service.uphold_escalation(escalation_id, actor_id, "ipid", reason=reason)
        if self.freeze_service and case_reference:
            freeze = self.freeze_service.freeze_case(
                case_reference,
                actor_id,
                "ipid",
                reason=f"IPID uphold decision for escalation {escalation_id}",
                source="IPID_REVIEW",
                related_escalation_id=escalation_id,
            )
            self.audit_service.log(
                {
                    "actor_id": actor_id,
                    "actor_role": "ipid",
                    "action": "ipid_docket_frozen",
                    "case_reference": case_reference,
                    "details": {
                        "escalation_id": escalation_id,
                        "freeze_id": freeze.get("freeze_id"),
                        "reason": freeze.get("reason"),
                    },
                }
            )

        updated_officer = self.identity_registry.revoke_access(str(implicated_officer_id))
        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": "ipid",
                "action": "officer_access_revoked",
                "case_reference": case_reference,
                "details": {
                    "officer_id": implicated_officer_id,
                    "officer_role": officer.get("role"),
                    "revocation_reason": reason,
                    "escalation_id": escalation_id,
                    "access_state": updated_officer.get("access_state") if updated_officer else None,
                },
            }
        )

        disciplinary_case = self.disciplinary_service.create_case(
            source_case_reference=case_reference,
            escalation_id=escalation_id,
            implicated_officer_id=implicated_officer_id,
            created_by=actor_id,
            created_by_role="ipid",
            reason=reason,
            category=escalation.get("category"),
        )
        reviewed["disciplinary_case"] = disciplinary_case
        reviewed["implicated_officer_id"] = implicated_officer_id
        reviewed["decision"] = "UPHELD"
        reviewed["decision_by"] = actor_id
        reviewed["decision_reason"] = reason
        return reviewed

    def reassign_case_officer(self, case_reference, target_officer_id, actor_id, reason=None):
        if not case_reference:
            raise ValueError("Case reference is required.")

        case = self.case_service.get_all_cases()
        if not any(item.get("case_reference") == case_reference for item in case):
            raise ValueError("Case not found.")

        identity = self.identity_registry.get_identity(str(target_officer_id))
        if identity is None or not identity.get("active", True):
            raise ValueError("Target officer not found.")
        if str(identity.get("access_state", "ACTIVE")).upper() == "REVOKED":
            raise ValueError("Target officer access has been revoked.")

        if self.assignment_service is None:
            raise ValueError("Assignment service is not configured.")

        assignment = self.assignment_service.create_replacement_assignment(
            case_reference=case_reference,
            officer_id=str(target_officer_id),
            assigned_by=actor_id,
            assigned_by_role="ipid",
            reason=reason,
            override_authority=True,
        )
        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": "ipid",
                "action": "ipid_case_reassigned",
                "case_reference": case_reference,
                "details": {
                    "target_officer_id": target_officer_id,
                    "reason": reason,
                    "assignment_id": assignment.get("assignment_id"),
                },
            }
        )

        if assignment.get("officer_role") == "detective" and self.investigation_service is not None:
            # Same fix as StationCommanderService.force_reassign_docket: without
            # this, the previously-assigned detective keeps sole access to any
            # investigation already opened on this case.
            self.investigation_service.reassign_active_investigation(
                case_reference, assignment.get("officer_id"), actor_id, reason=reason
            )

        return assignment

    def list_custody_cases(self):
        """Dockets IPID currently has frozen -- the "Cases in Custody"
        section (GitHub follow-up to issue #3): a reviewer needs a single
        place to find every case they've taken custody of, whether they're
        still actively reviewing it or it's already been upheld and the
        freeze is being kept in place through the disciplinary process."""
        if self.freeze_service is None:
            return []

        custody_cases = []
        for freeze in self.freeze_service.list_active_freezes(source="IPID_REVIEW"):
            case_reference = freeze.get("case_reference")
            case_summary = self._get_case_summary(case_reference) or {}
            escalation_id = freeze.get("related_escalation_id")
            escalation = self.escalation_service.get_by_id(escalation_id) if escalation_id else None
            custody_cases.append(
                {
                    "case_reference": case_reference,
                    "case_status": case_summary.get("status"),
                    "title": case_summary.get("title"),
                    "location": case_summary.get("location"),
                    "escalation_id": escalation_id,
                    "escalation_status": escalation.get("status") if escalation else None,
                    "escalation_decision": escalation.get("decision") if escalation else None,
                    "freeze_id": freeze.get("freeze_id"),
                    "frozen_at": freeze.get("frozen_at"),
                    "frozen_by": freeze.get("actor_id"),
                    "reason": freeze.get("reason"),
                }
            )
        return custody_cases

    def add_case_statement(self, case_reference, actor_id, payload=None):
        """Let an IPID reviewer record an additional victim/witness statement
        directly on the case docket, mirroring the detective's own
        `InvestigationService.add_statement` -- distinct from IPID's
        escalation-scoped review notes, this is visible to every role that
        already reads `docket.statements`. Freeze deliberately does not
        block this: IPID is the actor who freezes a docket, and needs to
        keep recording statements on a case they're actively reviewing in
        custody, not be locked out of their own investigation."""
        if not isinstance(payload, dict):
            raise ValueError("Statement payload must be a JSON object.")
        statement_text = str(payload.get("statement_text") or "").strip()
        if not statement_text:
            raise ValueError("Statement text is required.")

        case = None
        for candidate in self.case_service.get_all_cases():
            if candidate.get("case_reference") == case_reference:
                case = candidate
                break
        if case is None:
            raise ValueError("Docket not found.")

        statement = {
            "statement_id": len(case.get("statements", [])) + 1,
            "case_reference": case_reference,
            "citizen_id": case.get("citizen_id"),
            "statement_text": statement_text,
            "recorded_by": actor_id,
            "recorded_by_role": "ipid",
            "created_at": self._utc_now(),
        }
        case.setdefault("statements", []).append(statement)
        case.setdefault("timeline", []).append(
            {
                "event_type": "statement_added_by_ipid",
                "actor_id": actor_id,
                "actor_role": "ipid",
                "timestamp": statement["created_at"],
                "details": {"statement_id": statement["statement_id"]},
            }
        )
        self.case_service.update_case(case)
        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": "ipid",
                "action": "statement_added_by_ipid",
                "case_reference": case_reference,
                "details": {"statement_id": statement["statement_id"]},
            }
        )
        return dict(statement)

    def list_disciplinary_cases(self):
        return self.disciplinary_service.list_cases()

    def get_disciplinary_case(self, disciplinary_case_id):
        return self.disciplinary_service.get_case(disciplinary_case_id)

    def start_review(self, escalation_id, reviewer_id, reviewer_role="ipid"):
        return self.escalation_service.start_review(escalation_id, reviewer_id, reviewer_role)

    def take_custody(self, escalation_id, actor_id, actor_role="ipid", reason=None):
        """Let an IPID reviewer freeze the docket from other officers while a
        review is in progress, independent of the eventual dismiss/uphold
        decision (GitHub issue #3: opening a review did not lock the docket,
        so other officers could keep mutating a case under active review)."""
        escalation = self.escalation_service.get_by_id(escalation_id)
        if escalation is None:
            raise ValueError("Escalation not found.")
        if str(escalation.get("status") or "").upper() == "RESOLVED":
            raise ValueError("Escalation is already resolved; nothing to take custody of.")

        case_reference = escalation.get("case_reference")
        if not case_reference:
            raise ValueError("Escalation has no associated case.")
        if self.freeze_service is None:
            raise ValueError("Freeze service is not configured.")
        if self.freeze_service.is_case_frozen(case_reference):
            raise ValueError("Case is already frozen.")

        default_reason = f"IPID took custody of the docket while reviewing escalation {escalation_id}"
        freeze = self.freeze_service.freeze_case(
            case_reference,
            actor_id,
            actor_role,
            reason=f"{default_reason}: {reason}" if reason else default_reason,
            source="IPID_REVIEW",
            related_escalation_id=escalation_id,
        )
        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": actor_role,
                "action": "ipid_docket_frozen",
                "case_reference": case_reference,
                "details": {
                    "escalation_id": escalation_id,
                    "freeze_id": freeze.get("freeze_id"),
                    "reason": freeze.get("reason"),
                },
            }
        )
        return freeze
