"""Controlled regulatory rules for deterministic workflow compliance."""

from __future__ import annotations

from app.modules.regulatory_engine import corpus


def _slug(code):
    return "RULE-" + code.replace(".", "-").replace("_", "-")


def _build_statutory_rules():
    """Derive the Milestone 4 rules from the codified corpus so the rule
    registry and the decision engine can never drift apart."""
    rules = {}

    for code, category in corpus.S28_CATEGORIES.items():
        subsection = category["subsection"]
        rules[code] = {
            "rule_id": _slug(code),
            "rule_code": code,
            "rule_name": f"IPID Act s{subsection}: {category['title']}",
            "description": (
                f"An allegation falling under IPID Act 1 of 2011 section {subsection} ({category['title']}) "
                "must be referred to IPID and the docket frozen; it cannot be resolved locally."
            ),
            "legal_reference_id": category["legal_reference_id"],
            "rule_version": corpus.CORPUS_VERSION,
            "effective_from": "2012-04-01",
            "effective_to": None,
            "status": "ACTIVE",
            "priority": 120,
            "conditions": ["allegation_matches_s28_category"] if category["auto_detect"] else ["ministerial_prescription"],
            "required_controls": ["mandatory_ipid_referral", "case_freeze", "immutable_audit_record"],
            "prohibited_actions": ["local_resolution", "dismissal_without_ipid_review", "continued_operational_handling"],
            "resulting_action": "refer_to_ipid_and_freeze",
            "explanation": f"Statutory referral under {corpus.IPID_SECTION_28_BASIS}, paragraph {subsection.split(')', 1)[1]}.",
            "subsection": subsection,
            "auto_detect": category["auto_detect"],
        }

    rules["PRECCA.S34.REPORTING_DUTY"] = {
        "rule_id": _slug("PRECCA.S34.REPORTING_DUTY"),
        "rule_code": "PRECCA.S34.REPORTING_DUTY",
        "rule_name": "Duty to report corrupt activity",
        "description": "A corruption allegation must be reported; the system records the report and refers the matter to IPID.",
        "legal_reference_id": "RSA-PRECCA-S34",
        "rule_version": corpus.CORPUS_VERSION,
        "effective_from": "2004-04-27",
        "effective_to": None,
        "status": "ACTIVE",
        "priority": 115,
        "conditions": ["corruption_allegation_logged"],
        "required_controls": ["reporting_record", "mandatory_ipid_referral"],
        "prohibited_actions": ["suppress_corruption_report"],
        "resulting_action": "record_report_and_refer",
        "explanation": "PRECCA section 34 places a reporting duty on persons in positions of authority.",
    }
    rules["SAPS.NI3_2011.REGISTRATION_WINDOW"] = {
        "rule_id": _slug("SAPS.NI3_2011.REGISTRATION_WINDOW"),
        "rule_code": "SAPS.NI3_2011.REGISTRATION_WINDOW",
        "rule_name": "72-hour docket registration window",
        "description": "A submitted docket must be registered within 72 hours of submission.",
        "legal_reference_id": corpus.SLA_THRESHOLDS["legal_reference_id"],
        "rule_version": corpus.CORPUS_VERSION,
        "effective_from": "2011-01-01",
        "effective_to": None,
        "status": "ACTIVE",
        "priority": 70,
        "conditions": ["docket_submitted", "not_registered_within_window"],
        "required_controls": ["sla_evaluation"],
        "prohibited_actions": ["unlawful_delay"],
        "resulting_action": "flag_sla_breach",
        "explanation": "Delay beyond the statutory window is objectively measured and feeds misconduct tiering.",
        "window_hours": corpus.SLA_THRESHOLDS["registration_hours"],
    }
    rules["SAPS.NI3_2011.ATTENDANCE_WINDOW"] = {
        "rule_id": _slug("SAPS.NI3_2011.ATTENDANCE_WINDOW"),
        "rule_code": "SAPS.NI3_2011.ATTENDANCE_WINDOW",
        "rule_name": "72-hour docket attendance window",
        "description": "A registered docket must be attended to (investigation opened) within 72 hours of assignment.",
        "legal_reference_id": corpus.SLA_THRESHOLDS["legal_reference_id"],
        "rule_version": corpus.CORPUS_VERSION,
        "effective_from": "2011-01-01",
        "effective_to": None,
        "status": "ACTIVE",
        "priority": 70,
        "conditions": ["docket_registered", "no_investigation_within_window"],
        "required_controls": ["sla_evaluation"],
        "prohibited_actions": ["unlawful_delay"],
        "resulting_action": "flag_sla_breach",
        "explanation": "Delay beyond the statutory window is objectively measured and feeds misconduct tiering.",
        "window_hours": corpus.SLA_THRESHOLDS["attendance_hours"],
    }
    rules["SAPS.DISCIPLINE.MISCONDUCT_TIERING"] = {
        "rule_id": _slug("SAPS.DISCIPLINE.MISCONDUCT_TIERING"),
        "rule_code": "SAPS.DISCIPLINE.MISCONDUCT_TIERING",
        "rule_name": "Misconduct tiering",
        "description": "Every upheld infraction is placed in tier 1, 2 or 3 by the misconduct schedule; only objective aggravators can raise it.",
        "legal_reference_id": corpus.MISCONDUCT_LEGAL_REFERENCE_ID,
        "rule_version": corpus.CORPUS_VERSION,
        "effective_from": "2016-01-01",
        "effective_to": None,
        "status": "ACTIVE",
        "priority": 60,
        "conditions": ["disciplinary_finding_upheld"],
        "required_controls": ["misconduct_schedule_lookup"],
        "prohibited_actions": ["discretionary_tier_selection"],
        "resulting_action": "assign_misconduct_tier",
        "explanation": "Tiering removes discretion from the classification of misconduct.",
    }
    rules["SAPS.DISCIPLINE.SANCTION_MATRIX"] = {
        "rule_id": _slug("SAPS.DISCIPLINE.SANCTION_MATRIX"),
        "rule_code": "SAPS.DISCIPLINE.SANCTION_MATRIX",
        "rule_name": "Mandatory sanction matrix",
        "description": "The mandatory sanction is a function of misconduct tier and the officer's qualifying prior history.",
        "legal_reference_id": corpus.MISCONDUCT_LEGAL_REFERENCE_ID,
        "rule_version": corpus.CORPUS_VERSION,
        "effective_from": "2016-01-01",
        "effective_to": None,
        "status": "ACTIVE",
        "priority": 60,
        "conditions": ["misconduct_tier_assigned"],
        "required_controls": ["disciplinary_history_lookup"],
        "prohibited_actions": ["discretionary_sanction_selection", "unrecorded_deviation"],
        "resulting_action": "determine_mandatory_sanction",
        "explanation": "Identical facts and history always yield the identical sanction; deviations must be justified on the record.",
    }
    rules["CASE.CONFLICT_OF_INTEREST"] = {
        "rule_id": _slug("CASE.CONFLICT_OF_INTEREST"),
        "rule_code": "CASE.CONFLICT_OF_INTEREST",
        "rule_name": "Conflict of interest recusal",
        "description": (
            "An officer may not handle a docket where they are the complainant or the implicated officer, "
            "where the complainant has previously complained about them, or where a conflict is declared."
        ),
        "legal_reference_id": "RSA-PAJA-2000",
        "rule_version": corpus.CORPUS_VERSION,
        "effective_from": "2000-01-01",
        "effective_to": None,
        "status": "ACTIVE",
        "priority": 92,
        "conditions": ["identity_match_complainant_or_implicated", "prior_complaint_by_complainant", "declared_conflict"],
        "required_controls": ["identity_matching", "conflict_declaration_check"],
        "prohibited_actions": ["assign_conflicted_officer", "open_conflicted_docket", "open_conflicted_investigation"],
        "resulting_action": "deny_operation",
        "explanation": "PAJA section 3 requires a decision-maker free of bias or reasonable suspicion of bias.",
    }
    rules["CASE.ASSIGNMENT.ACTIVE_DISCIPLINARY_BLOCK"] = {
        "rule_id": _slug("CASE.ASSIGNMENT.ACTIVE_DISCIPLINARY_BLOCK"),
        "rule_code": "CASE.ASSIGNMENT.ACTIVE_DISCIPLINARY_BLOCK",
        "rule_name": "No assignment while a disciplinary case is open",
        "description": "An officer with an open disciplinary case may not be assigned new dockets until it is closed.",
        "legal_reference_id": "RSA-PACA-2004",
        "rule_version": corpus.CORPUS_VERSION,
        "effective_from": "2004-01-01",
        "effective_to": None,
        "status": "ACTIVE",
        "priority": 89,
        "conditions": ["assignee_has_open_disciplinary_case"],
        "required_controls": ["disciplinary_status_check"],
        "prohibited_actions": ["case_assignment"],
        "resulting_action": "deny_operation",
        "explanation": "Integrity-restricted officers must not take on new accountability-sensitive work.",
    }
    return rules


