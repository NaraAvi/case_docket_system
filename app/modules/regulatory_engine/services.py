"""Controlled regulatory rules for deterministic workflow compliance."""

from __future__ import annotations


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

    def __init__(self, legal_reference_service=None):
        self.legal_reference_service = legal_reference_service

    def list_rules(self):
        return [dict(rule) for rule in self.RULES.values()]

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
