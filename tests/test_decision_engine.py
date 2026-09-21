"""Unit tests for the Milestone 4 Objective Deterministic Decision Engine.

These exercise the pure functions (triage, SLA, tiering, sanction matrix) and
the codified corpus directly, without HTTP or persistence.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.decision_engine import sla, tiering, triage
from app.modules.regulatory_engine import corpus
from app.modules.regulatory_engine.services import RegulatoryRuleService


def _codes(text):
    return [item["rule_code"] for item in triage.detect_statutory_matters([("t", text)])]


class TestStatutoryTriage:
    def test_death_in_custody_is_detected(self):
        assert "IPID.S28.DEATH_IN_CUSTODY" in _codes("The suspect died in police custody last night.")

    def test_firearm_discharge_requires_a_police_actor(self):
        assert "IPID.S28.FIREARM_DISCHARGE" in _codes("The officer discharged his firearm at the car.")
        assert "IPID.S28.FIREARM_DISCHARGE" not in _codes("A neighbour discharged a firearm at the car.")

    def test_corruption_is_detected_and_flagged_precca(self):
        assert "IPID.S28.CORRUPTION" in _codes("The constable demanded a bribe to proceed.")
        assert corpus.S28_CATEGORIES["IPID.S28.CORRUPTION"]["precca_s34"] is True

    def test_negation_suppresses_a_match(self):
        assert _codes("The officer did not demand a bribe.") == []

    def test_neutral_text_never_triggers(self):
        assert _codes("Officer ignored my repeated follow-up requests.") == []
        assert _codes("Broken window overnight. Someone broke my window.") == []

    def test_pronoun_back_reference_uses_previous_sentence(self):
        assert "IPID.S28.FIREARM_DISCHARGE" in _codes("A police officer arrived. He discharged his firearm.")

    def test_detection_is_deterministic(self):
        text = "The police officer assaulted me and demanded a bribe."
        assert _codes(text) == _codes(text)

    def test_prescribed_matter_is_never_auto_detected(self):
        assert corpus.S28_CATEGORIES["IPID.S28.PRESCRIBED_MATTER"]["auto_detect"] is False

    def test_collect_text_sources_reads_statements_and_extras(self):
        sources = triage.collect_text_sources(
            {"title": "T", "description": "D", "statements": [{"statement_text": "S1"}]},
            extra_texts=[("flag", "F")],
        )
        texts = [text for _, text in sources]
        assert {"T", "D", "S1", "F"} <= set(texts)


class TestSlaEvaluation:
    NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)

    def test_paused_hours_clips_to_the_window(self):
        start = self.NOW - timedelta(hours=48)
        paused = sla.paused_hours(start, self.NOW, [(self.NOW - timedelta(hours=30), self.NOW - timedelta(hours=20))])
        assert paused == pytest.approx(10.0)

    def test_classify_delay_bands(self):
        assert sla.classify_delay(1) == "SLA_BREACH_MINOR"
        assert sla.classify_delay(24) == "SLA_BREACH_SERIOUS"

    def test_registration_window_overdue(self):
        submitted = self.NOW - timedelta(hours=100)
        result = sla.evaluate_windows(
            docket={"status": "AWAITING_CONSTABLE_REGISTRATION", "submitted_at": submitted.isoformat()},
            now=self.NOW,
        )
        assert result is not None

    def test_parse_timestamp_handles_none_and_iso(self):
        assert sla.parse_timestamp(None) is None
        assert sla.parse_timestamp("2026-03-10T12:00:00+00:00") == self.NOW


class TestMisconductTiering:
    def test_base_tiers_follow_the_schedule(self):
        assert tiering.classify_misconduct("UNBECOMING_CONDUCT")["misconduct_tier"] == 1
        assert tiering.classify_misconduct("NEGLECT_OF_DUTY")["misconduct_tier"] == 2
        assert tiering.classify_misconduct("CORRUPTION")["misconduct_tier"] == 3

    def test_escalation_category_maps_to_infraction(self):
        assert tiering.resolve_infraction("UNLAWFUL_DELAY") == "UNLAWFUL_DELAY"

    def test_unknown_or_blank_infraction_is_rejected(self):
        with pytest.raises(ValueError):
            tiering.resolve_infraction("NOT_A_THING")
        with pytest.raises(ValueError):
            tiering.resolve_infraction("")

    def test_concealment_raises_tier_by_one_capped(self):
        assert tiering.classify_misconduct("UNBECOMING_CONDUCT", {"concealment": True})["misconduct_tier"] == 2
        assert tiering.classify_misconduct("CORRUPTION", {"concealment": True})["misconduct_tier"] == 3

    def test_evidence_tampering_forces_tier_three(self):
        result = tiering.classify_misconduct("UNBECOMING_CONDUCT", {"evidence_tampering": True})
        assert result["misconduct_tier"] == 3
        assert result["infraction_type"] == "EVIDENCE_TAMPERING"
        assert "evidence_tampering" in result["aggravators_applied"]

    def test_s28_match_sets_tier_three_floor(self):
        result = tiering.classify_misconduct("UNBECOMING_CONDUCT", {"s28_rule_codes": ["IPID.S28.CORRUPTION"]})
        assert result["misconduct_tier"] == 3
        assert "statutory_referral" in result["aggravators_applied"]

    def test_sla_breach_is_banded_by_overdue_hours(self):
        minor = tiering.classify_misconduct("SLA_BREACH_SERIOUS", {"sla_overdue_hours": 5})
        serious = tiering.classify_misconduct("SLA_BREACH_MINOR", {"sla_overdue_hours": 30})
        assert minor["misconduct_tier"] == 1 and minor["reclassified_from"] == "SLA_BREACH_SERIOUS"
        assert serious["misconduct_tier"] == 2

    def test_classification_is_deterministic(self):
        ctx = {"concealment": True, "sla_overdue_hours": 3}
        assert tiering.classify_misconduct("SLA_BREACH_MINOR", ctx) == tiering.classify_misconduct("SLA_BREACH_MINOR", ctx)


class TestSanctionMatrix:
    NOW = datetime(2026, 6, 1, tzinfo=UTC)

    def _prior(self, tier, months_ago, case_id="DC"):
        moment = self.NOW - timedelta(days=30.4375 * months_ago)
        return {"disciplinary_case_id": case_id, "misconduct_tier": tier, "determined_at": moment.isoformat()}

    def test_first_offence_reads_first_column(self):
        assert tiering.determine_sanction(1, [], self.NOW)["mandatory_sanction"] == "WARNING"
        assert tiering.determine_sanction(2, [], self.NOW)["mandatory_sanction"] == "FINAL_WARNING"
        assert tiering.determine_sanction(3, [], self.NOW)["mandatory_sanction"] == "DISMISSAL"

    def test_priors_within_window_escalate_the_sanction(self):
        priors = [self._prior(1, 3, "A")]
        assert tiering.determine_sanction(1, priors, self.NOW)["mandatory_sanction"] == "FINAL_WARNING"
        priors.append(self._prior(1, 6, "B"))
        assert tiering.determine_sanction(1, priors, self.NOW)["mandatory_sanction"] == "SUSPENSION"

    def test_priors_are_capped_at_last_matrix_entry(self):
        priors = [self._prior(2, m, str(m)) for m in (1, 2, 3, 4, 5)]
        assert tiering.determine_sanction(2, priors, self.NOW)["mandatory_sanction"] == "DISMISSAL"

    def test_priors_outside_the_window_are_ignored(self):
        old = [self._prior(1, 30)]
        assert tiering.determine_sanction(1, old, self.NOW)["mandatory_sanction"] == "WARNING"

    def test_lower_tier_priors_do_not_count(self):
        priors = [self._prior(1, 2)]
        assert tiering.determine_sanction(2, priors, self.NOW)["mandatory_sanction"] == "FINAL_WARNING"

    def test_higher_tier_priors_count_toward_lower_tier(self):
        priors = [self._prior(3, 2)]
        assert tiering.determine_sanction(1, priors, self.NOW)["mandatory_sanction"] == "FINAL_WARNING"

    def test_invalid_tier_is_rejected(self):
        for bad in (0, 4, "x", None):
            with pytest.raises(ValueError):
                tiering.determine_sanction(bad, [], self.NOW)

    def test_result_records_prior_ids_and_deviation_rule(self):
        result = tiering.determine_sanction(1, [self._prior(1, 1, "X")], self.NOW)
        assert result["priors_considered"] == ["X"]
        assert result["deviation_requires_justification"] is True


class TestCodifiedCorpusAndRules:
    def test_eight_ipid_s28_categories_cover_a_to_h(self):
        subsections = sorted(item["subsection"] for item in corpus.S28_CATEGORIES.values())
        assert len(subsections) == 8
        assert subsections[0].endswith("(a)") and subsections[-1].endswith("(h)")

    def test_every_tier_has_a_matrix_row_and_valid_sanctions(self):
        assert set(corpus.SANCTION_MATRIX) == {1, 2, 3}
        for row in corpus.SANCTION_MATRIX.values():
            assert all(item in corpus.SANCTION_SEVERITY for item in row)

    def test_every_schedule_entry_has_a_valid_tier(self):
        assert all(1 <= item["tier"] <= corpus.MAX_TIER for item in corpus.MISCONDUCT_SCHEDULE.values())

    def test_statutory_rules_are_registered_and_reference_the_legal_catalog(self):
        from app.modules.legal_engine.services import LegalReferenceService

        service = RegulatoryRuleService()
        rules = service.list_rules()
        codes = {item["rule_code"] for item in rules}
        for expected in (
            "IPID.S28.CORRUPTION",
            "PRECCA.S34.REPORTING_DUTY",
            "SAPS.NI3_2011.REGISTRATION_WINDOW",
            "SAPS.DISCIPLINE.SANCTION_MATRIX",
            "CASE.CONFLICT_OF_INTEREST",
        ):
            assert expected in codes
        catalog = LegalReferenceService().LEGAL_REFERENCES
        for rule in rules:
            ref = rule.get("legal_reference_id")
            if ref:
                assert ref in catalog

    def test_list_rules_filters_by_family_prefix(self):
        service = RegulatoryRuleService()
        rules = service.list_rules("IPID.S28")
        assert rules and all(item["rule_code"].startswith("IPID.S28") for item in rules)
