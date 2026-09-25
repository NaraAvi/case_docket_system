"""Case lifecycle orchestration for citizen docket creation."""

from __future__ import annotations

from datetime import UTC, datetime

from app.database.repositories.case_repository import CaseRepository


class CaseService:
    """Application service to manage docket lifecycle orchestration."""

    PROCEDURAL_INDICATOR_ORDER = [
        "POLICE_INVOLVEMENT",
        "OFFICER_CONDUCT_INCIDENT",
        "PHYSICAL_HARM_REPORTED",
        "INJURY_REPORTED",
        "SERIOUS_INJURY_REPORTED",
        "MEDICAL_ATTENTION_REPORTED",
        "WITNESS_PRESENT",
        "SUPPORTING_EVIDENCE_DECLARED",
        "SUPPORTING_EVIDENCE_SUBMITTED",
        "MULTIPLE_PERSONS_INVOLVED",
        "CURRENT_SAFETY_CONCERN",
        "PROPERTY_IMPACT_REPORTED",
        "FINANCIAL_IMPACT_REPORTED",
        "PREVIOUS_REPORT_REFERENCED",
        "CONFLICTING_OR_UNCERTAIN_INFORMATION",
    ]

    def __init__(self, repository=None, app=None):
        self.app = app
        self.repository = repository or CaseRepository(app=app)

    @staticmethod
    def generate_case_reference(index):
        stamp = datetime.now(UTC).strftime("%Y%m%d")
        return f"CD-{stamp}-{index:06d}"

    @staticmethod
    def _timeline_event(event_type, actor_id, actor_role, details=None):
        return {
            "event_type": event_type,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "timestamp": datetime.now(UTC).isoformat(),
            "details": details or {},
        }

    @classmethod
    def generate_procedural_assessment(cls, case_data):
        if not isinstance(case_data, dict):
            return None

        case_reference = str(case_data.get("case_reference") or "CASE-UNSPECIFIED")
        nested_submission = case_data.get("citizen_submission") if isinstance(case_data.get("citizen_submission"), dict) else {}
        original_content = {}
        if isinstance(nested_submission.get("original_content"), dict):
            original_content.update(nested_submission["original_content"])
        if isinstance(case_data.get("original_content"), dict):
            original_content.update(case_data["original_content"])

        case_text_parts = [
            case_data.get("title"),
            case_data.get("description"),
            case_data.get("location"),
            case_data.get("incident_date"),
            case_data.get("status"),
            case_data.get("case_origin"),
            case_data.get("gate_decision"),
        ]
        flattened_values = []

        def append_value(value):
            if isinstance(value, dict):
                for nested in value.values():
                    append_value(nested)
            elif isinstance(value, list):
                for nested in value:
                    append_value(nested)
            elif value not in (None, ""):
                flattened_values.append(str(value))

        for item in case_text_parts:
            append_value(item)
        for item in original_content.values():
            append_value(item)

        combined = " ".join(flattened_values).lower()

        indicator_codes = set()
        relationship = str(original_content.get("reporter_relationship") or "").lower()

        if any(token in combined for token in ["police", "constable", "officer", "station gate", "station officer", "police station"]):
            indicator_codes.add("POLICE_INVOLVEMENT")
        if any(token in combined for token in ["officer conduct", "misconduct", "abuse", "assault", "harassment", "brutality"]):
            indicator_codes.add("OFFICER_CONDUCT_INCIDENT")

        if any(token in combined for token in ["physical harm", "physical injury", "injury", "hurt", "hit", "punch", "strike", "assault"]):
            indicator_codes.add("PHYSICAL_HARM_REPORTED")
        if any(token in combined for token in ["injured", "injury", "wound", "broken bone", "cut", "bruise"]):
            indicator_codes.add("INJURY_REPORTED")
        if any(token in combined for token in ["serious injury", "critical injury", "life threatening", "hospitalised", "hospitalized", "emergency treatment"]):
            indicator_codes.add("SERIOUS_INJURY_REPORTED")
        if original_content.get("medical_attention") in {"Yes", "YES", "yes", True} or "medical attention" in combined:
            indicator_codes.add("MEDICAL_ATTENTION_REPORTED")

        if relationship and relationship not in {"self", "complainant", "citizen", "officer", "suspect"}:
            indicator_codes.add("WITNESS_PRESENT")
        if original_content.get("evidence_available") in {"Yes", "YES", "yes", True} or "evidence" in combined:
            indicator_codes.add("SUPPORTING_EVIDENCE_DECLARED")
        if isinstance(case_data.get("evidence"), list) and case_data["evidence"] or isinstance(nested_submission.get("evidence"), list) and nested_submission["evidence"]:
            indicator_codes.add("SUPPORTING_EVIDENCE_SUBMITTED")
        if original_content.get("people_count") not in (None, "", "0") or "multiple people" in combined or "others involved" in combined:
            indicator_codes.add("MULTIPLE_PERSONS_INVOLVED")
        if original_content.get("current_safety_question") not in (None, "", "NO", "NOT_AT_RISK", "AFTER_EVENT_SAFE", "SAFE") or "current safety" in combined and "risk" in combined:
            indicator_codes.add("CURRENT_SAFETY_CONCERN")
        if original_content.get("property_impact_question") in {"Yes", "YES", "yes", True} or "property" in combined and ("damage" in combined or "loss" in combined):
            indicator_codes.add("PROPERTY_IMPACT_REPORTED")
        if original_content.get("property_value") not in (None, "") or "financial" in combined or "money" in combined:
            indicator_codes.add("FINANCIAL_IMPACT_REPORTED")
        if original_content.get("previous_report_question") in {"Yes", "YES", "yes", True} or "previous report" in combined:
            indicator_codes.add("PREVIOUS_REPORT_REFERENCED")
        if any(token in combined for token in ["uncertain", "unclear", "inconsistent", "conflicting", "unverified", "unknown"]):
            indicator_codes.add("CONFLICTING_OR_UNCERTAIN_INFORMATION")

        ordered = [code for code in cls.PROCEDURAL_INDICATOR_ORDER if code in indicator_codes]
        ordered.extend(sorted(indicator_codes.difference(ordered)))

        if "SERIOUS_INJURY_REPORTED" in indicator_codes or ("MEDICAL_ATTENTION_REPORTED" in indicator_codes and "CURRENT_SAFETY_CONCERN" in indicator_codes):
            attention_level = "CRITICAL"
        elif "OFFICER_CONDUCT_INCIDENT" in indicator_codes or "CURRENT_SAFETY_CONCERN" in indicator_codes or "MEDICAL_ATTENTION_REPORTED" in indicator_codes:
            attention_level = "HIGH"
        elif len(ordered) >= 3:
            attention_level = "ELEVATED"
        else:
            attention_level = "ROUTINE"

        if ordered:
            summary = (
                "Read-only system-generated assessment. The preserved source data contains the following procedural indicators: "
                + ", ".join(ordered) + ". No legal conclusion, misconduct finding, or criminal classification has been made."
            )
        else:
            summary = "Read-only system-generated assessment. The preserved source data did not trigger a procedural concern in this version of the rule set."

        assessment = {
            "assessment_id": f"PA-{case_reference}-{len(ordered) + 1:03d}",
            "case_reference": case_reference,
            "version": "v1",
            "generated_at": datetime.now(UTC).isoformat(),
            "attention_level": attention_level,
            "indicator_codes": ordered,
            "summary": summary,
            "read_only": True,
            "generated_by": "system",
            "source_scope": "case_level",
        }
        return assessment

    def create_case(self, citizen_id, case_data):
        if not citizen_id:
            raise ValueError("Citizen is required to create a case.")

        next_index = len(self.repository.list()) + 1
        explicit_status = str(case_data.get("status") or "DRAFT").strip() or "DRAFT"
        case_payload = {
            **case_data,
            "id": next_index,
            "citizen_id": citizen_id,
            "case_reference": self.generate_case_reference(next_index),
            "status": explicit_status,
            "statements": case_data.get("statements", []),
            "evidence": case_data.get("evidence", []),
            "timeline": case_data.get("timeline") or [
                self._timeline_event(
                    "docket_created",
                    citizen_id,
                    "citizen",
                    {"status": explicit_status},
                )
            ],
        }
        if not case_payload.get("procedural_assessment"):
            case_payload["procedural_assessment"] = self.generate_procedural_assessment(case_payload)
        return self.repository.create(case_payload)

    def update_case(self, case_data):
        case_id = case_data.get("id")
        if case_id is None:
            raise ValueError("Case identifier is required to update a case.")
        if not case_data.get("procedural_assessment"):
            case_data["procedural_assessment"] = self.generate_procedural_assessment(case_data)
        updated = self.repository.update(case_id, case_data)
        return updated

    def list_cases_for_citizen(self, citizen_id):
        return self.repository.list_for_citizen(citizen_id)

    def get_case_for_citizen(self, citizen_id, case_reference):
        return self.repository.get_for_citizen(citizen_id, case_reference)

    def get_case(self, case_reference):
        if not case_reference:
            return None
        for case in self.get_all_cases():
            if case.get("case_reference") == case_reference:
                return case
        return None

    def get_all_cases(self):
        cases = self.repository.list()
        for case in cases:
            if not case.get("procedural_assessment"):
                case["procedural_assessment"] = self.generate_procedural_assessment(case)
        return cases
