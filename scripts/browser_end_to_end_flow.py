from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"


def login(page, user_id, expected_role):
    page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    page.fill("#testId", user_id)
    page.click('button[type="submit"]')
    page.wait_for_url(f"**/{expected_role}", timeout=30000)
    return page.evaluate("localStorage.getItem('pdasToken')")


def api(page, path, method="GET", payload=None):
    return page.evaluate(
        """
        async (url, method, payload) => {
          const token = localStorage.getItem('pdasToken');
          const headers = { 'Content-Type': 'application/json' };
          if (token) headers.Authorization = 'Bearer ' + token;
          const options = { method, headers, credentials: 'same-origin' };
          if (payload !== undefined && payload !== null) options.body = JSON.stringify(payload);
          const response = await fetch(url, options);
          const text = await response.text();
          let data = null;
          try { data = JSON.parse(text); } catch { data = text; }
          return { status: response.status, ok: response.ok, data };
        }
        """,
        f"{BASE}{path}",
        method,
        payload,
    )


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    citizen = browser.new_page()
    login(citizen, "2200223333111", "citizen")
    citizen.goto(f"{BASE}/citizen/dockets/new", wait_until="domcontentloaded")
    citizen.fill("#crimeType", "Browser verification docket")
    citizen.fill("#incidentLocation", "123 Browser Lane, Springfield")
    citizen.fill("#incidentDate", "2026-09-05")
    citizen.fill("#description", "Created through the live browser flow to prove the deterministic path.")
    citizen.click("#submitCitizenDocket")
    citizen.wait_for_function("() => window.location.pathname.includes('/citizen/dockets/')", timeout=30000)
    case_ref = citizen.url.rstrip('/').split('/')[-1]
    print('CASE_REF', case_ref)
    print('SUBMIT', api(citizen, f"/api/v1/citizen/dockets/{case_ref}/submit"))
    print('ESCALATION', api(citizen, f"/api/v1/citizen/dockets/{case_ref}/escalations", "POST", {"category":"OFFICER_CONDUCT", "reason":"Browser verification escalation"}))

    constable = browser.new_page()
    login(constable, "2200223333114", "constable")
    queue = api(constable, "/api/v1/constable/dockets/unregistered")
    print('QUEUE_HAS_CASE', any(item.get('case_reference') == case_ref for item in queue['data'] if isinstance(item, dict)))
    interview = api(constable, f"/api/v1/constable/dockets/{case_ref}/interview", "POST")
    interview_id = interview['data'].get('interview_id') if isinstance(interview.get('data'), dict) else None
    print('INTERVIEW', interview)
    print('CITIZEN_RECORDING', api(constable, f"/api/v1/citizen/interviews/{interview_id}/recording", "POST", {"filename":"citizen.wav", "storage_reference":"citizen.wav"}))
    print('CONSTABLE_RECORDING', api(constable, f"/api/v1/constable/interviews/{interview_id}/recording", "POST", {"filename":"constable.wav", "storage_reference":"constable.wav"}))
    print('REGISTER', api(constable, f"/api/v1/constable/interviews/{interview_id}/register", "POST"))

    detective = browser.new_page()
    login(detective, "2200223333115", "detective")
    investigation = api(detective, f"/api/v1/detective/dockets/{case_ref}/investigation", "POST", {"notes":"Browser verification investigation"})
    investigation_id = investigation['data'].get('investigation_id') if isinstance(investigation.get('data'), dict) else None
    print('INVESTIGATION', investigation)
    print('FINDING', api(detective, f"/api/v1/detective/investigations/{investigation_id}/findings", "POST", {"finding_text":"Browser verification finding", "severity":"MEDIUM"}))
    print('COMPLETE', api(detective, f"/api/v1/detective/investigations/{investigation_id}/complete", "POST", {"outcome":"CLOSED"}))

    station = browser.new_page()
    login(station, "2200223333116", "station-commander")
    print('REASSIGN', api(station, f"/api/v1/station-commander/dockets/{case_ref}/reassign", "POST", {"officer_id":"2200223333115", "reason":"Browser validation"}))

    ipid = browser.new_page()
    login(ipid, "2200223333117", "ipid")
    print('IPID_LIST', api(ipid, "/api/v1/ipid/escalations"))
    browser.close()
