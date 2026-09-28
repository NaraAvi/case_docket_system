import pytest

VALID_CITIZEN_ID = "2200223333111"
VALID_CONSTABLE_ID = "2200223333114"
VALID_DETECTIVE_ID = "2200223333115"
OTHER_DETECTIVE_ID = "2200223333117"


def login(app_client, test_id):
    response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": test_id},
    )
    assert response.status_code == 200
    return response.get_json()["access_token"]


def create_and_submit_case(app_client, citizen_token, title="Investigative action case"):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_CITIZEN_ID, title, "Action test docket.", status="DRAFT")
    case_reference = case["case_reference"]

    response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"statement_text": "Primary statement for investigation."},
    )
    assert response.status_code == 201

    submit_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/submit",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert submit_response.status_code == 200

    return case_reference


def register_case_for_detective(app_client, citizen_token, constable_token, title="Detective action case"):
    case_reference = create_and_submit_case(app_client, citizen_token, title)

    interview = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/interview",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"status": "STARTED"},
    )
    assert interview.status_code == 201
    interview_id = interview.get_json()["interview_id"]

    app_client.post(
        f"/api/v1/citizen/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"recording_type": "citizen_recording", "storage_reference": "citizen.wav", "filename": "citizen.wav"},
    )
    app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"recording_type": "constable_recording", "storage_reference": "constable.wav", "filename": "constable.wav"},
    )

    register_response = app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/register",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert register_response.status_code == 200

    from tests.conftest import assign_detective_to_case

    assign_detective_to_case(app_client, case_reference, VALID_DETECTIVE_ID)
    return case_reference


def open_investigation(app_client, citizen_token, constable_token, detective_token, title="Investigation actions case"):
    case_reference = register_case_for_detective(app_client, citizen_token, constable_token, title)
    response = app_client.post(
        f"/api/v1/detective/dockets/{case_reference}/investigation",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={"notes": "Investigation opened for action testing."},
    )
    assert response.status_code == 201
    data = response.get_json()
    return case_reference, data["investigation_id"]


def test_required_investigative_actions_can_be_completed_in_any_order_before_findings(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token, "Required action sequence")
    case_service = app_client.application.extensions["case_service"]
    case = case_service.get_case(case_reference)
    case.setdefault("evidence", []).append({
        "evidence_id": "EV-REQ-1",
        "evidence_type": "PHOTO",
        "description": "Evidence for the investigation.",
        "source": "citizen",
        "status": "SUBMITTED",
    })
    case_service.update_case(case)

    service = app_client.application.extensions["investigation_service"]
    with pytest.raises(ValueError, match="not complete|remain|required"):
        service.create_finding(
            investigation_id,
            VALID_DETECTIVE_ID,
            {"finding_type": "VALID", "notes": "This is not allowed yet.", "evidence_ids": ["EV-REQ-1"]},
        )

    random_order = [
        "WITNESS_CONTACT",
        "SCENE_REVIEW",
        "INTERVIEW",
        "RECORD_REQUEST",
        "EVIDENCE_REVIEW",
        "EVIDENCE_COLLECTION",
    ]
    for action_type in random_order:
        service.create_action(
            investigation_id,
            VALID_DETECTIVE_ID,
            {
                "action_type": action_type,
                "purpose": f"Required investigative step: {action_type}",
                "description": f"Completed the {action_type.lower().replace('_', ' ')} requirement for the docket.",
                "result": "Completed.",
            },
        )

    finding = service.create_finding(
        investigation_id,
        VALID_DETECTIVE_ID,
        {"finding_type": "VALID", "notes": "All required actions are complete and the evidence supports the finding.", "evidence_ids": ["EV-REQ-1"]},
    )
    assert finding["finding_type"] == "VALID"


