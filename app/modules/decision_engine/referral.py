"""Automated statutory referral and freeze (Milestone 4.3).

When a citizen or constable logs an allegation that the decision engine
classifies under IPID Act 1 of 2011 section 28(1) -- corruption, assault or
torture, discharge of an official firearm, a death in custody or through police
action, rape -- this service, with no human discretion:

1. raises (or upgrades) an IPID escalation ticket,
2. freezes the docket with ``source="IPID_STATUTORY_MANDATE"``,
3. strips the assigned officer's write permissions (assignment SUSPENDED),
4. writes an immutable audit record citing the statute, and
5. for corruption, records the PRECCA section 34 report.

Only *newly logged* text is screened (a submission, an escalation, a flag), so
a referral IPID has already dismissed is never re-raised from the same words.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules.audit_engine.services import AuditTrailService
from app.modules.decision_engine import triage
from app.modules.regulatory_engine import corpus

TRIGGER_DOCKET_SUBMITTED = "DOCKET_SUBMITTED"
TRIGGER_CITIZEN_ESCALATION = "CITIZEN_ESCALATION"
TRIGGER_CONSTABLE_FLAG = "CONSTABLE_FLAG"


class StatutoryReferralService:
    """Boundary that turns an ODDE triage result into enforced consequences."""

    SOURCE = "IPID_STATUTORY_MANDATE"
    SYSTEM_ACTOR_ID = "SYSTEM_ODDE"
    SYSTEM_ACTOR_ROLE = "system_automation"

    def __init__(
        self,
        decision_engine,
        case_service,
        escalation_service,
        freeze_service,
        assignment_service=None,
        audit_service=None,
        integrity_service=None,
    ):
        self.decision_engine = decision_engine
        self.case_service = case_service
        self.escalation_service = escalation_service
        self.freeze_service = freeze_service
        self.assignment_service = assignment_service
        self.audit_service = audit_service or AuditTrailService()
        self.integrity_service = integrity_service

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _get_case(self, case_reference):
        for case in self.case_service.get_all_cases():
            if case.get("case_reference") == case_reference:
                return dict(case)
        return None

    @staticmethod
    def _describe(triage_result):
        first = triage_result["categories"][0]
        match = first["matches"][0]
        return (
            f"Automatic statutory referral ({triage_result['statutory_basis']}): "
            f"'{match['matched_text']}' in {match['source']}."
        )

    def _append_timeline(self, case_reference, triage_result, escalation_id, freeze_id, trigger):
        case = self._get_case(case_reference)
        if case is None:
            return
        case.setdefault("timeline", []).append(
            {
                "event_type": "statutory_ipid_referral",
                "actor_id": self.SYSTEM_ACTOR_ID,
                "actor_role": self.SYSTEM_ACTOR_ROLE,
                "timestamp": self._utc_now(),
                "details": {
                    "escalation_id": escalation_id,
                    "freeze_id": freeze_id,
                    "trigger": trigger,
                    "statutory_basis": triage_result["statutory_basis"],
                    "rule_codes": triage_result["rule_codes"],
                },
            }
        )
        self.case_service.update_case(case)

    # --------------------------------------------------------------- main entry
    def screen_allegation(
        self,
        case_reference,
        texts,
        trigger,
        triggered_by,
        triggered_by_role,
        existing_escalation_id=None,
    ):
        """Screen newly logged ``texts`` (``[(label, text), ...]``) and, if they
        describe a s28(1) matter, enforce the referral.

        Returns ``{"referred": False, "triage": ...}`` when nothing statutory
        was found, otherwise ``{"referred": True, "escalation", "freeze",
        "suspended_assignments", "triage", ...}``. Never raises for a clean
        docket; raises ``ValueError`` only if the docket has vanished.
        """
        case = self._get_case(case_reference)
        if case is None:
            raise ValueError("Case not found.")

        result = self.decision_engine.evaluate_statutory_triage({}, texts)
        if not result["mandatory_referral"]:
            return {"referred": False, "triage": result}

        rule_codes = ",".join(result["rule_codes"])
        # The assigned officer is treated as implicated unless they are the
        # person who logged the allegation (a constable flagging their own
        # docket is the reporter, not the accused).
        assignment = None
        if self.assignment_service is not None:
            current = self.assignment_service.get_current_assignment_for_case(case_reference)
            if current is not None and str(current.get("officer_id")) != str(triggered_by):
                assignment = current
        implicated_officer_id = assignment.get("officer_id") if assignment else None

        # --- 1. escalation ticket -------------------------------------------------
        escalation = None
        created_new = False
        if existing_escalation_id:
            escalation = self.escalation_service.mark_statutory(
                existing_escalation_id,
                result["statutory_basis"],
                rule_codes,
                trigger,
                implicated_officer_id=implicated_officer_id,
            )
        else:
            open_statutory = self.escalation_service.find_unresolved_statutory(case_reference)
            if open_statutory:
                escalation = open_statutory[0]
                covered = [code.strip() for code in str(escalation.get("rule_code") or "").split(",") if code.strip()]
                missing = [code for code in result["rule_codes"] if code not in covered]
                if missing:
                    merged = covered + missing
                    basis = ", ".join(
                        f"{corpus.IPID_ACT_CITATION}, section {corpus.S28_CATEGORIES[code]['subsection']}" for code in merged
                    )
                    escalation = self.escalation_service.extend_statutory(
                        escalation.get("escalation_id"), basis, ",".join(merged), self._describe(result)
                    )
            if escalation is None:
                escalation = self.escalation_service.create_statutory_escalation(
                    case_reference,
                    result["statutory_basis"],
                    rule_codes,
                    self._describe(result),
                    trigger,
                    implicated_officer_id=implicated_officer_id,
                )
                created_new = True
        escalation_id = escalation.get("escalation_id")

        # --- 2. freeze ---------------------------------------------------------
        freeze = self.freeze_service.get_current_freeze(case_reference)
        froze_now = False
        if freeze is None:
            freeze = self.freeze_service.freeze_case(
                case_reference,
                self.SYSTEM_ACTOR_ID,
                self.SYSTEM_ACTOR_ROLE,
                reason=f"Statutory IPID referral ({result['statutory_basis']}) -- escalation {escalation_id}",
                source=self.SOURCE,
                related_escalation_id=escalation_id,
            )
            froze_now = True

        # --- 3. strip the assigned officer's write permissions ------------------
        suspended = []
        if self.assignment_service is not None and assignment is not None:
            suspended = self.assignment_service.suspend_active_assignments(
                case_reference,
                self.SYSTEM_ACTOR_ID,
                self.SYSTEM_ACTOR_ROLE,
                reason=f"Statutory IPID referral -- escalation {escalation_id}",
            )

        # --- 4. immutable audit record, one per statute paragraph ---------------
        for category in result["categories"]:
            self.audit_service.log(
                {
                    "actor_id": self.SYSTEM_ACTOR_ID,
                    "actor_role": self.SYSTEM_ACTOR_ROLE,
                    "action": "statutory_ipid_referral",
                    "case_reference": case_reference,
                    "object_type": "escalation",
                    "object_id": escalation_id,
                    "new_state": "FROZEN",
                    "reason": category["title"],
                    "authorization_context": f"{corpus.IPID_ACT_CITATION}, section {category['subsection']}",
                    "rule_code": category["rule_code"],
                    "legal_reference": f"{corpus.IPID_ACT_CITATION}, section {category['subsection']}",
                    "details": {
                        "escalation_id": escalation_id,
                        "freeze_id": freeze.get("freeze_id"),
                        "trigger": trigger,
                        "triggered_by": triggered_by,
                        "triggered_by_role": triggered_by_role,
                        "implicated_officer_id": implicated_officer_id,
                        "suspended_assignment_ids": [item.get("assignment_id") for item in suspended],
                        "matched": [
                            {"source": match["source"], "matched_text": match["matched_text"]}
                            for match in category["matches"]
                        ],
                        "engine_version": result["engine_version"],
                        "corpus_version": result["corpus_version"],
                        "froze_now": froze_now,
                        "new_escalation": created_new,
                    },
                }
            )

        # --- 5. PRECCA s34 reporting record for corruption -----------------------
        if result["precca_s34_reportable"]:
            self.audit_service.log(
                {
                    "actor_id": self.SYSTEM_ACTOR_ID,
                    "actor_role": self.SYSTEM_ACTOR_ROLE,
                    "action": "precca_s34_report_recorded",
                    "case_reference": case_reference,
                    "object_type": "escalation",
                    "object_id": escalation_id,
                    "rule_code": "PRECCA.S34.REPORTING_DUTY",
                    "legal_reference": "Prevention and Combating of Corrupt Activities Act 12 of 2004, section 34",
                    "details": {
                        "escalation_id": escalation_id,
                        "reported_to": "IPID (via mandatory referral)",
                        "triggered_by": triggered_by,
                        "triggered_by_role": triggered_by_role,
                    },
                }
            )

        if implicated_officer_id and self.integrity_service is not None:
            try:
                self.integrity_service.record_allegation(
                    implicated_officer_id,
                    assignment.get("officer_role") if assignment else None,
                    case_reference,
                    details={"escalation_id": escalation_id, "rule_codes": result["rule_codes"]},
                )
            except Exception:  # noqa: BLE001 -- integrity tracking is best-effort, never blocks the referral
                pass

        self._append_timeline(case_reference, result, escalation_id, freeze.get("freeze_id"), trigger)

        return {
            "referred": True,
            "escalation": escalation,
            "freeze": freeze,
            "suspended_assignments": suspended,
            "implicated_officer_id": implicated_officer_id,
            "triage": result,
        }

    # -------------------------------------------------- trigger-specific entries
    def screen_docket_submission(self, case_reference, actor_id):
        """Screen the whole docket text once, at the moment it is submitted."""
        case = self._get_case(case_reference)
        if case is None:
            raise ValueError("Case not found.")
        texts = triage.collect_text_sources(case)
        return self.screen_allegation(case_reference, texts, TRIGGER_DOCKET_SUBMITTED, actor_id, "citizen")

    def screen_citizen_escalation(self, case_reference, escalation, actor_id):
        """Screen a citizen's own escalation and, if statutory, upgrade that
        very ticket instead of raising a duplicate."""
        return self.screen_allegation(
            case_reference,
            [("escalation", escalation.get("description"))],
            TRIGGER_CITIZEN_ESCALATION,
            actor_id,
            "citizen",
            existing_escalation_id=escalation.get("escalation_id"),
        )

    def screen_constable_flag(self, case_reference, flag, actor_id):
        return self.screen_allegation(
            case_reference,
            [("flag", flag.get("notes"))],
            TRIGGER_CONSTABLE_FLAG,
            actor_id,
            "constable",
        )

    def evaluate_post_investigation_action(self, case_reference):
        return self.decision_engine.evaluate_post_investigation_action(case_reference)
