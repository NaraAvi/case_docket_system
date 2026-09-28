from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:5000"
ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "browser_audit_evidence"
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def save_screenshot(page, relative_path: str):
    path = ARTIFACTS / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def login(page, user_id: str, expected_path: str):
    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    page.fill("#testId", str(user_id))
    page.click("button[type='submit']")
    page.wait_for_function(
        "() => { const p = window.location.pathname; return p === '/citizen' || p === '/constable' || p === '/detective' || p === '/station-commander' || p === '/ipid'; }",
        timeout=20000,
    )
    assert page.url.rstrip("/").endswith(expected_path), f"Expected {expected_path} but got {page.url}"
    token = page.evaluate("localStorage.getItem('pdasToken')")
    assert token, "No token after login"
    return page.url


def fetch_json(page, route: str, method: str = "GET", payload=None):
    return page.evaluate(
        """
        async (url, method, payload) => {
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
        f"{BASE_URL}{route}",
        method,
        payload,
    )


def main():
    report = {
        "browser_environment": "Playwright/Chromium headless browser on Windows",
        "base_url": BASE_URL,
        "application_startup": {},
        "role_matrix": {},
        "security": {},
        "citizen": {},
        "constable": {},
        "detective": {},
        "station_commander": {},
        "ipid": {},
        "final_verdict": "YELLOW",
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})

        login_page = context.new_page()
        login_page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
        save_screenshot(login_page, "01_auth/01_login_page.png")
        report["application_startup"] = {
            "login_url": login_page.url,
            "login_input_present": login_page.locator("#testId").count() == 1,
            "status": "UP",
        }

        role_specs = [
            ("2200223333111", "/citizen", "citizen"),
            ("2200223333114", "/constable", "constable"),
            ("2200223333115", "/detective", "detective"),
            ("2200223333116", "/station-commander", "station_commander"),
            ("2200223333117", "/ipid", "ipid"),
        ]

        for user_id, expected_path, role_name in role_specs:
            page = context.new_page()
            url = login(page, user_id, expected_path)
            save_screenshot(page, f"01_auth/02_{role_name}_dashboard.png")
            report["role_matrix"][role_name] = {
                "url": url,
                "token_present": bool(page.evaluate("localStorage.getItem('pdasToken')")),
                "role_heading_in_body": role_name.replace("_", " ").upper() in page.locator("body").inner_text().upper(),
            }
            page.close()

        # No-session security checks
        unauth = browser.new_context(viewport={"width": 1440, "height": 900})
        unauth_page = unauth.new_page()
        for route in ["/citizen", "/constable", "/detective", "/station-commander", "/ipid"]:
            unauth_page.goto(f"{BASE_URL}{route}", wait_until="domcontentloaded")
            save_screenshot(unauth_page, f"07_security/{route.strip('/').replace('/', '_')}_unauth.png")
            report["security"][route] = {"redirected_to_login": "/login" in unauth_page.url, "url": unauth_page.url}
        unauth_page.close(); unauth.close()

        # Citizen flow via the browser UI
        citizen_page = context.new_page()
        login(citizen_page, "2200223333111", "/citizen")
        citizen_page.goto(f"{BASE_URL}/citizen/dockets/new", wait_until="domcontentloaded")
        citizen_page.fill("#crimeType", "Browser verification docket")
        citizen_page.fill("#incidentLocation", "123 Browser Lane, Springfield")
        citizen_page.fill("#incidentDate", "2026-09-05")
        citizen_page.fill("#description", "Created through the browser workflow to verify the real deterministic citizen submission path.")
        save_screenshot(citizen_page, "02_citizen/01_form_ready.png")
        citizen_page.click("#submitCitizenDocket")
        citizen_page.wait_for_function("() => window.location.pathname.includes('/citizen/dockets/')", timeout=20000)
        case_ref = citizen_page.url.rstrip("/").split("/")[-1]
        save_screenshot(citizen_page, "02_citizen/02_case_created.png")
        report["citizen"]["case_reference"] = case_ref
        # Real browser-visible status update through API while authenticated in browser session
        submit_result = fetch_json(citizen_page, f"/api/v1/citizen/dockets/{case_ref}/submit", method="POST")
        escalation_result = fetch_json(
            citizen_page,
            f"/api/v1/citizen/dockets/{case_ref}/escalations",
            method="POST",
            payload={"category": "OFFICER_CONDUCT", "reason": "Citizen escalation created in browser verification"},
        )
        escalation_id = escalation_result.get("data", {}).get("escalation_id") if isinstance(escalation_result.get("data"), dict) else None
        report["citizen"]["submit_result"] = submit_result
        report["citizen"]["escalation_result"] = escalation_result
        report["citizen"]["escalation_id"] = escalation_id
        citizen_page.goto(f"{BASE_URL}/citizen/dockets/{case_ref}", wait_until="domcontentloaded")
        save_screenshot(citizen_page, "02_citizen/03_case_detail.png")
        citizen_page.close()

        # Constable flow
        constable_page = context.new_page()
        login(constable_page, "2200223333114", "/constable")
        queue = fetch_json(constable_page, "/api/v1/constable/dockets/unregistered")
        save_screenshot(constable_page, "03_constable/01_dashboard.png")
        constable_page.goto(f"{BASE_URL}/constable/dockets/{case_ref}", wait_until="domcontentloaded")
        save_screenshot(constable_page, "03_constable/02_review.png")
        interview_result = fetch_json(constable_page, f"/api/v1/constable/dockets/{case_ref}/interview", method="POST")
        interview_id = interview_result.get("data", {}).get("interview_id") if isinstance(interview_result.get("data"), dict) else None
        citizen_recording = fetch_json(
            constable_page,
            f"/api/v1/citizen/interviews/{interview_id}/recording",
            method="POST",
            payload={"filename": "citizen.wav", "storage_reference": "citizen.wav"},
        )
        constable_recording = fetch_json(
            constable_page,
            f"/api/v1/constable/interviews/{interview_id}/recording",
            method="POST",
            payload={"filename": "constable.wav", "storage_reference": "constable.wav"},
        )
        register_result = fetch_json(constable_page, f"/api/v1/constable/interviews/{interview_id}/register", method="POST")
        save_screenshot(constable_page, "03_constable/03_registered.png")
        report["constable"] = {
            "queue_contains_case": any(item.get("case_reference") == case_ref for item in queue.get("data", []) if isinstance(item, dict)),
            "interview_result": interview_result,
            "citizen_recording": citizen_recording,
            "constable_recording": constable_recording,
            "register_result": register_result,
        }
        constable_page.close()

        # Detective flow
        detective_page = context.new_page()
        login(detective_page, "2200223333115", "/detective")
        detective_page.goto(f"{BASE_URL}/detective/dockets/{case_ref}", wait_until="domcontentloaded")
        save_screenshot(detective_page, "04_detective/01_case_workspace.png")
        investigation = fetch_json(detective_page, f"/api/v1/detective/dockets/{case_ref}/investigation", method="POST", payload={"notes": "Browser verification investigation"})
        investigation_id = investigation.get("data", {}).get("investigation_id") if isinstance(investigation.get("data"), dict) else None
        finding = fetch_json(
            detective_page,
            f"/api/v1/detective/investigations/{investigation_id}/findings",
            method="POST",
            payload={"finding_text": "Browser verification finding", "severity": "MEDIUM"},
        )
        complete = fetch_json(
            detective_page,
            f"/api/v1/detective/investigations/{investigation_id}/complete",
            method="POST",
            payload={"outcome": "CLOSED"},
        )
        save_screenshot(detective_page, "04_detective/02_complete.png")
        report["detective"] = {"investigation": investigation, "finding": finding, "complete": complete}
        detective_page.close()

        # Station commander flow
        station_page = context.new_page()
        login(station_page, "2200223333116", "/station-commander")
        station_page.goto(f"{BASE_URL}/station-commander/dockets/{case_ref}", wait_until="domcontentloaded")
        save_screenshot(station_page, "05_station_commander/01_detail.png")
        reassignment = fetch_json(
            station_page,
            f"/api/v1/station-commander/dockets/{case_ref}/reassign",
            method="POST",
            payload={"officer_id": "2200223333115", "reason": "Browser verification reassignment"},
        )
        save_screenshot(station_page, "05_station_commander/02_reassigned.png")
        report["station_commander"] = {"reassignment": reassignment}
        station_page.close()

        # IPID flow
        ipid_page = context.new_page()
        login(ipid_page, "2200223333117", "/ipid")
        ipid_page.goto(f"{BASE_URL}/ipid/escalations/{escalation_id}", wait_until="domcontentloaded")
        save_screenshot(ipid_page, "06_ipid/01_escalation.png")
        review = fetch_json(ipid_page, f"/api/v1/ipid/escalations/{escalation_id}/review", method="POST")
        note = fetch_json(ipid_page, f"/api/v1/ipid/escalations/{escalation_id}/review-notes", method="POST", payload={"note_text": "Browser verification note"})
        dismiss = fetch_json(ipid_page, f"/api/v1/ipid/escalations/{escalation_id}/dismiss", method="POST", payload={"decision_reason": "Browser verification dismissal"})
        save_screenshot(ipid_page, "06_ipid/02_dismissed.png")
        report["ipid"] = {"review": review, "note": note, "dismiss": dismiss, "escalation_id": escalation_id}
        ipid_page.close()

        report_path = ARTIFACTS / "final_browser_certification.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))

        browser.close()


if __name__ == "__main__":
    main()
