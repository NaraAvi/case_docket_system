from __future__ import annotations

import re
from datetime import UTC, datetime


class IncidentCandidateService:
    """Deterministic, provisional grouping of citizen claims into incident hypotheses."""

    VALID_RELATIONSHIP_TYPES = {"POSSIBLE_DUPLICATE", "POTENTIALLY_RELATED", "CORROBORATES", "CONTRADICTS", "DISTINCT_FROM"}

    def __init__(self, app=None, submission_repository=None, assertion_repository=None, claim_repository=None,
                 candidate_repository=None, relationship_repository=None, rule_evaluation_repository=None,
                 control_evaluation_repository=None, audit_service=None, citizen_submission_service=None,
                 case_service=None, case_creation_gate=None):
        self.app = app
        self.submission_repository = submission_repository
        self.assertion_repository = assertion_repository
        self.claim_repository = claim_repository
        self.candidate_repository = candidate_repository
        self.relationship_repository = relationship_repository
        self.rule_evaluation_repository = rule_evaluation_repository
        self.control_evaluation_repository = control_evaluation_repository
        self.audit_service = audit_service
        self.citizen_submission_service = citizen_submission_service
        self.case_service = case_service
        self.case_creation_gate = case_creation_gate

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _normalize_text(value):
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _extract_time(text):
        match = re.search(r"(?:\b|\D)(\d{1,2}:\d{2}(?:\s?[APap][Mm])?)", text)
        return match.group(1).strip().lower() if match else None

    @staticmethod
    def _extract_date(text):
        match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        return match.group(1) if match else None

    @staticmethod
    def _extract_actor(text):
        match = re.search(r"(?:officer|officers?|police)\s+([A-Za-z0-9]+)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        match = re.search(r"\b(\d{4,})\b", text)
        return match.group(1) if match else None

    @staticmethod
    def _extract_location(text):
        lowered = text.lower()
        if "rear gate" in lowered:
            return "rear gate"
        if "station" in lowered:
            return "station"
        if "gate" in lowered:
            return "gate"
        if "entrance" in lowered:
            return "entrance"
        return None

    @staticmethod
    def _is_negated(text):
        lowers = text.lower()
        return any(token in lowers for token in ("did not", "not", "never", "didn't"))

    def _submission_from_citizen(self, citizen_id, submission_id):
        submission = self.citizen_submission_service.get_submission(citizen_id, submission_id)
        if submission is None:
            raise ValueError("Submission not found.")
        if str(submission.get("citizen_id")) != str(citizen_id):
            raise ValueError("Forbidden: citizen cannot access another citizen's submission.")
        return submission

    def _list_claims_for_submission(self, citizen_id, submission_id):
        return self.claim_repository.list_for_submission(submission_id)

    def _candidate_id(self, used_ids=None):
        used = set(used_ids or [])
        existing = self.candidate_repository.list_all()
        last = max((int(item.get("candidate_id", "").split("-")[-1]) for item in existing if str(item.get("candidate_id", "")).startswith("IC-")), default=0)
        while True:
            candidate = f"IC-{last + 1:06d}"
            if candidate not in used:
                return candidate
            last += 1

    def _relationship_id(self, used_ids=None):
        used = set(used_ids or [])
        existing = self.relationship_repository.list_all()
        last = max((int(item.get("relationship_id", "").split("-")[-1]) for item in existing if str(item.get("relationship_id", "")).startswith("REL-")), default=0)
        while True:
            candidate = f"REL-{last + 1:06d}"
            if candidate not in used:
                return candidate
            last += 1

    def _assertion_text_for_claim(self, claim):
        assertion_id = claim.get("assertion_id")
        if assertion_id and self.assertion_repository is not None:
            assertion = self.assertion_repository.get_by_id(assertion_id)
            if assertion is not None:
                return assertion.get("assertion_text") or ""
        return claim.get("object_value") or claim.get("subject") or claim.get("predicate") or claim.get("claim_type") or ""

    def _claim_context(self, submission, claim):
        assertion_text = self._assertion_text_for_claim(claim)
        text = self._normalize_text(assertion_text or claim.get("claim_type"))
        return {
            "claim_id": claim.get("claim_id"),
            "assertion_id": claim.get("assertion_id"),
            "submission_id": claim.get("submission_id") or submission.get("submission_id"),
            "citizen_id": claim.get("citizen_id") or submission.get("citizen_id"),
            "actor": self._extract_actor(text) or self._extract_actor(str(submission.get("title") or "") + " " + str(submission.get("description") or "")),
            "location": self._extract_location(text) or self._normalize_text(submission.get("location")),
            "date": self._extract_date(text) or self._normalize_text(submission.get("incident_date")),
            "time": self._extract_time(text),
            "text": text,
            "negated": self._is_negated(text),
            "subject": claim.get("subject"),
            "predicate": claim.get("predicate"),
            "object_value": claim.get("object_value"),
            "provenance": claim.get("provenance"),
        }

    def _build_candidate(self, citizen_id, submission_id, claims, related_submission_ids=None, relationship_summary=None):
        created_at = self._utc_now()
        ordered = [self._claim_context(self.submission_repository.get_by_id(submission_id), claim) for claim in claims]
        source_claim_ids = [item.get("claim_id") for item in ordered if item.get("claim_id")]
        source_assertion_ids = sorted({item.get("assertion_id") for item in ordered if item.get("assertion_id")})
        deterministic_basis = {
            "submission_count": 1 + len(related_submission_ids or []),
            "claim_count": len(ordered),
            "shared_actor": next((item.get("actor") for item in ordered if item.get("actor")), None),
            "shared_location": next((item.get("location") for item in ordered if item.get("location")), None),
            "shared_date": next((item.get("date") for item in ordered if item.get("date")), None),
            "related_submission_ids": sorted({str(item) for item in (related_submission_ids or []) if item}),
            "relationship_summary": relationship_summary or {},
        }
        explanation = "Provisional incident grouping derived from citizen-asserted claim context within the protected submission boundary."
        if relationship_summary:
            explanation = relationship_summary.get("explanation") or explanation
        record = {
            "candidate_id": self._candidate_id(),
            "status": "PROVISIONAL",
            "provenance": "SYSTEM_DERIVED",
            "derivation_rule": relationship_summary.get("rule_name") if isinstance(relationship_summary, dict) else "shared_claim_context",
            "explanation": explanation,
            "source_submission_ids": sorted({str(item) for item in ([submission_id] + list(related_submission_ids or [])) if item}),
            "source_assertion_ids": source_assertion_ids,
            "source_claim_ids": source_claim_ids,
            "deterministic_basis": deterministic_basis,
            "created_at": created_at,
            "created_by": "system",
            "source_actor_id": citizen_id,
            "source_actor_role": "system",
        }
        return self.candidate_repository.create(record)

    def _evaluate_rule(self, submission_id, candidate_id, rule_code, result, reason, subject, inputs=None, related_submission_id=None, case_reference=None, legal_basis=None, metadata=None, timestamp=None):
        if self.rule_evaluation_repository is None:
            return None
        record = {
            "evaluation_id": f"RUL-{submission_id}-{len(self.rule_evaluation_repository.list_all()) + 1:04d}",
            "rule_code": rule_code,
            "rule_version": "1.0",
            "subject": subject,
            "result": result,
            "reason": reason,
            "inputs": inputs or {},
            "timestamp": timestamp or self._utc_now(),
            "source_context": "citizen_submission_analysis",
            "related_submission_id": related_submission_id or submission_id,
            "related_candidate_id": candidate_id,
            "related_case_reference": case_reference,
            "legal_basis": legal_basis,
            "metadata": metadata or {},
        }
        return self.rule_evaluation_repository.create(record)

    def _evaluate_control(self, submission_id, candidate_id, subject_action, result, reason, related_rule_ids=None, actor_id=None, actor_role=None, case_reference=None, resulting_transition=None, metadata=None, timestamp=None):
        if self.control_evaluation_repository is None:
            return None
        record = {
            "control_evaluation_id": f"CTL-{submission_id}-{len(self.control_evaluation_repository.list_all()) + 1:04d}",
            "subject_action": subject_action,
            "related_rule_evaluation_ids": related_rule_ids or [],
            "result": result,
            "reason": reason,
            "timestamp": timestamp or self._utc_now(),
            "actor_id": actor_id,
            "actor_role": actor_role,
            "source_submission_id": submission_id,
            "source_candidate_id": candidate_id,
            "source_case_reference": case_reference,
            "resulting_transition": resulting_transition,
            "metadata": metadata or {},
        }
        return self.control_evaluation_repository.create(record)

    def _make_relationship(self, source_submission_id, related_submission_id, relationship_type, rule_name, explanation, source_claim_ids, source_assertion_ids, candidate_id=None, used_ids=None):
        payload = {
            "relationship_id": self._relationship_id(used_ids),
            "candidate_id": candidate_id,
            "source_submission_id": source_submission_id,
            "related_submission_id": related_submission_id,
            "relationship_type": relationship_type,
            "status": "PROVISIONAL",
            "provenance": "SYSTEM_DERIVED",
            "explanation": explanation,
            "source_basis": {
                "rule": rule_name,
                "source_submission_id": source_submission_id,
                "related_submission_id": related_submission_id,
                "relationship_type": relationship_type,
            },
            "source_claim_ids": list(source_claim_ids),
            "source_assertion_ids": list(source_assertion_ids),
            "created_at": self._utc_now(),
            "rule_name": rule_name,
            "version": 1,
        }
        if used_ids is not None:
            used_ids.add(payload["relationship_id"])
        return payload

    def _determine_relationships(self, submission_id, claims, all_submission_ids=None):
        relationships = []
        if not claims:
            return relationships

        used_relationship_ids = set()
        if all_submission_ids is None:
            all_submission_ids = [item.get("submission_id") for item in self.submission_repository.list_all() if item.get("submission_id")]

        claim_contexts = [self._claim_context(self.submission_repository.get_by_id(submission_id), claim) for claim in claims]
        if len(claim_contexts) == 1:
            relationships.append(
                self._make_relationship(
                    submission_id,
                    submission_id,
                    "POTENTIALLY_RELATED",
                    "single_submission_context",
                    "A single citizen assertion provides a provisional incident context for the protected submission.",
                    [claim_contexts[0]["claim_id"]],
                    [claim_contexts[0]["assertion_id"]],
                    used_ids=used_relationship_ids,
                )
            )

        candidate_ids = {submission_id}
        for other_submission_id in all_submission_ids:
            if other_submission_id == submission_id:
                continue
            other_submission = self.submission_repository.get_by_id(other_submission_id)
            if other_submission is None:
                continue
            other_claims = self.claim_repository.list_for_submission(other_submission_id)
            if not other_claims:
                continue
            other_contexts = [self._claim_context(other_submission, claim) for claim in other_claims]
            for left in claim_contexts:
                for right in other_contexts:
                    if not left.get("actor") or not right.get("actor"):
                        continue
                    same_actor = str(left["actor"]).lower() == str(right["actor"]).lower()
                    same_location = str(left.get("location") or "").lower() == str(right.get("location") or "").lower()
                    same_date = str(left.get("date") or "").lower() == str(right.get("date") or "").lower()
                    left_time = left.get("time")
                    right_time = right.get("time")
                    same_time = bool(left_time and right_time and str(left_time).lower() == str(right_time).lower())
                    contradiction = left.get("negated") != right.get("negated") and same_actor and same_location and same_date
                    if contradiction:
                        rel = self._make_relationship(
                            submission_id,
                            other_submission_id,
                            "CONTRADICTS",
                            "shared_actor_location_date_conflict",
                            "Both claims reference the same actor and event context but one asserts the conduct while the other negates it.",
                            [left.get("claim_id"), right.get("claim_id")],
                            [left.get("assertion_id"), right.get("assertion_id")],
                            used_ids=used_relationship_ids,
                        )
                        relationships.append(rel)
                        continue
                    if same_actor and same_date and same_location and same_time:
                        rel = self._make_relationship(
                            submission_id,
                            other_submission_id,
                            "POSSIBLE_DUPLICATE",
                            "same_actor_location_date_time",
                            "The claims describe the same alleged actor, date, time, and location, so they form a provisional duplicate hypothesis.",
                            [left.get("claim_id"), right.get("claim_id")],
                            [left.get("assertion_id"), right.get("assertion_id")],
                            used_ids=used_relationship_ids,
                        )
                        relationships.append(rel)
                        continue
                    if same_actor and same_date and same_location and not same_time:
                        rel = self._make_relationship(
                            submission_id,
                            other_submission_id,
                            "DISTINCT_FROM",
                            "same_actor_date_location_different_time",
                            "The claims share the same alleged actor and location on the same date but different times, so they are retained as distinct provisional event contexts.",
                            [left.get("claim_id"), right.get("claim_id")],
                            [left.get("assertion_id"), right.get("assertion_id")],
                            used_ids=used_relationship_ids,
                        )
                        relationships.append(rel)
                        continue
                    if same_actor and same_date and same_location:
                        rel = self._make_relationship(
                            submission_id,
                            other_submission_id,
                            "CORROBORATES",
                            "same_event_context_overlap",
                            "The claims overlap on actor, date, and location and may describe the same possible incident without confirming it.",
                            [left.get("claim_id"), right.get("claim_id")],
                            [left.get("assertion_id"), right.get("assertion_id")],
                            used_ids=used_relationship_ids,
                        )
                        relationships.append(rel)
                        continue
                    if same_actor and same_date:
                        rel = self._make_relationship(
                            submission_id,
                            other_submission_id,
                            "POTENTIALLY_RELATED",
                            "same_actor_date_proximity",
                            "The claims share a related actor and date but not enough deterministic detail to merge them as one incident.",
                            [left.get("claim_id"), right.get("claim_id")],
                            [left.get("assertion_id"), right.get("assertion_id")],
                            used_ids=used_relationship_ids,
                        )
                        relationships.append(rel)

        deduped = []
        seen = set()
        for relationship in relationships:
            key = (
                str(relationship["source_submission_id"]),
                str(relationship["related_submission_id"]),
                str(relationship["relationship_type"]),
                str(relationship["source_basis"]["rule"]),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(relationship)
        return deduped

    def analyze_submission(self, citizen_id, submission_id, payload=None):
        if not citizen_id:
            raise ValueError("Citizen identity is required.")
        submission = self._submission_from_citizen(citizen_id, submission_id)
        claims = self._list_claims_for_submission(citizen_id, submission_id)
        if not claims:
            raise ValueError("No claims available for analysis; a candidate cannot be fabricated without source claims.")

        all_submission_ids = [item.get("submission_id") for item in self.submission_repository.list_all() if item.get("submission_id")]
        all_submission_ids = [sid for sid in all_submission_ids if sid != submission_id]
        relationships = []
        for relationship in self._determine_relationships(submission_id, claims, all_submission_ids):
            existing = self.relationship_repository.get_by_rule(
                relationship["source_submission_id"],
                relationship["related_submission_id"],
                relationship["relationship_type"],
                relationship["rule_name"],
            )
            if existing is None:
                persisted = self.relationship_repository.create(relationship)
                relationships.append(persisted)
            else:
                relationships.append(existing)

        related_submission_ids = sorted({str(item["related_submission_id"]) for item in relationships if str(item["related_submission_id"]) != str(submission_id)})
        duplicate_count = sum(1 for item in relationships if str(item.get("relationship_type") or "").upper() == "POSSIBLE_DUPLICATE")
        related_count = sum(1 for item in relationships if str(item.get("relationship_type") or "").upper() in {"POTENTIALLY_RELATED", "CORROBORATES"})
        relationship_summary = {
            "rule_name": "citizen_submission_clustering",
            "duplicate_count": duplicate_count,
            "related_count": related_count,
            "related_submission_ids": related_submission_ids,
            "explanation": "Repeated or related submissions are clustered by provenance and event context; duplicate reports are not automatically converted into multiple cases.",
        }

        possible_duplicate = any(str(item.get("relationship_type") or "").upper() == "POSSIBLE_DUPLICATE" for item in relationships)
        candidate_status = "PROVISIONAL"
        if possible_duplicate and len(related_submission_ids) > 0:
            candidate_status = "REVIEW_REQUIRED"

        candidate = self._build_candidate(citizen_id, submission_id, claims, related_submission_ids=related_submission_ids, relationship_summary=relationship_summary)
        candidate.update({"status": candidate_status})
        self.candidate_repository.update(candidate["candidate_id"], {"status": candidate_status})
        candidate = self.candidate_repository.get_by_id(candidate["candidate_id"])

        rule_evals = []
        rule_evals.append(self._evaluate_rule(
            submission_id=submission_id,
            candidate_id=candidate["candidate_id"],
            rule_code="SUBMISSION.DUPLICATE_CLUSTER",
            result="ALLOWED" if not possible_duplicate else "REVIEW_REQUIRED",
            reason="Repeated reports are clustered and remain protected; identical submissions are not auto-multiplied into separate procedural cases." if possible_duplicate else "No duplicate cluster was identified for this submission.",
            subject="submission_relationship",
            inputs={"related_submissions": related_submission_ids, "duplicate_count": duplicate_count},
            related_submission_id=submission_id,
            legal_basis="Protected-submission clustering maintains a single incident decision boundary while preserving the original report history.",
            metadata={"candidate_id": candidate["candidate_id"], "duplicate_count": duplicate_count},
        ))
        rule_evals.append(self._evaluate_rule(
            submission_id=submission_id,
            candidate_id=candidate["candidate_id"],
            rule_code="SUBMISSION.NEW_INCIDENT_CONTROL",
            result="ALLOWED" if not possible_duplicate else "REVIEW_REQUIRED",
            reason="A new candidate is allowed only when the system finds it is not a repeated report of the same apparent incident.",
            subject="incident_candidate_creation",
            inputs={"related_submissions": related_submission_ids, "related_count": related_count},
            related_submission_id=submission_id,
            legal_basis="Citizen reporting is unlimited, but procedural case multiplication is controlled by the system.",
            metadata={"candidate_id": candidate["candidate_id"], "related_count": related_count},
        ))

        control_result = "ALLOWED" if not possible_duplicate else "REVIEW_REQUIRED"
        control_reason = "The system allows the protected submission to advance as an incident candidate without auto-multiplying cases." if control_result == "ALLOWED" else "The system flagged repeated or uncertain cluster semantics and requires review before procedural case creation."
        control_eval = self._evaluate_control(
            submission_id=submission_id,
            candidate_id=candidate["candidate_id"],
            subject_action="case_creation_gate",
            result=control_result,
            reason=control_reason,
            related_rule_ids=[item.get("evaluation_id") for item in rule_evals if item],
            actor_id=citizen_id,
            actor_role="citizen",
            resulting_transition="incident_candidate_provisional" if control_result == "ALLOWED" else "incident_candidate_review_required",
            metadata={"candidate_id": candidate["candidate_id"], "duplicate_cluster": possible_duplicate, "related_submission_ids": related_submission_ids},
        )

        if self.audit_service is not None:
            self.audit_service.log({
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "action": "incident_candidate_analyzed",
                "object_type": "incident_candidate",
                "object_id": candidate["candidate_id"],
                "details": {
                    "submission_id": submission_id,
                    "relationship_count": len(relationships),
                    "provenance": "SYSTEM_DERIVED",
                    "candidate_status": candidate_status,
                    "duplicate_report_detected": possible_duplicate,
                },
            })

        return {
            "candidate": candidate,
            "candidates": [candidate],
            "relationships": relationships,
            "submission_id": submission_id,
            "relationship_summary": relationship_summary,
            "rule_evaluations": [item for item in rule_evals if item is not None],
            "control_evaluation": control_eval,
            "status": candidate_status,
        }

    def list_candidates(self, citizen_id, submission_id):
        self._submission_from_citizen(citizen_id, submission_id)
        return self.candidate_repository.list_for_submission(submission_id)

    def list_relationships(self, citizen_id, submission_id):
        self._submission_from_citizen(citizen_id, submission_id)
        return self.relationship_repository.list_for_submission(submission_id)

    def create_case_from_candidate(self, citizen_id, submission_id, candidate_id):
        if not citizen_id:
            raise ValueError("Citizen identity is required.")

        submission = self._submission_from_citizen(citizen_id, submission_id)
        candidate = self.candidate_repository.get_by_id(candidate_id)
        if candidate is None:
            raise ValueError("Incident candidate not found.")
        if str(candidate.get("source_actor_id") or "").strip() and str(candidate.get("source_actor_id")) != str(citizen_id):
            raise ValueError("Forbidden: citizen cannot access another citizen's incident candidate.")

        if self.case_creation_gate is None:
            self.case_creation_gate = getattr(self.app.extensions, "get", lambda *_: None)("case_creation_gate") if self.app else None
        if self.case_creation_gate is None:
            from app.modules.control_gate import CaseCreationGate
            self.case_creation_gate = CaseCreationGate(case_service=self.case_service)

        candidate_hypothesis = self.candidate_repository.get_by_id(candidate_id)
        related_submission_ids = candidate_hypothesis.get("deterministic_basis", {}).get("related_submission_ids", []) if candidate_hypothesis else []
        duplicate_reports = bool(
            candidate_hypothesis and candidate_hypothesis.get("status") == "REVIEW_REQUIRED"
            and related_submission_ids
        )
        if duplicate_reports:
            control_evaluation = self._evaluate_control(
                submission_id=submission_id,
                candidate_id=candidate_id,
                subject_action="case_creation_gate",
                result="BLOCKED",
                reason="Repeated or uncertain cluster semantics block automatic procedural conversion; the system keeps the original protected submissions and requires review.",
                related_rule_ids=[],
                actor_id=citizen_id,
                actor_role="citizen",
                resulting_transition="case_creation_blocked_duplicate_cluster",
                metadata={"duplicate_cluster": True, "related_submission_ids": related_submission_ids},
            )
            return {
                "status": "BLOCKED",
                "gate": "case_creation",
                "candidate_id": candidate_id,
                "submission_id": submission_id,
                "reason": "Repeated or uncertain cluster semantics block automatic procedural conversion.",
                "details": {"duplicate_cluster": True, "related_submission_ids": related_submission_ids, "control_evaluation": control_evaluation},
            }

        gate_result = self.case_creation_gate.check(
            candidate=candidate,
            submission=submission,
            actor_id=citizen_id,
            actor_role="citizen",
            candidate_id=candidate_id,
            submission_id=submission_id,
        )

        result = {
            "status": gate_result.status,
            "gate": gate_result.gate,
            "candidate_id": candidate_id,
            "submission_id": submission_id,
            "reason": gate_result.message,
            "details": gate_result.details,
        }

        if not gate_result.allowed:
            if self.audit_service is not None:
                self.audit_service.log({
                    "actor_id": citizen_id,
                    "actor_role": "citizen",
                    "action": "incident_candidate_case_creation_blocked",
                    "object_type": "incident_candidate",
                    "object_id": candidate_id,
                    "details": {
                        "submission_id": submission_id,
                        "gate": gate_result.gate,
                        "status": gate_result.status,
                        "reason": gate_result.message,
                    },
                })
            return result

        if self.case_service is None:
            raise ValueError("Case service is unavailable for procedural case conversion.")

        case_payload = {
            "title": submission.get("title") or "Incident candidate review",
            "description": submission.get("description") or candidate.get("explanation") or "Procedural case generated after a reviewed incident candidate.",
            "incident_date": submission.get("incident_date"),
            "location": submission.get("location"),
            "source_submission_id": submission_id,
            "source_candidate_id": candidate_id,
            "case_origin": "incident_candidate",
            "gate_decision": gate_result.status,
            "status": "AWAITING_CONSTABLE_REGISTRATION",
            "submitted_at": self._utc_now(),
            "timeline": [{
                "event_type": "incident_candidate_case_created",
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "timestamp": self._utc_now(),
                "details": {
                    "candidate_id": candidate_id,
                    "submission_id": submission_id,
                    "gate": gate_result.gate,
                    "status": gate_result.status,
                },
            }],
        }
        case = self.case_service.create_case(citizen_id, case_payload)
        result["case_reference"] = case.get("case_reference")
        result["case_id"] = case.get("id")
        result["status"] = gate_result.status
        result["gate"] = gate_result.gate
        result["details"] = {**gate_result.details, "case_reference": case.get("case_reference")}

        if self.audit_service is not None:
            self.audit_service.log({
                "actor_id": citizen_id,
                "actor_role": "citizen",
                "action": "incident_candidate_case_created",
                "object_type": "case_docket",
                "object_id": case.get("case_reference"),
                "details": {
                    "candidate_id": candidate_id,
                    "submission_id": submission_id,
                    "gate": gate_result.gate,
                    "status": gate_result.status,
                    "case_reference": case.get("case_reference"),
                },
            })

        return result
