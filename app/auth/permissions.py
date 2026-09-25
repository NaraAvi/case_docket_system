"""Role and permission constants used by RBAC.

These placeholders define the actor boundaries required by the
case docket workflow.
"""

ROLES = {
    "citizen": "citizen",
    "constable": "constable",
    "detective": "detective",
    "station_commander": "station_commander",
    "ipid": "ipid",
    "ipid_officer": "ipid",
    "system_automation": "system_automation",
}

PERMISSIONS = {
    "submit_docket": "submit_docket",
    "register_docket": "register_docket",
    "investigate_case": "investigate_case",
    "review_escalation": "review_escalation",
    "assign_docket": "assign_docket",
    "archive_case": "archive_case",
    "access_audit_trail": "access_audit_trail",
}