def test_required_investigative_actions_are_blocked_until_six_completed(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token, "Partial action sequence")
    case_service = app_client.application.extensions["case_service"]
    case = case_service.get_case(case_reference)
    case.setdefault("evidence", []).append({
        "evidence_id": "EV-REQ-2",
        "evidence_type": "PHOTO",
        "description": "Evidence for partial investigation.",
        "source": "citizen",
        "status": "SUBMITTED",
    })
    case_service.update_case(case)

    service = app_client.application.extensions["investigation_service"]
    first_three = ["INTERVIEW", "EVIDENCE_REVIEW", "EVIDENCE_COLLECTION"]
    for action_type in first_three:
        service.create_action(
            investigation_id,
            VALID_DETECTIVE_ID,
            {
                "action_type": action_type,
                "purpose": f"Partial step: {action_type}",
                "description": f"Completed the {action_type.lower().replace('_', ' ')} action.",
                "result": "Recorded.",
            },
        )

    with pytest.raises(ValueError, match="not complete|remain|required"):
        service.create_finding(
            investigation_id,
            VALID_DETECTIVE_ID,
            {"finding_type": "VALID", "notes": "Not complete yet", "evidence_ids": ["EV-REQ-2"]},
        )

    service.create_action(
        investigation_id,
        VALID_DETECTIVE_ID,
        {"action_type": "RECORD_REQUEST", "purpose": "Request", "description": "Requested records.", "result": "Requested."},
    )
    service.create_action(
        investigation_id,
        VALID_DETECTIVE_ID,
        {"action_type": "WITNESS_CONTACT", "purpose": "Contact", "description": "Witness contacted.", "result": "Received information."},
    )
    service.create_action(
        investigation_id,
        VALID_DETECTIVE_ID,
        {"action_type": "SCENE_REVIEW", "purpose": "Review", "description": "Reviewed scene.", "result": "Site assessed."},
    )

    finding = service.create_finding(
        investigation_id,
        VALID_DETECTIVE_ID,
        {"finding_type": "VALID", "notes": "All required actions are complete and the evidence supports the finding.", "evidence_ids": ["EV-REQ-2"]},
    )
    assert finding["finding_type"] == "VALID"


