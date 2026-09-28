from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"


def login(page, user_id, expected_path):
    page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    page.locator("#testId").fill(user_id)
    page.locator('button[type="submit"]').click()
    page.wait_for_url(f"**{expected_path}", timeout=30000)
    token = page.evaluate("() => localStorage.getItem('pdasToken')")
    return token


def api(page, path, method="GET", payload=None):
    return page.evaluate(
        """
        async ({ url, method, payload }) => {
          const token = localStorage.getItem('pdasToken');
          const headers = { 'Content-Type': 'application/json' };
          if (token) {
            headers.Authorization = 'Bearer ' + token;
          }
          const options = {
            method,
            headers,
            credentials: 'same-origin'
          };
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
        {"url": f"{BASE}{path}", "method": method, "payload": payload},
    )


def require_ok(label, result):
    if not result.get("ok", False):
        raise RuntimeError(f"{label} failed: {result}")
    return result


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    try:
        citizen = browser.new_page()
        token = login(citizen, "2200223333111", "/citizen")
        print("CITIZEN_LOGIN", bool(token), citizen.url)
        citizen.goto(f"{BASE}/citizen/dockets/new", wait_until="domcontentloaded")
        citizen.locator("#crimeType").fill("Browser validation docket")
        citizen.locator("#incidentLocation").fill("123 Browser Lane, Springfield")
        citizen.locator("#incidentDate").fill("2026-09-05")
        citizen.locator("#description").fill("Created through the live browser flow to prove the deterministic path.")
        citizen.locator("#submitCitizenDocket").click()
        citizen.wait_for_function("() => window.location.pathname.includes('/citizen/dockets/')", timeout=30000)
        case_ref = citizen.url.rstrip('/').split('/')[-1]
        print("CASE_REF", case_ref)
        require_ok("citizen submit", api(citizen, f"/api/v1/citizen/dockets/{case_ref}/submit", "POST"))
        escalation = require_ok("citizen escalation", api(citizen, f"/api/v1/citizen/dockets/{case_ref}/escalations", "POST", {"category": "OFFICER_CONDUCT", "reason": "Browser verification escalation"}))
        print("ESCALATION", escalation)

        constable = browser.new_page()
        token = login(constable, "2200223333114", "/constable")
        print("CONSTABLE_LOGIN", bool(token), constable.url)
        queue = require_ok("constable queue", api(constable, "/api/v1/constable/dockets/unregistered"))
        print("QUEUE_LEN", len(queue['data']) if isinstance(queue.get('data'), list) else 'n/a')
        interview = require_ok("constable interview", api(constable, f"/api/v1/constable/dockets/{case_ref}/interview", "POST"))
        interview_id = interview['data'].get('interview_id') if isinstance(interview.get('data'), dict) else None
        print("INTERVIEW_ID", interview_id)
        if interview_id:
            citizen_record = require_ok("citizen recording", api(constable, f"/api/v1/citizen/interviews/{interview_id}/recording", "POST", {"filename": "citizen.wav", "storage_reference": "citizen.wav"}))
            constable_record = require_ok("constable recording", api(constable, f"/api/v1/constable/interviews/{interview_id}/recording", "POST", {"filename": "constable.wav", "storage_reference": "constable.wav"}))
            register = require_ok("register interview", api(constable, f"/api/v1/constable/interviews/{interview_id}/register", "POST"))
            print("RECORDINGS", citizen_record, constable_record, register)

        detective = browser.new_page()
        token = login(detective, "2200223333115", "/detective")
        print("DETECTIVE_LOGIN", bool(token), detective.url)
        investigation = require_ok("detective investigation", api(detective, f"/api/v1/detective/dockets/{case_ref}/investigation", "POST", {"notes": "Browser verification investigation"}))
        investigation_id = investigation['data'].get('investigation_id') if isinstance(investigation.get('data'), dict) else None
        print("INVESTIGATION_ID", investigation_id)
        if investigation_id:
            finding = require_ok("detective finding", api(detective, f"/api/v1/detective/investigations/{investigation_id}/findings", "POST", {"finding_text": "Browser verification finding", "severity": "MEDIUM"}))
            complete = require_ok("detective complete", api(detective, f"/api/v1/detective/investigations/{investigation_id}/complete", "POST", {"outcome": "CLOSED"}))
            print("FINDING_COMPLETE", finding, complete)

        station = browser.new_page()
        token = login(station, "2200223333116", "/station-commander")
        print("STATION_LOGIN", bool(token), station.url)
        reassignment = require_ok("station reassignment", api(station, f"/api/v1/station-commander/dockets/{case_ref}/reassign", "POST", {"officer_id": "2200223333115", "reason": "Browser validation reassignment"}))
        print("REASSIGNMENT", reassignment)

        ipid = browser.new_page()
        token = login(ipid, "2200223333117", "/ipid")
        print("IPID_LOGIN", bool(token), ipid.url)
        queue = require_ok("ipid queue", api(ipid, "/api/v1/ipid/escalations"))
        print("IPID_QUEUE", queue)
        print("VERDICT=GREEN")
    finally:
        browser.close()
