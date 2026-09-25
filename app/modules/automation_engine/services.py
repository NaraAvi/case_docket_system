"""Automation engine boundary for SLA monitoring and operational oversight."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.modules.escalation_engine.services import EscalationService


class SlaService:
    """Deterministic 72-hour operational SLA boundary based on case handling start."""

    SLA_HOURS = 72
    SLA_WINDOW = timedelta(hours=SLA_HOURS)

    def __init__(self, case_service=None, assignment_service=None):
        self.case_service = case_service
        self.assignment_service = assignment_service

    @staticmethod
    def _parse_timestamp(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    def _get_case(self, case_reference):
        if self.case_service is None:
            return None
        for case in self.case_service.get_all_cases():
            if case.get("case_reference") == case_reference:
                return case
        return None

    def _get_attendance_start(self, case_reference):
        if self.assignment_service is not None:
            current_assignment = self.assignment_service.get_current_assignment_for_case(case_reference)
            if current_assignment:
                candidate = current_assignment.get("assigned_at")
                if candidate:
                    parsed = self._parse_timestamp(candidate)
                    if parsed is not None:
                        return parsed

        case = self._get_case(case_reference)
        if case is None:
            return None
        for key in ("registered_at", "submitted_at", "created_at"):
            parsed = self._parse_timestamp(case.get(key))
            if parsed is not None:
                return parsed
        return None

    def calculate_case_sla(self, case_reference):
        case = self._get_case(case_reference)
        if case is None:
            return {
                "case_reference": case_reference,
                "status": "WITHIN_SLA",
                "breached": False,
                "elapsed_hours": 0,
                "remaining_hours": self.SLA_HOURS,
                "attendance_started_at": None,
                "sla_due_at": None,
                "assigned_officer_id": None,
                "assigned_officer_role": None,
            }

        attendance_started_at = self._get_attendance_start(case_reference)
        if attendance_started_at is None:
            attendance_started_at = datetime.now(UTC)

        assigned_officer = None
        assigned_role = None
        if self.assignment_service is not None:
            current_assignment = self.assignment_service.get_current_assignment_for_case(case_reference)
            if current_assignment:
                assigned_officer = current_assignment.get("officer_id")
                assigned_role = current_assignment.get("officer_role")

        sla_due_at = attendance_started_at + self.SLA_WINDOW
        now = datetime.now(UTC)
        elapsed = now - attendance_started_at
        remaining = max((sla_due_at - now).total_seconds() / 3600, 0)
        breached = now > sla_due_at
        status = "BREACHED" if breached else "WITHIN_SLA"

        return {
            "case_reference": case_reference,
            "status": status,
            "breached": breached,
            "elapsed_hours": round(elapsed.total_seconds() / 3600, 2),
            "remaining_hours": round(remaining, 2),
            "attendance_started_at": attendance_started_at.isoformat(),
            "sla_due_at": sla_due_at.isoformat(),
            "assigned_officer_id": assigned_officer,
            "assigned_officer_role": assigned_role,
            "current_status": case.get("status"),
        }

    def list_breaches(self):
        breaches = []
        if self.case_service is None:
            return breaches

        for case in self.case_service.get_all_cases():
            result = self.calculate_case_sla(case.get("case_reference"))
            if result.get("breached"):
                breaches.append(result)
        return breaches


class AutomationService:
    """Boundary for SLA monitoring and automatic case actions."""

    def __init__(
        self,
        case_service=None,
        assignment_service=None,
        audit_service=None,
        freeze_service=None,
        decision_engine=None,
        escalation_service=None,
        app=None,
    ):
        self.case_service = case_service
        self.assignment_service = assignment_service
        self.audit_service = audit_service
        self.freeze_service = freeze_service
        self.decision_engine = decision_engine
        self.app = app
        self.sla_service = SlaService(case_service=case_service, assignment_service=assignment_service)
        self.escalation_service = escalation_service or EscalationService(audit_service=audit_service, app=app)
        self._jobs = []

    def _get_case(self, case_reference):
        if self.case_service is None:
            return None
        for case in self.case_service.get_all_cases():
            if case.get("case_reference") == case_reference:
                return case
        return None

    def _evaluate_sla(self, case_reference):
        if self.decision_engine is not None:
            return self.decision_engine.evaluate_sla_compliance(case_reference)
        return self.sla_service.calculate_case_sla(case_reference)

    def _find_open_sla_escalation(self, case_reference):
        if self.escalation_service is None:
            return None
        for escalation in self.escalation_service.list_for_case(case_reference):
            if str(escalation.get("category") or "").upper() != "SLA_BREACH":
                continue
            status = str(escalation.get("status") or "").upper()
            if status in {"OPEN", "UNDER_REVIEW"}:
                return escalation
        return None

    def enforce_sla_breach(self, case_reference):
        if not case_reference:
            raise ValueError("Case reference is required.")

        case = self._get_case(case_reference)
        if case is None:
            raise ValueError("Case not found.")

        sla_result = self._evaluate_sla(case_reference)
        if not sla_result.get("breached"):
            return {"case_reference": case_reference, "breached": False, "sla": sla_result, "escalation": None, "freeze": None}

        existing = self._find_open_sla_escalation(case_reference)
        if existing is not None:
            freeze = self.freeze_service.get_current_freeze(case_reference) if self.freeze_service else None
            return {"case_reference": case_reference, "breached": True, "sla": sla_result, "escalation": existing, "freeze": freeze}

        escalation = self.escalation_service.create_escalation(
            case_reference,
            EscalationService.SYSTEM_ACTOR_ID,
            EscalationService.SYSTEM_ACTOR_ROLE,
            "SLA_BREACH",
            (
                "72-hour SLA breach detected for this docket; accountability escalation created and the docket "
                "has been frozen pending IPID review."
            ),
        )

        freeze = None
        if self.freeze_service is not None:
            current = self.freeze_service.get_current_freeze(case_reference)
            if current is None:
                freeze = self.freeze_service.freeze_case(
                    case_reference,
                    EscalationService.SYSTEM_ACTOR_ID,
                    EscalationService.SYSTEM_ACTOR_ROLE,
                    reason=f"SLA_BREACH escalation {escalation.get('escalation_id')} -- 72-hour accountability breach",
                    source="MANUAL",
                    related_escalation_id=escalation.get("escalation_id"),
                )
            else:
                freeze = current

        if self.audit_service is not None:
            self.audit_service.log(
                {
                    "actor_id": EscalationService.SYSTEM_ACTOR_ID,
                    "actor_role": EscalationService.SYSTEM_ACTOR_ROLE,
                    "action": "sla_breach_detected",
                    "case_reference": case_reference,
                    "object_type": "escalation",
                    "object_id": escalation.get("escalation_id"),
                    "reason": "SLA_BREACH",
                    "details": {
                        "breached": True,
                        "status": sla_result.get("status"),
                        "deadline_hours": sla_result.get("worst_overdue_hours"),
                        "escalation_id": escalation.get("escalation_id"),
                        "freeze_id": freeze.get("freeze_id") if freeze else None,
                    },
                }
            )

        return {"case_reference": case_reference, "breached": True, "sla": sla_result, "escalation": escalation, "freeze": freeze}

    def list_breaches(self):
        breaches = []
        if self.case_service is None:
            return breaches

        for case in self.case_service.get_all_cases():
            result = self._evaluate_sla(case.get("case_reference"))
            if result.get("breached"):
                enforcement = self.enforce_sla_breach(case.get("case_reference"))
                breaches.append({**result, "escalation": enforcement.get("escalation"), "freeze": enforcement.get("freeze")})
        return breaches

    def register(self, job_name, callback):
        self._jobs.append({"name": job_name, "callback": callback})
        return job_name

    def _resolve_registered_callback(self, callback):
        if callback is None:
            return None
        if isinstance(callback, str):
            return getattr(self, callback, None)
        if hasattr(callback, "__self__") and getattr(callback, "__self__", None) is self:
            return getattr(self, callback.__name__, None)
        return callback

    def trigger_registered_jobs(self):
        results = []
        for job in list(self._jobs):
            callback = self._resolve_registered_callback(job.get("callback"))
            if not callable(callback):
                continue
            try:
                result = callback()
            except Exception:
                if self.app is not None and hasattr(self.app, "logger"):
                    self.app.logger.exception("Registered automation job failed: %s", job.get("name"))
                continue
            results.append({**dict(job), "result": result})
        return results
