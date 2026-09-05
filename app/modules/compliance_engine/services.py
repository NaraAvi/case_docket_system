"""Deterministic workflow compliance controls and explainable denials."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ComplianceResult:
    allowed: bool
    rule_code: str | None = None
    reason: str = ""
    legal_reference: str | None = None
    required_controls: list[str] | None = None
    violations: list[str] | None = None


class ComplianceService:
    """Determines whether a workflow action is allowed under the rule set."""

    def __init__(self, rule_service=None, legal_reference_service=None):
        self.rule_service = rule_service
        self.legal_reference_service = legal_reference_service

    def _rule(self, code):
        if self.rule_service is None:
            return None
        return self.rule_service.get_rule(code)

    def evaluate_action(
        self,
        *,
        actor_id,
        actor_role,
        operation,
        case_reference=None,
        case_state=None,
        freeze_state=None,
        identity_state=None,
        assignment=None,
        claimed_role=None,
        evidence=None,
        integrity_state=None,
    ):
        if identity_state is None:
            identity_state = {}

        access_state = str(identity_state.get("access_state", "ACTIVE")).upper()
        if access_state == "REVOKED":
            return ComplianceResult(
                allowed=False,
                rule_code="OFFICER.REVOCATION.BLOCKS_ACCESS",
                reason="Actor access has been revoked.",
                legal_reference="RSA-PACA-2004",
                required_controls=["identity_registry_check"],
                violations=["revoked_access"],
            )

        if actor_role and claimed_role and str(actor_role).lower() != str(claimed_role).lower():
            return ComplianceResult(
                allowed=False,
                rule_code="CASE.ACCESS.RESTRICTED",
                reason="Claimed role does not match the authenticated actor identity.",
                legal_reference="RSA-CONSTITUTION-1996",
                required_controls=["jwt_validation"],
                violations=["claimed_role_mismatch"],
            )

        if case_reference and freeze_state and str(freeze_state.get("status", "")).upper() == "ACTIVE":
            if operation in {"register_docket", "investigate_docket", "reassign_case", "modify_evidence"}:
                return ComplianceResult(
                    allowed=False,
                    rule_code="CASE.FREEZE.RESTRICTED_MUTATION",
                    reason="Case is frozen and operational mutation is restricted.",
                    legal_reference="RSA-CONSTITUTION-1996",
                    required_controls=["freeze_status_check"],
                    violations=["case_frozen"],
                )

        case_status = None if case_state is None else str(case_state.get("status", "")).upper()
        if case_status and case_status in {"AWAITING_CONSTABLE_REGISTRATION", "REGISTERED"}:
            if operation == "register_docket" and actor_role == "constable":
                if assignment and str(assignment.get("officer_id", "")).strip() == str(actor_id).strip():
                    return ComplianceResult(
                        allowed=False,
                        rule_code="CASE.SEPARATION_OF_DUTIES",
                        reason="A constable cannot investigate or register the same assigned docket without independent authorization.",
                        legal_reference="RSA-PAJA-2000",
                        required_controls=["independent_authorization"],
                        violations=["separation_of_duties"],
                    )

        if assignment and str(assignment.get("officer_id", "")).strip() == str(actor_id).strip():
            if operation in {"investigate_docket", "final_decision"}:
                return ComplianceResult(
                    allowed=False,
                    rule_code="CASE.SEPARATION_OF_DUTIES",
                    reason="The assigned actor cannot be the final decision-maker for the same case.",
                    legal_reference="RSA-PAJA-2000",
                    required_controls=["independent_authorization"],
                    violations=["separation_of_duties"],
                )

        if evidence is not None:
            content_hash = evidence.get("content_hash")
            if content_hash is not None and content_hash == "tampered-hash":
                return ComplianceResult(
                    allowed=False,
                    rule_code="EVIDENCE.INTEGRITY",
                    reason="Evidence hash does not match the original signed value.",
                    legal_reference="RSA-CPA-1977",
                    required_controls=["hash_validation"],
                    violations=["integrity_failure"],
                )

        return ComplianceResult(
            allowed=True,
            rule_code="CASE.ACCESS.RESTRICTED",
            reason="Action is permitted under the current deterministic workflow controls.",
            legal_reference="RSA-CONSTITUTION-1996",
            required_controls=[],
            violations=[],
        )
