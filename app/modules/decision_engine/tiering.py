"""Misconduct tiering and mandatory sanction determination (pure functions).

Tier is read from ``corpus.MISCONDUCT_SCHEDULE``; only the objective
aggravators in ``corpus.AGGRAVATORS`` may raise it. The sanction is then read
from ``corpus.SANCTION_MATRIX`` by tier and the officer's qualifying prior
determinations. Neither step consults rank, name or any free-text field.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.modules.decision_engine.sla import parse_timestamp
from app.modules.regulatory_engine import corpus

TIERING_RULE_CODE = "SAPS.DISCIPLINE.MISCONDUCT_TIERING"
SANCTION_RULE_CODE = "SAPS.DISCIPLINE.SANCTION_MATRIX"
_DAYS_PER_MONTH = 30.4375


def resolve_infraction(infraction_type):
    """Accept a schedule key *or* an IPID escalation category and return the
    schedule key, or raise ``ValueError``."""
    key = str(infraction_type or "").strip().upper()
    if not key:
        raise ValueError("Infraction type is required.")
    if key in corpus.MISCONDUCT_SCHEDULE:
        return key
    mapped = corpus.ESCALATION_CATEGORY_TO_INFRACTION.get(key)
    if mapped:
        return mapped
    raise ValueError(f"Unknown infraction type: {key}.")


def classify_misconduct(infraction_type, evidence_context=None):
    """Assign the misconduct tier for an upheld infraction.

    ``evidence_context`` keys (all optional):

    * ``s28_rule_codes`` -- IPID s28 rule codes triggered on the matter
      (tier-3 floor; infraction re-classified to the category's conduct).
    * ``evidence_tampering`` -- bool; re-classifies to EVIDENCE_TAMPERING.
    * ``sla_overdue_hours`` -- float; re-classifies SLA infractions by band.
    * ``concealment`` -- bool; raises the tier by one (max 3).
    """
    context = evidence_context or {}
    infraction = resolve_infraction(infraction_type)
    base_tier = corpus.MISCONDUCT_SCHEDULE[infraction]["tier"]
    tier = base_tier
    aggravators = []
    reclassified_from = None

    if infraction in {"SLA_BREACH_MINOR", "SLA_BREACH_SERIOUS"} and context.get("sla_overdue_hours") is not None:
        overdue = float(context["sla_overdue_hours"])
        banded = "SLA_BREACH_MINOR" if overdue < corpus.SLA_THRESHOLDS["minor_overdue_hours"] else "SLA_BREACH_SERIOUS"
        if banded != infraction:
            reclassified_from, infraction = infraction, banded
            tier = base_tier = corpus.MISCONDUCT_SCHEDULE[infraction]["tier"]

    s28_table = corpus.active_s28_table()
    s28_codes = [code for code in (context.get("s28_rule_codes") or []) if code in s28_table]
    if s28_codes:
        aggravators.append("statutory_referral")
        if tier < corpus.MAX_TIER:
            reclassified_from = reclassified_from or infraction
            infraction = s28_table[s28_codes[0]]["infraction_type"]
            tier = corpus.MISCONDUCT_SCHEDULE[infraction]["tier"]

    if context.get("evidence_tampering"):
        aggravators.append("evidence_tampering")
        if infraction != "EVIDENCE_TAMPERING":
            reclassified_from = reclassified_from or infraction
            infraction = "EVIDENCE_TAMPERING"
        tier = corpus.MAX_TIER

    if context.get("concealment") and tier < corpus.MAX_TIER:
        aggravators.append("concealment")
        tier = min(tier + 1, corpus.MAX_TIER)

    return {
        "rule_code": TIERING_RULE_CODE,
        "legal_reference_id": corpus.MISCONDUCT_LEGAL_REFERENCE_ID,
        "infraction_type": infraction,
        "description": corpus.MISCONDUCT_SCHEDULE[infraction]["description"],
        "base_tier": base_tier,
        "misconduct_tier": tier,
        "reclassified_from": reclassified_from,
        "aggravators_applied": aggravators,
        "aggravator_explanations": {name: corpus.AGGRAVATORS[name] for name in aggravators},
        "s28_rule_codes": s28_codes,
        "corpus_version": corpus.CORPUS_VERSION,
    }


def qualifying_priors(tier, prior_determinations, now=None):
    """Prior determinations at least as serious as ``tier`` and within the
    rolling history window."""
    now = parse_timestamp(now) or datetime.now(UTC)
    cutoff = now - timedelta(days=corpus.PRIOR_HISTORY_WINDOW_MONTHS * _DAYS_PER_MONTH)
    qualifying = []
    for prior in prior_determinations or []:
        prior_tier = prior.get("misconduct_tier")
        if prior_tier is None or int(prior_tier) < int(tier):
            continue
        determined_at = parse_timestamp(prior.get("determined_at") or prior.get("created_at"))
        if determined_at is None or determined_at < cutoff:
            continue
        qualifying.append(prior)
    qualifying.sort(key=lambda item: str(item.get("determined_at") or item.get("created_at") or ""))
    return qualifying


def determine_sanction(tier, prior_determinations=None, now=None):
    """Read the mandatory sanction from the matrix for ``tier`` and history."""
    try:
        tier = int(tier)
    except (TypeError, ValueError):
        raise ValueError("Misconduct tier must be 1, 2 or 3.") from None
    if tier not in corpus.SANCTION_MATRIX:
        raise ValueError("Misconduct tier must be 1, 2 or 3.")

    priors = qualifying_priors(tier, prior_determinations, now)
    row = corpus.SANCTION_MATRIX[tier]
    sanction = row[min(len(priors), len(row) - 1)]
    return {
        "rule_code": SANCTION_RULE_CODE,
        "legal_reference_id": corpus.MISCONDUCT_LEGAL_REFERENCE_ID,
        "misconduct_tier": tier,
        "mandatory_sanction": sanction,
        "sanction_severity": corpus.SANCTION_SEVERITY[sanction],
        "sanction_description": corpus.SANCTION_DESCRIPTIONS[sanction],
        "prior_count": len(priors),
        "priors_considered": [prior.get("disciplinary_case_id") for prior in priors],
        "matrix_row": list(row),
        "history_window_months": corpus.PRIOR_HISTORY_WINDOW_MONTHS,
        "deviation_requires_justification": corpus.DEVIATION_REQUIRES_JUSTIFICATION,
        "corpus_version": corpus.CORPUS_VERSION,
    }
