"""SLA evaluation against the SAPS National Instruction 3/2011 windows.

Pure functions. Two windows are measured independently:

* REGISTRATION -- docket submitted -> constable registration.
* ATTENDANCE   -- assignment (or registration) -> investigation opened.

Time a docket spends frozen by IPID is *excluded*: an officer cannot be
penalised for a delay that the oversight process itself caused (PAJA
procedural fairness).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules.regulatory_engine import corpus


def parse_timestamp(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        moment = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _hours(delta):
    return delta.total_seconds() / 3600.0


def paused_hours(start, end, paused_intervals):
    """Hours of ``[start, end]`` that overlap any (frozen) interval."""
    total = 0.0
    for interval_start, interval_end in paused_intervals or []:
        interval_start = parse_timestamp(interval_start)
        interval_end = parse_timestamp(interval_end) or end
        if interval_start is None:
            continue
        overlap_start = max(start, interval_start)
        overlap_end = min(end, interval_end)
        if overlap_end > overlap_start:
            total += _hours(overlap_end - overlap_start)
    return total


def _evaluate_phase(name, window_hours, start, end, now, paused_intervals, at_risk_ratio):
    stop = end or now
    elapsed = max(_hours(stop - start) - paused_hours(start, stop, paused_intervals), 0.0)
    overdue = max(elapsed - window_hours, 0.0)
    completed = end is not None
    if overdue > 0:
        status = "COMPLETED_LATE" if completed else "BREACHED"
    elif completed:
        status = "COMPLETED_WITHIN_SLA"
    elif elapsed >= window_hours * at_risk_ratio:
        status = "AT_RISK"
    else:
        status = "WITHIN_SLA"
    return {
        "phase": name,
        "window_hours": window_hours,
        "started_at": start.isoformat(),
        "completed_at": end.isoformat() if end else None,
        "elapsed_hours": round(elapsed, 2),
        "remaining_hours": round(max(window_hours - elapsed, 0.0), 2) if not completed else 0.0,
        "overdue_hours": round(overdue, 2),
        "breached": overdue > 0,
        "status": status,
    }


def classify_delay(overdue_hours):
    """Map an overdue interval onto the schedule's delay infractions."""
    if overdue_hours is None or overdue_hours <= 0:
        return None
    if overdue_hours < corpus.SLA_THRESHOLDS["minor_overdue_hours"]:
        return "SLA_BREACH_MINOR"
    return "SLA_BREACH_SERIOUS"


def evaluate_windows(*, docket, assignment=None, investigations=None, paused_intervals=None, now=None):
    """Evaluate both statutory windows for ``docket``; see module docstring."""
    now = parse_timestamp(now) or datetime.now(UTC)
    thresholds = corpus.SLA_THRESHOLDS
    docket = docket or {}
    phases = []

    submitted_at = parse_timestamp(docket.get("submitted_at"))
    registered_at = parse_timestamp(docket.get("registered_at"))
    status = str(docket.get("status") or "").upper()

    if submitted_at is not None and status != "DRAFT":
        registration_end = registered_at
        if registration_end is None and status not in {"AWAITING_CONSTABLE_REGISTRATION"}:
            registration_end = submitted_at  # legacy record: registered with no timestamp
        phases.append(
            _evaluate_phase(
                "REGISTRATION",
                thresholds["registration_hours"],
                submitted_at,
                registration_end,
                now,
                paused_intervals,
                thresholds["at_risk_ratio"],
            )
        )

    attendance_start = None
    responsible = {"officer_id": None, "officer_role": None}
    if assignment:
        attendance_start = parse_timestamp(assignment.get("assigned_at"))
        responsible = {"officer_id": assignment.get("officer_id"), "officer_role": assignment.get("officer_role")}
    if attendance_start is None:
        attendance_start = registered_at

    if attendance_start is not None and status not in {"DRAFT", "AWAITING_CONSTABLE_REGISTRATION"}:
        opened = sorted(
            moment
            for moment in (parse_timestamp(item.get("created_at")) for item in (investigations or []))
            if moment is not None
        )
        attendance_end = opened[0] if opened else None
        phase = _evaluate_phase(
            "ATTENDANCE",
            thresholds["attendance_hours"],
            attendance_start,
            attendance_end,
            now,
            paused_intervals,
            thresholds["at_risk_ratio"],
        )
        phase["responsible_officer_id"] = responsible["officer_id"]
        phase["responsible_officer_role"] = responsible["officer_role"]
        phases.append(phase)

    worst = max(phases, key=lambda item: item["overdue_hours"], default=None)
    if not phases:
        overall = "NOT_APPLICABLE"
    elif any(item["breached"] for item in phases):
        overall = "BREACHED"
    elif any(item["status"] == "AT_RISK" for item in phases):
        overall = "AT_RISK"
    else:
        overall = "WITHIN_SLA"

    return {
        "case_reference": docket.get("case_reference"),
        "status": overall,
        "breached": overall == "BREACHED",
        "phases": phases,
        "worst_phase": worst["phase"] if worst and worst["breached"] else None,
        "worst_overdue_hours": worst["overdue_hours"] if worst else 0.0,
        "delay_infraction": classify_delay(worst["overdue_hours"]) if worst else None,
        "legal_reference_id": thresholds["legal_reference_id"],
        "evaluated_at": now.isoformat(),
    }