def test_each_required_action_accepts_its_action_specific_contract(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)
    service = app_client.application.extensions["investigation_service"]
    case = service._get_case(case_reference)
    case.setdefault("evidence", []).append({
        "evidence_id": "EVD-CASE-101",
        "evidence_type": "PHOTO",
        "description": "Existing scene photo",
        "source": "constable",
        "status": "SUBMITTED",
    })
    service.case_service.update_case(case)

    valid_contracts = {
        "WITNESS_CONTACT": {
            "action_type": "WITNESS_CONTACT",
            "witness_name": "Jane Doe",
            "relationship_to_incident": "Neighbour",
            "contact_date": "2026-09-26",
            "contact_time": "09:15",
            "contact_method": "PHONE",
            "result": "UNAVAILABLE",
            "information_obtained": "No useful information was obtained.",
            "lead_generated": False,
            "explanation": "Witness was unavailable after repeated attempts."
        },
        "INTERVIEW": {
            "action_type": "INTERVIEW",
            "person_name": "John Smith",
            "role": "WITNESS",
            "interview_date": "2026-09-26",
            "interview_time": "11:00",
            "location_method": "PHONE",
            "interview_type": "FOLLOW_UP",
            "recording_uploads": ["rec-001.mp3"],
            "information_obtained": "He reported seeing the vehicle near the alley.",
            "contradictions": "NONE_IDENTIFIED",
            "follow_up_lead": False,
            "outcome": "INFORMATION_OBTAINED",
        },
        "EVIDENCE_REVIEW": {
            "action_type": "EVIDENCE_REVIEW",
            "selected_evidence_ids": ["EVD-CASE-101"],
            "observation": "The image shows a white van at the scene.",
            "interpretation": "This may align with the reported suspect vehicle.",
            "unknown_limitation": "The image is too narrow to establish the plate.",
            "consistency": "SUPPORTS_EXISTING_INFORMATION",
            "related_evidence_ids": [],
        },
        "EVIDENCE_COLLECTION": {
            "action_type": "EVIDENCE_COLLECTION",
            "evidence_type": "PHOTO",
            "description": "Body-worn camera still from the officer call point.",
            "source": "Police evidence locker",
            "where_obtained": "HQ evidence office",
            "date_time_obtained": "2026-09-26T12:00:00Z",
            "provider": "Evidence office",
            "collection_method": "PHOTOGRAPH_VIDEO",
            "result": "OBTAINED",
        },
        "RECORD_REQUEST": {
            "action_type": "RECORD_REQUEST",
            "record_type": "CCTV",
            "record_holder": "Local authority",
            "specific_record_requested": "CCTV footage for the alley entry",
            "date_range_from": "2026-09-25",
            "date_range_to": "2026-09-26",
            "reason_relevant": "The footage may confirm the suspect route.",
            "date_requested": "2026-09-26",
            "request_reference": "REQ-1001",
            "request_method": "EMAIL",
            "response": "PENDING",
        },
        "SCENE_REVIEW": {
            "action_type": "SCENE_REVIEW",
            "location": "Alley entrance",
            "scene_date": "2026-09-26",
            "scene_time": "08:30",
            "persons_present": "Detective and forensic technician",
            "scene_condition": "Dry and well lit",
            "observations": "Footprints and discarded packaging were visible near the gate.",
            "consistent_with_incident": "The placement was consistent with the reported route.",
            "differed": "No fresh blood marks were seen.",
            "not_established": "The exact origin of the packaging could not be confirmed.",
            "scene_material": [{"type": "PHOTOGRAPH", "reference": "scene-1.jpg"}],
            "visibility": "GOOD",
            "lighting": "ARTIFICIAL",
            "access_points": "Single alley entrance gate",
            "distances": "Approximately 8 metres between entrance and debris",
            "obstructions": "No major obstruction noted",
            "limitations": "The scene had already been disturbed before the review."
        },
    }

    for action_type, payload in valid_contracts.items():
        response = app_client.post(
            f"/api/v1/detective/investigations/{investigation_id}/actions",
            headers={"Authorization": f"Bearer {detective_token}"},
            json=payload,
        )
        assert response.status_code == 201, (action_type, response.get_data(as_text=True))
        body = response.get_json()
        assert body["action_type"] == action_type
        assert isinstance(body.get("record_data"), dict)

    response = app_client.get(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
    )
    assert response.status_code == 200
    actions = response.get_json()
    assert len(actions) == 6


def test_interview_supports_multiple_numbered_interviews_and_recording_numbers(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)
    service = app_client.application.extensions["investigation_service"]

    first = service.create_action(
        investigation_id,
        VALID_DETECTIVE_ID,
        {
            "action_type": "INTERVIEW",
            "person_name": "John Smith",
            "role": "WITNESS",
            "interview_date": "2026-09-26",
            "interview_time": "11:00",
            "location_method": "PHONE",
            "interview_type": "INITIAL",
            "recordings": [{"filename": "first-interview.mp3", "storage_reference": "recordings/first-interview.mp3"}],
            "information_obtained": "He described what he saw.",
            "contradictions": "NONE_IDENTIFIED",
            "follow_up_lead": False,
            "outcome": "INFORMATION_OBTAINED",
        },
    )
    second = service.create_action(
        investigation_id,
        VALID_DETECTIVE_ID,
        {
            "action_type": "INTERVIEW",
            "person_name": "John Smith",
            "role": "WITNESS",
            "interview_date": "2026-09-27",
            "interview_time": "12:00",
            "location_method": "IN_PERSON",
            "interview_type": "FOLLOW_UP",
            "recordings": [{"filename": "second-interview.mp3", "storage_reference": "recordings/second-interview.mp3"}],
            "information_obtained": "He clarified the timeline.",
            "contradictions": "IDENTIFIED",
            "contradiction_explanation": "He corrected the route after seeing the alley.",
            "follow_up_lead": True,
            "lead_description": "Check the alley side gate CCTV.",
            "outcome": "INFORMATION_OBTAINED",
        },
    )

    assert first["record_data"]["interview_number"] == 1
    assert second["record_data"]["interview_number"] == 2
    assert first["record_data"]["recordings"][0]["recording_number"] == 1
    assert second["record_data"]["recordings"][0]["recording_number"] == 1
    assert len(service.list_actions_for_investigation(investigation_id, VALID_DETECTIVE_ID)) == 2


