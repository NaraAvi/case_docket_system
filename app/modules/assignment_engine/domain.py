"""Assignment domain concepts for operational case responsibility."""


class Assignment:
    """Minimal assignment representation for case-to-officer operations."""

    def __init__(
        self,
        assignment_id=None,
        case_reference=None,
        officer_id=None,
        officer_role=None,
        assigned_by=None,
        assigned_by_role=None,
        assigned_at=None,
        status="ACTIVE",
        reason=None,
        previous_assignment_id=None,
    ):
        self.assignment_id = assignment_id
        self.case_reference = case_reference
        self.officer_id = officer_id
        self.officer_role = officer_role
        self.assigned_by = assigned_by
        self.assigned_by_role = assigned_by_role
        self.assigned_at = assigned_at
        self.status = status
        self.reason = reason
        self.previous_assignment_id = previous_assignment_id

    def to_dict(self):
        return {
            "assignment_id": self.assignment_id,
            "case_reference": self.case_reference,
            "officer_id": self.officer_id,
            "officer_role": self.officer_role,
            "assigned_by": self.assigned_by,
            "assigned_by_role": self.assigned_by_role,
            "assigned_at": self.assigned_at,
            "status": self.status,
            "reason": self.reason,
            "previous_assignment_id": self.previous_assignment_id,
        }
