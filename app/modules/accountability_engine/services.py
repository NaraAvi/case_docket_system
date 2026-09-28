"""Accountability and demerit service for operational identities."""

from __future__ import annotations

from datetime import UTC, datetime

from app.auth.service import TestIdentityRegistry
from app.database.repositories.accountability_repository import AccountabilityEventRepository, AccountabilityProfileRepository
from app.modules.audit_engine.services import AuditTrailService
from app.modules.control_gate import ControlGateResult


class AccountabilityService:
    """Server-controlled demerit aggregation for officer identities.

    This layer intentionally reuses the existing user/identity registry instead of
    creating a second identity system. The user profile is evaluated and updated in
    place, while all append-only accountability events remain immutable.
    """

    THRESHOLD_NORMAL = 0
    THRESHOLD_REVIEW = 3
    THRESHOLD_FROZEN = 5
    VALID_EVENT_TYPES = {"DEMERIT", "WARNING", "REVIEW", "CLEARANCE"}

    def _create_accountability_review_item(self, subject_id, actor_id, actor_role, total_demerits):
        if subject_id is None or total_demerits < self.THRESHOLD_REVIEW:
            return None

        from app.modules.escalation_engine.services import EscalationService

        app_ext = getattr(self.app, "extensions", {}) if self.app is not None else {}
        escalation_service = app_ext.get("escalation_service")
        if escalation_service is None:
            escalation_service = EscalationService(audit_service=self.audit_service, app=self.app)

        case_reference = f"ACCOUNTABILITY-{str(subject_id)}"
        description = (
            f"Automatic IPID accountability review triggered for officer {subject_id} after {total_demerits} total demerits."
        )

        for escalation in escalation_service.list_for_case(case_reference):
            category = str(escalation.get("category") or "").upper()
            text = str(escalation.get("description") or "")
            if category == "OFFICER_CONDUCT" and "ACCOUNTABILITY" in text.upper():
                return escalation

        try:
            return escalation_service.create_escalation(
                case_reference=case_reference,
                created_by=str(actor_id or "SYSTEM_ODDE"),
                created_by_role=str(actor_role or "system_automation").lower(),
                category="OFFICER_CONDUCT",
                description=description,
            )
        except ValueError:
            return None

    def __init__(self, profile_repository=None, event_repository=None, audit_service=None, identity_registry=None, app=None):
        self.app = app
        self.profile_repository = profile_repository or AccountabilityProfileRepository(app=app)
        self.event_repository = event_repository or AccountabilityEventRepository(app=app)
        self.audit_service = audit_service or AuditTrailService()
        self.identity_registry = identity_registry or TestIdentityRegistry()
        self.user_repository = getattr(self.identity_registry, "user_repository", None)

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _subject_role(self, subject_id, fallback_role=None):
        if subject_id is None:
            return str(fallback_role or "constable").lower()
        identity = self.identity_registry.get_identity(str(subject_id))
        if identity:
            return str(identity.get("role") or fallback_role or "constable").lower()
        return str(fallback_role or "constable").lower()

    def _evaluate_status(self, total_demerits):
        if total_demerits >= self.THRESHOLD_REVIEW:
            return "ACCOUNTABILITY_REVIEW", "ACCOUNTABILITY_REVIEW", True, True
        return "CLEAR", "ACTIVE", False, False

    def _sync_identity_access_state(self, subject_id, access_state):
        if subject_id is None:
            return None
        if self.user_repository is None:
            return None
        existing = self.user_repository.get_by_id(str(subject_id))
        if existing is None:
            return None
        updated = self.user_repository.update(str(subject_id), {"access_state": access_state})
        return updated

    def _ensure_profile(self, subject_id, subject_role=None):
        if subject_id is None:
            raise ValueError("Subject identity is required.")
        subject_id = str(subject_id)
        existing = self.profile_repository.get_for_subject(subject_id)
        if existing is not None:
            return dict(existing)

        profile = self.profile_repository.create(
            {
                "profile_id": f"ACCT-PROFILE-{subject_id}",
                "subject_id": subject_id,
                "subject_role": str(subject_role or self._subject_role(subject_id)).lower(),
                "total_demerits": 0,
                "status": "CLEAR",
                "access_state": "ACTIVE",
                "threshold_reached": False,
                "review_required": False,
                "last_event_id": None,
                "last_triggered_at": None,
                "created_at": self._utc_now(),
                "updated_at": self._utc_now(),
            }
        )
        return dict(profile)

    def get_profile(self, subject_id):
        if subject_id is None:
            return None
        profile = self.profile_repository.get_for_subject(str(subject_id))
        if profile is None:
            return self._ensure_profile(subject_id)
        return dict(profile)

    def list_events(self, subject_id):
        if subject_id is None:
            return []
        return [dict(item) for item in self.event_repository.list_for_subject(str(subject_id))]

    def record_event(
        self,
        *,
        subject_id,
        actor_id,
        actor_role,
        reason,
        delta=1,
        event_type="DEMERIT",
        idempotency_key=None,
        source="MANUAL",
        metadata=None,
    ):
        if subject_id is None:
            raise ValueError("Subject identity is required.")
        if actor_id is None:
            raise ValueError("Actor identity is required.")

        event_type = str(event_type or "DEMERIT").upper()
        if event_type not in self.VALID_EVENT_TYPES:
            raise ValueError("Unsupported accountability event type.")

        normalized_delta = int(delta or 0)
        if normalized_delta < 0:
            raise ValueError("Accountability delta cannot be negative.")

        if idempotency_key:
            existing = self.event_repository.get_by_idempotency_key(str(idempotency_key))
            if existing is not None:
                raise ValueError("Accountability event already recorded for this idempotency key.")

        profile = self._ensure_profile(subject_id, self._subject_role(subject_id))
        previous_total = int(profile.get("total_demerits", 0) or 0)
        total_after = previous_total + normalized_delta
        status, access_state, threshold_reached, review_required = self._evaluate_status(total_after)

        event = self.event_repository.create(
            {
                "event_id": None,
                "subject_id": str(subject_id),
                "subject_role": str(profile.get("subject_role") or self._subject_role(subject_id)).lower(),
                "actor_id": str(actor_id),
                "actor_role": str(actor_role or "system").lower(),
                "event_type": event_type,
                "delta": normalized_delta,
                "total_after": total_after,
                "reason": str(reason or "Accountability event recorded.").strip() or "Accountability event recorded.",
                "idempotency_key": str(idempotency_key) if idempotency_key else None,
                "source": str(source or "MANUAL").upper(),
                "metadata": metadata or {},
                "created_at": self._utc_now(),
            }
        )

        profile_update = {
            "subject_id": str(subject_id),
            "subject_role": str(profile.get("subject_role") or self._subject_role(subject_id)).lower(),
            "total_demerits": total_after,
            "status": status,
            "access_state": access_state,
            "threshold_reached": threshold_reached,
            "review_required": review_required,
            "last_event_id": event.get("event_id"),
            "last_triggered_at": event.get("created_at"),
            "updated_at": self._utc_now(),
        }
        updated_profile = self.profile_repository.update(str(subject_id), profile_update)

        if access_state in {"ACCOUNTABILITY_REVIEW", "REVIEW_REQUIRED", "FROZEN"}:
            self._sync_identity_access_state(subject_id, access_state)

        if previous_total < self.THRESHOLD_REVIEW and total_after >= self.THRESHOLD_REVIEW:
            review_item = self._create_accountability_review_item(subject_id, actor_id, actor_role, total_after)
            if review_item is not None:
                self.audit_service.log(
                    {
                        "actor_id": str(actor_id),
                        "actor_role": str(actor_role or "system").lower(),
                        "action": "accountability_review_item_created",
                        "case_reference": review_item.get("case_reference"),
                        "object_type": "escalation",
                        "object_id": review_item.get("escalation_id"),
                        "reason": "Total demerits reached the automated accountability review threshold.",
                        "details": {
                            "subject_id": str(subject_id),
                            "total_demerits": total_after,
                            "category": review_item.get("category"),
                            "case_reference": review_item.get("case_reference"),
                        },
                    }
                )

        self.audit_service.log(
            {
                "actor_id": str(actor_id),
                "actor_role": str(actor_role or "system").lower(),
                "action": "accountability_event_recorded",
                "case_reference": None,
                "object_type": "accountability_profile",
                "object_id": str(subject_id),
                "reason": profile_update["status"],
                "details": {
                    "subject_id": str(subject_id),
                    "event_id": event.get("event_id"),
                    "delta": normalized_delta,
                    "total_demerits": total_after,
                    "status": status,
                    "access_state": access_state,
                    "idempotency_key": idempotency_key,
                },
            }
        )
        return dict(updated_profile or profile_update)

    def evaluate_subject(self, subject_id):
        profile = self.get_profile(subject_id)
        if profile is None:
            return {"subject_id": str(subject_id), "total_demerits": 0, "status": "CLEAR", "review_required": False, "threshold_reached": False}
        status = str(profile.get("status") or "CLEAR").upper()
        return {
            "subject_id": profile.get("subject_id"),
            "total_demerits": int(profile.get("total_demerits", 0) or 0),
            "status": status,
            "threshold_reached": bool(profile.get("threshold_reached", False)) or status in {"REVIEW_REQUIRED", "ACCOUNTABILITY_REVIEW", "FROZEN"},
            "review_required": bool(profile.get("review_required", False)) or status in {"REVIEW_REQUIRED", "ACCOUNTABILITY_REVIEW", "FROZEN"},
            "access_state": profile.get("access_state") or "ACTIVE",
            "last_event_id": profile.get("last_event_id"),
        }


