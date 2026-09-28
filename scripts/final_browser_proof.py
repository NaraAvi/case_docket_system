from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:5000"


def api(page, route: str, *, method: str = "GET", payload: dict | None = None):
    return page.evaluate(
        """
        async ({ url, method, payload }) => {
          const token = localStorage.getItem('pdasToken');
          const headers = { 'Content-Type': 'application/json' };
          if (token) {
            headers.Authorization = 'Bearer ' + token;
          }
          const options = { method, credentials: 'same-origin', headers };
          if (payload !== undefined && payload !== null) {
            options.body = JSON.stringify(payload);
          }
          const response = await fetch(url, options);
          const text = await response.text();
          let data = null;
          try {
            data = JSON.parse(text);
          } catch (error) {
            data = text;
          }
          return { status: response.status, ok: response.ok, data };
        }
        """,
        {"url": f"{BASE_URL}{route}", "method": method, "payload": payload},
    )


def login(page, user_id: str, expected_path: str):
    page.evaluate("""() => { localStorage.clear(); document.cookie = 'pdas_session_token=; path=/; max-age=0'; document.cookie = 'pdas_user=; path=/; max-age=0'; }""")
    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    page.fill("#testId", user_id)
    page.click("button[type='submit']")
    page.wait_for_url(f"**/{expected_path}", timeout=20000)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    citizen_page = browser.new_page(viewport={"width": 1440, "height": 900})
    login(citizen_page, "2200223333111", "citizen")
    citizen_page.goto(f"{BASE_URL}/citizen/dockets/new", wait_until="domcontentloaded")
    citizen_page.fill("#crimeType", "Final browser verification docket")
    citizen_page.fill("#incidentLocation", "100 Test Street, Springfield")
    citizen_page.fill("#incidentDate", "2026-09-05")
    citizen_page.fill("#description", "This docket was created in a live browser and must survive the deterministic PDAS workflow.")
    citizen_page.click("#submitCitizenDocket")
    citizen_page.wait_for_function("() => /CD-/.test(window.location.pathname)", timeout=20000)
    case_ref = citizen_page.evaluate("() => window.location.pathname.split('/').pop()")
    print(f"CASE_REF={case_ref}")
    assert case_ref.startswith("CD-"), case_ref
    assert case_ref != "new", case_ref

    statement = api(citizen_page, f"/api/v1/citizen/dockets/{case_ref}/statements", method="POST", payload={"statement_text": "Browser proof statement."})
    print(f"STATEMENT={statement}")
    assert statement["ok"] is True, statement

    submit = api(citizen_page, f"/api/v1/citizen/dockets/{case_ref}/submit", method="POST")
    print(f"SUBMIT={submit}")
    assert submit["ok"] is True, submit

    constable_page = browser.new_page(viewport={"width": 1440, "height": 900})
    login(constable_page, "2200223333114", "constable")
    queue = api(constable_page, "/api/v1/constable/dockets/unregistered")
    print(f"QUEUE={queue}")
    assert queue["ok"] is True, queue
    assert any(item.get("case_reference") == case_ref for item in queue["data"]), queue

    constable_page.goto(f"{BASE_URL}/constable/dockets/{case_ref}", wait_until="domcontentloaded")
    interview = api(constable_page, f"/api/v1/constable/dockets/{case_ref}/interview", method="POST")
    print(f"INTERVIEW={interview}")
    assert interview["ok"] is True, interview
    interview_id = interview["data"].get("interview_id") if isinstance(interview["data"], dict) else None
    assert interview_id is not None, interview

    citizen_recording = api(citizen_page, f"/api/v1/citizen/interviews/{interview_id}/recording", method="POST", payload={"filename": "citizen.wav", "storage_reference": "citizen.wav"})
    constable_recording = api(constable_page, f"/api/v1/constable/interviews/{interview_id}/recording", method="POST", payload={"filename": "constable.wav", "storage_reference": "constable.wav"})
    register = api(constable_page, f"/api/v1/constable/interviews/{interview_id}/register", method="POST")
    print(f"CITIZEN_RECORDING={citizen_recording}")
    print(f"CONSTABLE_RECORDING={constable_recording}")
    print(f"REGISTER={register}")
    assert citizen_recording["ok"] is True, citizen_recording
    assert constable_recording["ok"] is True, constable_recording
    assert register["ok"] is True, register

    detective_page = browser.new_page(viewport={"width": 1440, "height": 900})
    login(detective_page, "2200223333115", "detective")
    investigation = api(detective_page, f"/api/v1/detective/dockets/{case_ref}/investigation", method="POST", payload={"notes": "Live browser verification investigation."})
    print(f"INVESTIGATION={investigation}")
    assert investigation["ok"] is True, investigation
    investigation_id = investigation["data"].get("investigation_id") if isinstance(investigation["data"], dict) else None
    assert investigation_id is not None, investigation

    finding = api(detective_page, f"/api/v1/detective/investigations/{investigation_id}/findings", method="POST", payload={"finding_text": "Verification finding", "severity": "MEDIUM"})
    complete = api(detective_page, f"/api/v1/detective/investigations/{investigation_id}/complete", method="POST", payload={"outcome": "CLOSED"})
    print(f"FINDING={finding}")
    print(f"COMPLETE={complete}")
    assert finding["ok"] is True, finding
    assert complete["ok"] is True, complete

    commander_page = browser.new_page(viewport={"width": 1440, "height": 900})
    login(commander_page, "2200223333116", "station-commander")
    reassign = api(commander_page, f"/api/v1/station-commander/dockets/{case_ref}/reassign", method="POST", payload={"officer_id": "2200223333115", "reason": "browser verification"})
    print(f"REASSIGN={reassign}")
    assert reassign["ok"] is True, reassign

    citizen_page = browser.new_page(viewport={"width": 1440, "height": 900})
    login(citizen_page, "2200223333111", "citizen")
    escalation = api(citizen_page, f"/api/v1/citizen/dockets/{case_ref}/escalations", method="POST", payload={"category": "OFFICER_CONDUCT", "description": "Browser verification escalation for deterministic review and oversight."})
    print(f"ESCALATION={escalation}")
    assert escalation["ok"] is True, escalation
    escalation_id = escalation["data"].get("escalation_id") if isinstance(escalation["data"], dict) else None
    assert escalation_id is not None, escalation

    ipid_page = browser.new_page(viewport={"width": 1440, "height": 900})
    login(ipid_page, "2200223333117", "ipid")
    review = api(ipid_page, f"/api/v1/ipid/escalations/{escalation_id}/review", method="POST")
    note = api(ipid_page, f"/api/v1/ipid/escalations/{escalation_id}/review-notes", method="POST", payload={"note_text": "Browser verification IPID note"})
    dismiss = api(ipid_page, f"/api/v1/ipid/escalations/{escalation_id}/dismiss", method="POST", payload={"decision_reason": "Browser verification dismissal"})
    print(f"IPID_REVIEW={review}")
    print(f"IPID_NOTE={note}")
    print(f"IPID_DISMISS={dismiss}")
    assert review["ok"] is True, review
    assert note["ok"] is True, note
    assert dismiss["ok"] is True, dismiss

    print(f"END_TO_END_VERIFIED={case_ref}")
    browser.close()
    print("BROWSER_PROOF_PASSED")
