"""Regression coverage for the three open repository issues."""

from io import BytesIO

import pytest

from app import create_app


ROLE_IDS = {
    "citizen": "2200223333111",
    "other_citizen": "2200223333112",
    "constable": "2200223333114",
    "detective": "2200223333115",
    "station_commander": "2200223333116",
    "ipid": "2200223333117",
}


@pytest.fixture()
def client():
    app = create_app(testing=True)
    with app.test_client() as test_client:
        yield test_client


def login(client, role="citizen"):
    response = client.post("/api/v1/auth/login", json={"test_id": ROLE_IDS[role]})
    assert response.status_code == 200, response.get_json()
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


def create_docket(client, role="citizen"):
    headers = login(client, role)
    response = client.post(
        "/api/v1/citizen/dockets",
        json={
            "title": "Test docket",
            "description": "A sufficiently detailed description for the test docket.",
            "location": "Test location",
            "incident_date": "2026-01-01",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["case_reference"], headers


def submit_docket(client, case_reference, headers):
    response = client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        json={"statement_text": "The registering officer refused to explain the next step."},
        headers=headers,
    )
    assert response.status_code == 201, response.get_json()
    response = client.post(f"/api/v1/citizen/dockets/{case_reference}/submit", headers=headers)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


class TestIssue10EvidenceRemoval:
    def test_detail_page_exposes_pending_file_clear_and_persisted_remove_controls(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        template = (root / "app/templates/citizen_docket_detail.html").read_text(encoding="utf-8")
        script = (root / "app/static/js/pdas.js").read_text(encoding="utf-8")
        for element_id in ("citizenEvidenceFile", "clearCitizenEvidenceFile", "citizenCaseEvidence", "data-remove-evidence"):
            if element_id == "data-remove-evidence":
                assert element_id in script
            else:
                assert element_id in template
        assert "method: 'DELETE'" in script

    def test_citizen_can_remove_evidence_and_new_ids_do_not_reuse_old_ids(self, client):
        case_reference, citizen = create_docket(client)
        first = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            json={"evidence_type": "DOCUMENT", "description": "First document", "filename": "first.pdf"},
            headers=citizen,
        )
        second = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            json={"evidence_type": "PHOTO", "description": "Second photo", "filename": "second.jpg"},
            headers=citizen,
        )
        assert first.status_code == second.status_code == 201
        first_id = first.get_json()["evidence_id"]
        second_id = second.get_json()["evidence_id"]

        removed = client.delete(
            f"/api/v1/citizen/dockets/{case_reference}/evidence/{first_id}",
            headers=citizen,
        )
        assert removed.status_code == 200, removed.get_json()
        assert removed.get_json()["filename"] == "first.pdf"

        remaining = client.get(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            headers=citizen,
        )
        assert remaining.status_code == 200
        assert [item["evidence_id"] for item in remaining.get_json()] == [second_id]

        replacement = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            json={"evidence_type": "OTHER", "description": "Replacement", "filename": "replacement.txt"},
            headers=citizen,
        )
        assert replacement.status_code == 201
        assert replacement.get_json()["evidence_id"] not in {first_id, second_id}

        docket = client.get(f"/api/v1/citizen/dockets/{case_reference}", headers=citizen)
        assert docket.status_code == 200
        assert first_id not in [item["evidence_id"] for item in docket.get_json()["evidence"]]
        assert any(event["action"] == "evidence_removed" for event in client.application.extensions["audit_service"].get_for_case(case_reference))

    def test_evidence_ids_are_not_reused_after_highest_or_all_items_are_removed(self, client):
        case_reference, citizen = create_docket(client)
        ids = []
        for index in range(2):
            response = client.post(
                f"/api/v1/citizen/dockets/{case_reference}/evidence",
                json={"evidence_type": "DOCUMENT", "description": f"Evidence {index}", "filename": f"{index}.txt"},
                headers=citizen,
            )
            assert response.status_code == 201
            ids.append(response.get_json()["evidence_id"])

        assert client.delete(
            f"/api/v1/citizen/dockets/{case_reference}/evidence/{ids[1]}",
            headers=citizen,
        ).status_code == 200
        third = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            json={"evidence_type": "DOCUMENT", "description": "Evidence after high removal", "filename": "third.txt"},
            headers=citizen,
        )
        assert third.status_code == 201
        third_id = third.get_json()["evidence_id"]
        assert third_id not in ids

        for evidence_id in [ids[0], third_id]:
            assert client.delete(
                f"/api/v1/citizen/dockets/{case_reference}/evidence/{evidence_id}",
                headers=citizen,
            ).status_code == 200
        fourth = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            json={"evidence_type": "DOCUMENT", "description": "Evidence after all removal", "filename": "fourth.txt"},
            headers=citizen,
        )
        assert fourth.status_code == 201
        assert fourth.get_json()["evidence_id"] not in {*ids, third_id}

    def test_non_owner_cannot_remove_evidence(self, client):
        case_reference, _ = create_docket(client)
        citizen = login(client)
        evidence = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            json={"evidence_type": "DOCUMENT", "description": "Private document", "filename": "private.pdf"},
            headers=citizen,
        )
        assert evidence.status_code == 201
        evidence_id = evidence.get_json()["evidence_id"]

        other = login(client, "other_citizen")
        denied = client.delete(
            f"/api/v1/citizen/dockets/{case_reference}/evidence/{evidence_id}",
            headers=other,
        )
        assert denied.status_code == 404
        assert client.get(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            headers=citizen,
        ).get_json()[0]["evidence_id"] == evidence_id

    def test_multipart_evidence_can_be_uploaded_and_removed(self, client, tmp_path):
        # Keep the test's physical upload out of the repository working tree.
        client.application.extensions["media_manager"].storage_root = str(tmp_path / "uploads")
        case_reference, citizen = create_docket(client)
        upload = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            data={
                "file": (BytesIO(b"evidence bytes"), "proof.txt"),
                "evidence_type": "DOCUMENT",
                "description": "Uploaded proof",
            },
            content_type="multipart/form-data",
            headers=citizen,
        )
        assert upload.status_code == 201, upload.get_json()
        evidence = upload.get_json()
        assert evidence["storage_reference"].startswith("evidence/")
        removed = client.delete(
            f"/api/v1/citizen/dockets/{case_reference}/evidence/{evidence['evidence_id']}",
            headers=citizen,
        )
        assert removed.status_code == 200

    def test_multipart_cleanup_runs_when_docket_persistence_fails(self, client, tmp_path, monkeypatch):
        client.application.extensions["media_manager"].storage_root = str(tmp_path / "uploads")
        case_reference, citizen = create_docket(client)

        def fail_update(*args, **kwargs):
            raise RuntimeError("simulated docket persistence failure")

        monkeypatch.setattr(
            client.application.extensions["citizen_docket_service"].docket_manager,
            "update_docket",
            fail_update,
        )
        with pytest.raises(RuntimeError):
            client.post(
                f"/api/v1/citizen/dockets/{case_reference}/evidence",
                data={
                    "file": (BytesIO(b"orphan bytes"), "orphan.txt"),
                    "evidence_type": "DOCUMENT",
                    "description": "Upload that cannot be persisted",
                },
                content_type="multipart/form-data",
                headers=citizen,
            )
        assert not list((tmp_path / "uploads").rglob("*.txt"))

    def test_json_evidence_cannot_reference_another_docket_upload(self, client, tmp_path):
        manager = client.application.extensions["media_manager"]
        manager.storage_root = str(tmp_path / "uploads")
        first_case, first_citizen = create_docket(client)
        upload = client.post(
            f"/api/v1/citizen/dockets/{first_case}/evidence",
            data={
                "file": (BytesIO(b"private evidence"), "private.txt"),
                "evidence_type": "DOCUMENT",
                "description": "Private upload",
            },
            content_type="multipart/form-data",
            headers=first_citizen,
        )
        assert upload.status_code == 201
        storage_reference = upload.get_json()["storage_reference"]
        stored_path = manager.resolve_path(storage_reference)
        assert stored_path is not None and stored_path.exists()

        second_case, second_citizen = create_docket(client, "other_citizen")
        metadata = client.post(
            f"/api/v1/citizen/dockets/{second_case}/evidence",
            json={
                "evidence_type": "DOCUMENT",
                "description": "Untrusted reference",
                "filename": "fake.txt",
                "storage_reference": storage_reference,
            },
            headers=second_citizen,
        )
        assert metadata.status_code == 201
        assert metadata.get_json()["storage_managed"] is False
        assert metadata.get_json()["storage_reference"] is None
        assert client.delete(
            f"/api/v1/citizen/dockets/{second_case}/evidence/{metadata.get_json()['evidence_id']}",
            headers=second_citizen,
        ).status_code == 200
        assert stored_path.exists()