def test_case_evidence_is_enforced_for_evidence_review_and_collection_payloads(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)
    service = app_client.application.extensions["investigation_service"]
    case = service._get_case(case_reference)
    case.setdefault("evidence", []).extend([
        {"evidence_id": "EVD-CASE-101", "evidence_type": "PHOTO", "description": "Scene photo", "source": "citizen", "status": "SUBMITTED"},
        {"evidence_id": "EVD-CASE-102", "evidence_type": "STATEMENT", "description": "Witness statement", "source": "citizen", "status": "SUBMITTED"},
    ])
    service.case_service.update_case(case)

    service.create_action(
        investigation_id,
        VALID_DETECTIVE_ID,
        {
            "action_type": "EVIDENCE_REVIEW",
            "selected_evidence_ids": ["EVD-CASE-101"],
            "observation": "The image shows a white van at the alley.",
            "interpretation": "This matches the reported vehicle movement.",
            "unknown_limitation": "The photo is slightly pixelated.",
            "consistency": "SUPPORTS_EXISTING_INFORMATION",
        },
    )

    with pytest.raises(ValueError, match="does not match any evidence item on this case"):
        service.create_action(
            investigation_id,
            VALID_DETECTIVE_ID,
            {
                "action_type": "EVIDENCE_REVIEW",
                "selected_evidence_ids": ["EVD-CROSS-CASE"],
                "observation": "No actual evidence was reviewed.",
                "interpretation": "This should fail.",
                "unknown_limitation": "The evidence is not on the case.",
                "consistency": "INCONCLUSIVE",
            },
        )

    collected = service.create_action(
        investigation_id,
        VALID_DETECTIVE_ID,
        {
            "action_type": "EVIDENCE_COLLECTION",
            "description": "Recovered scene still from the property manager.",
            "evidence_type": "PHOTO",
            "source": "Property manager",
            "date_time_obtained": "2026-09-26T15:30:00Z",
            "provider": "Property manager",
            "collection_method": "PHOTOGRAPH_VIDEO",
            "result": "OBTAINED",
            "collected_evidence_items": [
                {"description": "Still image from the rear gate", "evidence_type": "PHOTO", "source": "Property manager"},
                {"description": "Door camera still", "evidence_type": "PHOTO", "source": "Property manager"},
            ],
        },
    )

    assert isinstance(collected["record_data"].get("collected_evidence_items"), list)
    assert len(collected["record_data"]["collected_evidence_items"]) == 2


def test_evidence_review_accepts_authoritative_protected_case_evidence(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)
    case_service = app_client.application.extensions["case_service"]
    case = case_service.get_case(case_reference)

    submission_service = app_client.application.extensions["citizen_submission_service"]
    submission = submission_service.create_submission(
        VALID_CITIZEN_ID,
        {
            "title": "Protected evidence review case",
            "description": "Separate submission preserving the evidence the detective reviews.",
            "incident_date": "2026-09-26",
            "location": "Alley entrance",
        },
    )
    case["source_submission_id"] = submission["submission_id"]
    case["evidence"] = []
    case_service.update_case(case)

    evidence = submission_service.create_evidence(
        VALID_CITIZEN_ID,
        submission["submission_id"],
        {
            "evidence_type": "PHOTO",
            "description": "Protected citizen evidence reviewed by detective.",
            "filename": "protected-review.jpg",
            "storage_reference": "uploads/protected-review.jpg",
            "content_type": "image/jpeg",
        },
    )

    service = app_client.application.extensions["investigation_service"]
    action = service.create_action(
        investigation_id,
        VALID_DETECTIVE_ID,
        {
            "action_type": "EVIDENCE_REVIEW",
            "selected_evidence_ids": [evidence["evidence_id"]],
            "observation": "The item clearly shows the alley gate.",
            "interpretation": "It is consistent with the reported route.",
            "unknown_limitation": "It does not show the suspect identity.",
            "consistency": "SUPPORTS_EXISTING_INFORMATION",
        },
    )

    assert action["record_data"]["selected_evidence_ids"] == [evidence["evidence_id"]]


