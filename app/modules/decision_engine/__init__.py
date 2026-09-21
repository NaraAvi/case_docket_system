"""Objective Deterministic Decision Engine (ODDE) -- Milestone 4.

Public surface:

* :class:`ObjectiveDecisionEngine` -- statutory triage, SLA evaluation,
  misconduct tiering and mandatory sanction determination (M4.2).
* :class:`StatutoryReferralService` -- automatic IPID referral, docket freeze
  and permission stripping (M4.3).
* :class:`ConflictOfInterestService` -- separation of duties and conflict of
  interest enforcement (M4.4).

Every decision is a pure function of the codified corpus in
``app.modules.regulatory_engine.corpus`` plus the inputs supplied, so the same
facts always produce the same outcome.
"""

from app.modules.decision_engine.conflict import ConflictOfInterestService
from app.modules.decision_engine.referral import StatutoryReferralService
from app.modules.decision_engine.service import ObjectiveDecisionEngine

__all__ = ["ConflictOfInterestService", "ObjectiveDecisionEngine", "StatutoryReferralService"]
