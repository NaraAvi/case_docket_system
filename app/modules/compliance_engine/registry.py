"""Versioned metadata registry for the legal compliance rule catalogue."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class FlagDraft:
    rule_code: str
    case_reference: str | None = None
    subject_officer_id: str | None = None
    actor_role: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    due_at: Any = None


@dataclass
class ComplianceRule:
    code: str
    title: str
    actor_role: str
    trigger: str
    deadline_hours: int | None
    legal_reference_id: str
    provision: str
    verification: str
    infraction: str | None
    routes_to: str
    evaluate: Callable[[dict[str, Any]], list[FlagDraft]] = field(repr=False, compare=False)

    def to_dict(self):
        return {
            "code": self.code,
            "title": self.title,
            "actor_role": self.actor_role,
            "trigger": self.trigger,
            "deadline_hours": self.deadline_hours,
            "legal_reference_id": self.legal_reference_id,
            "provision": self.provision,
            "verification": self.verification,
            "infraction": self.infraction,
            "routes_to": self.routes_to,
        }


def _no_op(_context):
    return []


def _rule(code, title, actor_role, trigger, deadline_hours, legal_reference_id, provision, verification, infraction, routes_to):
    return ComplianceRule(code, title, actor_role, trigger, deadline_hours, legal_reference_id, provision, verification, infraction, routes_to, _no_op)


_RULES = [
    _rule("R01", "Register submitted docket", "constable", "event:docket_submitted", 72, "RSA-SAPS-NI-3-2011", "NI 3/2011", "unverified", "SLA_BREACH_MINOR", "station_commander"),
    _rule("R02", "Attend to registered docket", "detective", "event:docket_registered", 72, "RSA-SAPS-NI-3-2011", "NI 3/2011", "unverified", "UNLAWFUL_DELAY", "station_commander"),
    _rule("R03", "Preserve evidence integrity", "constable", "event:evidence_uploaded", None, "RSA-CPA-1977", "s212", "unverified", "EVIDENCE_TAMPERING", "station_commander"),
    _rule("R04", "Record statutory IPID referral", "system", "event:statutory_matter_detected", None, "RSA-IPID-2011", "s28(1)", "unverified", "DEFEATING_ENDS_OF_JUSTICE", "ipid"),
    _rule("R05", "Maintain separation of duties", "station_commander", "event:assignment_requested", None, "RSA-PAJA-2000", "s3", "verified", "CONFLICT_OF_INTEREST_BREACH", "station_commander"),
    _rule("R06", "Respect statutory docket freeze", "officer", "event:frozen_case_mutation", None, "RSA-IPID-2011", "s28(1)", "verified", "GENERAL_MISCONDUCT", "ipid"),
    _rule("R07", "Maintain immutable accountability record", "system", "event:status_changed", None, "RSA-PAJA-2000", "s3", "verified", None, "station_commander"),
    _rule("R08", "Respond to compliance flag", "officer", "schedule", 72, "RSA-SAPS-SO-321", "SO 321", "verified", "INCOMPLETE_RECORD_KEEPING", "station_commander"),
    _rule("R09", "Escalate upheld disciplinary conduct", "ipid", "event:disciplinary_finding_upheld", None, "RSA-SAPS-DISCIPLINE-2016", "misconduct schedule", "verified", "GENERAL_MISCONDUCT", "ipid"),
    _rule("R10", "Respond to domestic violence matter", "constable", "event:domestic_violence_reported", None, "RSA-DVA-1998", "protection and response duties", "verified", "NEGLECT_OF_DUTY", "station_commander"),
    _rule("R11", "Respond to sexual offence matter", "constable", "event:sexual_offence_reported", None, "RSA-SOA-2007", "sexual offences and victim protection", "verified", "RAPE_OR_SEXUAL_VIOLENCE", "ipid"),
    _rule("R12", "Report corrupt activity", "officer", "event:corruption_alleged", None, "RSA-PRECCA-2004", "s34", "verified", "CORRUPTION", "ipid"),
    _rule("R13", "Cooperate with IPID investigation", "officer", "event:ipid_request", None, "RSA-IPID-REGS-2012", "IPID Regulations", "verified", "UNBECOMING_CONDUCT", "ipid"),
    _rule("R14", "Maintain independent investigation", "detective", "event:investigation_opened", None, "RSA-PAJA-2000", "s3", "verified", "CONFLICT_OF_INTEREST_BREACH", "station_commander"),
    _rule("R15", "Comply with audit and record duties", "officer", "event:audit_required", None, "RSA-SAPS-SO-321", "SO 321", "verified", "INCOMPLETE_RECORD_KEEPING", "station_commander"),
    _rule("R16", "Report attempted murder by firearm or weapon", "officer", "event:attempted_murder_alleged", None, "RSA-IPID-2011", "s28(1)(gA)", "unverified", "DEFEATING_ENDS_OF_JUSTICE", "ipid"),
    _rule("R17", "Apply misconduct sanction matrix", "ipid", "event:misconduct_tier_determined", None, "RSA-SAPS-DISCIPLINE-2016", "sanction matrix", "verified", "GENERAL_MISCONDUCT", "ipid"),
    _rule("R18", "Apply amended IPID s28 categories", "system", "schedule", None, "RSA-IPID-2011", "s28(1)(a)-(gA)", "unverified", "DEFEATING_ENDS_OF_JUSTICE", "ipid"),
]


class ComplianceRuleRegistry:
    def __init__(self, rules=None):
        self._rules = {rule.code: rule for rule in (rules or _RULES)}

    def get(self, code):
        return self._rules.get(str(code))

    def all(self):
        return list(self._rules.values())

    def by_trigger(self, trigger):
        return [rule for rule in self._rules.values() if rule.trigger == trigger]


DEFAULT_RULE_REGISTRY = ComplianceRuleRegistry()