class RegulatoryRuleService:
    """System-controlled rule corpus with legal provenance and versioning.

    This service stores the deterministic rules that the application uses. It is
    intended to be controlled by the release process and is not editable through a
    normal user-facing admin workflow.
    """

    RULES = {
        "CASE.ACCESS.RESTRICTED": {
            "rule_id": "RULE-CASE-ACCESS-RESTRICTED",
            "rule_code": "CASE.ACCESS.RESTRICTED",
            "rule_name": "Restricted case access",
            "description": "Case access is restricted to authorized actors based on role, case state, and current integrity status.",
            "legal_reference_id": "RSA-CONSTITUTION-1996",
            "rule_version": 1,
            "effective_from": "1996-02-04",
            "effective_to": None,
            "status": "ACTIVE",
            "priority": 100,
            "conditions": ["role_allowed", "access_valid", "case_state_valid"],
            "required_controls": ["jwt_validation", "identity_status_check", "assignment_check"],
            "prohibited_actions": ["unauthorized_access", "case_mutation_when_frozen"],
            "resulting_action": "deny_operation",
            "explanation": "The application uses constitutional administrative fairness and integrity controls to constrain access.",
        },
        "CASE.FREEZE.RESTRICTED_MUTATION": {
            "rule_id": "RULE-CASE-FREEZE-RESTRICTED-MUTATION",
            "rule_code": "CASE.FREEZE.RESTRICTED_MUTATION",
            "rule_name": "Frozen case mutation restriction",
            "description": "Frozen cases prevent unauthorized operational mutation until oversight or legal review authorizes release.",
            "legal_reference_id": "RSA-CONSTITUTION-1996",
            "rule_version": 1,
            "effective_from": "1996-02-04",
            "effective_to": None,
            "status": "ACTIVE",
            "priority": 90,
            "conditions": ["case_frozen"],
            "required_controls": ["freeze_status_check", "override_authorization"],
            "prohibited_actions": ["register_docket", "investigate_docket", "reassign_case", "modify_evidence"],
            "resulting_action": "deny_operation",
            "explanation": "Frozen cases require explicit oversight authority and a reviewable reason before mutation.",
        },
        "CASE.SEPARATION_OF_DUTIES": {
            "rule_id": "RULE-CASE-SEPARATION-OF-DUTIES",
            "rule_code": "CASE.SEPARATION_OF_DUTIES",
            "rule_name": "Separation of duties",
            "description": "An actor must not be both the case handler and the final decision-maker for the same workflow step.",
            "legal_reference_id": "RSA-PAJA-2000",
            "rule_version": 1,
            "effective_from": "2000-01-01",
            "effective_to": None,
            "status": "ACTIVE",
            "priority": 80,
            "conditions": ["same_actor_for_conflicting_roles"],
            "required_controls": ["independent_authorization", "assignment_conflict_check"],
            "prohibited_actions": ["register_same_case", "final_decision_same_actor"],
            "resulting_action": "deny_operation",
            "explanation": "Operational independence prevents conflicts of interest and corruption opportunities.",
        },
        "OFFICER.REVOCATION.BLOCKS_ACCESS": {
            "rule_id": "RULE-OFFICER-REVOCATION-BLOCKS-ACCESS",
            "rule_code": "OFFICER.REVOCATION.BLOCKS_ACCESS",
            "rule_name": "Revoked officer access block",
            "description": "A revoked officer cannot legitimately continue operational access to cases or assignments.",
            "legal_reference_id": "RSA-PACA-2004",
            "rule_version": 1,
            "effective_from": "2004-01-01",
            "effective_to": None,
            "status": "ACTIVE",
            "priority": 95,
            "conditions": ["access_state_revoked"],
            "required_controls": ["identity_registry_check", "token_revalidation"],
            "prohibited_actions": ["operate_case", "access_case_data", "reassign_case"],
            "resulting_action": "deny_operation",
            "explanation": "Operational access must terminate immediately when an officer is revoked or restricted.",
        },
        "EVIDENCE.INTEGRITY": {
            "rule_id": "RULE-EVIDENCE-INTEGRITY",
            "rule_code": "EVIDENCE.INTEGRITY",
            "rule_name": "Evidence integrity and chain of custody",
            "description": "Evidence content hashes and custody records must be preserved to detect tampering.",
            "legal_reference_id": "RSA-CPA-1977",
            "rule_version": 1,
            "effective_from": "1977-01-01",
            "effective_to": None,
            "status": "ACTIVE",
            "priority": 85,
            "conditions": ["evidence_hash_changed", "custody_mismatch"],
            "required_controls": ["hash_validation", "chain_of_custody_record"],
            "prohibited_actions": ["silent_evidence_overwrite", "unauthorized_transfer"],
            "resulting_action": "deny_operation",
            "explanation": "Tampering with evidence creates an integrity failure and must be auditable.",
        },
        "ACTOR.INTEGRITY.RESTRICTS_OPERATION": {
            "rule_id": "RULE-ACTOR-INTEGRITY-RESTRICTS-OPERATION",
            "rule_code": "ACTOR.INTEGRITY.RESTRICTS_OPERATION",
            "rule_name": "Actor integrity restriction",
            "description": "A currently reviewed or disciplined actor must be treated as integrity-restricted while the status remains unresolved.",
            "legal_reference_id": "RSA-PACA-2004",
            "rule_version": 1,
            "effective_from": "2004-01-01",
            "effective_to": None,
            "status": "ACTIVE",
            "priority": 88,
            "conditions": ["integrity_status_restricted"],
            "required_controls": ["integrity_record_check", "disciplinary_status_check"],
            "prohibited_actions": ["case_assignment", "evidence_review", "final_decision"],
            "resulting_action": "deny_operation",
            "explanation": "Integrity restrictions require a documented review process and cannot be inferred from an allegation alone.",
        },
    }

    RULES.update(_build_statutory_rules())

    def __init__(self, legal_reference_service=None):
        self.legal_reference_service = legal_reference_service

    def list_rules(self, rule_family=None):
        """All rules, optionally narrowed to a code prefix (for example
        ``"IPID.S28"`` or ``"SAPS.DISCIPLINE"``)."""
        rules = [dict(rule) for rule in self.RULES.values()]
        if rule_family:
            prefix = str(rule_family).upper()
            rules = [rule for rule in rules if str(rule["rule_code"]).upper().startswith(prefix)]
        return rules

    # --- Milestone 4 corpus accessors (read-only views of regulatory_engine.corpus) ---

    @staticmethod
    def get_statutory_categories():
        return {code: dict(category) for code, category in corpus.S28_CATEGORIES.items()}

    @staticmethod
    def get_misconduct_schedule():
        return {
            "legal_reference_id": corpus.MISCONDUCT_LEGAL_REFERENCE_ID,
            "infractions": {key: dict(value) for key, value in corpus.MISCONDUCT_SCHEDULE.items()},
            "escalation_category_map": dict(corpus.ESCALATION_CATEGORY_TO_INFRACTION),
            "aggravators": dict(corpus.AGGRAVATORS),
            "max_tier": corpus.MAX_TIER,
        }

    @staticmethod
    def get_sanction_matrix():
        return {
            "legal_reference_id": corpus.MISCONDUCT_LEGAL_REFERENCE_ID,
            "matrix": {tier: list(row) for tier, row in corpus.SANCTION_MATRIX.items()},
            "descriptions": dict(corpus.SANCTION_DESCRIPTIONS),
            "prior_history_window_months": corpus.PRIOR_HISTORY_WINDOW_MONTHS,
            "deviation_requires_justification": corpus.DEVIATION_REQUIRES_JUSTIFICATION,
            "corpus_version": corpus.CORPUS_VERSION,
        }

    @staticmethod
    def get_sla_thresholds():
        return dict(corpus.SLA_THRESHOLDS)

    def get_rule(self, code):
        rule = self.RULES.get(str(code))
        if rule is None:
            return None
        return dict(rule)

    def get_version_history(self, code):
        rule = self.RULES.get(str(code))
        if rule is None:
            return []
        return [{"rule_id": rule["rule_id"], "rule_version": rule["rule_version"], "status": rule["status"]}]

    def update_rule(self, rule_id, updates):
        if not rule_id:
            raise ValueError("Rule identifier is required.")
        for rule in self.RULES.values():
            if rule.get("rule_id") == rule_id:
                raise PermissionError("Legal rules are system-controlled and cannot be modified by runtime users.")
        raise PermissionError("Rule not found.")
