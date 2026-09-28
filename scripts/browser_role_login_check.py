from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:5000"
ROLES = [
    ("citizen", "2200223333111", "/citizen"),
    ("constable", "2200223333114", "/constable"),
    ("detective", "2200223333115", "/detective"),
    ("station_commander", "2200223333116", "/station-commander"),
    ("ipid", "2200223333117", "/ipid"),
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for role, user_id, expected_path in ROLES:
        page = browser.new_page()
        page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
        page.fill("#testId", user_id)
        page.click('button[type="submit"]')
        page.wait_for_url(f"**{expected_path}", timeout=30000)
        token = page.evaluate("localStorage.getItem('pdasToken')")
        print(role, "OK", page.url, "token_present=", bool(token))
        page.close()
    browser.close()
