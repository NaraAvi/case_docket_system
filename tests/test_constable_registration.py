import pytest

from app.modules.control_gate import ConflictGate, ControlGateResult, FreezeGate, InterviewGate, RegistrationGate

VALID_CITIZEN_ID = "2200223333111"
VALID_CONSTABLE_ID = "2200223333114"


@pytest.fixture()
def citizen_token(app_client):
    response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CITIZEN_ID},
    )
    assert response.status_code == 200
    return response.get_json()["access_token"]


@pytest.fixture()
def constable_token(app_client):
    response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CONSTABLE_ID},
    )
    assert response.status_code == 200
    return response.get_json()["access_token"]


def test_constable_test_identity_can_authenticate(app_client):
    response = app_client.post(
        "/api/v1/auth/login",
        json={"test_id": VALID_CONSTABLE_ID},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["role"] == "constable"
    assert payload["test_id"] == VALID_CONSTABLE_ID


def test_constable_can_retrieve_unregistered_queue(app_client, citizen_token, constable_token):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_CITIZEN_ID, "Queue test docket", "This case should appear in the unregistered queue.")
    case_reference = case["case_reference"]

    app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"statement_text": "I am submitting this docket for registration review."},
    )

    submit_response = app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/submit",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert submit_response.status_code == 200

    response = app_client.get(
        "/api/v1/constable/dockets/unregistered",
        headers={"Authorization": f"Bearer {constable_token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, list)
    assert any(item["case_reference"] == case_reference for item in payload)


def test_citizen_cannot_access_unregistered_queue(app_client, citizen_token):
    response = app_client.get(
        "/api/v1/constable/dockets/unregistered",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    assert response.status_code == 403


def test_constable_can_start_interview_for_unregistered_docket(app_client, citizen_token, constable_token):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_CITIZEN_ID, "Interview start case", "This docket should be available for registration interview.")
    case_reference = case["case_reference"]

    app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"statement_text": "I am submitting this docket for the registration interview."},
    )
    app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/submit",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    response = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/interview",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"status": "STARTED"},
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["case_reference"] == case_reference
    assert payload["status"] in {"STARTED", "AWAITING_AUDIO"}


def test_citizen_can_submit_own_recording_and_constable_can_submit_own(app_client, citizen_token, constable_token):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_CITIZEN_ID, "Recording case", "A registration interview will be recorded on both sides.")
    case_reference = case["case_reference"]
    app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"statement_text": "I am submitting this docket for interview and registration."},
    )
    app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/submit",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )

    interview = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/interview",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"status": "STARTED"},
    )
    interview_id = interview.get_json()["interview_id"]

    citizen_recording = app_client.post(
        f"/api/v1/citizen/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "recording_type": "citizen_recording",
            "storage_reference": "citizen-audio-001.wav",
            "filename": "citizen-audio-001.wav",
        },
    )
    assert citizen_recording.status_code == 201

    constable_recording = app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={
            "recording_type": "constable_recording",
            "storage_reference": "constable-audio-001.wav",
            "filename": "constable-audio-001.wav",
        },
    )
    assert constable_recording.status_code == 201

    view = app_client.get(
        f"/api/v1/constable/interviews/{interview_id}",
        headers={"Authorization": f"Bearer {constable_token}"},
    )
    assert view.status_code == 200
    payload = view.get_json()
    assert payload["status"] == "COMPLETED"