class TestIssue11DuplicateEscalations:
    def test_second_unresolved_escalation_is_rejected_but_resolved_ticket_can_be_replaced(self, client):
        case_reference, citizen = create_docket(client)
        first = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OFFICER_CONDUCT", "description": "The officer was rude during the intake."},
            headers=citizen,
        )
        assert first.status_code == 201, first.get_json()
        escalation_id = first.get_json()["escalation_id"]

        duplicate = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "UNLAWFUL_DELAY", "description": "A second complaint about the same docket."},
            headers=citizen,
        )
        assert duplicate.status_code == 409
        assert duplicate.get_json()["escalation_id"] == escalation_id
        assert duplicate.get_json()["status"] == "OPEN"

        ipid = login(client, "ipid")
        assert client.post(f"/api/v1/ipid/escalations/{escalation_id}/review", headers=ipid).status_code == 200
        queue = client.get("/api/v1/ipid/escalations", headers=ipid)
        assert queue.status_code == 200
        assert any(item["escalation_id"] == escalation_id and item["status"] == "UNDER_REVIEW" for item in queue.get_json())
        still_duplicate = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OTHER", "description": "A third attempt while the first is under review."},
            headers=citizen,
        )
        assert still_duplicate.status_code == 409
        assert client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/dismiss",
            json={"reason": "The complaint was resolved without further review."},
            headers=ipid,
        ).status_code == 200

        replacement = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OTHER", "description": "A new complaint after the first was resolved."},
            headers=citizen,
        )
        assert replacement.status_code == 201
        assert replacement.get_json()["escalation_id"] != escalation_id

    def test_startup_recreates_the_active_ticket_index_for_existing_schema(self, tmp_path):
        from sqlalchemy import inspect, text

        from app import create_app
        from app.extensions import db

        database_uri = f"sqlite:///{tmp_path / 'case.db'}"
        first_app = create_app(database_uri=database_uri)
        with first_app.app_context():
            db.session.execute(text("DROP INDEX uq_escalation_unresolved_case"))
            db.session.commit()
            db.session.remove()
            db.engine.dispose()

        second_app = create_app(database_uri=database_uri)
        with second_app.app_context():
            indexes = {item["name"] for item in inspect(db.engine).get_indexes("escalations")}
            assert "uq_escalation_unresolved_case" in indexes

    def test_database_guard_rejects_two_active_rows_for_one_docket(self, client):
        from sqlalchemy.exc import IntegrityError

        from app.database.repositories.escalation_repository import EscalationRepository

        with client.application.app_context():
            repository = EscalationRepository()
            repository.create({
                "escalation_id": "ESC-DB-1",
                "case_reference": "CD-DB-1",
                "created_by": ROLE_IDS["citizen"],
                "created_by_role": "citizen",
                "category": "OTHER",
                "description": "First active database row.",
                "status": "OPEN",
            })
            with pytest.raises(IntegrityError):
                repository.create({
                    "escalation_id": "ESC-DB-2",
                    "case_reference": "CD-DB-1",
                    "created_by": ROLE_IDS["citizen"],
                    "created_by_role": "citizen",
                    "category": "OTHER",
                    "description": "Second active database row.",
                    "status": "OPEN",
                })

    def test_duplicate_check_preserves_the_original_timeline(self, client):
        case_reference, citizen = create_docket(client)
        first = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OTHER", "description": "The first escalation description."},
            headers=citizen,
        )
        assert first.status_code == 201
        client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OTHER", "description": "The duplicate escalation description."},
            headers=citizen,
        )
        docket = client.get(f"/api/v1/citizen/dockets/{case_reference}", headers=citizen).get_json()
        events = [event for event in docket["timeline"] if event["event_type"] == "citizen_escalation_submitted"]
        assert len(events) == 1


