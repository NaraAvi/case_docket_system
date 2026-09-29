"""Procedure foundation for detective-only legal and evidentiary controls."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.database.repositories.procedure_repository import (
    CaseProcedureStateRepository,
    ProcedureProfileRepository,
    ProcedureRequirementRepository,
    ProcedureRuleRepository,
    SourceRegisterRepository,
)
from app.modules.audit_engine.services import AuditTrailService
from app.modules.control_gate import BaseControlGate, ControlGateResult


class ProcedureGateEngine(BaseControlGate):
    """Gate engine for detective procedure and protected-source continuity."""

    gate_name = "procedure"
    REQUIREMENT_STATES = {
        "NOT_STARTED",
        "IN_PROGRESS",
        "COMPLETED",
        "NOT_COMPLETED",
        "NOT_APPLICABLE",
        "BLOCKED",
    }
    DEFAULT_RULESET_VERSION = "procedure-v1"

    def __init__(
        self,
        case_service=None,
        audit_service=None,
        source_repository=None,
        rule_repository=None,
        profile_repository=None,
        state_repository=None,
        requirement_repository=None,
        assignment_service=None,
        citizen_submission_service=None,
        incident_candidate_service=None,
        app=None,
    ):
        super().__init__(
            freeze_service=None,
            conflict_service=None,
            assignment_service=assignment_service,
            audit_service=audit_service,
            case_service=case_service,
        )
        self.app = app
        self.case_service = case_service
        self.audit_service = audit_service or AuditTrailService()
        self.source_repository = source_repository or SourceRegisterRepository(app=app)
        self.rule_repository = rule_repository or ProcedureRuleRepository(app=app)
        self.profile_repository = profile_repository or ProcedureProfileRepository(app=app)
        self.state_repository = state_repository or CaseProcedureStateRepository(app=app)
        self.requirement_repository = requirement_repository or ProcedureRequirementRepository(app=app)
        self.assignment_service = assignment_service
        self.citizen_submission_service = citizen_submission_service
        self.incident_candidate_service = incident_candidate_service

    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _normalize_requirement_state(self, state):
        if state is None:
            return "NOT_STARTED"
        normalized = str(state).upper()
        if normalized not in self.REQUIREMENT_STATES:
            raise ValueError(f"Unsupported requirement state: {state}")
        return normalized

    def _case_requires_assignment(self, action):
        action_name = str(action or "view_preserved_evidence").lower()
        return action_name in {"review_case", "verify_case_facts", "start_investigation", "complete_investigation"}

    def _assert_detective_assignment(self, case_reference, actor_id=None, actor_role=None, action="view_preserved_evidence"):
        if self.assignment_service is None:
            return
        if not self._case_requires_assignment(action):
            return
        if actor_role is None:
            raise ValueError("Detective procedure action requires a validated actor role.")
        if str(actor_role).lower() != "detective":
            raise ValueError("Only a detective may mutate or advance procedure state.")
        if actor_id is None:
            raise ValueError("Detective identity is required for procedure action.")
        case = self._load_case(case_reference)
        if case is None:
            raise ValueError("Docket not found.")
        current_assignment = self.assignment_service.get_current_assignment_for_case(case_reference)
        if current_assignment is None or str(current_assignment.get("status") or "").upper() != "ACTIVE":
            raise ValueError("Detective access requires an active assignment, and the detective must be assigned to this docket.")
        if str(current_assignment.get("officer_role") or "").lower() != "detective":
            raise ValueError("The active assignment for this docket is not held by a detective; the detective must be assigned to this docket.")
        if str(current_assignment.get("officer_id") or "") != str(actor_id):
            raise ValueError("The detective is not assigned to this docket.")

    def _get_current_case_binding(self, case_reference):
        state = self.state_repository.get_latest_for_case(str(case_reference))
        source_record = self.get_case_source(str(case_reference))
        if state is None:
            return {
                "source_identifier": (source_record or {}).get("source_id"),
                "source_version": (source_record or {}).get("source_version") or "v1",
                "rule_id": None,
                "rule_version": "v1",
                "ruleset_version": self.DEFAULT_RULESET_VERSION,
                "procedure_version": self.DEFAULT_RULESET_VERSION,
            }
        return {
            "source_identifier": state.get("source_identifier") or (source_record or {}).get("source_id"),
            "source_version": state.get("source_version") or (source_record or {}).get("source_version") or "v1",
            "rule_id": state.get("rule_id"),
            "rule_version": state.get("rule_version") or "v1",
            "ruleset_version": state.get("ruleset_version") or self.DEFAULT_RULESET_VERSION,
            "procedure_version": state.get("procedure_version") or self.DEFAULT_RULESET_VERSION,
        }

    def _audit_event(self, *, action, actor_id, actor_role, case_reference, object_type, object_id, rule_code=None, rule_version=None, source_version=None, previous_state=None, new_state=None, decision=None, reason=None, details=None):
        if self.audit_service is None:
            return None
        return self.audit_service.log(
            {
                "action": action,
                "actor_id": actor_id or "system",
                "actor_role": actor_role or "system",
                "case_reference": case_reference,
                "object_type": object_type,
                "object_id": object_id,
                "previous_state": previous_state,
                "new_state": new_state,
                "rule_code": rule_code,
                "rule_version": rule_version,
                "source_version": source_version,
                "decision": decision,
                "reason": reason,
                "details": details or {},
            }
        )

    def _load_case(self, case_reference):
        if case_reference is None:
            return None
        if self.case_service is not None:
            case = self.case_service.get_case(str(case_reference))
            if case is not None:
                return case
        if self.app is not None and hasattr(self.app, "extensions"):
            shared_case_service = self.app.extensions.get("case_service")
            if shared_case_service is not None:
                return shared_case_service.get_case(str(case_reference))
        return None

    def _load_protected_context(self, case):
        if case is None:
            return {
                "citizen_submission": None,
                "citizen_assertions": [],
                "citizen_claims": [],
                "incident_candidate": None,
                "relationships": [],
                "citizen_evidence": [],
            }

        if self.citizen_submission_service is None and self.app is not None and hasattr(self.app, "extensions"):
            self.citizen_submission_service = self.app.extensions.get("citizen_submission_service")
        if self.incident_candidate_service is None and self.app is not None and hasattr(self.app, "extensions"):
            self.incident_candidate_service = self.app.extensions.get("incident_candidate_service")

        submission_id = case.get("source_submission_id")
        candidate_id = case.get("source_candidate_id")
        submission = None
        evidence = []
        assertions = []
        claims = []
        candidate = None
        relationships = []

        if submission_id and self.citizen_submission_service is not None:
            repository = getattr(self.citizen_submission_service, "repository", None)
            if repository is not None:
                submission = repository.get_by_id(submission_id)
            assertion_repository = getattr(self.citizen_submission_service, "assertion_repository", None)
            if assertion_repository is not None:
                assertions = assertion_repository.list_for_submission(submission_id)
            claim_repository = getattr(self.citizen_submission_service, "claim_repository", None)
            if claim_repository is not None:
                claims = claim_repository.list_for_submission(submission_id)
            evidence_repository = getattr(self.citizen_submission_service, "evidence_repository", None)
            if evidence_repository is not None:
                evidence = evidence_repository.list_for_submission(submission_id)

        if candidate_id and self.incident_candidate_service is not None:
            candidate_repository = getattr(self.incident_candidate_service, "candidate_repository", None)
            if candidate_repository is not None:
                candidate = candidate_repository.get_by_id(candidate_id)

        if self.incident_candidate_service is not None:
            relationship_repository = getattr(self.incident_candidate_service, "relationship_repository", None)
            if relationship_repository is not None and submission_id:
                relationships = relationship_repository.list_for_submission(submission_id)
                if candidate_id:
                    relationships = [
                        item
                        for item in relationships
                        if str(item.get("candidate_id") or "") == str(candidate_id)
                        or str(item.get("source_submission_id") or "") == str(submission_id)
                    ]

        return {
            "citizen_submission": submission,
            "citizen_assertions": assertions,
            "citizen_claims": claims,
            "incident_candidate": candidate,
            "relationships": relationships,
            "citizen_evidence": evidence,
        }

    def _default_rules(self):
        return [
            {
                "rule_code": "PROCEDURE.SOURCE_CHAIN",
                "title": "Protected source chain",
                "category": "SOURCE_CONTINUITY",
                "description": "Detective review must preserve the authorized source submission and candidate chain.",
                "legal_basis": "Protected citizen reporting remains authoritative for the procedural case.",
                "applicability": {"actions": ["view_preserved_evidence", "review_case", "start_investigation", "complete_investigation"]},
                "required_records": ["source_submission", "source_candidate"],
                "required_action": "view_preserved_evidence",
                "severity": "HIGH",
                "active": True,
                "version": "v1",
            },
            {
                "rule_code": "PROCEDURE.EVIDENCE_PRESERVED",
                "title": "Preserved evidence required",
                "category": "READ_ONLY_EVIDENCE",
                "description": "Detective review must rely on preserved citizen evidence rather than contrived client-side state.",
                "legal_basis": "Protected evidence continuity is required before any investigation step is permitted.",
                "applicability": {"actions": ["view_preserved_evidence", "review_case", "start_investigation", "complete_investigation"]},
                "required_records": ["source_evidence"],
                "required_action": "review_case",
                "severity": "HIGH",
                "active": True,
                "version": "v1",
            },
            {
                "rule_code": "PROCEDURE.CASE_FACTS_VERIFICATION",
                "title": "Case facts verification",
                "category": "FACTS_VERIFICATION",
                "description": "The detective must verify the relevant incident facts and resolve preserved-source discrepancies before the case can proceed.",
                "legal_basis": "The investigative procedure requires a verified factual baseline before the case can proceed.",
                "applicability": {"actions": ["verify_case_facts", "start_investigation"]},
                "required_records": ["incident_date", "incident_time", "location", "people_involved", "witnesses", "harm_types"],
                "required_action": "verify_case_facts",
                "severity": "HIGH",
                "active": True,
                "version": "v1",
            },
            {
                "rule_code": "PROCEDURE.ROLE_DETECTIVE",
                "title": "Detective authority",
                "category": "AUTHORIZATION",
                "description": "Only a detective may advance a procedure to enforcement or completion.",
                "legal_basis": "Operational authority is bound to the detective role.",
                "applicability": {"actions": ["review_case", "start_investigation", "complete_investigation"]},
                "required_records": ["actor_role"],
                "required_action": "complete_investigation",
                "severity": "HIGH",
                "active": True,
                "version": "v1",
            },
            {
                "rule_code": "PROCEDURE.FORGED_COMPLETION_BLOCKED",
                "title": "Forged completion blocked",
                "category": "CONTROL_BOUNDARY",
                "description": "No client-side bypass may fabricate completion without the underlying procedural state.",
                "legal_basis": "Only the system can validate the final procedural state.",
                "applicability": {"actions": ["complete_investigation"]},
                "required_records": ["state_validation"],
                "required_action": "complete_investigation",
                "severity": "CRITICAL",
                "active": True,
                "version": "v1",
            },
        ]

    def ensure_builtin_rules(self):
        for raw_rule in self._default_rules():
            rule_code = raw_rule["rule_code"]
            version = raw_rule["version"]
            existing = self.rule_repository.get_by_code_version(rule_code, version)
            if existing is not None:
                continue
            self.register_rule(
                rule_code=rule_code,
                title=raw_rule["title"],
                category=raw_rule["category"],
                description=raw_rule["description"],
                legal_basis=raw_rule["legal_basis"],
                applicability=raw_rule["applicability"],
                required_records=raw_rule["required_records"],
                required_action=raw_rule["required_action"],
                severity=raw_rule["severity"],
                active=raw_rule["active"],
                version=version,
            )
        return self.rule_repository.list_active()

    def create_requirement(
        self,
        case_reference,
        rule_code,
        rule_version="v1",
        description="Procedure requirement.",
        required_action=None,
        required_record=None,
        actor_id=None,
        actor_role=None,
        reason=None,
        evidence_reference=None,
        state="NOT_STARTED",
        payload=None,
    ):
        if not case_reference:
            raise ValueError("A case reference is required.")
        normalized_state = self._normalize_requirement_state(state)
        requirement_id = f"REQ-{str(case_reference).upper()}-{str(rule_code).upper().replace('.', '-')}-{len(self.requirement_repository.list_for_case(case_reference)) + 1:04d}"
        requirement_payload = {
            "requirement_id": requirement_id,
            "state_id": f"CPS-{str(case_reference).upper()}-{len(self.state_repository.list_for_case(case_reference)) + 1:04d}",
            "case_reference": str(case_reference),
            "rule_code": str(rule_code).upper(),
            "rule_version": str(rule_version or "v1"),
            "requirement_type": "PROCEDURE_REQUIREMENT",
            "description": str(description or "Procedure requirement."),
            "required_action": required_action,
            "required_record": required_record,
            "state": normalized_state,
            "expected_status": normalized_state,
            "satisfied": normalized_state in {"COMPLETED", "NOT_APPLICABLE"},
            "reason": reason,
            "evidence_reference": evidence_reference,
            "actor_id": actor_id or "system",
            "actor_role": actor_role or "system",
            "history": [{"state": normalized_state, "actor_id": actor_id or "system", "actor_role": actor_role or "system", "timestamp": self._utc_now()}],
            "version": str(rule_version or "v1"),
            "created_at": self._utc_now(),
            "updated_at": self._utc_now(),
        }
        if payload and isinstance(payload, dict) and "satisfied" in payload and payload.get("satisfied") is True and normalized_state == "NOT_STARTED":
            requirement_payload["state"] = "NOT_STARTED"
            requirement_payload["satisfied"] = False
        created = self.requirement_repository.create(requirement_payload)
        self._audit_event(
            action="procedure_requirement_created",
            actor_id=actor_id or "system",
            actor_role=actor_role or "system",
            case_reference=str(case_reference),
            object_type="procedure_requirement",
            object_id=created.get("requirement_id"),
            rule_code=str(rule_code).upper(),
            rule_version=str(rule_version or "v1"),
            source_version=(self.get_case_source(str(case_reference)) or {}).get("source_version") or "v1",
            new_state=normalized_state,
            reason=reason,
            details={"required_action": required_action, "required_record": required_record},
        )
        return created

    def update_requirement_state(
        self,
        requirement_id,
        new_state,
        actor_id=None,
        actor_role=None,
        reason=None,
        evidence_reference=None,
        payload=None,
    ):
        requirement = self.requirement_repository.get_by_id(requirement_id)
        if requirement is None:
            raise ValueError("Requirement not found.")
        if payload and isinstance(payload, dict) and "satisfied" in payload and new_state is None:
            return requirement
        previous_state = self._normalize_requirement_state(requirement.get("state"))
        next_state = self._normalize_requirement_state(new_state if new_state is not None else requirement.get("state") or "NOT_STARTED")
        requirement["state"] = next_state
        requirement["expected_status"] = next_state
        requirement["satisfied"] = next_state in {"COMPLETED", "NOT_APPLICABLE"}
        requirement["reason"] = reason or requirement.get("reason") or requirement.get("description")
        requirement["evidence_reference"] = evidence_reference or requirement.get("evidence_reference")
        requirement["actor_id"] = actor_id or requirement.get("actor_id") or "system"
        requirement["actor_role"] = actor_role or requirement.get("actor_role") or "system"
        requirement["updated_at"] = self._utc_now()
        history = list(requirement.get("history") or [])
        history.append({
            "state": next_state,
            "actor_id": requirement["actor_id"],
            "actor_role": requirement["actor_role"],
            "timestamp": self._utc_now(),
            "reason": requirement["reason"],
        })
        requirement["history"] = history
        updated = self.requirement_repository.update(requirement_id, requirement)
        self._audit_event(
            action="procedure_requirement_state_changed",
            actor_id=requirement["actor_id"],
            actor_role=requirement["actor_role"],
            case_reference=requirement.get("case_reference"),
            object_type="procedure_requirement",
            object_id=requirement_id,
            rule_code=requirement.get("rule_code"),
            rule_version=requirement.get("rule_version"),
            source_version=(self.get_case_source(requirement.get("case_reference")) or {}).get("source_version") or "v1",
            previous_state=previous_state,
            new_state=next_state,
            decision="requirement_state_change",
            reason=requirement.get("reason"),
            details={"required_action": requirement.get("required_action"), "required_record": requirement.get("required_record")},
        )
        return updated

    def register_rule(
        self,
        rule_code,
        title,
        category,
        description,
        legal_basis,
        applicability=None,
        required_records=None,
        required_action=None,
        severity="HIGH",
        active=True,
        version="v1",
        source_reference=None,
        trigger=None,
        ruleset_version=None,
        rule_classification="SYSTEM_CONTROL",
    ):
        if not rule_code:
            raise ValueError("A procedure rule code is required.")
        rule_id = f"PRULE-{str(rule_code).upper().replace('.', '-')}-{str(version).upper()}"
        payload = {
            "rule_id": rule_id,
            "rule_code": str(rule_code).upper(),
            "version": str(version),
            "title": str(title or rule_code),
            "category": str(category or "SOURCE_CONTINUITY"),
            "description": str(description or "Procedure rule."),
            "legal_basis": str(legal_basis or "System-derived legal control."),
            "applicability": applicability or {},
            "required_records": list(required_records or []),
            "required_action": required_action,
            "source_reference": source_reference,
            "rule_classification": str(rule_classification or "SYSTEM_CONTROL").upper(),
            "trigger": trigger,
            "ruleset_version": ruleset_version or self.DEFAULT_RULESET_VERSION,
            "severity": str(severity or "HIGH").upper(),
            "active": bool(active),
            "created_at": self._utc_now(),
        }
        existing = self.rule_repository.get_by_code_version(payload["rule_code"], payload["version"])
        if existing is not None:
            persisted = self.rule_repository.update(existing["rule_id"], payload)
        else:
            persisted = self.rule_repository.create(payload)
        if self.audit_service is not None:
            self.audit_service.log(
                {
                    "action": "procedure_rule_registered",
                    "actor_id": "system",
                    "actor_role": "system",
                    "case_reference": None,
                    "object_type": "procedure_rule",
                    "object_id": persisted.get("rule_id"),
                    "rule_code": persisted.get("rule_code"),
                    "rule_version": persisted.get("version"),
                    "ruleset_version": persisted.get("ruleset_version"),
                    "legal_reference": persisted.get("legal_basis"),
                    "details": {"version": persisted.get("version"), "required_records": persisted.get("required_records", [])},
                }
            )
        return persisted

    def list_rule_versions(self, rule_code):
        return self.rule_repository.versions_for_code(str(rule_code).upper())

    def register_case_source(
        self,
        case_reference,
        source_submission_id=None,
        source_candidate_id=None,
        evidence_ids=None,
        provenance=None,
        created_by=None,
        authority=None,
        verification_status="VERIFIED",
    ):
        if not case_reference:
            raise ValueError("A case reference is required.")
        source_submission_id = str(source_submission_id or "").strip() or None
        source_candidate_id = str(source_candidate_id or "").strip() or None
        existing = self.source_repository.get_latest_for_case(case_reference)
        next_version = 1 if existing is None else int(existing.get("version") or 1) + 1
        source_version = f"v{next_version}"
        source_id = existing["source_id"] if existing is not None else f"SR-{str(case_reference).upper()}-{next_version:04d}"
        payload = {
            "source_id": source_id,
            "source_identifier": source_id,
            "case_reference": str(case_reference),
            "source_type": "CITIZEN_SUBMISSION",
            "source_submission_id": source_submission_id,
            "source_candidate_id": source_candidate_id,
            "source_evidence_ids": list(evidence_ids or []),
            "source_assertion_ids": [],
            "source_claim_ids": [],
            "provenance": provenance or {"source": "protected_submission"},
            "register_status": "REGISTERED",
            "authority": authority or "citizen_submission",
            "verification_status": verification_status,
            "source_version": source_version,
            "version": next_version,
            "effective_from": self._utc_now(),
            "effective_to": None,
            "is_current": True,
            "created_by": created_by or "system",
            "created_at": self._utc_now(),
            "updated_at": self._utc_now(),
        }
        if existing is not None:
            payload["is_current"] = True
            persisted = self.source_repository.update(existing["source_id"], payload)
        else:
            persisted = self.source_repository.create(payload)
        if self.audit_service is not None:
            self.audit_service.log(
                {
                    "action": "case_source_registered",
                    "actor_id": created_by or "system",
                    "actor_role": "system",
                    "case_reference": case_reference,
                    "object_type": "source_register",
                    "object_id": persisted.get("source_id"),
                    "rule_code": "PROCEDURE.SOURCE_CHAIN",
                    "rule_version": persisted.get("source_version"),
                    "source_version": persisted.get("source_version"),
                    "legal_reference": "Protected citizen submission origin remains authoritative.",
                    "details": {
                        "source_submission_id": source_submission_id,
                        "source_candidate_id": source_candidate_id,
                        "evidence_ids": persisted.get("source_evidence_ids", []),
                    },
                }
            )
        return persisted

    def get_case_source(self, case_reference):
        return self.source_repository.get_latest_for_case(case_reference)

    @staticmethod
    def _format_action_label(action):
        label_map = {
            "view_preserved_evidence": "Review preserved evidence",
            "review_case": "Review case continuity",
            "verify_case_facts": "Verify case facts",
            "start_investigation": "Start investigation",
            "record_finding": "Document finding",
            "complete_investigation": "Complete investigation",
            "view_case": "Review case",
        }
        normalized = str(action or "view_preserved_evidence").strip()
        return label_map.get(normalized.lower(), normalized.replace("_", " ").title())

    @staticmethod
    def _procedure_stage_for_action(action):
        stage_map = {
            "view_preserved_evidence": "CASE_REVIEW",
            "review_case": "CASE_REVIEW",
            "verify_case_facts": "CASE_FACTS_VERIFICATION",
            "start_investigation": "INVESTIGATION_OPEN",
            "record_finding": "FINDINGS_READY",
            "complete_investigation": "INVESTIGATION_COMPLETE",
            "view_case": "CASE_REVIEW",
        }
        normalized = str(action or "view_preserved_evidence").strip().lower()
        return stage_map.get(normalized, "CASE_REVIEW")

    def _required_investigation_actions_complete(self, investigation):
        if investigation is None:
            return False
        investigation_id = str((investigation or {}).get("investigation_id") or "").strip()
        if not investigation_id:
            return False
        service = None
        if self.app is not None and hasattr(self.app, "extensions"):
            service = self.app.extensions.get("investigation_service")
        if service is None or not hasattr(service, "REQUIRED_ACTION_SEQUENCE") or not hasattr(service, "_completed_required_actions"):
            return False
        completed = set(service._completed_required_actions(investigation_id))
        required = list(getattr(service, "REQUIRED_ACTION_SEQUENCE", []))
        return bool(required) and all(action_type in completed for action_type in required)

    def _get_active_investigation(self, case_reference):
        if not str(case_reference or "").strip():
            return None
        if self.app is not None and hasattr(self.app, "extensions"):
            service = self.app.extensions.get("investigation_service")
            if service is not None and hasattr(service, "_get_investigation_by_case"):
                return service._get_investigation_by_case(str(case_reference))
        return None

    def _get_latest_investigation(self, case_reference):
        if not str(case_reference or "").strip():
            return None
        if self.app is not None and hasattr(self.app, "extensions"):
            service = self.app.extensions.get("investigation_service")
            if service is not None and hasattr(service, "_get_latest_investigation_by_case"):
                return service._get_latest_investigation_by_case(str(case_reference))
        return self._get_active_investigation(case_reference)

    def _is_investigation_open(self, case_reference):
        investigation = self._get_active_investigation(case_reference)
        if investigation is None:
            return False
        return str((investigation or {}).get("status") or "").upper() in {"OPEN", "IN_PROGRESS"}

    def reconcile_investigation_state(self, case_reference, actor_id=None, actor_role=None, investigation=None):
        active = investigation or self._get_active_investigation(case_reference)
        latest = investigation or self._get_latest_investigation(case_reference)
        if active is None and latest is None:
            return self.get_case_state(case_reference)

        status = str((active or latest or {}).get("status") or "").upper()
        if status == "COMPLETED":
            case = self._load_case(case_reference)
            persisted = self._persist_state(
                case_reference,
                "complete_investigation",
                [],
                allowed=True,
                actor_id=actor_id,
                actor_role=actor_role,
            )
            current = self.get_case_state(case_reference) or {}
            current["current_stage"] = "INVESTIGATION_COMPLETE"
            current["procedure_status"] = "COMPLETED"
            current["next_permitted_action"] = "Investigation completed"
            current["current_action"] = "complete_investigation"
            current["allowed"] = True
            return current if persisted is None else {**persisted, **current}

        if status not in {"OPEN", "IN_PROGRESS"}:
            return self.get_case_state(case_reference)

        case = self._load_case(case_reference)
        case_facts_verified = bool(case and self._case_facts_verified(case))
        required_actions_complete = self._required_investigation_actions_complete(active or latest)
        if case_facts_verified:
            if required_actions_complete:
                current_stage = "FINDINGS_READY"
                next_permitted_action = "Document finding"
                current_action = "record_finding"
            else:
                current_stage = "INVESTIGATION_OPEN"
                next_permitted_action = "Complete investigation"
                current_action = "complete_investigation"
        else:
            current_stage = "CASE_FACTS_VERIFICATION"
            next_permitted_action = "Verify case facts"
            current_action = "verify_case_facts"
        requirements = self._build_rule_requirements(case, current_action, actor_id=actor_id, actor_role=actor_role)
        if not case_facts_verified and not any(str(item.get("rule_code") or "").upper() == "PROCEDURE.CASE_FACTS_VERIFICATION" for item in requirements):
            requirements.append({
                "rule_code": "PROCEDURE.CASE_FACTS_VERIFICATION",
                "title": "Case facts verification",
                "version": "v1",
                "category": "FACTS_VERIFICATION",
                "description": "The detective must verify the relevant incident facts and resolve any preserved-source discrepancies before the case can proceed.",
                "legal_basis": "The investigative procedure requires a verified factual baseline before the case can proceed to later procedural gates.",
                "required_action": "verify_case_facts",
                "required_records": ["incident_date", "incident_time", "location", "people_involved", "witnesses", "harm_types", "injury_types", "police_involvement"],
                "rule_classification": "SYSTEM_CONTROL",
                "source_reference": "protected citizen submission",
                "trigger": "procedure gate",
                "state": "NOT_STARTED",
                "satisfied": False,
                "requires_review": True,
                "status": "BLOCKED",
                "blocking_reason": "Case facts verification remains pending for this investigation.",
            })
        persisted = self._persist_state(
            case_reference,
            current_action,
            requirements,
            allowed=True,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        current = self.get_case_state(case_reference) or {}
        current["current_stage"] = current_stage
        current["procedure_status"] = "ACTIVE"
        current["next_permitted_action"] = next_permitted_action
        current["current_action"] = current_action
        return current if persisted is None else {**persisted, **current}

    def _case_facts_verification_record(self, case):
        if case is None:
            return {}
        assessment = case.get("procedural_assessment") if isinstance(case.get("procedural_assessment"), dict) else {}
        record = assessment.get("case_facts_verification") if isinstance(assessment.get("case_facts_verification"), dict) else {}
        if record:
            return record
        explicit = case.get("case_facts_verification") if isinstance(case.get("case_facts_verification"), dict) else {}
        return explicit

    @staticmethod
    def _normalize_case_fact_value(value):
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        if isinstance(value, (list, tuple, set)):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            return sorted(cleaned)
        if isinstance(value, dict):
            return {str(key): ProcedureGateEngine._normalize_case_fact_value(item) for key, item in value.items()}
        return value

    def _case_fact_snapshot(self, case):
        if case is None:
            return {}
        protected_context = self._load_protected_context(case)
        source = protected_context.get("citizen_submission") or {}
        original_content = {}
        if isinstance(source.get("original_content"), dict):
            original_content.update(source["original_content"])
        if isinstance(case.get("original_content"), dict):
            original_content.update(case["original_content"])
        candidate = protected_context.get("incident_candidate") or {}
        if isinstance(candidate.get("original_content"), dict):
            original_content.update(candidate["original_content"])
        return {
            "incident_date": case.get("incident_date") or original_content.get("incident_date") or source.get("incident_date") or candidate.get("incident_date"),
            "incident_time": case.get("incident_time") or original_content.get("incident_time") or source.get("incident_time") or candidate.get("incident_time"),
            "location": case.get("location") or original_content.get("location") or source.get("location") or candidate.get("location"),
            "people_involved": case.get("people_involved") or original_content.get("people_involved") or source.get("people_involved") or candidate.get("people_involved"),
            "witnesses": case.get("witnesses") or original_content.get("witnesses") or source.get("witnesses") or candidate.get("witnesses"),
            "harm_types": case.get("harm_types") or original_content.get("harm_types") or source.get("harm_types") or candidate.get("harm_types"),
            "injury_types": case.get("injury_types") or original_content.get("injury_types") or source.get("injury_types") or candidate.get("injury_types"),
            "police_involvement": case.get("police_involvement") if case.get("police_involvement") is not None else original_content.get("police_involvement") or source.get("police_involvement") or candidate.get("police_involvement"),
        }

    @staticmethod
    def _case_fact_is_not_established(value):
        if value is None:
            return True
        if isinstance(value, str):
            stripped = value.strip()
            return stripped == "" or stripped.upper() in {"UNKNOWN", "NOT_ESTABLISHED", "N/A", "NA"}
        if isinstance(value, (list, tuple, set)):
            values = [str(item).strip() for item in value if str(item).strip()]
            if not values:
                return True
            return all(str(item).upper() in {"UNKNOWN", "NOT_ESTABLISHED", "N/A", "NA"} for item in values)
        return False

    def _compare_case_facts(self, case, normalized_facts):
        source_snapshot = self._case_fact_snapshot(case)
        discrepancies = []
        for key in ["incident_date", "incident_time", "location", "people_involved", "witnesses", "harm_types", "injury_types", "police_involvement"]:
            original_value = self._normalize_case_fact_value(source_snapshot.get(key))
            observed_value = self._normalize_case_fact_value(normalized_facts.get(key))
            if original_value is None:
                continue
            if observed_value is None:
                discrepancies.append({
                    "field": key,
                    "original_value": source_snapshot.get(key),
                    "observed_value": normalized_facts.get(key),
                    "basis": "The detective verification record did not include the preserved incident fact needed for comparison.",
                    "status": "OPEN",
                    "resolved": False,
                })
                continue
            if original_value != observed_value:
                discrepancies.append({
                    "field": key,
                    "original_value": source_snapshot.get(key),
                    "observed_value": normalized_facts.get(key),
                    "basis": "The detective verification record differs from the preserved case facts and requires a documented explanation.",
                    "status": "OPEN",
                    "resolved": False,
                })
        return discrepancies

    def _build_case_fact_comparison(self, case, normalized_facts, discrepancy_entries=None):
        source_snapshot = self._case_fact_snapshot(case)
        comparison = {}
        comparison_results = []
        discrepancy_entries = list(discrepancy_entries or [])
        ordered_keys = ["incident_date", "incident_time", "location", "people_involved", "witnesses", "harm_types", "injury_types", "police_involvement"]

        for key in ordered_keys:
            source_value = source_snapshot.get(key)
            observed_value = self._normalize_case_fact_value(normalized_facts.get(key))
            source_known = not self._case_fact_is_not_established(source_value)
            observed_known = not self._case_fact_is_not_established(observed_value)

            if not source_known:
                comparison_entry = {
                    "field": key,
                    "source_value": source_value,
                    "observed_value": observed_value,
                    "comparison_status": "NOT_ESTABLISHED",
                    "status": "NOT_ESTABLISHED",
                    "resolution_status": "NOT_ESTABLISHED",
                    "resolved": True,
                    "basis": "The protected source record does not establish this fact.",
                }
            else:
                source_norm = self._normalize_case_fact_value(source_value)
                observed_norm = self._normalize_case_fact_value(observed_value)
                if source_norm == observed_norm:
                    comparison_entry = {
                        "field": key,
                        "source_value": source_value,
                        "observed_value": observed_value,
                        "comparison_status": "MATCH",
                        "status": "MATCH",
                        "resolution_status": "MATCH",
                        "resolved": True,
                        "basis": "The detective record matches the protected source fact.",
                    }
                else:
                    comparison_entry = {
                        "field": key,
                        "source_value": source_value,
                        "observed_value": observed_value,
                        "comparison_status": "DISCREPANCY",
                        "status": "DISCREPANCY",
                        "resolution_status": "UNRESOLVED",
                        "resolved": False,
                        "basis": "The detective verification record differs from the protected source fact.",
                    }

            explicit_match = None
            for item in discrepancy_entries:
                if not isinstance(item, dict):
                    continue
                if str(item.get("field") or "").lower() != key.lower():
                    continue
                explicit_match = item
                break

            if explicit_match is not None:
                basis = explicit_match.get("basis") or explicit_match.get("explanation") or comparison_entry.get("basis")
                if self._discrepancy_is_addressed(explicit_match):
                    comparison_entry["resolution_status"] = "ADDRESSED"
                    comparison_entry["resolved"] = True
                    if comparison_entry["comparison_status"] == "DISCREPANCY":
                        comparison_entry["status"] = "DISCREPANCY"
                    else:
                        comparison_entry["status"] = "ADDRESSED"
                    comparison_entry["basis"] = basis
                else:
                    comparison_entry["comparison_status"] = "DISCREPANCY"
                    comparison_entry["status"] = "DISCREPANCY"
                    comparison_entry["resolution_status"] = "UNRESOLVED"
                    comparison_entry["resolved"] = False
                    comparison_entry["basis"] = basis

            comparison[key] = comparison_entry
            comparison_results.append(comparison_entry)

        return {"comparison": comparison, "comparison_results": comparison_results}

    @staticmethod
    def _discrepancy_is_addressed(discrepancy):
        if not isinstance(discrepancy, dict):
            return False

        status = str(discrepancy.get("status") or discrepancy.get("resolution_status") or "").upper()
        if status in {"ADDRESSED", "RESOLVED", "CLOSED", "SATISFIED"}:
            return True
        if status in {"OPEN", "PENDING", "UNRESOLVED", "BLOCKED"}:
            return False

        if discrepancy.get("resolved") is True:
            return True
        if discrepancy.get("addressed") is True:
            return True
        if discrepancy.get("resolved_by") is not None or discrepancy.get("resolution") not in (None, "", False):
            return True
        if discrepancy.get("investigative_basis") not in (None, "") and discrepancy.get("basis") not in (None, ""):
            return True
        return False

    def _case_facts_verified(self, case):
        record = self._case_facts_verification_record(case)
        if not record:
            return False
        status = str(record.get("status") or record.get("verification_status") or "").upper()
        if record.get("verified") is True or status == "VERIFIED":
            return True
        discrepancies = record.get("discrepancies") or []
        if isinstance(discrepancies, list) and discrepancies:
            unresolved = [item for item in discrepancies if not self._discrepancy_is_addressed(item)]
            return not unresolved
        return False

    def _rule_matches_action(self, rule, action):
        actions = set(str(item).strip().lower() for item in (rule.get("applicability") or {}).get("actions") or [])
        return not actions or action.lower() in actions

    def _list_active_rules(self):
        rules = self.rule_repository.list_active()
        if rules:
            return rules
        self.ensure_builtin_rules()
        return self.rule_repository.list_active()

    def _case_protected_source_summary(self, case, protected_context=None):
        if case is None:
            return {
                "source_submission_id": "",
                "source_candidate_id": "",
                "has_protected_source": False,
                "has_preserved_evidence": False,
                "evidence_ids": [],
            }

        protected_context = protected_context or self._load_protected_context(case)
        source_submission_id = str(case.get("source_submission_id") or (protected_context.get("citizen_submission") or {}).get("submission_id") or "").strip()
        source_candidate_id = str(case.get("source_candidate_id") or (protected_context.get("incident_candidate") or {}).get("candidate_id") or "").strip()
        source_record = self.get_case_source(case.get("case_reference"))
        if not source_submission_id:
            source_submission_id = str((source_record or {}).get("source_submission_id") or "").strip()
        if not source_candidate_id:
            source_candidate_id = str((source_record or {}).get("source_candidate_id") or "").strip()

        evidence_ids = list((source_record or {}).get("source_evidence_ids") or [])
        if not evidence_ids:
            evidence_ids = [str(item.get("evidence_id") or "") for item in (case.get("evidence") or []) if isinstance(item, dict) and item.get("evidence_id")]
        if not evidence_ids:
            evidence_ids = [str(item.get("evidence_id") or "") for item in (protected_context.get("citizen_evidence") or []) if isinstance(item, dict) and item.get("evidence_id")]

        has_preserved_evidence = bool(evidence_ids or case.get("statements") or protected_context.get("citizen_evidence"))
        has_protected_source = bool(
            source_submission_id
            or source_candidate_id
            or has_preserved_evidence
            or protected_context.get("citizen_assertions")
            or protected_context.get("citizen_claims")
            or case.get("statements")
        )
        return {
            "source_submission_id": source_submission_id,
            "source_candidate_id": source_candidate_id,
            "has_protected_source": has_protected_source,
            "has_preserved_evidence": has_preserved_evidence,
            "evidence_ids": [str(item).strip() for item in evidence_ids if str(item).strip()],
        }

    def _build_rule_requirements(self, case, action, actor_id=None, actor_role=None):
        rules = self._list_active_rules()
        protected_context = self._load_protected_context(case)
        source_summary = self._case_protected_source_summary(case, protected_context)
        case_submission_id = source_summary["source_submission_id"]
        case_candidate_id = source_summary["source_candidate_id"]
        evidence_ids = source_summary["evidence_ids"]

        persisted_requirements = {
            requirement.get("rule_code"): requirement
            for requirement in self.requirement_repository.list_for_case(case.get("case_reference"))
            if isinstance(requirement, dict) and requirement.get("rule_code")
        }

        requirements = []
        for rule in rules:
            if not self._rule_matches_action(rule, action):
                continue
            rule_code = rule.get("rule_code")
            persisted = persisted_requirements.get(rule_code)
            dynamic_rule_codes = {
                "PROCEDURE.SOURCE_CHAIN",
                "PROCEDURE.EVIDENCE_PRESERVED",
                "PROCEDURE.CASE_FACTS_VERIFICATION",
                "PROCEDURE.ROLE_DETECTIVE",
                "PROCEDURE.FORGED_COMPLETION_BLOCKED",
            }
            if rule_code in dynamic_rule_codes:
                satisfied = True
                if rule_code == "PROCEDURE.SOURCE_CHAIN":
                    satisfied = bool(source_summary["has_protected_source"])
                elif rule_code == "PROCEDURE.EVIDENCE_PRESERVED":
                    satisfied = bool(source_summary["has_preserved_evidence"])
                elif rule_code == "PROCEDURE.CASE_FACTS_VERIFICATION":
                    satisfied = self._case_facts_verified(case)
                elif rule_code == "PROCEDURE.ROLE_DETECTIVE":
                    satisfied = str(actor_role or "").lower() == "detective"
                elif rule_code == "PROCEDURE.FORGED_COMPLETION_BLOCKED":
                    satisfied = action != "complete_investigation" or str(actor_role or "").lower() == "detective"
                state = "COMPLETED" if satisfied else "NOT_STARTED"
            elif persisted is not None:
                state = self._normalize_requirement_state(persisted.get("state") or ("COMPLETED" if persisted.get("satisfied") else "NOT_STARTED"))
                satisfied = state in {"COMPLETED", "NOT_APPLICABLE"}
            else:
                satisfied = True
                state = "COMPLETED"
            required_records = list(rule.get("required_records") or [])
            blocking_reason = None
            if not satisfied:
                if required_records:
                    blocking_reason = f"Required records are missing: {', '.join(required_records)}."
                else:
                    blocking_reason = f"{rule.get('title') or rule_code} must be satisfied before this action can proceed."
            requirements.append(
                {
                    "rule_code": rule_code,
                    "title": rule.get("title") or rule_code,
                    "version": rule.get("version"),
                    "category": rule.get("category"),
                    "description": rule.get("description"),
                    "legal_basis": rule.get("legal_basis"),
                    "required_records": required_records,
                    "required_action": rule.get("required_action") or action,
                    "rule_classification": str(rule.get("rule_classification") or rule.get("category") or "SYSTEM_CONTROL").upper(),
                    "source_reference": rule.get("source_reference") or "protected citizen submission",
                    "trigger": rule.get("trigger") or "procedure evaluation",
                    "state": state,
                    "satisfied": satisfied,
                    "requires_review": rule.get("severity", "HIGH").upper() == "CRITICAL" and not satisfied,
                    "status": "COMPLETED" if satisfied else "BLOCKED",
                    "blocking_reason": blocking_reason,
                }
            )
        return requirements

    def _persist_state(self, case_reference, action, requirements, allowed, actor_id=None, actor_role=None):
        case = self._load_case(case_reference)
        source_record = self.get_case_source(case_reference)
        existing = self.state_repository.get_latest_for_case(case_reference)
        bound = self._get_current_case_binding(case_reference)
        failed = [item for item in requirements if not item.get("satisfied")]
        next_candidate = next((item.get("required_action") for item in failed if item.get("required_action")), action)
        state_status = "ACTIVE" if allowed else ("REVIEW_REQUIRED" if any(item.get("requires_review") for item in failed) else "BLOCKED")
        if any(str(item.get("rule_code") or "").upper() == "PROCEDURE.CASE_FACTS_VERIFICATION" for item in failed):
            next_candidate = "verify_case_facts"
        investigation_open = self._is_investigation_open(case_reference)
        case_facts_verified = bool(case and self._case_facts_verified(case))
        if investigation_open and case_facts_verified:
            next_candidate = "complete_investigation"
        elif not case_facts_verified:
            next_candidate = "verify_case_facts"
        state_payload = {
            "state_id": f"CPS-{str(case_reference).upper()}-{len(self.state_repository.list_for_case(case_reference)) + 1:04d}",
            "case_reference": str(case_reference),
            "source_id": (source_record or {}).get("source_id") or bound.get("source_identifier"),
            "source_identifier": (source_record or {}).get("source_identifier") or bound.get("source_identifier"),
            "source_version": (existing or {}).get("source_version") or (source_record or {}).get("source_version") or bound.get("source_version"),
            "rule_id": (existing or {}).get("rule_id") or next((item.get("rule_id") for item in self.rule_repository.list_active() if item.get("rule_code") == (requirements[0] if requirements else {}).get("rule_code")), None),
            "rule_version": (existing or {}).get("rule_version") or ((requirements[0] if requirements else {}).get("version") or "v1"),
            "ruleset_version": (existing or {}).get("ruleset_version") or self.DEFAULT_RULESET_VERSION,
            "procedure_version": (existing or {}).get("procedure_version") or self.DEFAULT_RULESET_VERSION,
            "profile_name": "DEFAULT",
            "status": state_status,
            "gate": self.gate_name,
            "current_action": action,
            "next_permitted_action": self._format_action_label(next_candidate) if not allowed else self._format_action_label(action),
            "requirement_summary": {
                "total": len(requirements),
                "satisfied": sum(1 for item in requirements if item.get("satisfied")),
                "failed": sum(1 for item in requirements if not item.get("satisfied")),
            },
            "rule_results": requirements,
            "source_submission_id": (case or {}).get("source_submission_id"),
            "source_candidate_id": (case or {}).get("source_candidate_id"),
            "created_by": actor_id or "system",
            "created_at": self._utc_now(),
            "updated_at": self._utc_now(),
        }
        if investigation_open and case_facts_verified:
            state_payload["current_action"] = action or "complete_investigation"
            state_payload["next_permitted_action"] = "Complete investigation"
        elif not case_facts_verified:
            state_payload["current_action"] = action or "verify_case_facts"
            state_payload["next_permitted_action"] = "Verify case facts"
        if existing is not None:
            state_payload["state_id"] = existing["state_id"]
            persisted = self.state_repository.update(existing["state_id"], state_payload)
        else:
            persisted = self.state_repository.create(state_payload)
        for requirement in requirements:
            matching = None
            for item in self.requirement_repository.list_for_case(case_reference):
                if item.get("rule_code") == requirement.get("rule_code"):
                    matching = item
                    break
            if matching is not None:
                state_value = self._normalize_requirement_state(requirement.get("state") or ("COMPLETED" if requirement.get("satisfied") else "NOT_STARTED"))
                self.update_requirement_state(
                    matching["requirement_id"],
                    state_value,
                    actor_id=actor_id or matching.get("actor_id") or "system",
                    actor_role=actor_role or matching.get("actor_role") or "system",
                    reason=requirement.get("description"),
                    evidence_reference=matching.get("evidence_reference"),
                )
                continue
            requirement_record = {
                "requirement_id": f"REQ-{str(case_reference).upper()}-{requirement['rule_code'].replace('.', '-')}-{len(self.requirement_repository.list_for_case(case_reference)) + 1:04d}",
                "state_id": persisted["state_id"],
                "case_reference": str(case_reference),
                "rule_code": requirement["rule_code"],
                "rule_version": requirement.get("version") or "v1",
                "requirement_type": requirement["category"],
                "description": requirement["description"],
                "required_action": requirement.get("required_action"),
                "required_record": ",".join(requirement.get("required_records") or []),
                "state": self._normalize_requirement_state(requirement.get("state") or ("COMPLETED" if requirement.get("satisfied") else "NOT_STARTED")),
                "expected_status": "COMPLETED" if requirement.get("satisfied") else "NOT_STARTED",
                "satisfied": bool(requirement.get("satisfied")),
                "reason": requirement.get("description"),
                "evidence_reference": None,
                "actor_id": actor_id or "system",
                "actor_role": actor_role or "system",
                "history": [{
                    "state": self._normalize_requirement_state(requirement.get("state") or ("COMPLETED" if requirement.get("satisfied") else "NOT_STARTED")),
                    "actor_id": actor_id or "system",
                    "actor_role": actor_role or "system",
                    "timestamp": self._utc_now(),
                    "reason": requirement.get("description"),
                }],
                "version": requirement.get("version") or "v1",
                "created_at": self._utc_now(),
                "updated_at": self._utc_now(),
            }
            self.requirement_repository.create(requirement_record)
        return persisted

    def record_case_facts_verification(self, case_reference, actor_id=None, actor_role=None, facts=None, discrepancies=None, payload=None):
        if not str(case_reference or "").strip():
            raise ValueError("Case reference is required.")
        case = self._load_case(case_reference)
        if case is None:
            raise ValueError("Docket not found.")
        if str(actor_role or "").lower() != "detective":
            raise ValueError("Only a detective may verify case facts.")
        self._assert_detective_assignment(case_reference, actor_id=actor_id, actor_role=actor_role, action="verify_case_facts")

        request = payload or {}
        if not isinstance(request, dict):
            raise ValueError("Case facts verification payload must be a JSON object.")
        normalized_facts = dict(request.get("facts") or facts or {}) if isinstance(request.get("facts") or facts or {}, dict) else {}
        if not normalized_facts and isinstance(request.get("case_facts"), dict):
            normalized_facts = dict(request.get("case_facts"))
        if not normalized_facts and isinstance(case.get("case_facts_verification"), dict):
            normalized_facts = dict(case.get("case_facts_verification").get("facts") or {})
        normalized_discrepancies = request.get("discrepancies") or discrepancies or []
        if not isinstance(normalized_discrepancies, list):
            normalized_discrepancies = [normalized_discrepancies]

        required_fact_keys = ["incident_date", "location", "people_involved", "witnesses", "harm_types", "injury_types", "police_involvement"]
        missing_required = [
            key for key in required_fact_keys if self._coerce_case_fact_value(normalized_facts.get(key)) is None
        ]
        if missing_required:
            raise ValueError(f"Case facts verification is incomplete; missing required facts: {', '.join(missing_required)}.")

        existing_record = self._case_facts_verification_record(case)
        if isinstance(existing_record, dict) and self._case_facts_verified(case):
            existing_record = dict(existing_record)
            existing_record["idempotent"] = True
            return {
                "case_reference": case_reference,
                "verified": True,
                "status": str(existing_record.get("status") or "VERIFIED").upper(),
                "required_issues": [],
                "discrepancies": list(existing_record.get("discrepancies") or []),
                "record": existing_record,
                "idempotent": True,
                "next_permitted_action": self._format_action_label("start_investigation"),
            }

        auto_discrepancies = self._compare_case_facts(case, normalized_facts)
        normalized_discrepancies_list = []
        seen = {}
        for item in list(auto_discrepancies) + list(normalized_discrepancies):
            if not isinstance(item, dict):
                continue
            normalized_item = dict(item)
            status = str(normalized_item.get("status") or normalized_item.get("resolution_status") or "").upper()
            if normalized_item.get("basis") is None and normalized_item.get("explanation") is None and normalized_item.get("field") is not None:
                raise ValueError("Every discrepancy must include a basis or explanation before it can be resolved.")
            if status in {"ADDRESSED", "RESOLVED", "CLOSED", "SATISFIED"}:
                normalized_item["resolved"] = True
                normalized_item["addressed"] = True
            elif status in {"UNRESOLVED", "OPEN", "PENDING", "BLOCKED"}:
                normalized_item["resolved"] = False
                normalized_item["addressed"] = False
            composite_key = (
                str(normalized_item.get("field") or ""),
                str(normalized_item.get("original_value") or ""),
                str(normalized_item.get("observed_value") or ""),
            )
            if composite_key in seen:
                prior_index = seen[composite_key]
                prior_item = normalized_discrepancies_list[prior_index]
                prior_addressed = self._discrepancy_is_addressed(prior_item)
                candidate_addressed = self._discrepancy_is_addressed(normalized_item)
                if candidate_addressed and not prior_addressed:
                    normalized_discrepancies_list[prior_index] = normalized_item
                elif not prior_item.get("basis") and normalized_item.get("basis"):
                    prior_item["basis"] = normalized_item["basis"]
                    prior_item["explanation"] = normalized_item.get("explanation") or prior_item.get("explanation")
                    prior_item["status"] = normalized_item.get("status") or prior_item.get("status")
                    prior_item["resolved"] = prior_item.get("resolved") or normalized_item.get("resolved")
                    prior_item["addressed"] = prior_item.get("addressed") or normalized_item.get("addressed")
                continue
            seen[composite_key] = len(normalized_discrepancies_list)
            normalized_discrepancies_list.append(normalized_item)

        comparison_matrix = self._build_case_fact_comparison(case, normalized_facts, normalized_discrepancies_list)
        comparison_results = comparison_matrix["comparison_results"]
        unresolved = [item for item in comparison_results if str(item.get("comparison_status") or item.get("status") or "").upper() == "DISCREPANCY" and not item.get("resolved")]
        verified = not unresolved
        record = {
            "status": "VERIFIED" if verified else "PENDING",
            "verified": verified,
            "verified_by": actor_id,
            "verified_at": self._utc_now(),
            "facts": normalized_facts,
            "discrepancies": normalized_discrepancies_list,
            "comparison": comparison_matrix["comparison"],
            "comparison_results": comparison_results,
            "notes": request.get("notes") or request.get("basis") or request.get("verification_notes") or "",
            "requires_resolution": bool(unresolved),
        }
        assessment = case.get("procedural_assessment") if isinstance(case.get("procedural_assessment"), dict) else {}
        assessment["case_facts_verification"] = record
        case["procedural_assessment"] = assessment
        case["case_facts_verification"] = record
        if self.case_service is not None:
            self.case_service.update_case(case)

        requirements = self._build_rule_requirements(case, "verify_case_facts", actor_id=actor_id, actor_role=actor_role)
        self._persist_state(case_reference, "verify_case_facts", requirements, allowed=verified, actor_id=actor_id, actor_role=actor_role)
        return {
            "case_reference": case_reference,
            "verified": verified,
            "status": record["status"],
            "required_issues": missing_required,
            "discrepancies": normalized_discrepancies_list,
            "record": record,
            "next_permitted_action": self._format_action_label("start_investigation") if verified else self._format_action_label("verify_case_facts"),
        }

    @staticmethod
    def _coerce_case_fact_value(value):
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip() or None
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            return cleaned or None
        if isinstance(value, dict):
            return value or None
        return value

    def evaluate_case(self, case_reference, actor_id=None, actor_role=None, action="view_preserved_evidence", payload=None):
        if not str(case_reference or "").strip():
            return ControlGateResult.deny(self.gate_name, "PROCEDURE.CASE_MISSING", "Case reference is required.").__dict__

        case = self._load_case(case_reference)
        if case is None:
            return ControlGateResult.deny(self.gate_name, "PROCEDURE.CASE_NOT_FOUND", "Docket not found.", case_reference=case_reference).__dict__

        action_name = str(action or "view_preserved_evidence").lower()
        active_investigation = self._get_active_investigation(case_reference)
        latest_investigation = self._get_latest_investigation(case_reference)
        if latest_investigation is not None and str((latest_investigation or {}).get("status") or "").upper() == "COMPLETED":
            self.reconcile_investigation_state(case_reference, actor_id=actor_id, actor_role=actor_role, investigation=latest_investigation)
        elif active_investigation is not None and str((active_investigation or {}).get("status") or "").upper() in {"OPEN", "IN_PROGRESS"}:
            self.reconcile_investigation_state(case_reference, actor_id=actor_id, actor_role=actor_role, investigation=active_investigation)
        if action_name in {"review_case", "verify_case_facts", "start_investigation", "complete_investigation"} and str(actor_role or "").lower() != "detective":
            result = ControlGateResult.deny(
                self.gate_name,
                "PROCEDURE.ROLE_DETECTIVE",
                "Only a detective may advance or mutate the procedural case.",
                case_reference=case_reference,
                actor_id=actor_id,
                actor_role=actor_role,
                action=action,
            )
            self._persist_state(case_reference, action, [], allowed=False, actor_id=actor_id, actor_role=actor_role)
            self._audit_event(
                action="procedure_gate_blocked",
                actor_id=actor_id or "unknown",
                actor_role=actor_role or "unknown",
                case_reference=case_reference,
                object_type="procedure_gate",
                object_id=case_reference,
                rule_code="PROCEDURE.ROLE_DETECTIVE",
                rule_version="v1",
                source_version=(self.get_case_source(case_reference) or {}).get("source_version") or "v1",
                previous_state=None,
                new_state="BLOCKED",
                decision="BLOCKED",
                reason="Only a detective may advance or mutate the procedural case.",
                details={"action": action, "assigned_detective_required": True},
            )
            return {**result.__dict__, "requirements": [], "status": result.status, "allowed": result.allowed, "gate": result.gate}

        try:
            self._assert_detective_assignment(case_reference, actor_id=actor_id, actor_role=actor_role, action=action)
        except ValueError as exc:
            result = ControlGateResult.deny(
                self.gate_name,
                "PROCEDURE.ASSIGNMENT_REQUIRED",
                str(exc),
                case_reference=case_reference,
                actor_id=actor_id,
                actor_role=actor_role,
                action=action,
            )
            self._persist_state(case_reference, action, [], allowed=False, actor_id=actor_id, actor_role=actor_role)
            self._audit_event(
                action="procedure_gate_blocked",
                actor_id=actor_id or "unknown",
                actor_role=actor_role or "unknown",
                case_reference=case_reference,
                object_type="procedure_gate",
                object_id=case_reference,
                rule_code="PROCEDURE.SOURCE_CHAIN",
                rule_version="v1",
                source_version=(self.get_case_source(case_reference) or {}).get("source_version") or "v1",
                previous_state=None,
                new_state="BLOCKED",
                decision="BLOCKED",
                reason=str(exc),
                details={"action": action, "assigned_detective_required": True},
            )
            return {**result.__dict__, "requirements": [], "status": result.status, "allowed": result.allowed, "gate": result.gate}

        requirements = self._build_rule_requirements(case, action, actor_id=actor_id, actor_role=actor_role)
        failed = [item for item in requirements if not item.get("satisfied")]

        if (
            active_investigation is not None
            and str((active_investigation or {}).get("status") or "").upper() in {"OPEN", "IN_PROGRESS"}
            and self._case_facts_verified(case)
            and action_name not in {"verify_case_facts", "complete_investigation"}
        ):
            failed = [
                item for item in failed if str(item.get("rule_code") or "").upper() != "PROCEDURE.CASE_FACTS_VERIFICATION"
            ]

        latest_state = self.get_case_state(case_reference) or {}
        if action_name == "complete_investigation":
            active_phase_ready = (
                active_investigation is not None
                and str((active_investigation or {}).get("status") or "").upper() in {"OPEN", "IN_PROGRESS"}
            )
            if not active_phase_ready and latest_investigation is not None and str((latest_investigation or {}).get("status") or "").upper() == "COMPLETED":
                active_phase_ready = True
            prior_stage_ready = (
                str((latest_state or {}).get("status") or "").upper() in {"ACTIVE", "COMPLETED"}
                and str((latest_state or {}).get("current_stage") or "").upper() in {"INVESTIGATION_OPEN", "FINDINGS_READY", "INVESTIGATION_COMPLETE"}
                and str((latest_state or {}).get("current_action") or "").lower() in {"start_investigation", "complete_investigation"}
            )
            if not prior_stage_ready and active_phase_ready:
                procedural_stage = self.reconcile_investigation_state(case_reference, actor_id=actor_id, actor_role=actor_role, investigation=active_investigation or latest_investigation)
                latest_state = procedural_stage or self.get_case_state(case_reference) or {}
                prior_stage_ready = (
                    str((latest_state or {}).get("status") or "").upper() in {"ACTIVE", "COMPLETED"}
                    and str((latest_state or {}).get("current_stage") or "").upper() in {"INVESTIGATION_OPEN", "FINDINGS_READY", "INVESTIGATION_COMPLETE"}
                    and str((latest_state or {}).get("current_action") or "").lower() in {"start_investigation", "complete_investigation"}
                )
            if not prior_stage_ready and not active_phase_ready:
                failed.append({
                    "rule_code": "PROCEDURE.INVESTIGATION_OPEN_REQUIRED",
                    "title": "Investigation must already be open",
                    "version": "v1",
                    "category": "CONTROL_BOUNDARY",
                    "description": "Completion is blocked until the investigation is opened and the backend records the procedural start.",
                    "required_action": "start_investigation",
                    "required_records": ["investigation_opened"],
                    "satisfied": False,
                    "requires_review": True,
                    "blocking_reason": "The procedure must first record an open investigation before completion is permitted.",
                    "trigger": "procedure gate",
                    "source_reference": "detective procedure state",
                    "rule_classification": "SYSTEM_CONTROL",
                })

            if active_investigation is not None and str((active_investigation or {}).get("status") or "").upper() in {"OPEN", "IN_PROGRESS"}:
                investigation_service = None
                if self.app is not None and hasattr(self.app, "extensions"):
                    investigation_service = self.app.extensions.get("investigation_service")
                if investigation_service is not None and hasattr(investigation_service, "REQUIRED_ACTION_SEQUENCE") and hasattr(investigation_service, "_completed_required_actions"):
                    completed_actions = set(investigation_service._completed_required_actions(str((active_investigation or {}).get("investigation_id") or "")))
                    required_actions = list(getattr(investigation_service, "REQUIRED_ACTION_SEQUENCE", []))
                    missing_actions = [action_name for action_name in required_actions if action_name not in completed_actions]
                    if missing_actions:
                        failed.append({
                            "rule_code": "PROCEDURE.INVESTIGATION_ACTIONS_REQUIRED",
                            "title": "All required investigative actions must be complete",
                            "version": "v1",
                            "category": "CONTROL_BOUNDARY",
                            "description": "Completion is blocked until the six required investigative actions have been recorded for this case.",
                            "required_action": "complete_investigation",
                            "required_records": missing_actions,
                            "satisfied": False,
                            "requires_review": True,
                            "blocking_reason": "The investigation cannot be completed until every required investigative action is recorded: " + ", ".join(missing_actions) + ".",
                            "trigger": "procedure gate",
                            "source_reference": "investigation action ledger",
                            "rule_classification": "SYSTEM_CONTROL",
                        })

        source_summary = self._case_protected_source_summary(case)
        if action_name != "start_investigation" and action != "view_preserved_evidence" and not source_summary["has_protected_source"]:
            failed.append({
                "rule_code": "PROCEDURE.SOURCE_CHAIN",
                "version": "v1",
                "category": "SOURCE_CONTINUITY",
                "description": "The case is missing the protected citizen source chain.",
                "required_records": ["source_submission", "source_candidate"],
                "satisfied": False,
                "requires_review": False,
            })

        if action == "complete_investigation" and str(actor_role or "").lower() != "detective":
            result = ControlGateResult.deny(
                self.gate_name,
                "PROCEDURE.FORGED_COMPLETION_BLOCKED",
                "Only a detective may complete the investigation for this procedural case.",
                case_reference=case_reference,
                actor_id=actor_id,
                actor_role=actor_role,
                action=action,
            )
            self._persist_state(case_reference, action, requirements, allowed=False, actor_id=actor_id, actor_role=actor_role)
            self._audit_event(
                action="procedure_gate_blocked",
                actor_id=actor_id or "unknown",
                actor_role=actor_role or "unknown",
                case_reference=case_reference,
                object_type="procedure_gate",
                object_id=case_reference,
                rule_code="PROCEDURE.FORGED_COMPLETION_BLOCKED",
                rule_version="v1",
                source_version=(self.get_case_source(case_reference) or {}).get("source_version") or "v1",
                previous_state=None,
                new_state="BLOCKED",
                decision="BLOCKED",
                reason="Only the detective role may authorize completion.",
                details={"action": action, "blocked": True},
            )
            return {
                **result.__dict__,
                "requirements": requirements,
                "status": result.status,
                "allowed": result.allowed,
                "gate": result.gate,
            }

        effective_requirements = list(requirements)
        seen_rule_codes = {str(item.get("rule_code") or "").upper() for item in effective_requirements}
        for item in failed:
            rule_code = str(item.get("rule_code") or "").upper()
            if rule_code and rule_code not in seen_rule_codes:
                effective_requirements.append(item)
                seen_rule_codes.add(rule_code)
        requirements = effective_requirements
        allowed = not failed

        if not allowed and any(str(item.get("rule_code") or "").upper() == "PROCEDURE.CASE_FACTS_VERIFICATION" for item in requirements):
            next_action = "verify_case_facts"
        if active_investigation is not None and str((active_investigation or {}).get("status") or "").upper() in {"OPEN", "IN_PROGRESS"} and not self._case_facts_verified(case):
            next_action = "verify_case_facts"
        result = ControlGateResult.allow(self.gate_name, "PROCEDURE.ALLOWED", "Detective procedure checks passed.", case_reference=case_reference, actor_id=actor_id, actor_role=actor_role, action=action) if allowed else ControlGateResult.deny(
            self.gate_name,
            "PROCEDURE.REVIEW_REQUIRED" if any(item.get("requires_review") for item in failed) else "PROCEDURE.BLOCKED",
            "Detective procedure requirements are not yet satisfied.",
            case_reference=case_reference,
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            requirements=failed,
        )
        self._persist_state(case_reference, action, requirements, allowed=allowed, actor_id=actor_id, actor_role=actor_role)
        self._audit_event(
            action="procedure_gate_evaluated",
            actor_id=actor_id or "system",
            actor_role=actor_role or "system",
            case_reference=case_reference,
            object_type="procedure_gate",
            object_id=case_reference,
            rule_code=(requirements[0] if requirements else {}).get("rule_code") or "PROCEDURE.SOURCE_CHAIN",
            rule_version=(requirements[0] if requirements else {}).get("version") or "v1",
            source_version=(self.get_case_source(case_reference) or {}).get("source_version") or "v1",
            previous_state=None,
            new_state="ALLOWED" if allowed else ("REVIEW_REQUIRED" if any(item.get("requires_review") for item in failed) else "BLOCKED"),
            decision=result.status,
            reason=result.message,
            details={"action": action, "status": result.status, "allowed": allowed, "requirements": requirements},
        )
        state_snapshot = self.get_case_state(case_reference) or {}
        blocking_requirements = [
            {
                "rule_code": item.get("rule_code"),
                "title": item.get("title") or item.get("description"),
                "description": item.get("description"),
                "required_action": item.get("required_action"),
                "blocking_reason": item.get("blocking_reason") or item.get("description"),
                "rule_classification": item.get("rule_classification"),
                "source_reference": item.get("source_reference"),
                "trigger": item.get("trigger"),
            }
            for item in requirements
            if not item.get("satisfied")
        ]
        blocking_reason = None if not blocking_requirements else "; ".join(
            item.get("blocking_reason") or item.get("description") or item.get("title") or item.get("rule_code")
            for item in blocking_requirements
        )
        current_stage = "CASE_REVIEW"
        current_action = action
        next_permitted_action = self._format_action_label(action)
        next_action = next((item.get("required_action") for item in requirements if not item.get("satisfied") and item.get("required_action")), action)
        if active_investigation is not None and str((active_investigation or {}).get("status") or "").upper() in {"OPEN", "IN_PROGRESS"}:
            if self._case_facts_verified(case):
                next_action = "record_finding" if self._required_investigation_actions_complete(active_investigation or latest_investigation) else "complete_investigation"
            else:
                next_action = "verify_case_facts"
        elif not allowed and any(str(item.get("rule_code") or "").upper() == "PROCEDURE.CASE_FACTS_VERIFICATION" for item in requirements):
            next_action = "verify_case_facts"
        procedure_status = "ACTIVE" if allowed else ("REVIEW_REQUIRED" if any(item.get("requires_review") for item in requirements if not item.get("satisfied")) else "BLOCKED")
        assigned_detective_id = None
        assigned_detective_role = None
        if self.assignment_service is not None:
            current_assignment = self.assignment_service.get_current_assignment_for_case(case_reference)
            if current_assignment is not None:
                assigned_detective_id = current_assignment.get("officer_id")
                assigned_detective_role = current_assignment.get("officer_role")

        if latest_investigation is not None and str((latest_investigation or {}).get("status") or "").upper() == "COMPLETED":
            current_stage = "INVESTIGATION_COMPLETE"
            current_action = "complete_investigation"
            next_action = "complete_investigation"
            next_permitted_action = "Investigation completed"
            procedure_status = "COMPLETED"
        elif active_investigation is not None and str((active_investigation or {}).get("status") or "").upper() in {"OPEN", "IN_PROGRESS"}:
            if self._case_facts_verified(case):
                required_actions_complete = self._required_investigation_actions_complete(active_investigation or latest_investigation)
                if required_actions_complete:
                    current_stage = "FINDINGS_READY"
                    next_permitted_action = "Document finding"
                    current_action = "record_finding"
                    next_action = "record_finding"
                else:
                    current_stage = "INVESTIGATION_OPEN"
                    next_permitted_action = "Complete investigation"
                    current_action = "complete_investigation"
                    next_action = "complete_investigation"
            else:
                current_stage = "CASE_FACTS_VERIFICATION"
                next_permitted_action = "Verify case facts"
                current_action = "verify_case_facts"
                next_action = "verify_case_facts"
        elif not allowed and any(str(item.get("rule_code") or "").upper() == "PROCEDURE.CASE_FACTS_VERIFICATION" for item in requirements):
            current_stage = "CASE_FACTS_VERIFICATION"
        else:
            current_stage = "CASE_REVIEW"

        if current_action is None:
            current_action = next_action if next_action is not None else action
        if latest_investigation is not None and str((latest_investigation or {}).get("status") or "").upper() == "COMPLETED":
            current_action = "complete_investigation"
        return {
            **result.__dict__,
            "case_reference": case_reference,
            "assigned_detective_id": assigned_detective_id,
            "assigned_detective_role": assigned_detective_role,
            "profile_name": (state_snapshot or {}).get("profile_name") or "DEFAULT",
            "ruleset_version": (state_snapshot or {}).get("ruleset_version") or self.DEFAULT_RULESET_VERSION,
            "rule_version": (state_snapshot or {}).get("rule_version") or "v1",
            "source_version": (state_snapshot or {}).get("source_version") or (self.get_case_source(case_reference) or {}).get("source_version") or "v1",
            "current_stage": current_stage,
            "current_action": current_action,
            "procedure_status": procedure_status,
            "next_permitted_action": next_permitted_action if latest_investigation is not None and str((latest_investigation or {}).get("status") or "").upper() == "COMPLETED" else (next_permitted_action if active_investigation is not None and str((active_investigation or {}).get("status") or "").upper() in {"OPEN", "IN_PROGRESS"} else (self._format_action_label(next_action) if not allowed else self._format_action_label(action))),
            "blocking_requirements": blocking_requirements,
            "blocking_reason": blocking_reason,
            "requirements": requirements,
            "status": result.status,
            "allowed": result.allowed,
            "gate": result.gate,
        }

    def get_case_state(self, case_reference):
        return self.state_repository.get_latest_for_case(str(case_reference))

    def _list_case_evidence_reviews(self, case_reference, actor_id=None):
        events = self.audit_service.get_for_case(str(case_reference)) if self.audit_service is not None else []
        review_events = []
        for event in events:
            action = str((event or {}).get("action") or "").lower()
            if action not in {"detective_evidence_review_completed", "evidence_review_completed", "detective_protected_evidence_reviewed"}:
                continue
            if actor_id is not None and str((event or {}).get("actor_id") or "") != str(actor_id):
                continue
            review_events.append(event)
        return review_events

    def record_evidence_review(self, case_reference, actor_id=None, actor_role=None, evidence_ids=None, payload=None):
        if not str(case_reference or "").strip():
            raise ValueError("Case reference is required.")

        case = self._load_case(case_reference)
        if case is None:
            raise ValueError("Docket not found.")
        if str(actor_role or "").lower() != "detective":
            raise ValueError("Only a detective may complete protected evidence review.")
        self._assert_detective_assignment(case_reference, actor_id=actor_id, actor_role=actor_role, action="review_case")

        if evidence_ids is None:
            evidence_ids = (payload or {}).get("evidence_ids") if isinstance(payload, dict) else None
        if evidence_ids is None:
            evidence_ids = list((self.get_case_source(case_reference) or {}).get("source_evidence_ids") or [])
        if not evidence_ids:
            protected_context = self._load_protected_context(case)
            evidence_ids = [
                str(item.get("evidence_id") or "")
                for item in (protected_context.get("citizen_evidence") or [])
                if isinstance(item, dict) and item.get("evidence_id")
            ]
        normalized = [str(item).strip() for item in (evidence_ids or []) if str(item).strip()]
        if not normalized:
            raise ValueError("Protected evidence review requires at least one preserved evidence item.")

        reviewed_at = self._utc_now()
        event = self._audit_event(
            action="detective_evidence_review_completed",
            actor_id=actor_id or "unknown",
            actor_role=actor_role or "detective",
            case_reference=case_reference,
            object_type="evidence_review",
            object_id=f"review-{str(case_reference).upper()}",
            rule_code="PROCEDURE.REVIEW_REQUIRED",
            rule_version="v1",
            source_version=(self.get_case_source(case_reference) or {}).get("source_version") or "v1",
            previous_state="CASE_REVIEW",
            new_state="REVIEW_COMPLETED",
            decision="ALLOWED",
            reason="Detective completed protected evidence review.",
            details={
                "case_reference": case_reference,
                "evidence_ids": normalized,
                "reviewed_by": actor_id,
                "reviewed_at": reviewed_at,
                "action": "detective_evidence_review_completed",
            },
        )

        requirements = self._build_rule_requirements(case, "review_case", actor_id=actor_id, actor_role=actor_role)
        for requirement in requirements:
            if requirement.get("rule_code") == "PROCEDURE.EVIDENCE_PRESERVED":
                requirement["state"] = "COMPLETED"
                requirement["status"] = "COMPLETED"
                requirement["satisfied"] = True
                requirement["requires_review"] = False
                requirement["blocking_reason"] = None
        self._persist_state(case_reference, "review_case", requirements, allowed=True, actor_id=actor_id, actor_role=actor_role)
        state_result = self.evaluate_case(case_reference, actor_id=actor_id, actor_role=actor_role, action="start_investigation")
        return {
            "case_reference": case_reference,
            "action": "detective_evidence_review_completed",
            "event_id": (event or {}).get("event_id") if isinstance(event, dict) else None,
            "reviewed_by": actor_id,
            "reviewed_at": reviewed_at,
            "evidence_ids": normalized,
            "allowed": bool(state_result.get("allowed")),
            "status": state_result.get("status") or "ALLOWED",
            "procedure_state": state_result,
        }

    def evaluate_action(self, case_reference, actor_id=None, actor_role=None, action="view_preserved_evidence", payload=None):
        return self.evaluate_case(case_reference, actor_id=actor_id, actor_role=actor_role, action=action, payload=payload)


class ProcedureEngineService(ProcedureGateEngine):
    """Backward-compatible alias for the detective procedure engine."""


class DetectiveProcedureService(ProcedureGateEngine):
    """Public detective procedure service used by the runtime and tests."""


__all__ = [
    "ProcedureGateEngine",
    "ProcedureEngineService",
    "DetectiveProcedureService",
]