def test_evidence_review_and_collection_can_repeat_as_independent_action_records(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)
    service = app_client.application.extensions["investigation_service"]
    case = service._get_case(case_reference)
    case.setdefault("evidence", []).extend([
        {"evidence_id": "EVD-REVIEW-01", "evidence_type": "PHOTO", "description": "First review item", "source": "citizen", "status": "SUBMITTED"},
        {"evidence_id": "EVD-REVIEW-02", "evidence_type": "DOCUMENT", "description": "Second review item", "source": "constable", "status": "SUBMITTED"},
    ])
    service.case_service.update_case(case)

    first_review = service.create_action(
        investigation_id,
        VALID_DETECTIVE_ID,
        {
            "action_type": "EVIDENCE_REVIEW",
            "selected_evidence_ids": ["EVD-REVIEW-01"],
            "observation": "The first item shows the rear gate.",
            "interpretation": "This is consistent with the reported route.",
            "unknown_limitation": "The image is not broad enough to establish the full movement.",
            "consistency": "SUPPORTS_EXISTING_INFORMATION",
        },
    )
    second_review = service.create_action(
        investigation_id,
        VALID_DETECTIVE_ID,
        {
            "action_type": "EVIDENCE_REVIEW",
            "selected_evidence_ids": ["EVD-REVIEW-02"],
            "observation": "The second item confirms the witness account.",
            "interpretation": "The record supports the timeline.",
            "unknown_limitation": "The record does not establish the suspect identity.",
            "consistency": "PROVIDES_NEW_INFORMATION",
        },
    )

    first_collection = service.create_action(
        investigation_id,
        VALID_DETECTIVE_ID,
        {
            "action_type": "EVIDENCE_COLLECTION",
            "evidence_type": "PHOTO",
            "description": "Recovered still from the security gate.",
            "source": "Property manager",
            "date_time_obtained": "2026-09-26T15:30:00Z",
            "provider": "Property manager",
            "collection_method": "PHOTOGRAPH_VIDEO",
            "result": "OBTAINED",
        },
    )
    second_collection = service.create_action(
        investigation_id,
        VALID_DETECTIVE_ID,
        {
            "action_type": "EVIDENCE_COLLECTION",
            "evidence_type": "DOCUMENT",
            "description": "Statement from the property manager.",
            "source": "Property manager",
            "date_time_obtained": "2026-09-27T09:00:00Z",
            "provider": "Property manager",
            "collection_method": "DOCUMENT_SUPPLIED",
            "result": "OBTAINED",
        },
    )

    actions = service.list_actions_for_investigation(investigation_id, VALID_DETECTIVE_ID)
    assert first_review["action_id"] != second_review["action_id"]
    assert first_collection["action_id"] != second_collection["action_id"]
    assert len(actions) == 4
    assert {item["action_type"] for item in actions} == {"EVIDENCE_REVIEW", "EVIDENCE_COLLECTION"}


def test_interview_requires_recording_or_notes_and_invalid_contract_rejected(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "action_type": "INTERVIEW",
            "person_name": "John Smith",
            "role": "WITNESS",
            "interview_date": "2026-09-26",
            "interview_time": "11:00",
            "location_method": "PHONE",
            "interview_type": "FOLLOW_UP",
            "information_obtained": "He described what he saw.",
            "contradictions": "NONE_IDENTIFIED",
            "follow_up_lead": False,
            "outcome": "INFORMATION_OBTAINED",
        },
    )

    assert response.status_code == 400


@pytest.fixture()
def citizen_token(app_client):
    return login(app_client, VALID_CITIZEN_ID)


@pytest.fixture()
def constable_token(app_client):
    return login(app_client, VALID_CONSTABLE_ID)


@pytest.fixture()
def detective_token(app_client):
    return login(app_client, VALID_DETECTIVE_ID)


