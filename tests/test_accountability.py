import pytest

from app import create_app

STATION_COMMANDER_ID = "2200223333116"
CONSTABLE_ID = "2200223333114"


def test_accountability_profile_tracks_demerits_and_threshold():
    app = create_app(testing=True)
    service = app.extensions["accountability_service"]

    service.record_event(
        subject_id=CONSTABLE_ID,
        actor_id=STATION_COMMANDER_ID,
        actor_role="station_commander",
        reason="Missed required docket handoff window.",
        delta=1,
        event_type="DEMERIT",
    )
    service.record_event(
        subject_id=CONSTABLE_ID,
        actor_id=STATION_COMMANDER_ID,
        actor_role="station_commander",
        reason="Repeated evidence handoff failure.",
        delta=1,
        event_type="DEMERIT",
    )
    service.record_event(
        subject_id=CONSTABLE_ID,
        actor_id=STATION_COMMANDER_ID,
        actor_role="station_commander",
        reason="Third demerit triggers review requirement.",
        delta=1,
        event_type="DEMERIT",
    )

    profile = service.get_profile(CONSTABLE_ID)
    assert profile["total_demerits"] == 3
    assert profile["threshold_reached"] is True
    assert profile["status"] in {"REVIEW_REQUIRED", "FROZEN", "ACCOUNTABILITY_REVIEW"}

    identity = app.extensions["identity_registry"].get_identity(CONSTABLE_ID)
    assert str(identity["access_state"]).upper() in {"ACCOUNTABILITY_REVIEW", "REVIEW_REQUIRED", "REVOKED", "FROZEN"}


def test_accountability_events_reject_duplicate_idempotency_keys():
    app = create_app(testing=True)
    service = app.extensions["accountability_service"]

    service.record_event(
        subject_id=CONSTABLE_ID,
        actor_id=STATION_COMMANDER_ID,
        actor_role="station_commander",
        reason="Duplicate attempt should be rejected.",
        delta=1,
        event_type="DEMERIT",
        idempotency_key="duplicate-001",
    )

    with pytest.raises(ValueError, match="duplicate|already recorded"):
        service.record_event(
            subject_id=CONSTABLE_ID,
            actor_id=STATION_COMMANDER_ID,
            actor_role="station_commander",
            reason="Duplicate attempt should be rejected.",
            delta=1,
            event_type="DEMERIT",
            idempotency_key="duplicate-001",
        )


def test_accountability_uses_clear_active_until_review_threshold_and_auto_creates_ipid_review_item():
    app = create_app(testing=True)
    service = app.extensions["accountability_service"]
    escalation_service = app.extensions["escalation_service"]

    service.record_event(
        subject_id=CONSTABLE_ID,
        actor_id=STATION_COMMANDER_ID,
        actor_role="station_commander",
        reason="First accountability warning.",
        delta=1,
        event_type="DEMERIT",
    )
    service.record_event(
        subject_id=CONSTABLE_ID,
        actor_id=STATION_COMMANDER_ID,
        actor_role="station_commander",
        reason="Second accountability warning.",
        delta=1,
        event_type="DEMERIT",
    )

    profile = service.get_profile(CONSTABLE_ID)
    assert profile["status"] in {"CLEAR", "NORMAL"}
    assert profile["access_state"] in {"ACTIVE", "CLEAR"}

    service.record_event(
        subject_id=CONSTABLE_ID,
        actor_id=STATION_COMMANDER_ID,
        actor_role="station_commander",
        reason="Third demerit requires automatic IPID review.",
        delta=1,
        event_type="DEMERIT",
    )

    updated_profile = service.get_profile(CONSTABLE_ID)
    assert updated_profile["total_demerits"] == 3
    assert updated_profile["status"] == "ACCOUNTABILITY_REVIEW"
    assert str(updated_profile["access_state"]).upper() in {"ACCOUNTABILITY_REVIEW", "RESTRICTED", "FROZEN"}

    review_items = escalation_service.list_for_case(f"ACCOUNTABILITY-{CONSTABLE_ID}")
    assert any(
        str(item.get("category") or "").upper() == "OFFICER_CONDUCT"
        and "ACCOUNTABILITY" in str(item.get("description") or "").upper()
        for item in review_items
    )


def test_accountability_gate_blocks_review_required_accounts():
    app = create_app(testing=True)
    service = app.extensions["accountability_service"]
    gate = app.extensions["accountability_gate"]

    service.record_event(
        subject_id=CONSTABLE_ID,
        actor_id=STATION_COMMANDER_ID,
        actor_role="station_commander",
        reason="Threshold reached for gate denial.",
        delta=3,
        event_type="DEMERIT",
    )

    result = gate.check(CONSTABLE_ID, actor_id=CONSTABLE_ID, actor_role="constable", operation="assignment")
    assert result.allowed is False
    assert result.status in {"REVIEW_REQUIRED", "ACCOUNTABILITY_REVIEW", "BLOCKED"}
