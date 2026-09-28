from pathlib import Path
from playwright.sync_api import sync_playwright
import json

BASE = "http://127.0.0.1:5000"
ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "browser_evidence"
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def login(page, user_id, expected_path):
    page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    page.fill("#testId", user_id)
    page.click('button[type="submit"]')
    page.wait_for_url(f"**{expected_path}", timeout=30000)
    token = page.evaluate("localStorage.getItem('pdasToken')")
    return token


def call_api(page, path, method="GET", payload=None):
    script = """
    async (url, method, payload) => {
      const token = localStorage.getItem('pdasToken');
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers.Authorization = 'Bearer ' + token;
      const options = { method, headers, credentials: 'same-origin' };
      if (payload !== undefined && payload !== null) options.body = JSON.stringify(payload);
      const response = await fetch(url, options);
      const text = await response.text();
      let data = null;
      try { data = JSON.parse(text); } catch (error) { data = text; }
      return { status: response.status, ok: response.ok, data };
    }
    """
    return page.evaluate(script, f"{BASE}{path}", method, payload)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    result = {"role_logins": {}, "workflow": {}}

    # citizen
    citizen = browser.new_page()
    result["role_logins"]["citizen"] = {"token_present": bool(login(citizen, "2200223333111", "/citizen"))}
    created = call_api(
        citizen,
        "/api/v1/citizen/dockets",
        "POST",
        {
            "title": "Browser validation docket",
            "description": "Created by the browser flow to prove the deterministic path end-to-end.",
            "incident_date": "2026-09-05",
            "location": "123 Browser Lane, Springfield",
        },
    )
    result["workflow"]["citizen_create"] = created
    case_ref = created["data"].get("case_reference") if isinstance(created.get("data"), dict) else None
    if case_ref:
        submit = call_api(citizen, f"/api/v1/citizen/dockets/{case_ref}/submit", "POST")
        result["workflow"]["citizen_submit"] = submit
        escalation = call_api(
            citizen,
            f"/api/v1/citizen/dockets/{case_ref}/escalations",
            "POST",
            {"category": "OFFICER_CONDUCT", "reason": "Browser validation escalation"},
        )
        result["workflow"]["citizen_escalation"] = escalation
    citizen.screenshot(path=str(ARTIFACTS / "01_citizen_dashboard.png"), full_page=True)
    citizen.close()

    # constable
    constable = browser.new_page()
    result["role_logins"]["constable"] = {"token_present": bool(login(constable, "2200223333114", "/constable"))}
    queue = call_api(constable, "/api/v1/constable/dockets/unregistered")
    result["workflow"]["constable_queue"] = queue
    if case_ref:
        interview = call_api(constable, f"/api/v1/constable/dockets/{case_ref}/interview", "POST")
        result["workflow"]["constable_interview"] = interview
        interview_id = interview["data"].get("interview_id") if isinstance(interview.get("data"), dict) else None
        if interview_id:
            citizen_recording = call_api(
                constable,
                f"/api/v1/citizen/interviews/{interview_id}/recording",
                "POST",
                {"filename": "citizen.wav", "storage_reference": "citizen.wav"},
            )
            constable_recording = call_api(
                constable,
                f"/api/v1/constable/interviews/{interview_id}/recording",
                "POST",
                {"filename": "constable.wav", "storage_reference": "constable.wav"},
            )
            register = call_api(constable, f"/api/v1/constable/interviews/{interview_id}/register", "POST")
            result["workflow"]["recordings"] = {"citizen": citizen_recording, "constable": constable_recording, "register": register}
    constable.screenshot(path=str(ARTIFACTS / "02_constable_dashboard.png"), full_page=True)
    constable.close()

    # detective
    detective = browser.new_page()
    result["role_logins"]["detective"] = {"token_present": bool(login(detective, "2200223333115", "/detective"))}
    if case_ref:
        investigation = call_api(detective, f"/api/v1/detective/dockets/{case_ref}/investigation", "POST", {"notes": "Browser validation investigation"})
        result["workflow"]["detective_investigation"] = investigation
        investigation_id = investigation["data"].get("investigation_id") if isinstance(investigation.get("data"), dict) else None
        if investigation_id:
            finding = call_api(
                detective,
                f"/api/v1/detective/investigations/{investigation_id}/findings",
                "POST",
                {"finding_text": "Browser validation finding", "severity": "MEDIUM"},
            )
            complete = call_api(
                detective,
                f"/api/v1/detective/investigations/{investigation_id}/complete",
                "POST",
                {"outcome": "CLOSED"},
            )
            result["workflow"]["detective_findings"] = {"finding": finding, "complete": complete}
    detective.screenshot(path=str(ARTIFACTS / "03_detective_dashboard.png"), full_page=True)
    detective.close()

    # station commander
    station = browser.new_page()
    result["role_logins"]["station_commander"] = {"token_present": bool(login(station, "2200223333116", "/station-commander"))}
    if case_ref:
        reassignment = call_api(
            station,
            f"/api/v1/station-commander/dockets/{case_ref}/reassign",
            "POST",
            {"officer_id": "2200223333115", "reason": "Browser validation reassignment"},
        )
        result["workflow"]["station_reassignment"] = reassignment
    station.screenshot(path=str(ARTIFACTS / "04_station_commander_dashboard.png"), full_page=True)
    station.close()

    # IPID
    ipid = browser.new_page()
    result["role_logins"]["ipid"] = {"token_present": bool(login(ipid, "2200223333117", "/ipid"))}
    escalation_list = call_api(ipid, "/api/v1/ipid/escalations")
    result["workflow"]["ipid_queue"] = escalation_list
    browser.close()

    outfile = ARTIFACTS / "verified_browser_flow.json"
    outfile.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