class TestIssue12RefusalToRegister:
    def test_registered_case_with_assignment_keeps_officer_accountability_path(self, client):
        case_reference, citizen = create_docket(client)
        submit_docket(client, case_reference, citizen)
        constable = login(client, "constable")
        interview = client.post(
            f"/api/v1/constable/dockets/{case_reference}/interview",
            headers=constable,
        )
        assert interview.status_code == 201, interview.get_json()
        interview_id = interview.get_json()["interview_id"]
        assert client.post(
            f"/api/v1/citizen/interviews/{interview_id}/recording",
            json={"filename": "citizen.wav"},
            headers=citizen,
        ).status_code == 201
        assert client.post(
            f"/api/v1/constable/interviews/{interview_id}/recording",
            json={"filename": "constable.wav"},
            headers=constable,
        ).status_code == 201
        assert client.post(
            f"/api/v1/constable/interviews/{interview_id}/register",
            headers=constable,
        ).status_code == 200

        assignment = client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/reassign",
            json={"officer_id": ROLE_IDS["detective"], "reason": "Assign for investigation."},
            headers=login(client, "station_commander"),
        )
        assert assignment.status_code == 200, assignment.get_json()
        escalation = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OFFICER_CONDUCT", "description": "The assigned officer mishandled the complaint."},
            headers=citizen,
        )
        assert escalation.status_code == 201, escalation.get_json()
        escalation_id = escalation.get_json()["escalation_id"]
        ipid = login(client, "ipid")
        assert client.post(f"/api/v1/ipid/escalations/{escalation_id}/review", headers=ipid).status_code == 200
        upheld = client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/uphold",
            json={"reason": "The assigned officer's conduct was substantiated."},
            headers=ipid,
        )
        assert upheld.status_code == 200, upheld.get_json()
        body = upheld.get_json()
        assert body["implicated_officer_id"] == ROLE_IDS["detective"]
        assert body["disciplinary_case"]["implicated_officer_id"] == ROLE_IDS["detective"]
        assert client.get("/api/v1/ipid/disciplinary-cases", headers=ipid).get_json()

    def test_registered_case_without_assignment_is_not_silently_upheld(self, client):
        case_reference, citizen = create_docket(client)
        submit_docket(client, case_reference, citizen)
        with client.application.app_context():
            from app.database.repositories.case_repository import CaseRepository

            repository = CaseRepository()
            case = repository.get_for_citizen(ROLE_IDS["citizen"], case_reference)
            repository.update(case["id"], {**case, "status": "REGISTERED"})

        escalation = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OFFICER_CONDUCT", "description": "An allegation without an assigned officer."},
            headers=citizen,
        )
        escalation_id = escalation.get_json()["escalation_id"]
        ipid = login(client, "ipid")
        assert client.post(f"/api/v1/ipid/escalations/{escalation_id}/review", headers=ipid).status_code == 200
        response = client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/uphold",
            json={"reason": "This must not silently drop officer accountability."},
            headers=ipid,
        )
        assert response.status_code == 400
        detail = client.get(f"/api/v1/ipid/escalations/{escalation_id}", headers=ipid)
        assert detail.get_json()["status"] == "UNDER_REVIEW"
        assert detail.get_json()["freeze_status"] == "NOT_FROZEN"

    def test_uphold_rolls_back_all_writes_when_disciplinary_creation_fails(self, client, monkeypatch):
        case_reference, citizen = create_docket(client)
        submit_docket(client, case_reference, citizen)
        constable = login(client, "constable")
        interview = client.post(
            f"/api/v1/constable/dockets/{case_reference}/interview",
            headers=constable,
        )
        interview_id = interview.get_json()["interview_id"]
        assert client.post(
            f"/api/v1/citizen/interviews/{interview_id}/recording",
            json={"filename": "citizen.wav"},
            headers=citizen,
        ).status_code == 201
        assert client.post(
            f"/api/v1/constable/interviews/{interview_id}/recording",
            json={"filename": "constable.wav"},
            headers=constable,
        ).status_code == 201
        assert client.post(
            f"/api/v1/constable/interviews/{interview_id}/register",
            headers=constable,
        ).status_code == 200
        assert client.post(
            f"/api/v1/station-commander/dockets/{case_reference}/reassign",
            json={"officer_id": ROLE_IDS["detective"], "reason": "Assign for investigation."},
            headers=login(client, "station_commander"),
        ).status_code == 200
        escalation = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OFFICER_CONDUCT", "description": "The assigned officer mishandled the complaint."},
            headers=citizen,
        )
        escalation_id = escalation.get_json()["escalation_id"]
        ipid = login(client, "ipid")
        assert client.post(f"/api/v1/ipid/escalations/{escalation_id}/review", headers=ipid).status_code == 200

        with client.application.app_context():
            service = client.application.extensions["ipid_service"]

            def fail_create_case(*args, **kwargs):
                raise RuntimeError("simulated disciplinary persistence failure")

            monkeypatch.setattr(service.disciplinary_service, "create_case", fail_create_case)
            with pytest.raises(RuntimeError):
                service.uphold_escalation(
                    escalation_id,
                    ROLE_IDS["ipid"],
                    {"reason": "This write must roll back."},
                )

            from app.database.repositories.disciplinary_case_repository import DisciplinaryCaseRepository
            from app.database.repositories.escalation_repository import EscalationRepository
            from app.database.repositories.freeze_repository import FreezeRepository

            assert EscalationRepository().get_by_id(escalation_id)["status"] == "UNDER_REVIEW"
            assert FreezeRepository().get_current_for_case(case_reference) is None
            assert DisciplinaryCaseRepository().list() == []
            assert service.identity_registry.get_identity(ROLE_IDS["detective"])["access_state"] == "ACTIVE"

    def test_unregistered_refusal_can_be_upheld_and_frozen_without_officer_discipline(self, client):
        case_reference, citizen = create_docket(client)
        submit_docket(client, case_reference, citizen)
        escalation = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "REFUSAL_TO_REGISTER", "description": "The station refused to register this lawful complaint."},
            headers=citizen,
        )
        assert escalation.status_code == 201, escalation.get_json()
        escalation_id = escalation.get_json()["escalation_id"]

        ipid = login(client, "ipid")
        assert client.post(f"/api/v1/ipid/escalations/{escalation_id}/review", headers=ipid).status_code == 200
        upheld = client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/uphold",
            json={"reason": "The refusal complaint is substantiated and requires registration review."},
            headers=ipid,
        )
        assert upheld.status_code == 200, upheld.get_json()
        body = upheld.get_json()
        assert body["decision"] == "UPHELD"
        assert body["status"] == "RESOLVED"
        assert body["implicated_officer_id"] is None
        assert body["disciplinary_case"] is None
        assert body["officer_accountability"]["reason_code"] == "NO_ACTIVE_ASSIGNMENT"

        docket = client.get(f"/api/v1/citizen/dockets/{case_reference}", headers=citizen)
        assert docket.status_code == 200
        assert docket.get_json()["status"] == "AWAITING_CONSTABLE_REGISTRATION"
        detail = client.get(f"/api/v1/ipid/escalations/{escalation_id}", headers=ipid)
        assert detail.get_json()["freeze_status"] == "FROZEN"
        assert client.get("/api/v1/ipid/disciplinary-cases", headers=ipid).get_json() == []
        events = client.application.extensions["audit_service"].get_for_case(case_reference)
        assert any(event["action"] == "ipid_officer_accountability_skipped" for event in events)
        assert not any(event["action"] == "officer_access_revoked" for event in events)

        # IPID custody must prevent the constable from starting/continuing
        # the registration workflow.
        constable = login(client, "constable")
        blocked = client.post(
            f"/api/v1/constable/dockets/{case_reference}/interview",
            headers=constable,
        )
        assert blocked.status_code == 400
        assert "frozen" in blocked.get_json()["error"].lower()
        evidence_blocked = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            json={"evidence_type": "DOCUMENT", "description": "Late evidence", "filename": "late.txt"},
            headers=citizen,
        )
        assert evidence_blocked.status_code == 400
        escalation_blocked = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OTHER", "description": "A late escalation during IPID custody."},
            headers=citizen,
        )
        assert escalation_blocked.status_code == 400
        assert "frozen" in escalation_blocked.get_json()["error"].lower()

    def test_non_refusal_unregistered_escalation_fails_before_resolution(self, client):
        case_reference, citizen = create_docket(client)
        submit_docket(client, case_reference, citizen)
        escalation = client.post(
            f"/api/v1/citizen/dockets/{case_reference}/escalations",
            json={"category": "OFFICER_CONDUCT", "description": "An allegation that is not about registration refusal."},
            headers=citizen,
        )
        escalation_id = escalation.get_json()["escalation_id"]
        ipid = login(client, "ipid")
        client.post(f"/api/v1/ipid/escalations/{escalation_id}/review", headers=ipid)
        response = client.post(
            f"/api/v1/ipid/escalations/{escalation_id}/uphold",
            json={"reason": "This should be rejected before any state changes."},
            headers=ipid,
        )
        assert response.status_code == 400
        detail = client.get(f"/api/v1/ipid/escalations/{escalation_id}", headers=ipid)
        assert detail.get_json()["status"] == "UNDER_REVIEW"
        assert detail.get_json()["freeze_status"] == "NOT_FROZEN"
