"""Objective Deterministic Decision Engine (ODDE).

Strips discretion out of four accountability decisions and replaces it with a
function of the codified statutory corpus:

1. ``evaluate_statutory_triage``      -- is this an IPID Act s28(1) matter?
2. ``evaluate_sla_compliance``        -- was the SAPS NI 3/2011 window met?
3. ``calculate_misconduct_tier``      -- which tier is the upheld conduct?
4. ``determine_mandatory_sanction``   -- what does the matrix mandate?

Collaborators are injected so the engine has no persistence of its own; every
argument is optional and the engine degrades to the pure functions when a
collaborator is absent.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules.decision_engine import sla as sla_module
from app.modules.decision_engine import tiering, triage
from app.modules.regulatory_engine import corpus

TAMPERED_STATES = {"TAMPERED", "HASH_MISMATCH", "INTEGRITY_FAILURE"}
TAMPERED_HASH_MARKER = "tampered-hash"  # same marker ComplianceService treats as a failed hash check


class ObjectiveDecisionEngine:
    """Deterministic statutory decision boundary (Milestone 4.2)."""

    def __init__(
        self,
        case_service=None,
        assignment_service=None,
        investigation_service=None,
        freeze_service=None,
        disciplinary_service=None,
        audit_service=None,
        clock=None,
    ):
        self.case_service = case_service
        self.assignment_service = assignment_service
        self.investigation_service = investigation_service
        self.freeze_service = freeze_service
        self.disciplinary_service = disciplinary_service
        self.audit_service = audit_service
        self._clock = clock

    # ------------------------------------------------------------------ helpers
    def _now(self):
        return self._clock() if self._clock is not None else datetime.now(UTC)

    def _get_case(self, case_reference):
        if self.case_service is None or not case_reference:
            return None
        for case in self.case_service.get_all_cases():
            if case.get("case_reference") == case_reference:
                return dict(case)
        return None

    @staticmethod
    def has_evidence_tampering(evidence_items):
        for item in evidence_items or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("integrity_status") or "").upper() in TAMPERED_STATES:
                return True
            if item.get("content_hash") == TAMPERED_HASH_MARKER or item.get("sha256_hash") == TAMPERED_HASH_MARKER:
                return True
        return False

    # ------------------------------------------------- 1. statutory triage
    def evaluate_statutory_triage(self, docket_data=None, extra_texts=None):
        """Inspect a docket's incident text and categories for IPID Act s28(1)
        matters.

        ``docket_data`` is a docket dict (``title``, ``description``,
        ``statements``, ``evidence``, ``flags``); ``extra_texts`` is an
        optional list of ``(label, text)`` pairs (or a ``{label: text}`` dict)
        for newly logged text such as an escalation description.
        """
        sources = triage.collect_text_sources(docket_data, extra_texts)
        matters = triage.detect_statutory_matters(sources)

        categories = []
        active_table = corpus.active_s28_table()
        for matter in matters:
            category = active_table[matter["rule_code"]]
            categories.append(
                {
                    "rule_code": matter["rule_code"],
                    "subsection": category["subsection"],
                    "title": category["title"],
                    "legal_reference_id": category["legal_reference_id"],
                    "infraction_type": category["infraction_type"],
                    "precca_s34": bool(category.get("precca_s34")),
                    "matches": matter["matches"],
                }
            )

        precca = any(item["precca_s34"] for item in categories)
        legal_references = ["RSA-IPID-2011"] if categories else []
        if precca:
            legal_references.append("RSA-PRECCA-S34")
        basis = ", ".join(f"{corpus.IPID_ACT_CITATION}, section {item['subsection']}" for item in categories)

        return {
            "mandatory_referral": bool(categories),
            "requires_freeze": bool(categories),
            "requires_permission_strip": bool(categories),
            "categories": categories,
            "rule_codes": [item["rule_code"] for item in categories],
            "subsections": [item["subsection"] for item in categories],
            "statutory_basis": basis,
            "primary_infraction": categories[0]["infraction_type"] if categories else None,
            "precca_s34_reportable": precca,
            "legal_references": legal_references,
            "sources_scanned": [label for label, _ in sources],
            "engine_version": corpus.ENGINE_VERSION,
            "corpus_version": corpus.CORPUS_VERSION,
        }

    # ---------------------------------------------------- 2. SLA compliance
    def evaluate_sla_compliance(self, case_reference, now=None):
        """Evaluate the registration and attendance windows for a docket,
        excluding time the docket spent frozen by IPID."""
        case = self._get_case(case_reference)
        if case is None:
            raise ValueError("Case not found.")

        assignment = None
        if self.assignment_service is not None:
            # A statutory freeze suspends the assignment but the officer stays
            # the responsible one for the window that ran before it.
            getter = getattr(self.assignment_service, "get_implicated_assignment", None) or self.assignment_service.get_current_assignment_for_case
            assignment = getter(case_reference)

        investigations = []
        if self.investigation_service is not None:
            investigations = self.investigation_service.repository.list_for_case(case_reference)

        paused = []
        if self.freeze_service is not None:
            for freeze in self.freeze_service.get_freeze_history(case_reference):
                paused.append((freeze.get("frozen_at"), freeze.get("released_at")))

        result = sla_module.evaluate_windows(
            docket=case,
            assignment=assignment,
            investigations=investigations,
            paused_intervals=paused,
            now=now or self._now(),
        )
        result["frozen_intervals_excluded"] = len(paused)
        result["current_status"] = case.get("status")
        return result

    # -------------------------------------------------- 3. misconduct tier
    def calculate_misconduct_tier(self, officer_id, infraction_type, evidence_context=None):
        """Determine tier 1, 2 or 3 for ``infraction_type`` (a schedule key or
        an IPID escalation category) given the objective ``evidence_context``
        (see :func:`tiering.classify_misconduct`)."""
        if not officer_id:
            raise ValueError("Officer identity is required.")
        result = tiering.classify_misconduct(infraction_type, evidence_context)
        result["officer_id"] = str(officer_id)
        return result

    # ------------------------------------------- 4. mandatory sanction
    def _prior_determinations(self, officer_id, exclude_case_id=None):
        if self.disciplinary_service is None:
            return []
        priors = []
        for case in self.disciplinary_service.list_cases():
            if str(case.get("implicated_officer_id")) != str(officer_id):
                continue
            if exclude_case_id and case.get("disciplinary_case_id") == exclude_case_id:
                continue
            if case.get("misconduct_tier") is None:
                continue
            priors.append(case)
        return priors

    def determine_mandatory_sanction(self, officer_id, misconduct_tier, exclude_case_id=None, now=None):
        """Read the mandatory sanction for ``misconduct_tier`` from the matrix,
        progressing it by the officer's qualifying prior determinations."""
        if not officer_id:
            raise ValueError("Officer identity is required.")
        priors = self._prior_determinations(officer_id, exclude_case_id)
        result = tiering.determine_sanction(misconduct_tier, priors, now or self._now())
        result["officer_id"] = str(officer_id)
        return result

    # ------------------------------------------------ composition (used by IPID)
    def build_evidence_context(self, case_reference, escalation=None, concealment=False):
        """Assemble the objective inputs the tiering rules consume."""
        case = self._get_case(case_reference) or {}
        context = {"concealment": bool(concealment)}

        s28_codes = []
        stored = str((escalation or {}).get("rule_code") or "")
        active_table = corpus.active_s28_table()
        for code in [item.strip() for item in stored.split(",") if item.strip()]:
            if code in active_table and code not in s28_codes:
                s28_codes.append(code)
        if not s28_codes and escalation and escalation.get("description"):
            retriaged = self.evaluate_statutory_triage({}, [("escalation", escalation["description"])])
            s28_codes = list(retriaged["rule_codes"])
        context["s28_rule_codes"] = s28_codes
        context["evidence_tampering"] = self.has_evidence_tampering(case.get("evidence"))
        context["evidence_count"] = len(case.get("evidence") or [])

        if case_reference and case:
            try:
                sla = self.evaluate_sla_compliance(case_reference)
            except ValueError:
                sla = None
            if sla is not None:
                context["sla_status"] = sla["status"]
                context["sla_overdue_hours"] = sla["worst_overdue_hours"] if sla["breached"] else None
                context["sla_delay_infraction"] = sla["delay_infraction"]
        return context

    def determine_disciplinary_outcome(self, officer_id, escalation, concealment=False, exclude_case_id=None, now=None):
        """Full pipeline for an upheld escalation: context -> tier -> sanction.

        The returned dict is persisted verbatim on the disciplinary case so the
        outcome can be re-verified against the corpus version that produced it.
        """
        escalation = escalation or {}
        moment = sla_module.parse_timestamp(now) or self._now()
        case_reference = escalation.get("case_reference")
        context = self.build_evidence_context(case_reference, escalation, concealment)

        category = str(escalation.get("category") or "").upper()
        infraction = corpus.ESCALATION_CATEGORY_TO_INFRACTION.get(category)
        if category == "UNLAWFUL_DELAY" and context.get("sla_delay_infraction"):
            infraction = context["sla_delay_infraction"]  # objectively measured delay replaces the generic label
        if infraction is None and context["s28_rule_codes"]:
            infraction = corpus.active_s28_table()[context["s28_rule_codes"][0]]["infraction_type"]
        infraction = infraction or "GENERAL_MISCONDUCT"

        tier_result = self.calculate_misconduct_tier(officer_id, infraction, context)
        sanction = self.determine_mandatory_sanction(
            officer_id, tier_result["misconduct_tier"], exclude_case_id=exclude_case_id, now=moment
        )
        return {
            "officer_id": str(officer_id),
            "escalation_id": escalation.get("escalation_id"),
            "case_reference": case_reference,
            "misconduct_tier": tier_result["misconduct_tier"],
            "infraction_type": tier_result["infraction_type"],
            "mandatory_sanction": sanction["mandatory_sanction"],
            "tiering": tier_result,
            "sanction": sanction,
            "inputs": context,
            "engine_version": corpus.ENGINE_VERSION,
            "corpus_version": corpus.CORPUS_VERSION,
            "determined_at": moment.isoformat(),
        }
