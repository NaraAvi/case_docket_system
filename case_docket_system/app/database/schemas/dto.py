"""DTO/schema contracts for request and response serialization."""


class CaseDocketDTO:
    """Placeholder for docket DTOs and validation contracts."""

    def __init__(self, case_id=None, title=None):
        self.case_id = case_id
        self.title = title


class CitizenSubmissionDTO:
    """Placeholder for citizen submission payloads."""

    def __init__(self, reporter_name=None, summary=None):
        self.reporter_name = reporter_name
        self.summary = summary


class InvestigationCaseViewDTO:
    """Operational detective view of a registered case."""

    def __init__(self, investigation_id=None, case_reference=None, case_status=None, title=None, description=None):
        self.investigation_id = investigation_id
        self.case_reference = case_reference
        self.case_status = case_status
        self.title = title
        self.description = description

    def to_dict(self):
        return {
            "investigation_id": self.investigation_id,
            "case_reference": self.case_reference,
            "case_status": self.case_status,
            "title": self.title,
            "description": self.description,
        }


class StatementReviewDTO:
    """Detective-accessible statement payload."""

    def __init__(self, statement_id=None, case_reference=None, statement_type=None, statement_content=None):
        self.statement_id = statement_id
        self.case_reference = case_reference
        self.statement_type = statement_type or "citizen_statement"
        self.statement_content = statement_content

    def to_dict(self):
        return {
            "statement_id": self.statement_id,
            "case_reference": self.case_reference,
            "statement_type": self.statement_type,
            "statement_content": self.statement_content,
        }


class EvidenceReviewDTO:
    """Evidence metadata surfaced during investigation review."""

    def __init__(self, evidence_id=None, evidence_type=None, description=None, source=None, storage_reference=None):
        self.evidence_id = evidence_id
        self.evidence_type = evidence_type
        self.description = description
        self.source = source
        self.storage_reference = storage_reference

    def to_dict(self):
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type,
            "description": self.description,
            "source": self.source,
            "storage_reference": self.storage_reference,
        }


class FlagReviewDTO:
    """Constable flag metadata surfaced during detective review."""

    def __init__(self, flag_id=None, category=None, notes=None, status=None, created_by_role=None):
        self.flag_id = flag_id
        self.category = category
        self.notes = notes
        self.status = status
        self.created_by_role = created_by_role

    def to_dict(self):
        return {
            "flag_id": self.flag_id,
            "category": self.category,
            "notes": self.notes,
            "status": self.status,
            "created_by_role": self.created_by_role,
        }


class RelatedCaseReviewDTO:
    """Related-case metadata surfaced during detective review."""

    def __init__(self, relationship_id=None, source_case_reference=None, related_case_reference=None, relationship_type=None):
        self.relationship_id = relationship_id
        self.source_case_reference = source_case_reference
        self.related_case_reference = related_case_reference
        self.relationship_type = relationship_type

    def to_dict(self):
        return {
            "relationship_id": self.relationship_id,
            "source_case_reference": self.source_case_reference,
            "related_case_reference": self.related_case_reference,
            "relationship_type": self.relationship_type,
        }


class FindingCreationDTO:
    """Finding request contract for a detective investigation."""

    def __init__(self, finding_type=None, notes=None):
        self.finding_type = finding_type
        self.notes = notes


class FindingResponseDTO:
    """Finding response contract."""

    def __init__(self, finding_id=None, investigation_id=None, case_reference=None, detective_id=None, finding_type=None, notes=None):
        self.finding_id = finding_id
        self.investigation_id = investigation_id
        self.case_reference = case_reference
        self.detective_id = detective_id
        self.finding_type = finding_type
        self.notes = notes

    def to_dict(self):
        return {
            "finding_id": self.finding_id,
            "investigation_id": self.investigation_id,
            "case_reference": self.case_reference,
            "detective_id": self.detective_id,
            "finding_type": self.finding_type,
            "notes": self.notes,
        }


class InvestigationCompletionRequestDTO:
    """Request contract for completing an investigation."""

    def __init__(self, outcome=None, final_notes=None):
        self.outcome = outcome
        self.final_notes = final_notes


class CompletedInvestigationResponseDTO:
    """Response contract for a completed investigation."""

    def __init__(self, investigation_id=None, case_reference=None, outcome=None, status=None, completed_at=None):
        self.investigation_id = investigation_id
        self.case_reference = case_reference
        self.outcome = outcome
        self.status = status
        self.completed_at = completed_at

    def to_dict(self):
        return {
            "investigation_id": self.investigation_id,
            "case_reference": self.case_reference,
            "outcome": self.outcome,
            "status": self.status,
            "completed_at": self.completed_at,
        }
