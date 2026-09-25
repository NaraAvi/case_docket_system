"""Automation engine boundary for SLA monitoring and operational oversight."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


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

    def __init__(self, case_service=None, assignment_service=None, audit_service=None, freeze_service=None):
        self.case_service = case_service
        self.assignment_service = assignment_service
        self.audit_service = audit_service
        self.freeze_service = freeze_service
        self.sla_service = SlaService(case_service=case_service, assignment_service=assignment_service)
        self._jobs = []

    def register(self, job_name, callback):
        self._jobs.append({"name": job_name, "callback": callback})
        return job_name
