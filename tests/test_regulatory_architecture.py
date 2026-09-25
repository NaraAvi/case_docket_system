import pytest

from app import create_app


def _create_registered_case(app):
    case_service = app.extensions["case_service"]
    case = case_service.create_case("2200223333111", {"title": "Regulatory control case", "description": "Legal and compliance controls."})
    case["status"] = "REGISTERED"
    case_service.update_case(case)
    return case


def test_legal_reference_catalog_has_authoritative_south_african_sources():
    app = create_app(testing=True)
    service = app.extensions["legal_reference_service"]

    ref = service.get_reference("RSA-CONSTITUTION-1996")

    assert ref is not None
    assert ref["act_name"] == "Constitution of the Republic of South Africa"
    assert ref["status"] == "ACTIVE"
    assert ref["source_type"] in {"official_legislation", "official_government"}


def test_regulatory_rules_are_system_controlled_and_versioned():
    app = create_app(testing=True)
    service = app.extensions["regulatory_rule_service"]

    rule = service.get_rule("CASE.ACCESS.RESTRICTED")

    assert rule["rule_code"] == "CASE.ACCESS.RESTRICTED"
    assert rule["status"] == "ACTIVE"
    assert rule["rule_version"] >= 1
    assert rule["legal_reference_id"] == "RSA-CONSTITUTION-1996"
    assert len(service.get_version_history("CASE.ACCESS.RESTRICTED")) >= 1

    with pytest.raises(PermissionError):
        service.update_rule(rule["rule_id"], {"rule_name": "tampered"})


def test_compliance_blocks_frozen_and_revoked_access():
    app = create_app(testing=True)
    case = _create_registered_case(app)
    freeze_service = app.extensions["freeze_service"]
    compliance = app.extensions["compliance_service"]
    registry = app.extensions["identity_registry"]

    freeze_service.freeze_case(case["case_reference"], "2200223333116", "station_commander", "Operational review")

    result = compliance.evaluate_action(
        actor_id="2200223333114",
        actor_role="constable",
        operation="register_docket",
        case_reference=case["case_reference"],
        case_state=case,
        freeze_state=freeze_service.get_current_freeze(case["case_reference"]),
        identity_state={"access_state": "ACTIVE"},
    )
    assert result.allowed is False
    assert result.rule_code == "CASE.FREEZE.RESTRICTED_MUTATION"

    registry.revoke_access("2200223333114")
    revoked = compliance.evaluate_action(
        actor_id="2200223333114",
        actor_role="constable",
        operation="register_docket",
        case_reference=case["case_reference"],
        case_state=case,
        freeze_state=None,
        identity_state=registry.get_identity("2200223333114"),
    )
    assert revoked.allowed is False
    assert "revoked" in revoked.reason.lower()


def test_integrity_tracks_allegation_to_finding_and_disciplinary_action():
    app = create_app(testing=True)
    service = app.extensions["integrity_service"]

    allegation = service.record_allegation(
        actor_id="2200223333114",
        actor_role="constable",
        case_reference="CD-20250101-0001",
        details={"reason": "Officer misconduct allegation"},
    )
    assert allegation["integrity_status"] == "ALLEGATION"

    review = service.record_review(
        actor_id="2200223333116",
        actor_role="station_commander",
        subject_event_id=allegation["integrity_event_id"],
        decision="MENTIONED_FOR_REVIEW",
    )
    assert review["integrity_status"] == "REVIEW"

    finding = service.confirm_finding(
        actor_id="2200223333116",
        actor_role="station_commander",
        subject_event_id=review["integrity_event_id"],
        findings={"summary": "Official misconduct confirmed"},
    )
    assert finding["integrity_status"] == "CONFIRMED_FINDING"

    discipline = service.apply_disciplinary_action(
        actor_id="2200223333116",
        actor_role="station_commander",
        subject_event_id=finding["integrity_event_id"],
        action_type="ACCESS_RESTRICTION",
    )
    assert discipline["integrity_status"] == "DISCIPLINARY_ACTION"


def test_evidence_integrity_detects_tampering():
    app = create_app(testing=True)
    service = app.extensions["integrity_service"]

    evidence = service.register_evidence(
        {
            "evidence_id": "EV-100",
            "case_reference": "CD-20250101-0001",
            "uploaded_by": "2200223333111",
            "storage_reference": "upload://evidence.pdf",
            "content_hash": "initial-hash",
        }
    )

    tampered = dict(evidence)
    tampered["content_hash"] = "tampered-hash"
    result = service.verify_evidence_integrity(tampered)

    assert result["integrity_status"] == "INTEGRITY_FAILURE"


def test_compliance_rejects_separation_of_duties_and_identity_spoofing():
    app = create_app(testing=True)
    case = _create_registered_case(app)
    compliance = app.extensions["compliance_service"]

    result = compliance.evaluate_action(
        actor_id="2200223333114",
        actor_role="constable",
        operation="investigate_docket",
        case_reference=case["case_reference"],
        case_state={**case, "assigned_officer_id": "2200223333114"},
        assignment={"officer_id": "2200223333114"},
        identity_state={"role": "constable"},
    )
    assert result.allowed is False
    assert result.rule_code == "CASE.SEPARATION_OF_DUTIES"

    spoofed = compliance.evaluate_action(
        actor_id="2200223333114",
        actor_role="citizen",
        claimed_role="constable",
        operation="register_docket",
        case_reference=case["case_reference"],
        case_state=case,
        identity_state={"role": "constable"},
    )
    assert spoofed.allowed is False
    assert "claimed role" in spoofed.reason.lower()


def test_audit_events_are_append_only_and_track_rule_context():
    app = create_app(testing=True)
    audit = app.extensions["audit_service"]

    event = audit.log(
        {
            "actor_id": "2200223333116",
            "actor_role": "station_commander",
            "action": "case_frozen",
            "case_reference": "CD-20250101-0001",
            "object_type": "case",
            "object_id": "CD-20250101-0001",
            "previous_state": "REGISTERED",
            "new_state": "FROZEN",
            "reason": "Regulatory review",
            "rule_code": "CASE.FREEZE.RESTRICTED_MUTATION",
            "legal_reference": "RSA-CONSTITUTION-1996",
        }
    )

    assert event["rule_code"] == "CASE.FREEZE.RESTRICTED_MUTATION"
    assert event["legal_reference"] == "RSA-CONSTITUTION-1996"

    with pytest.raises(ValueError):
        audit.update_event(event["event_id"], {"action": "tampered"})
