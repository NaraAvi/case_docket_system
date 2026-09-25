IPID_TEST_ID = "2200223333117"


def _login(client, test_id):
    return client.post("/api/v1/auth/login", json={"test_id": test_id})


def test_ipid_review_workspace_includes_case_context_and_internal_review_records(app_client):
    from tests.conftest import create_case_via_service

    citizen_token = _login(app_client, "2200223333112").get_json()["access_token"]
    case = create_case_via_service(app_client, "2200223333112", "IPID review workspace", "Case context for internal review.")
    case_reference = case["case_reference"]

    escalation_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/escalations",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "category": "OFFICER_CONDUCT",
            "description": "The officer delayed registration and the citizen raised a conduct complaint.",
        },
    )
    escalation_id = escalation_response.get_json()["escalation_id"]

    ipid_token = _login(app_client, IPID_TEST_ID).get_json()["access_token"]
    workspace_response = app_client.get(
        f"/api/v1/ipid/escalations/{escalation_id}/review-workspace",
        headers={"Authorization": f"Bearer {ipid_token}"},
    )
    assert workspace_response.status_code == 200
    workspace = workspace_response.get_json()
    assert workspace["escalation_id"] == escalation_id
    assert workspace["case_reference"] == case_reference
    assert "readiness" in workspace
    assert "audit_history" in workspace
    assert "review_notes" in workspace
    assert "review_findings" in workspace

    note_response = app_client.post(
        f"/api/v1/ipid/escalations/{escalation_id}/review-notes",
        headers={"Authorization": f"Bearer {ipid_token}"},
        json={"note": "Initial review note: officer timeline requires validation."},
    )
    assert note_response.status_code == 201
    note = note_response.get_json()
    assert note["note_text"] == "Initial review note: officer timeline requires validation."

    finding_response = app_client.post(
        f"/api/v1/ipid/escalations/{escalation_id}/review-findings",
        headers={"Authorization": f"Bearer {ipid_token}"},
        json={
            "finding_type": "FURTHER_REVIEW_REQUIRED",
            "summary": "Additional case context is required before a misconduct conclusion.",
        },
    )
    assert finding_response.status_code == 201
    finding = finding_response.get_json()
    assert finding["finding_type"] == "FURTHER_REVIEW_REQUIRED"

    list_notes = app_client.get(
        f"/api/v1/ipid/escalations/{escalation_id}/review-notes",
        headers={"Authorization": f"Bearer {ipid_token}"},
    )
    assert list_notes.status_code == 200
    assert any(item["note_text"] == note["note_text"] for item in list_notes.get_json())

    list_findings = app_client.get(
        f"/api/v1/ipid/escalations/{escalation_id}/review-findings",
        headers={"Authorization": f"Bearer {ipid_token}"},
    )
    assert list_findings.status_code == 200
    assert any(item["finding_type"] == "FURTHER_REVIEW_REQUIRED" for item in list_findings.get_json())


def test_non_ipid_roles_cannot_access_review_workspace(app_client):
    citizen_token = _login(app_client, "2200223333111").get_json()["access_token"]
    response = app_client.get(
        "/api/v1/ipid/escalations/does-not-exist/review-workspace",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert response.status_code == 403
