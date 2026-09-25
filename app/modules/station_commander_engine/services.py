"""Station Commander oversight service.

This boundary intentionally reuses existing case, investigation, and audit data
without creating a parallel operational model or broader reassignment workflow.
"""

from __future__ import annotations

from app.auth.service import TestIdentityRegistry
from app.infrastructure.storage.media_manager import MediaManager
from app.modules.assignment_engine.services import AssignmentService
from app.modules.audit_engine.services import AuditTrailService
from app.modules.evidence_engine.services import EvidenceManagementService
from app.services.case_service import CaseService, new_evidence_id


class StationCommanderService:
    """Read-only oversight and force-reassignment boundary for station commanders."""

    def __init__(
        self,
        case_service=None,
        audit_service=None,
        identity_registry=None,
        assignment_service=None,
        freeze_service=None,
        automation_service=None,
        evidence_service=None,
        constable_service=None,
        investigation_service=None,
        media_manager=None,
    ):
        self.case_service = case_service or CaseService()
        self.audit_service = audit_service or AuditTrailService()
        self.identity_registry = identity_registry or TestIdentityRegistry()
        self.freeze_service = freeze_service
        self.automation_service = automation_service
        self.evidence_service = evidence_service or EvidenceManagementService()
        self.constable_service = constable_service
        self.investigation_service = investigation_service
        self.media_manager = media_manager or MediaManager()
        self.assignment_service = assignment_service or AssignmentService(
            case_service=self.case_service,
            audit_service=self.audit_service,
            identity_registry=self.identity_registry,
            freeze_service=self.freeze_service,
        )

    def _attach_current_assignment(self, case):
        if case is None:
            return None
        current = self.assignment_service.get_current_assignment_for_case(case.get("case_reference"))
        if current is not None:
            case["current_assignment"] = current
            case["assigned_officer_id"] = current.get("officer_id")
            case["assigned_officer_role"] = current.get("officer_role")
            case["assignment_timestamp"] = current.get("assigned_at")

        freeze = self.freeze_service.get_current_freeze(case.get("case_reference")) if self.freeze_service else None
        case["is_frozen"] = freeze is not None
        case["freeze_status"] = freeze.get("status") if freeze else "NOT_FROZEN"
        case["freeze_reason"] = freeze.get("reason") if freeze else None
        case["frozen_by"] = freeze.get("actor_id") if freeze else None
        case["current_freeze"] = freeze
        return case

    def get_profile(self, test_id):
        identity = self.identity_registry.get_identity(str(test_id))
        if not identity or not identity.get("active"):
            return None
        return {
            "test_id": identity["test_id"],
            "full_name": identity["full_name"],
            "role": identity["role"],
            "active": identity["active"],
        }

    def _build_operational_summary(self, case):
        if case is None:
            return None

        summary = dict(case)
        self._attach_current_assignment(summary)

        if self.automation_service and self.automation_service.sla_service:
            summary["sla"] = self.automation_service.sla_service.calculate_case_sla(summary.get("case_reference"))
            summary["sla_status"] = summary["sla"].get("status")
            summary["sla_due_timestamp"] = summary["sla"].get("sla_due_at")
            summary["is_sla_breached"] = summary["sla"].get("breached")

        if self.constable_service is not None:
            summary["flags"] = self.constable_service.list_flags_for_case(summary.get("case_reference"))
            summary["related_cases"] = self.constable_service.list_related_cases(summary.get("case_reference"))
            summary["evidence_summary"] = {
                "count": len(summary.get("evidence", [])),
                "items": [dict(item) for item in summary.get("evidence", [])],
            }

        if self.investigation_service is not None:
            investigations = self.investigation_service.repository.list_for_case(summary.get("case_reference"))
            summary["investigation_status"] = investigations[-1].get("status") if investigations else None
            summary["investigation"] = investigations[-1] if investigations else None

        return summary

    def list_dockets(self):
        dockets = []
        for case in self.case_service.get_all_cases():
            sanitized = {
                "id": case.get("id"),
                "case_reference": case.get("case_reference"),
                "title": case.get("title"),
                "description": case.get("description"),
                "status": case.get("status"),
                "citizen_id": case.get("citizen_id"),
                "incident_date": case.get("incident_date"),
                "location": case.get("location"),
                "created_at": case.get("created_at"),
            }
            dockets.append(self._build_operational_summary(sanitized))
        return dockets

    def get_docket(self, case_reference):
        for case in self.case_service.get_all_cases():
            if case.get("case_reference") == case_reference:
                return self._build_operational_summary(dict(case))
        return None

    def get_case_audit(self, case_reference):
        return self.audit_service.get_for_case(case_reference)

    def get_officer_audit(self, officer_id, actor_id=None):
        if officer_id is None:
            raise ValueError("Officer ID is required.")
        events = self.audit_service.get_events_by_actor(officer_id)
        if actor_id is not None:
            self.audit_service.log(
                {
                    "actor_id": actor_id,
                    "actor_role": "station_commander",
                    "action": "station_commander_reviewed_officer_audit",
                    "case_reference": None,
                    "details": {"officer_id": officer_id, "event_count": len(events)},
                }
            )
        return [
            {
                "actor_id": event.get("actor_id"),
                "actor_role": event.get("actor_role"),
                "action": event.get("action"),
                "case_reference": event.get("case_reference"),
                "timestamp": event.get("timestamp"),
                "details": event.get("details"),
            }
            for event in events
        ]

    def get_assignment_summary(self, case_reference):
        return {
            "case_reference": case_reference,
            "current_assignment": self.assignment_service.get_current_assignment_for_case(case_reference),
            "history": self.assignment_service.get_assignment_history_for_case(case_reference),
        }

    def get_sla_breaches(self):
        if self.automation_service is None or self.automation_service.sla_service is None:
            return []
        return self.automation_service.sla_service.list_breaches()

    def upload_frozen_docket_evidence(self, case_reference, actor_id, payload=None):
        if not isinstance(payload, dict):
            raise ValueError("Evidence payload must be a JSON object.")

        case = self.case_service.get_all_cases()
        case_record = None
        for item in case:
            if item.get("case_reference") == case_reference:
                case_record = item
                break
        if case_record is None:
            raise ValueError("Case not found.")
        if not self.freeze_service or not self.freeze_service.is_case_frozen(case_reference):
            raise ValueError("Case is not frozen.")

        evidence_type = str(payload.get("evidence_type") or "").strip()
        description = str(payload.get("description") or "").strip()
        filename = str(payload.get("filename") or "").strip()
        if not evidence_type or not description or not filename:
            raise ValueError("Evidence type, description, and filename are required.")

        storage_reference = payload.get("storage_reference") or filename
        media = self.media_manager.register_file(filename, {"storage_reference": storage_reference, "case_reference": case_reference})
        evidence = {
            "evidence_id": new_evidence_id(),
            "case_reference": case_reference,
            "submitted_by": actor_id,
            "submitted_by_role": "station_commander",
            "evidence_type": evidence_type,
            "description": description,
            "filename": media.get("filename"),
            "storage_reference": media.get("storage_reference"),
            "storage_root": media.get("storage_root"),
            "created_at": self.assignment_service._utc_now() if hasattr(self.assignment_service, "_utc_now") else None,
        }
        case_record.setdefault("evidence", []).append(evidence)
        self.case_service.update_case(case_record)
        self.evidence_service.add_evidence(dict(evidence))

        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": "station_commander",
                "action": "station_commander_evidence_uploaded_to_frozen_docket",
                "case_reference": case_reference,
                "details": {"evidence_id": evidence["evidence_id"], "evidence_type": evidence_type},
            }
        )
        return evidence

    def force_reassign_docket(self, case_reference, target_officer_id, actor_id, reason=None):
        case = self.get_docket(case_reference)
        if case is None:
            raise ValueError("Case not found.")

        current = self.assignment_service.get_current_assignment_for_case(case_reference)
        previous_officer_id = current.get("officer_id") if current else None
        previous_officer_role = current.get("officer_role") if current else None

        assignment = self.assignment_service.create_replacement_assignment(
            case_reference=case_reference,
            officer_id=target_officer_id,
            assigned_by=actor_id,
            assigned_by_role="station_commander",
            reason=reason,
            override_authority=True,
        )

        self.audit_service.log(
            {
                "actor_id": actor_id,
                "actor_role": "station_commander",
                "action": "station_commander_force_reassigned_docket",
                "case_reference": case_reference,
                "details": {
                    "previous_officer_id": previous_officer_id,
                    "previous_officer_role": previous_officer_role,
                    "new_officer_id": assignment.get("officer_id"),
                    "new_officer_role": assignment.get("officer_role"),
                    "reason": reason,
                    "assignment_id": assignment.get("assignment_id"),
                },
            }
        )
        return assignment
