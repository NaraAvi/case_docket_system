"""Separation of duties and conflict-of-interest enforcement (Milestone 4.4).

PAJA section 3 requires a decision-maker free of bias, or of a reasonable
suspicion of bias. Instead of trusting an officer (or a station commander) to
notice a conflict, this service matches the identities involved in a docket and
refuses the assignment or the opening of the docket when a disqualifying
relationship exists.

Conflicts detected (each carries the rule code and legal reference it applies):

* COMPLAINANT_IS_OFFICER       -- the officer is the docket's complainant.
* IMPLICATED_OFFICER           -- the officer is, or was, the subject of an
                                  IPID referral, disciplinary case or
                                  suspended assignment on this docket.
* ACTIVE_DISCIPLINARY_CASE     -- the officer has an OPEN disciplinary case
                                  (assignments only).
* PRIOR_COMPLAINT_BY_COMPLAINANT -- the complainant has an undismissed
                                  complaint about work this officer handled.
* DECLARED_CONFLICT            -- the officer (or a supervisor on their
                                  behalf) declared a family / business /
                                  personal conflict with this docket or with
                                  the complainant.
* SAME_OFFICER_REGISTERED_AND_INVESTIGATED -- the officer who registered the
                                  docket may not also open its investigation.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules.audit_engine.services import AuditTrailService

RULE_CONFLICT = "CASE.CONFLICT_OF_INTEREST"
RULE_DISCIPLINARY = "CASE.ASSIGNMENT.ACTIVE_DISCIPLINARY_BLOCK"
RULE_SEPARATION = "CASE.SEPARATION_OF_DUTIES"
LEGAL_REFERENCE_PAJA = "RSA-PAJA-2000"
LEGAL_REFERENCE_PACA = "RSA-PACA-2004"


class ConflictOfInterestService:
    """Identity matching and recusal enforcement for operational officers."""

    RELATIONSHIP_TYPES = {"FAMILY", "BUSINESS", "PERSONAL", "FORMER_COMPLAINT", "OTHER"}
    OPERATIONS = {"assignment", "open_docket", "open_investigation"}
    DECLARING_ROLES = {"constable", "detective", "station_commander", "ipid"}
    DECLARE_ON_BEHALF_ROLES = {"station_commander", "ipid"}

    def __init__(
        self,
        case_service=None,
        assignment_service=None,
        escalation_service=None,
        disciplinary_service=None,
        declaration_repository=None,
        identity_registry=None,
        constable_service=None,
        audit_service=None,
    ):
        self.case_service = case_service
        self.assignment_service = assignment_service
        self.escalation_service = escalation_service
        self.disciplinary_service = disciplinary_service
        self.declaration_repository = declaration_repository
        self.identity_registry = identity_registry
        self.constable_service = constable_service
        self.audit_service = audit_service or AuditTrailService()

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _utc_now():
        return datetime.now(UTC).isoformat()

    def _cases_by_reference(self):
        if self.case_service is None:
            return {}
        return {case.get("case_reference"): case for case in self.case_service.get_all_cases()}

    @staticmethod
    def _conflict(conflict_type, reason, rule_code=RULE_CONFLICT, legal_reference_id=LEGAL_REFERENCE_PAJA, **evidence):
        return {
            "type": conflict_type,
            "reason": reason,
            "rule_code": rule_code,
            "legal_reference_id": legal_reference_id,
            "evidence": evidence,
        }

    # --------------------------------------------------------- identity matching
    def get_implicated_officer_ids(self, case_reference):
        """Every officer identity implicated on ``case_reference`` (IPID
        referrals, disciplinary cases, suspended assignments)."""
        implicated = set()
        if self.escalation_service is not None:
            for escalation in self.escalation_service.list_for_case(case_reference):
                if escalation.get("implicated_officer_id"):
                    implicated.add(str(escalation["implicated_officer_id"]))
        if self.disciplinary_service is not None:
            for record in self.disciplinary_service.get_for_case(case_reference):
                if record.get("implicated_officer_id"):
                    implicated.add(str(record["implicated_officer_id"]))
        if self.assignment_service is not None:
            for assignment in self.assignment_service.get_assignment_history_for_case(case_reference):
                if assignment.get("status") == "SUSPENDED":
                    implicated.add(str(assignment.get("officer_id")))
        return implicated

    def _officer_case_references(self, officer_id):
        references = set()
        if self.assignment_service is not None:
            for assignment in self.assignment_service.query_assignments_by_officer(officer_id):
                references.add(assignment.get("case_reference"))
        if self.escalation_service is not None:
            for escalation in self.escalation_service.list_all():
                if str(escalation.get("implicated_officer_id") or "") == officer_id:
                    references.add(escalation.get("case_reference"))
        references.discard(None)
        return references

    def _prior_complaints(self, complainant_id, officer_id, cases):
        """Undismissed complaints by ``complainant_id`` about work ``officer_id`` handled."""
        if self.escalation_service is None:
            return []
        officer_cases = self._officer_case_references(officer_id)
        matches = []
        for escalation in self.escalation_service.list_all():
            if escalation.get("case_reference") not in officer_cases:
                continue
            if str(escalation.get("status") or "").upper() == "RESOLVED" and str(escalation.get("decision") or "").upper() == "DISMISSED":
                continue
            if str(escalation.get("created_by_role") or "").lower() == "citizen":
                filed_by = str(escalation.get("created_by"))
            else:
                # Statutory referrals are raised by the system on behalf of
                # the docket's complainant.
                filed_by = str((cases.get(escalation.get("case_reference")) or {}).get("citizen_id"))
            if filed_by == str(complainant_id):
                matches.append(escalation)
        return matches

    # ---------------------------------------------------------------- evaluation
    def evaluate(self, case_reference, officer_id, operation="assignment"):
        """Return every conflict between ``officer_id`` and ``case_reference``."""
        if operation not in self.OPERATIONS:
            raise ValueError("Unsupported operation for conflict evaluation.")
        cases = self._cases_by_reference()
        case = cases.get(case_reference)
        if case is None:
            raise ValueError("Case not found.")
        officer_id = str(officer_id or "").strip()
        if not officer_id:
            raise ValueError("Officer identity is required.")
        complainant_id = case.get("citizen_id")

        conflicts = []

        if complainant_id is not None and str(complainant_id) == officer_id:
            conflicts.append(
                self._conflict(
                    "COMPLAINANT_IS_OFFICER",
                    "The officer is the complainant on this docket.",
                    complainant_id=str(complainant_id),
                )
            )

        if officer_id in self.get_implicated_officer_ids(case_reference):
            conflicts.append(
                self._conflict(
                    "IMPLICATED_OFFICER",
                    "The officer is implicated in an IPID matter on this docket.",
                    legal_reference_id=LEGAL_REFERENCE_PACA,
                )
            )

        if operation == "assignment" and self.disciplinary_service is not None:
            open_cases = self.disciplinary_service.list_open_for_officer(officer_id)
            if open_cases:
                conflicts.append(
                    self._conflict(
                        "ACTIVE_DISCIPLINARY_CASE",
                        "The officer has an open disciplinary case and cannot take on new dockets.",
                        rule_code=RULE_DISCIPLINARY,
                        legal_reference_id=LEGAL_REFERENCE_PACA,
                        disciplinary_case_ids=[item.get("disciplinary_case_id") for item in open_cases],
                    )
                )

        prior = self._prior_complaints(complainant_id, officer_id, cases)
        if prior:
            conflicts.append(
                self._conflict(
                    "PRIOR_COMPLAINT_BY_COMPLAINANT",
                    "The complainant has an undismissed complaint about this officer's earlier handling of a docket.",
                    escalation_ids=[item.get("escalation_id") for item in prior],
                )
            )

        if self.declaration_repository is not None:
            declared = [
                item
                for item in self.declaration_repository.list_active_for_officer(officer_id)
                if item.get("case_reference") == case_reference
                or (item.get("party_id") and str(item.get("party_id")) == str(complainant_id))
            ]
            if declared:
                conflicts.append(
                    self._conflict(
                        "DECLARED_CONFLICT",
                        "The officer has a declared conflict of interest with this docket or its complainant.",
                        declaration_ids=[item.get("declaration_id") for item in declared],
                        relationship_types=sorted({item.get("relationship_type") for item in declared}),
                    )
                )

        if operation == "open_investigation" and self.constable_service is not None and case.get("interview_id"):
            interview = self.constable_service.get_interview_by_id(case.get("interview_id"))
            if interview and str(interview.get("constable_id")) == officer_id:
                conflicts.append(
                    self._conflict(
                        "SAME_OFFICER_REGISTERED_AND_INVESTIGATED",
                        "The officer who registered this docket cannot also open its investigation.",
                        rule_code=RULE_SEPARATION,
                        interview_id=case.get("interview_id"),
                    )
                )

        return {
            "case_reference": case_reference,
            "officer_id": officer_id,
            "operation": operation,
            "conflicted": bool(conflicts),
            "conflicts": conflicts,
            "rule_code": RULE_CONFLICT,
            "legal_reference_id": LEGAL_REFERENCE_PAJA,
        }

    def assert_no_conflict(self, case_reference, officer_id, operation="assignment", actor_id=None, actor_role=None):
        """Raise ``ValueError`` (and write an audit record) if the officer is
        conflicted; return the clean evaluation otherwise."""
        result = self.evaluate(case_reference, officer_id, operation)
        if not result["conflicted"]:
            return result

        first = result["conflicts"][0]
        self.audit_service.log(
            {
                "actor_id": actor_id or str(officer_id),
                "actor_role": actor_role,
                "action": "conflict_of_interest_blocked",
                "case_reference": case_reference,
                "rule_code": first["rule_code"],
                "legal_reference": "Promotion of Administrative Justice Act 3 of 2000, section 3",
                "details": {
                    "officer_id": str(officer_id),
                    "operation": operation,
                    "conflict_types": [item["type"] for item in result["conflicts"]],
                },
            }
        )
        raise ValueError(f"Conflict of interest: {first['reason']}")

    # -------------------------------------------------------------- declarations
    def declare_conflict(self, officer_id, payload, declared_by, declared_by_role):
        """Record a conflict declaration for ``officer_id``. Officers declare
        for themselves; a station commander or IPID reviewer may declare on an
        officer's behalf."""
        if self.declaration_repository is None:
            raise ValueError("Conflict declarations are not configured.")
        if not isinstance(payload, dict):
            raise ValueError("Declaration payload must be a JSON object.")
        if str(declared_by_role or "").lower() not in self.DECLARING_ROLES:
            raise ValueError("Role is not permitted to declare a conflict of interest.")

        officer_id = str(officer_id or "").strip()
        if not officer_id:
            raise ValueError("Officer identity is required.")
        if officer_id != str(declared_by) and str(declared_by_role).lower() not in self.DECLARE_ON_BEHALF_ROLES:
            raise ValueError("Only the officer, a station commander or IPID can declare this conflict.")

        officer_role = None
        if self.identity_registry is not None:
            identity = self.identity_registry.get_identity(officer_id)
            if identity is None or not identity.get("active", True):
                raise ValueError("Officer identity is unknown.")
            officer_role = identity.get("role")
            if officer_role not in {"constable", "detective", "station_commander"}:
                raise ValueError("Conflicts can only be declared for operational officers.")

        relationship_type = str(payload.get("relationship_type") or "").strip().upper()
        if relationship_type not in self.RELATIONSHIP_TYPES:
            raise ValueError("Relationship type is invalid.")

        case_reference = str(payload.get("case_reference") or "").strip() or None
        party_id = str(payload.get("party_id") or "").strip() or None
        if not case_reference and not party_id:
            raise ValueError("A case reference or a party identity is required.")
        if case_reference and case_reference not in self._cases_by_reference():
            raise ValueError("Case not found.")

        record = self.declaration_repository.create(
            {
                "officer_id": officer_id,
                "officer_role": officer_role,
                "case_reference": case_reference,
                "party_id": party_id,
                "relationship_type": relationship_type,
                "description": str(payload.get("description") or "").strip() or None,
                "status": "ACTIVE",
                "declared_by": str(declared_by),
                "declared_by_role": str(declared_by_role).lower(),
                "declared_at": self._utc_now(),
            }
        )
        self.audit_service.log(
            {
                "actor_id": declared_by,
                "actor_role": declared_by_role,
                "action": "conflict_of_interest_declared",
                "case_reference": case_reference,
                "rule_code": RULE_CONFLICT,
                "legal_reference": "Promotion of Administrative Justice Act 3 of 2000, section 3",
                "details": {
                    "declaration_id": record.get("declaration_id"),
                    "officer_id": officer_id,
                    "party_id": party_id,
                    "relationship_type": relationship_type,
                },
            }
        )
        return dict(record)

    def list_declarations(self, officer_id=None, case_reference=None):
        if self.declaration_repository is None:
            return []
        if officer_id:
            records = self.declaration_repository.list_for_officer(officer_id)
        elif case_reference:
            records = self.declaration_repository.list_for_case(case_reference)
        else:
            records = self.declaration_repository.list()
        if case_reference:
            records = [item for item in records if item.get("case_reference") == case_reference]
        return [dict(item) for item in records]
