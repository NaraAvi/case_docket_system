"""Tests for real file upload/storage/retrieval of evidence and interview
recordings, added on user request after manual testing showed both were
metadata-only text fields with no way to view what was "uploaded"."""

import hashlib
import io

import pytest

ROLE_TEST_IDS = {
    "citizen": "2200223333111",
    "citizen_two": "2200223333112",
    "constable": "2200223333114",
    "detective": "2200223333115",
    "station_commander": "2200223333116",
    "ipid": "2200223333117",
}


@pytest.fixture()
def app_client(tmp_path):
    from app import create_app

    app = create_app(testing=True, upload_storage_root=str(tmp_path / "uploads"))
    with app.test_client() as client:
        yield client


def _login(app_client, role):
    response = app_client.post("/api/v1/auth/login", json={"test_id": ROLE_TEST_IDS[role]})
    assert response.status_code == 200
    return response.get_json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_docket(app_client, citizen_token):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, ROLE_TEST_IDS["citizen"], "Vandalism", "Broken window overnight", location="Main St", incident_date="2026-01-01")
    return case["case_reference"]


class TestEvidenceFileUpload:
    def test_upload_evidence_computes_a_real_sha256_hash(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_docket(app_client, citizen_token)

        content = b"fake jpeg bytes for testing"
        expected_hash = hashlib.sha256(content).hexdigest()

        response = app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            data={
                "file": (io.BytesIO(content), "window.jpg"),
                "evidence_type": "PHOTO",
                "description": "Photo of the broken window.",
            },
            content_type="multipart/form-data",
            headers=_auth_headers(citizen_token),
        )
        assert response.status_code == 201
        evidence = response.get_json()
        assert evidence["sha256_hash"] == expected_hash
        assert evidence["size_bytes"] == len(content)
        assert evidence["filename"] == "window.jpg"
        assert evidence["storage_reference"].startswith("evidence/")

    def test_evidence_without_a_file_still_works_as_metadata_only(self, app_client):
        """Backward compatibility: JSON-only submission (no file) must keep working."""
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_docket(app_client, citizen_token)

        response = app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            json={"evidence_type": "PHOTO", "description": "No file attached.", "filename": "placeholder.jpg"},
            headers=_auth_headers(citizen_token),
        )
        assert response.status_code == 201
        assert response.get_json()["sha256_hash"] is None

    def test_owning_citizen_can_view_the_uploaded_file(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_docket(app_client, citizen_token)
        content = b"fake jpeg bytes"
        upload_response = app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            data={"file": (io.BytesIO(content), "window.jpg"), "evidence_type": "PHOTO", "description": "Broken window."},
            content_type="multipart/form-data",
            headers=_auth_headers(citizen_token),
        )
        storage_reference = upload_response.get_json()["storage_reference"]
        stored_filename = storage_reference.split("/", 1)[1]

        view_response = app_client.get(f"/api/v1/media/evidence/{stored_filename}", headers=_auth_headers(citizen_token))
        assert view_response.status_code == 200
        assert view_response.data == content
        assert view_response.headers["Content-Type"].startswith("image/")

    def test_a_different_citizen_cannot_view_someone_elses_evidence(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_docket(app_client, citizen_token)
        upload_response = app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            data={"file": (io.BytesIO(b"secret"), "window.jpg"), "evidence_type": "PHOTO", "description": "Broken window."},
            content_type="multipart/form-data",
            headers=_auth_headers(citizen_token),
        )
        stored_filename = upload_response.get_json()["storage_reference"].split("/", 1)[1]

        other_citizen_token = _login(app_client, "citizen_two")
        response = app_client.get(f"/api/v1/media/evidence/{stored_filename}", headers=_auth_headers(other_citizen_token))
        assert response.status_code == 403

    @pytest.mark.parametrize("role", ["constable", "detective", "station_commander", "ipid"])
    def test_operational_roles_can_view_any_evidence(self, app_client, role):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_docket(app_client, citizen_token)
        upload_response = app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/evidence",
            data={"file": (io.BytesIO(b"evidence bytes"), "window.jpg"), "evidence_type": "PHOTO", "description": "Broken window."},
            content_type="multipart/form-data",
            headers=_auth_headers(citizen_token),
        )
        stored_filename = upload_response.get_json()["storage_reference"].split("/", 1)[1]

        role_token = _login(app_client, role)
        response = app_client.get(f"/api/v1/media/evidence/{stored_filename}", headers=_auth_headers(role_token))
        assert response.status_code == 200

    def test_unknown_file_is_404(self, app_client):
        token = _login(app_client, "constable")
        response = app_client.get("/api/v1/media/evidence/does-not-exist.jpg", headers=_auth_headers(token))
        assert response.status_code == 404

    def test_path_traversal_attempt_is_rejected_not_500(self, app_client):
        token = _login(app_client, "constable")
        response = app_client.get("/api/v1/media/evidence/..%2f..%2fapp%2fconfig.py", headers=_auth_headers(token))
        assert response.status_code == 404