def test_detective_authorised_assignee_can_create_investigative_action(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "action_type": "INTERVIEW",
            "purpose": "Follow-up witness verification",
            "description": "Conducted the follow-up interview with the witness and documented the timeline.",
            "result": "Witness corroborated the reported sequence of events.",
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["action_type"] == "INTERVIEW"
    assert payload["investigation_id"] == investigation_id
    assert payload["case_reference"] == case_reference
    assert payload["detective_id"] == VALID_DETECTIVE_ID
    assert payload["action_id"]
    assert payload["provenance"]["actor_id"] == VALID_DETECTIVE_ID
    assert payload["provenance"]["source"] == "investigative_action"


def test_investigative_action_requires_authentication(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        json={
            "action_type": "EVIDENCE_REVIEW",
            "purpose": "Review evidence",
            "description": "Checked the evidence.",
            "result": "Relevant.",
        },
    )

    assert response.status_code == 401


def test_non_detective_rejected(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)
    citizen_token_2 = login(app_client, VALID_CITIZEN_ID)

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {citizen_token_2}"},
        json={
            "action_type": "EVIDENCE_REVIEW",
            "purpose": "Review evidence",
            "description": "Citizen trying to add action.",
            "result": "Rejected.",
        },
    )

    assert response.status_code == 403


def test_detective_assigned_to_another_case_rejected(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)
    other_detective_token = login(app_client, OTHER_DETECTIVE_ID)

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {other_detective_token}"},
        json={
            "action_type": "WITNESS_CONTACT",
            "purpose": "Follow-up contact",
            "description": "Other detective tries to record an action on this case.",
            "result": "Blocked.",
        },
    )

    assert response.status_code == 403


def test_missing_investigation_rejected(app_client, citizen_token, constable_token, detective_token):
    response = app_client.post(
        "/api/v1/detective/investigations/INV-999999/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "action_type": "INTERVIEW",
            "purpose": "Review",
            "description": "Missing investigation.",
            "result": "Rejected.",
        },
    )

    assert response.status_code == 404


def test_investigation_not_open_or_in_progress_rejected(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)
    service = app_client.application.extensions["investigation_service"]
    investigation = service.repository.get_by_investigation_id(investigation_id)
    investigation["status"] = "COMPLETED"
    service.repository.update(investigation["id"], investigation)

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "action_type": "RECORD_REQUEST",
            "purpose": "Request call records",
            "description": "Attempted while case was closed.",
            "result": "Rejected.",
        },
    )

    assert response.status_code == 400


def test_frozen_case_rejected(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)
    freeze_service = app_client.application.extensions["freeze_service"]
    freeze_service.freeze_case(case_reference, actor_id=VALID_CONSTABLE_ID, actor_role="constable", reason="Test freeze")

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "action_type": "SCENE_REVIEW",
            "purpose": "Site inspection",
            "description": "Could not proceed because the case is frozen.",
            "result": "Blocked by freeze.",
        },
    )

    assert response.status_code == 400


def test_client_detective_id_cannot_impersonate_another_detective(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "detective_id": OTHER_DETECTIVE_ID,
            "action_type": "WITNESS_CONTACT",
            "purpose": "Follow-up contact",
            "description": "Attempted impersonation.",
            "result": "Rejected.",
        },
    )

    assert response.status_code == 400


def test_client_case_binding_cannot_escape_authorised_case(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "case_reference": "CD-999999",
            "investigation_id": investigation_id,
            "action_type": "SCENE_REVIEW",
            "purpose": "Incorrect case context",
            "description": "Request tries to force a different case.",
            "result": "Rejected.",
        },
    )

    assert response.status_code == 400


def test_client_timestamp_and_provenance_metadata_rejected(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "action_type": "INTERVIEW",
            "purpose": "Follow-up witness verification",
            "description": "Attempt to forge provenance.",
            "result": "Rejected.",
            "performed_at": "2099-01-01T00:00:00Z",
            "created_at": "2099-01-01T00:00:00Z",
            "audit_actor": "other-detective",
            "provenance": {"actor_id": "other-detective"},
        },
    )

    assert response.status_code == 400