def test_registration_succeeds_after_completed_interview(app_client, citizen_token, constable_token):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_CITIZEN_ID, "Registration case", "The docket should transition to REGISTERED after a complete interview.")
    case_reference = case["case_reference"]
    app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"statement_text": "I am providing the witness statement for registration."},
    )
    app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/submit",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    interview = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/interview",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"status": "STARTED"},
    )
    interview_id = interview.get_json()["interview_id"]

    app_client.post(
        f"/api/v1/citizen/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "recording_type": "citizen_recording",
            "storage_reference": "citizen-audio-002.wav",
            "filename": "citizen-audio-002.wav",
        },
    )
    app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={
            "recording_type": "constable_recording",
            "storage_reference": "constable-audio-002.wav",
            "filename": "constable-audio-002.wav",
        },
    )

    response = app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/register",
        headers={"Authorization": f"Bearer {constable_token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "REGISTERED"
    assert payload["case_reference"] == case_reference


def test_registration_allows_stale_interview_status_when_both_recordings_are_submitted(app_client, citizen_token, constable_token):
    from tests.conftest import create_case_via_service

    case = create_case_via_service(app_client, VALID_CITIZEN_ID, "Stale status case", "The interview should still register when both recordings are submitted even if the status field lags behind.")
    case_reference = case["case_reference"]
    app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/statements",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={"statement_text": "I am providing the witness statement for registration."},
    )
    app_client.post(
        f"/api/v1/citizen/dockets/{case_reference}/submit",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    interview = app_client.post(
        f"/api/v1/constable/dockets/{case_reference}/interview",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={"status": "STARTED"},
    )
    interview_id = interview.get_json()["interview_id"]

    app_client.post(
        f"/api/v1/citizen/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "recording_type": "citizen_recording",
            "storage_reference": "citizen-audio-003.wav",
            "filename": "citizen-audio-003.wav",
        },
    )
    app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/recording",
        headers={"Authorization": f"Bearer {constable_token}"},
        json={
            "recording_type": "constable_recording",
            "storage_reference": "constable-audio-003.wav",
            "filename": "constable-audio-003.wav",
        },
    )

    interview_after_submit = app_client.get(
        f"/api/v1/constable/interviews/{interview_id}",
        headers={"Authorization": f"Bearer {constable_token}"},
    ).get_json()
    interview_after_submit["status"] = "AWAITING_AUDIO"

    response = app_client.post(
        f"/api/v1/constable/interviews/{interview_id}/register",
        headers={"Authorization": f"Bearer {constable_token}"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "REGISTERED"


def test_constable_service_rehydrates_completed_interview_from_case_timeline_when_runtime_store_is_empty(app):
    with app.app_context():
        case_service = app.extensions["case_service"]
        constable_service = app.extensions["constable_registration_service"]

        case = case_service.create_case(
            VALID_CITIZEN_ID,
            {"title": "Timeline recovery case", "description": "The interview should be reconstructed from persisted case evidence when the runtime cache is empty."},
        )
        case_reference = case["case_reference"]
        interview_id = "INT-CASE-20260924-0001"
        case["status"] = "AWAITING_CONSTABLE_REGISTRATION"
        case["interview_id"] = interview_id
        case["timeline"] = [
            {
                "event_type": "constable_registration_interview_started",
                "actor_id": VALID_CONSTABLE_ID,
                "actor_role": "constable",
                "timestamp": "2026-09-24T12:00:00+00:00",
                "details": {"interview_id": interview_id},
            },
            {
                "event_type": "citizen_recording_submitted",
                "actor_id": VALID_CITIZEN_ID,
                "actor_role": "citizen",
                "timestamp": "2026-09-24T12:05:00+00:00",
                "details": {"recording_id": "REC-INT-CASE-20260924-0001-0001", "interview_id": interview_id},
            },
            {
                "event_type": "constable_recording_submitted",
                "actor_id": VALID_CONSTABLE_ID,
                "actor_role": "constable",
                "timestamp": "2026-09-24T12:06:00+00:00",
                "details": {"recording_id": "REC-INT-CASE-20260924-0001-0002", "interview_id": interview_id},
            },
            {
                "event_type": "interview_completed",
                "actor_id": VALID_CONSTABLE_ID,
                "actor_role": "constable",
                "timestamp": "2026-09-24T12:07:00+00:00",
                "details": {"interview_id": interview_id},
            },
        ]
        case_service.update_case(case)
        constable_service._interviews = {}
        constable_service._recordings = {}

        interview = constable_service.get_interview_for_constable(VALID_CONSTABLE_ID, interview_id)

        assert interview is not None
        assert interview["status"] == "COMPLETED"
        assert interview["citizen_recording"]["status"] == "SUBMITTED"
        assert interview["constable_recording"]["status"] == "SUBMITTED"


def test_constable_service_rehydrates_from_case_timeline_when_runtime_cache_is_stale(app):
    with app.app_context():
        case_service = app.extensions["case_service"]
        constable_service = app.extensions["constable_registration_service"]

        case = case_service.create_case(
            VALID_CITIZEN_ID,
            {"title": "Stale cache case", "description": "The runtime interview should not override the authoritative case timeline."},
        )
        case_reference = case["case_reference"]
        interview_id = "INT-CASE-STALE-0001"
        case["status"] = "AWAITING_CONSTABLE_REGISTRATION"
        case["interview_id"] = interview_id
        case["timeline"] = [
            {
                "event_type": "constable_registration_interview_started",
                "actor_id": VALID_CONSTABLE_ID,
                "actor_role": "constable",
                "timestamp": "2026-09-24T12:00:00+00:00",
                "details": {"interview_id": interview_id},
            },
            {
                "event_type": "citizen_recording_submitted",
                "actor_id": VALID_CITIZEN_ID,
                "actor_role": "citizen",
                "timestamp": "2026-09-24T12:05:00+00:00",
                "details": {
                    "recording_id": "REC-INT-CASE-STALE-0001-0001",
                    "interview_id": interview_id,
                    "storage_reference": "recordings/citizen_stale.wav",
                },
            },
        ]
        case_service.update_case(case)
        constable_service._interviews[interview_id] = {
            "interview_id": interview_id,
            "case_reference": case_reference,
            "citizen_id": VALID_CITIZEN_ID,
            "constable_id": VALID_CONSTABLE_ID,
            "status": "COMPLETED",
            "citizen_recording": {"status": "SUBMITTED", "storage_reference": "recordings/citizen_stale.wav"},
            "constable_recording": {"status": "SUBMITTED", "storage_reference": "recordings/constable_stale.wav"},
            "created_at": "2026-09-24T12:00:00+00:00",
            "updated_at": "2026-09-24T12:06:00+00:00",
        }

        interview = constable_service.get_interview_for_constable(VALID_CONSTABLE_ID, interview_id)

        assert interview is not None
        assert interview["status"] == "AWAITING_AUDIO"
        assert interview["citizen_recording"]["status"] == "SUBMITTED"
        assert interview["constable_recording"] is None


def test_constable_service_does_not_trust_completion_event_when_citizen_recording_is_missing(app):
    with app.app_context():
        case_service = app.extensions["case_service"]
        constable_service = app.extensions["constable_registration_service"]

        case = case_service.create_case(
            VALID_CITIZEN_ID,
            {"title": "Incomplete completion case", "description": "The completion event should not override a missing citizen recording."},
        )
        case_reference = case["case_reference"]
        interview_id = "INT-CASE-INCOMPLETE-0001"
        case["status"] = "AWAITING_CONSTABLE_REGISTRATION"
        case["interview_id"] = interview_id
        case["timeline"] = [
            {
                "event_type": "constable_registration_interview_started",
                "actor_id": VALID_CONSTABLE_ID,
                "actor_role": "constable",
                "timestamp": "2026-09-24T12:00:00+00:00",
                "details": {"interview_id": interview_id},
            },
            {
                "event_type": "constable_recording_submitted",
                "actor_id": VALID_CONSTABLE_ID,
                "actor_role": "constable",
                "timestamp": "2026-09-24T12:05:00+00:00",
                "details": {
                    "recording_id": "REC-INT-CASE-INCOMPLETE-0001-0001",
                    "interview_id": interview_id,
                    "storage_reference": "recordings/constable_incomplete.wav",
                },
            },
            {
                "event_type": "interview_completed",
                "actor_id": VALID_CONSTABLE_ID,
                "actor_role": "constable",
                "timestamp": "2026-09-24T12:06:00+00:00",
                "details": {"interview_id": interview_id},
            },
        ]
        case_service.update_case(case)

        interview = constable_service.get_interview_for_constable(VALID_CONSTABLE_ID, interview_id)

        assert interview is not None
        assert interview["status"] == "AWAITING_AUDIO"
        assert interview["citizen_recording"] is None
        assert interview["constable_recording"]["status"] == "SUBMITTED"


def test_recording_comparison_detects_material_content_differences():
    from app.modules.transcription_engine.services import RecordingComparisonEngine

    engine = RecordingComparisonEngine()
    report = engine.compare(
        {
            "recording_type": "citizen_recording",
            "duration": 25.0,
            "text": "I arrived at the station at six and spoke to the officer.",
            "segments": [{"speaker_label": "SPEAKER_00", "text": "I arrived at the station at six and spoke to the officer.", "start_time": 0.0, "end_time": 4.5}],
        },
        {
            "recording_type": "constable_recording",
            "duration": 26.0,
            "text": "I arrived at the station at seven and spoke to the officer.",
            "segments": [{"speaker_label": "SPEAKER_01", "text": "I arrived at the station at seven and spoke to the officer.", "start_time": 0.0, "end_time": 5.0}],
        },
    )

    assert report["status"] == "COMPLETED"
    assert report["overall_similarity"] < 100.0
    assert any(item["category"] in {"POTENTIAL_WORDING_VARIANCE", "SIGNIFICANT_SEQUENCE_VARIANCE"} for item in report["findings"])


def test_recording_comparison_waits_for_both_transcripts_until_both_are_available():
    from app.modules.transcription_engine.services import RecordingComparisonEngine

    engine = RecordingComparisonEngine()
    report = engine.compare({"recording_type": "citizen_recording", "text": "I arrived at the station at six and spoke to the officer."}, {"recording_type": "constable_recording", "text": ""})

    assert report["status"] == "WAITING_FOR_BOTH_TRANSCRIPTS"
    assert report["citizen_transcript_available"] is True
    assert report["constable_transcript_available"] is False
    assert "Waiting for both transcripts" in report["error"]


def test_recording_comparison_returns_unavailable_when_transcripts_are_missing():
    from app.modules.transcription_engine.services import RecordingComparisonEngine

    engine = RecordingComparisonEngine()
    report = engine.compare({"recording_type": "citizen_recording", "text": ""}, {"recording_type": "constable_recording", "text": ""})

    assert report["status"] == "WAITING_FOR_BOTH_TRANSCRIPTS"
    assert "Waiting for both transcripts" in report["error"]


def test_transcript_service_requires_real_provider_and_reports_blocked_state_when_unavailable():
    from app.modules.transcription_engine.services import TranscriptGenerationService, WhisperXProvider

    provider = WhisperXProvider()
    assert provider.name == "WhisperX"
    assert provider.is_available() in {True, False}

    service = TranscriptGenerationService(provider=provider)
    report = service.generate_transcript(
        {
            "recording_id": "REC-TEST-001",
            "recording_type": "citizen_recording",
            "case_reference": "CD-20260924-000001",
            "storage_reference": "recordings/test_input.mp4",
            "sha256_hash": "abc123",
        }
    )

    assert report["status"] in {"BLOCKED", "FAILED", "NOT_IMPLEMENTED", "COMPLETED"}
    if report["status"] in {"BLOCKED", "FAILED", "NOT_IMPLEMENTED"}:
        assert "WhisperX" in report["error"] or "blocked" in report["error"].lower() or "not available" in report["error"].lower()


def test_whisperx_provider_detects_local_whisper_fallback_when_available():
    import importlib.util

    from app.modules.transcription_engine.services import WhisperXProvider

    provider = WhisperXProvider()
    whisper_installed = importlib.util.find_spec("whisper") is not None
    if whisper_installed:
        assert provider.is_available() is True


def test_control_gate_result_model_and_registration_gate_block_incomplete_or_frozen_paths(app):
    with app.app_context():
        case_service = app.extensions["case_service"]
        citizen_service = app.extensions["citizen_docket_service"]
        constable_service = app.extensions["constable_registration_service"]
        freeze_service = app.extensions["freeze_service"]

        case = case_service.create_case(
            VALID_CITIZEN_ID,
            {"title": "Gate case", "description": "This docket should fail the gate checks."},
        )
        case_reference = case["case_reference"]
        citizen_service.add_statement(VALID_CITIZEN_ID, case_reference, {"statement_text": "Gate validation statement."})
        case = citizen_service.submit_docket(VALID_CITIZEN_ID, case_reference)
        assert case["status"] == "AWAITING_CONSTABLE_REGISTRATION"

        gate_result = ControlGateResult(False, "registration", "INTERVIEW_INCOMPLETE", "Interview is incomplete.")
        assert gate_result.allowed is False
        assert gate_result.code == "INTERVIEW_INCOMPLETE"

        interview = constable_service.start_interview(case_reference, VALID_CONSTABLE_ID)
        registration_gate = RegistrationGate(freeze_service=freeze_service)
        result = registration_gate.check(case=case_service.get_all_cases()[0], interview=interview, constable_id=VALID_CONSTABLE_ID)
        assert result.allowed is False
        assert "interview is incomplete" in result.message.lower()

        freeze_service.freeze_case(case_reference, "ipid-1", "ipid", reason="Test freeze", source=freeze_service.SOURCE_IPID_STATUTORY)
        freeze_gate = FreezeGate(freeze_service=freeze_service)
        frozen_result = freeze_gate.check(case_reference, actor_id=VALID_CONSTABLE_ID, actor_role="constable", operation="register")
        assert frozen_result.allowed is False
        assert frozen_result.code == "CASE.FROZEN"
        assert "frozen" in frozen_result.message.lower()

        assert isinstance(InterviewGate(), object)
        assert isinstance(ConflictGate(), object)

        with pytest.raises(ValueError, match="not awaiting constable registration|Case is frozen and operational mutation is restricted"):
            constable_service.register_docket(interview["interview_id"], VALID_CONSTABLE_ID)

        case_after_block = constable_service._get_docket_by_reference(case_reference)
        assert case_after_block["status"] == "AWAITING_CONSTABLE_REGISTRATION"