class TestRecordingFileUpload:
    def _start_interview_and_upload_citizen_recording(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_docket(app_client, citizen_token)
        app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/statements",
            json={"statement_text": "Someone broke my window."},
            headers=_auth_headers(citizen_token),
        )
        app_client.post(f"/api/v1/citizen/dockets/{case_reference}/submit", headers=_auth_headers(citizen_token))

        constable_token = _login(app_client, "constable")
        interview_response = app_client.post(f"/api/v1/constable/dockets/{case_reference}/interview", headers=_auth_headers(constable_token))
        interview_id = interview_response.get_json()["interview_id"]

        content = b"fake wav bytes"
        upload_response = app_client.post(
            f"/api/v1/citizen/interviews/{interview_id}/recording",
            data={"file": (io.BytesIO(content), "my_statement.wav")},
            content_type="multipart/form-data",
            headers=_auth_headers(citizen_token),
        )
        return citizen_token, constable_token, interview_id, upload_response, content

    def test_citizen_recording_upload_computes_a_real_hash(self, app_client):
        _, _, _, upload_response, content = self._start_interview_and_upload_citizen_recording(app_client)
        assert upload_response.status_code == 201
        recording = upload_response.get_json()
        assert recording["recording_type"] == "citizen_recording"
        assert recording["sha256_hash"] == hashlib.sha256(content).hexdigest()
        assert recording["storage_reference"].startswith("recordings/")

    def test_full_pipeline_with_real_file_uploads_reaches_registered(self, app_client):
        citizen_token, constable_token, interview_id, _, _ = self._start_interview_and_upload_citizen_recording(app_client)

        constable_upload = app_client.post(
            f"/api/v1/constable/interviews/{interview_id}/recording",
            data={"file": (io.BytesIO(b"constable audio"), "constable_interview.wav")},
            content_type="multipart/form-data",
            headers=_auth_headers(constable_token),
        )
        assert constable_upload.status_code == 201
        assert constable_upload.get_json()["recording_type"] == "constable_recording"

        register_response = app_client.post(f"/api/v1/constable/interviews/{interview_id}/register", headers=_auth_headers(constable_token))
        assert register_response.status_code == 200
        assert register_response.get_json()["status"] == "REGISTERED"

    def test_owning_citizen_can_view_their_recording(self, app_client):
        citizen_token, _, _, upload_response, content = self._start_interview_and_upload_citizen_recording(app_client)
        stored_filename = upload_response.get_json()["storage_reference"].split("/", 1)[1]

        response = app_client.get(f"/api/v1/media/recordings/{stored_filename}", headers=_auth_headers(citizen_token))
        assert response.status_code == 200
        assert response.data == content

    def test_unrelated_citizen_cannot_view_the_recording(self, app_client):
        _, _, _, upload_response, _ = self._start_interview_and_upload_citizen_recording(app_client)
        stored_filename = upload_response.get_json()["storage_reference"].split("/", 1)[1]

        other_citizen_token = _login(app_client, "citizen_two")
        response = app_client.get(f"/api/v1/media/recordings/{stored_filename}", headers=_auth_headers(other_citizen_token))
        assert response.status_code == 403

    def test_recording_without_a_file_still_works_as_metadata_only(self, app_client):
        citizen_token = _login(app_client, "citizen")
        case_reference = _create_docket(app_client, citizen_token)
        app_client.post(
            f"/api/v1/citizen/dockets/{case_reference}/statements",
            json={"statement_text": "Someone broke my window."},
            headers=_auth_headers(citizen_token),
        )
        app_client.post(f"/api/v1/citizen/dockets/{case_reference}/submit", headers=_auth_headers(citizen_token))
        constable_token = _login(app_client, "constable")
        interview_response = app_client.post(f"/api/v1/constable/dockets/{case_reference}/interview", headers=_auth_headers(constable_token))
        interview_id = interview_response.get_json()["interview_id"]

        response = app_client.post(
            f"/api/v1/citizen/interviews/{interview_id}/recording",
            json={"filename": "legacy.wav"},
            headers=_auth_headers(citizen_token),
        )
        assert response.status_code == 201
        assert response.get_json()["sha256_hash"] is None