def test_investigative_action_is_persisted_correctly(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "action_type": "INTERVIEW",
            "purpose": "Interview the identified witness",
            "description": "Conducted the required first interview to establish the factual baseline.",
            "result": "Witness statement was recorded and added to the investigation record.",
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    repository = app_client.application.extensions["investigation_service"].action_repository
    record = repository.get_by_id(payload["action_id"])
    assert record["case_reference"] == case_reference
    assert record["investigation_id"] == investigation_id
    assert record["detective_id"] == VALID_DETECTIVE_ID
    assert record["action_type"] == "INTERVIEW"
    assert record["purpose"] == "Interview the identified witness"
    assert record["description"] == "Conducted the required first interview to establish the factual baseline."


def test_investigative_action_creates_audit_event(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "action_type": "INTERVIEW",
            "purpose": "Secure witness interview",
            "description": "Completed the required interview action and logged the witness account.",
            "result": "Witness account was recorded and preserved for review.",
        },
    )
    assert response.status_code == 201
    action = response.get_json()

    events = app_client.application.extensions["audit_service"].get_for_case(case_reference)
    assert any(event.get("action") == "investigative_action_created" for event in events)
    assert any(str(event.get("object_id") or "") == str(action["action_id"]) for event in events)


def test_protected_evidence_remains_unchanged(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)
    service = app_client.application.extensions["case_service"]
    case = service.get_case(case_reference)
    original = list(case.get("evidence") or [])

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "action_type": "EVIDENCE_REVIEW",
            "purpose": "Protected source review",
            "description": "Reviewed preserved evidence in the source chain.",
            "result": "No mutation to the protected evidence was made.",
            "evidence_id": "EVD-999999",
        },
    )

    assert response.status_code == 400
    refreshed = service.get_case(case_reference)
    assert refreshed.get("evidence") == original


def test_another_cases_evidence_cannot_be_linked(app_client, citizen_token, constable_token, detective_token):
    case_reference_1, investigation_id_1 = open_investigation(app_client, citizen_token, constable_token, detective_token, "Case A")

    other_case = app_client.application.extensions["case_service"].create_case(
        VALID_CITIZEN_ID,
        {"title": "Case B", "description": "Other case", "status": "REGISTERED"},
    )
    other_case_reference = other_case["case_reference"]
    app_client.application.extensions["assignment_service"].ensure_initial_detective_assignment(other_case_reference)

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id_1}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "action_type": "EVIDENCE_REVIEW",
            "purpose": "Incorrect evidence reference",
            "description": "Attempts to attach evidence from another case.",
            "result": "Rejected.",
            "evidence_id": (other_case.get("evidence") or [{}])[0].get("evidence_id", "EVD-OTHER"),
        },
    )

    assert response.status_code == 400


def test_detective_can_retrieve_investigative_actions_for_their_investigation(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)

    create_response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "action_type": "INTERVIEW",
            "purpose": "Witness follow-up",
            "description": "Completed a witness interview.",
            "result": "Witness provided a clarifying statement.",
        },
    )
    assert create_response.status_code == 201

    response = app_client.get(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload) >= 1
    assert any(item["action_type"] == "INTERVIEW" for item in payload)


def test_procedure_state_remains_investigation_open_after_recording_action(app_client, citizen_token, constable_token, detective_token):
    case_reference, investigation_id = open_investigation(app_client, citizen_token, constable_token, detective_token)

    response = app_client.post(
        f"/api/v1/detective/investigations/{investigation_id}/actions",
        headers={"Authorization": f"Bearer {detective_token}"},
        json={
            "action_type": "INTERVIEW",
            "purpose": "Document the first investigative interview",
            "description": "Completed the required first investigative action without altering the final case state.",
            "result": "Record created without changing the case state.",
        },
    )

    assert response.status_code == 201
    state = app_client.get(
        f"/api/v1/detective/dockets/{case_reference}/procedure-state",
        headers={"Authorization": f"Bearer {detective_token}"},
    )
    assert state.status_code == 200
    payload = state.get_json()
    assert payload["current_stage"] == "INVESTIGATION_OPEN"
    assert payload["next_permitted_action"] == "Complete investigation"