class AccountabilityGate:
    """Control gate to deny operational privileges while an officer is in accountability review."""

    gate_name = "accountability"

    def __init__(self, accountability_service=None):
        self.accountability_service = accountability_service

    def check(self, subject_id, actor_id=None, actor_role=None, operation="mutate"):
        subject_id = str(subject_id or "").strip()
        if not subject_id:
            return ControlGateResult.deny(self.gate_name, "ACCOUNTABILITY.MISSING", "Subject identity is required.", subject_id=subject_id)

        if self.accountability_service is None:
            return ControlGateResult.allow(self.gate_name, "ACCOUNTABILITY.NOT_CONFIGURED", "Accountability evaluation is not configured.", subject_id=subject_id)

        evaluation = self.accountability_service.evaluate_subject(subject_id)
        status = str(evaluation.get("status") or "NORMAL").upper()
        if status in {"REVIEW_REQUIRED", "ACCOUNTABILITY_REVIEW", "FROZEN"}:
            return ControlGateResult.deny(
                self.gate_name,
                "ACCOUNTABILITY.REVIEW_REQUIRED",
                "Officer is under accountability review and cannot continue operational action.",
                subject_id=subject_id,
                actor_id=actor_id,
                actor_role=actor_role,
                operation=operation,
                total_demerits=evaluation.get("total_demerits", 0),
                status=status,
            )

        return ControlGateResult.allow(
            self.gate_name,
            "ACCOUNTABILITY.CLEAR",
            "Accountability evaluation is clear.",
            subject_id=subject_id,
            actor_id=actor_id,
            actor_role=actor_role,
            operation=operation,
            total_demerits=evaluation.get("total_demerits", 0),
            status=status,
        )

    def enforce(self, subject_id, actor_id=None, actor_role=None, operation="mutate"):
        result = self.check(subject_id, actor_id=actor_id, actor_role=actor_role, operation=operation)
        result.raise_for_block()
        return result
