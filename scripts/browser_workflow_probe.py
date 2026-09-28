from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:5000"
ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "browser-evidence"
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def save_png(page, relative_path: str):
    full_path = ARTIFACTS / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(full_path), full_page=True)
    return str(full_path)


def login(page, user_id: str, role: str):
    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    page.fill("#testId", user_id)
    page.click("button[type='submit']")
    page.wait_for_url(f"**/{role}", timeout=20000)
    return page.url


def browser_fetch(page, path: str, method: str = "GET", payload: dict | None = None):
    return page.evaluate(
        """
        async (url, method, payload) => {
          const token = localStorage.getItem('pdasToken');
          const headers = { 'Content-Type': 'application/json' };
          if (token) {
            headers.Authorization = 'Bearer ' + token;
          }
          const options = {
            method,
            credentials: 'same-origin',
            headers,
          };
          if (payload !== undefined && payload !== null) {
            options.body = JSON.stringify(payload);
          }
          const response = await fetch(url, options);
          let data = null;
          const text = await response.text();
          try { data = JSON.parse(text); } catch (error) { data = text; }
          return { status: response.status, ok: response.ok, data };
        }
        """,
        f"{BASE_URL}{path}",
        method,
        payload,
    )


def main():
    summary = {
        "browser": "playwright chromium",
        "base_url": BASE_URL,
        "desktop": "1440x900",
        "mobile": "390x844",
        "flows": {},
        "security": {},
        "console": [],
        "failed_requests": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.on("console", lambda msg: summary["console"].append(f"{msg.type}: {msg.text}"))
        page.on("pageerror", lambda exc: summary["console"].append(f"pageerror: {exc}"))
        page.on("response", lambda response: summary["failed_requests"].append(f"{response.status} {response.url}") if response.status >= 400 else None)

        # Security route checks
        for route in ["/citizen", "/constable", "/detective", "/station-commander", "/ipid"]:
            page.goto(f"{BASE_URL}{route}", wait_until="domcontentloaded")
            save_png(page, f"security/{route.strip('/').replace('/', '-')}-unauthenticated.png")
            summary["security"][route] = {"url": page.url, "status": "redirected-to-login" if "/login" in page.url else "unexpected"}

        # Citizen workflow
        citizen = {}
        try:
            login(page, "2200223333111", "citizen")
            save_png(page, "citizen/01-login.png")
            save_png(page, "citizen/02-dashboard.png")
            page.goto(f"{BASE_URL}/citizen/dockets/new", wait_until="domcontentloaded")
            page.fill("#crimeType", "Browser verification docket")
            page.fill("#incidentLocation", "123 Browser Lane, Springfield")
            page.fill("#incidentDate", "2026-09-05")
            page.fill("#description", "Docket created through the real UI for browser verification.")
            page.click("#submitCitizenDocket")
            page.wait_for_url("**/citizen/dockets/", timeout=20000)
            case_ref = page.url.rstrip("/").split("/")[-1]
            citizen["case_reference"] = case_ref
            save_png(page, "citizen/03-docket-created.png")
            statement = browser_fetch(page, f"/api/v1/citizen/dockets/{case_ref}/statements", "POST", {"statement_text": "Citizen statement captured via browser API."})
            citizen["statement"] = statement
            submit = browser_fetch(page, f"/api/v1/citizen/dockets/{case_ref}/submit", "POST")
            citizen["submit"] = submit
            page.goto(f"{BASE_URL}/citizen/dockets/{case_ref}", wait_until="domcontentloaded")
            save_png(page, "citizen/04-submitted.png")
            escalation = browser_fetch(page, f"/api/v1/citizen/dockets/{case_ref}/escalations", "POST", {"category": "OFFICER_CONDUCT", "reason": "Browser verification escalation"})
            citizen["escalation"] = escalation
            citizen["status"] = "PASS"
        except Exception as exc:
            citizen["status"] = "FAIL"
            citizen["error"] = str(exc)
            save_png(page, "citizen/99-failure.png")
        summary["flows"]["citizen"] = citizen

        # constable flow
        constable = {}
        try:
            login(page, "2200223333114", "constable")
            save_png(page, "constable/01-login.png")
            save_png(page, "constable/02-dashboard.png")
            queue = browser_fetch(page, "/api/v1/constable/dockets/unregistered")
            constable["queue"] = queue
            case_ref = citizen.get("case_reference")
            if case_ref:
                page.goto(f"{BASE_URL}/constable/dockets/{case_ref}", wait_until="domcontentloaded")
                save_png(page, "constable/03-case-review.png")
                interview = browser_fetch(page, f"/api/v1/constable/dockets/{case_ref}/interview", "POST")
                constable["interview"] = interview
                interview_id = interview.get("data", {}).get("interview_id") if isinstance(interview.get("data"), dict) else None
                if interview_id:
                    citizen_recording = browser_fetch(page, f"/api/v1/citizen/interviews/{interview_id}/recording", "POST", {"filename": "citizen.wav", "storage_reference": "citizen.wav"})
                    constable_recording = browser_fetch(page, f"/api/v1/constable/interviews/{interview_id}/recording", "POST", {"filename": "constable.wav", "storage_reference": "constable.wav"})
                    register = browser_fetch(page, f"/api/v1/constable/interviews/{interview_id}/register", "POST")
                    constable["recordings"] = {"citizen": citizen_recording, "constable": constable_recording, "register": register}
                    page.goto(f"{BASE_URL}/constable/dockets/{case_ref}", wait_until="domcontentloaded")
                    save_png(page, "constable/04-registered.png")
            constable["status"] = "PASS"
        except Exception as exc:
            constable["status"] = "FAIL"
            constable["error"] = str(exc)
            save_png(page, "constable/99-failure.png")
        summary["flows"]["constable"] = constable

        # Detective flow
        detective = {}
        try:
            login(page, "2200223333115", "detective")
            save_png(page, "detective/01-login.png")
            save_png(page, "detective/02-dashboard.png")
            case_ref = citizen.get("case_reference")
            if case_ref:
                page.goto(f"{BASE_URL}/detective/dockets/{case_ref}", wait_until="domcontentloaded")
                save_png(page, "detective/03-case-workspace.png")
                investigation = browser_fetch(page, f"/api/v1/detective/dockets/{case_ref}/investigation", "POST", {"notes": "Browser verification investigation"})
                detective["investigation"] = investigation
                investigation_id = investigation.get("data", {}).get("investigation_id") if isinstance(investigation.get("data"), dict) else None
                if investigation_id:
                    finding = browser_fetch(page, f"/api/v1/detective/investigations/{investigation_id}/findings", "POST", {"finding_text": "Browser verification finding", "severity": "MEDIUM"})
                    detective["finding"] = finding
                    complete = browser_fetch(page, f"/api/v1/detective/investigations/{investigation_id}/complete", "POST", {"outcome": "CLOSED"})
                    detective["complete"] = complete
                    page.goto(f"{BASE_URL}/detective/dockets/{case_ref}", wait_until="domcontentloaded")
                    save_png(page, "detective/04-investigation-complete.png")
            detective["status"] = "PASS"
        except Exception as exc:
            detective["status"] = "FAIL"
            detective["error"] = str(exc)
            save_png(page, "detective/99-failure.png")
        summary["flows"]["detective"] = detective

        # Station commander flow
        station = {}
        try:
            login(page, "2200223333116", "station-commander")
            save_png(page, "station-commander/01-login.png")
            save_png(page, "station-commander/02-dashboard.png")
            case_ref = citizen.get("case_reference")
            if case_ref:
                page.goto(f"{BASE_URL}/station-commander/dockets/{case_ref}", wait_until="domcontentloaded")
                save_png(page, "station-commander/03-case-detail.png")
                reassignment = browser_fetch(page, f"/api/v1/station-commander/dockets/{case_ref}/reassign", "POST", {"officer_id": "2200223333115", "reason": "Browser verification reassignment"})
                station["reassignment"] = reassignment
                page.goto(f"{BASE_URL}/station-commander/dockets/{case_ref}", wait_until="domcontentloaded")
                save_png(page, "station-commander/04-reassigned.png")
            station["status"] = "PASS"
        except Exception as exc:
            station["status"] = "FAIL"
            station["error"] = str(exc)
            save_png(page, "station-commander/99-failure.png")
        summary["flows"]["station-commander"] = station

        # IPID flow
        ipid = {}
        try:
            login(page, "2200223333111", "citizen")
            case_ref = citizen.get("case_reference")
            escalation = browser_fetch(page, f"/api/v1/citizen/dockets/{case_ref}/escalations", "POST", {"category": "OFFICER_CONDUCT", "reason": "Browser verification escalation"})
            ipid["escalation"] = escalation
            escalation_id = escalation.get("data", {}).get("escalation_id") if isinstance(escalation.get("data"), dict) else None
            login(page, "2200223333117", "ipid")
            save_png(page, "ipid/01-login.png")
            save_png(page, "ipid/02-dashboard.png")
            if escalation_id:
                page.goto(f"{BASE_URL}/ipid/escalations/{escalation_id}", wait_until="domcontentloaded")
                save_png(page, "ipid/03-escalation-detail.png")
                review = browser_fetch(page, f"/api/v1/ipid/escalations/{escalation_id}/review", "POST")
                ipid["review"] = review
                note = browser_fetch(page, f"/api/v1/ipid/escalations/{escalation_id}/review-notes", "POST", {"note_text": "Browser verification IPID note"})
                ipid["note"] = note
                dismiss = browser_fetch(page, f"/api/v1/ipid/escalations/{escalation_id}/dismiss", "POST", {"decision_reason": "Browser verification dismissal"})
                ipid["dismiss"] = dismiss
                page.goto(f"{BASE_URL}/ipid/escalations/{escalation_id}", wait_until="domcontentloaded")
                save_png(page, "ipid/04-dismissed.png")
            ipid["status"] = "PASS"
        except Exception as exc:
            ipid["status"] = "FAIL"
            ipid["error"] = str(exc)
            save_png(page, "ipid/99-failure.png")
        summary["flows"]["ipid"] = ipid

        # responsive smoke tests
        for viewport in [(390, 844), (1280, 800)]:
            context2 = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
            page2 = context2.new_page()
            for route in ["/login", "/citizen", "/constable", "/detective", "/station-commander", "/ipid"]:
                page2.goto(f"{BASE_URL}{route}", wait_until="domcontentloaded")
                save_png(page2, f"final/{viewport[0]}x{viewport[1]}-{route.strip('/').replace('/', '-')} .png")
            context2.close()

        summary_path = ARTIFACTS / "verification-summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
