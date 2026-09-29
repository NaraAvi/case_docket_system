import pytest

from app.modules.transcription_engine.services import TranscriptGenerationService


class FakeProvider:
    name = "Fake"
    engine_version = "fake-1.0"

    def is_available(self):
        return True

    def transcribe(self, recording):
        # Deterministic small transcript based on storage_reference
        rec = recording or {}
        ref = rec.get("storage_reference") or rec.get("filename") or "unknown"
        text = f"Transcript for {ref}"
        return {
            "status": "COMPLETED",
            "provider": self.name,
            "engine_version": self.engine_version,
            "transcript": {"text": text, "segments": []},
        }


def auth_headers(client, test_id):
    from tests.conftest import login

    token = login(client, test_id)
    return {"Authorization": f"Bearer {token}"}


def test_transcription_persistence_and_comparison(app_client):
    # Create a case and start an interview
    case = app_client.application.extensions["case_service"].create_case("2200223333111", {"title": "T", "description": "D", "status": "AWAITING_CONSTABLE_REGISTRATION"})
    case_ref = case.get("case_reference")

    constable_headers = auth_headers(app_client, "2200223333114")
    r = app_client.post(f"/api/v1/constable/dockets/{case_ref}/interview", headers=constable_headers, json={})
    assert r.status_code == 201
    interview = r.get_json()
    interview_id = interview.get("interview_id")
    assert interview_id

    # Install fake transcription service for deterministic tests. It must be
    # available before the final recording submission so automatic generation
    # runs during the submit flow.
    app_client.application.extensions["transcript_service"] = TranscriptGenerationService(provider=FakeProvider())

    # Submit citizen and constable recording metadata
    citizen_headers = auth_headers(app_client, "2200223333111")
    cr = app_client.post(f"/api/v1/citizen/interviews/{interview_id}/recording", headers=citizen_headers, json={"filename": "citizen.wav", "storage_reference": "recordings/citizen_test.wav"})
    assert cr.status_code == 201
    rr = app_client.post(f"/api/v1/constable/interviews/{interview_id}/recording", headers=constable_headers, json={"filename": "constable.wav", "storage_reference": "recordings/constable_test.wav"})
    assert rr.status_code == 201

    comp = app_client.get(f"/api/v1/constable/interviews/{interview_id}/recording-comparison", headers=constable_headers)
    assert comp.status_code == 200
    report = comp.get_json()
    assert report["status"] == "COMPLETED"
    assert "overall_similarity" in report

    # Install fake transcription service for deterministic tests. The service
    # should be invoked automatically once both recordings are submitted.
    app_client.application.extensions["transcript_service"] = TranscriptGenerationService(provider=FakeProvider())

    # After the constable submission (which completes the interview), the
    # system should auto-generate transcripts and then auto-run the
    # comparison. We do not call the transcript POST endpoint explicitly.
    # Comparison should now complete

    # Citizen can read transcripts and comparison via citizen endpoints
    ct = app_client.get(f"/api/v1/citizen/interviews/{interview_id}/transcripts", headers=citizen_headers)
    assert ct.status_code == 200
    ctp = ct.get_json()
    assert ctp["interview_id"] == interview_id
    assert ctp["transcripts"]["citizen_recording"]["status"] == "COMPLETED"

    cc = app_client.get(f"/api/v1/citizen/interviews/{interview_id}/recording-comparison", headers=citizen_headers)
    assert cc.status_code == 200
    crep = cc.get_json()
    assert crep["status"] == "COMPLETED"

    # Citizen should be forbidden from calling constable-only endpoint
    bad = app_client.get(f"/api/v1/constable/interviews/{interview_id}/recording-comparison", headers=citizen_headers)
    assert bad.status_code == 403


class PlaceholderBrowserProvider:
    name = "FakeBrowser"
    engine_version = "fake-browser-1.0"

    def is_available(self):
        return True

    def transcribe(self, recording):
        return {
            "status": "COMPLETED",
            "provider": self.name,
            "engine_version": self.engine_version,
            "transcript": {"text": "We agree on the same statement. The facts match exactly.", "segments": []},
        }


def test_transcript_results_persist_raw_spoken_text(app_client):
    case = app_client.application.extensions["case_service"].create_case("2200223333112", {"title": "T", "description": "D", "status": "AWAITING_CONSTABLE_REGISTRATION"})
    interview = app_client.application.extensions["constable_registration_service"].start_interview(case["case_reference"], "2200223333114")
    interview_id = interview["interview_id"]
    app_client.application.extensions["constable_registration_service"].save_transcript_result(
        interview_id,
        "citizen_recording",
        {
            "status": "COMPLETED",
            "provider": "WhisperX",
            "engine_version": "whisperx-test",
            "transcript": {
                "text": "We agree on the same statement. The facts match exactly.",
                "segments": [{"text": "We agree on the same statement."}, {"text": "The facts match exactly."}],
            },
        },
    )
    recording = app_client.application.extensions["constable_registration_service"]._get_authoritative_interview(interview_id)["citizen_recording"]
    assert recording["transcript_text"] == "We agree on the same statement. The facts match exactly."
    assert recording["transcript_segments"][0]["text"] == "We agree on the same statement."


def test_unavailable_whisperx_provider_does_not_fabricate_transcript_text():
    service = TranscriptGenerationService(provider="WhisperX")
    report = service.generate_transcript({"recording_id": "REC-demo", "filename": "citizen_recording.wav", "storage_reference": "recordings/citizen_recording.wav"})

    assert report["status"] in {"BLOCKED", "FAILED"}
    assert "The audio says on summer of 95 five people were there." not in str(report.get("transcript", {}).get("text", ""))
    error_text = str(report.get("error", "")).lower()
    assert "whisper" in error_text or "transcription" in error_text or "blocked" in error_text


def test_placeholder_browser_transcripts_are_rejected():
    service = TranscriptGenerationService(provider=PlaceholderBrowserProvider())
    report = service.generate_transcript({"recording_id": "REC-1", "storage_reference": "recordings/example.wav"})
    assert report["status"] == "FAILED"
    assert "placeholder" in report.get("error", "").lower() or "browser verification" in report.get("error", "").lower()
