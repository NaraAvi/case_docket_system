/**
 * System-level test: exercises the real entrypoint wiring every real module
 * together (auth, api, ui, and each role module) against a simulated full
 * page, with only the network boundary (fetch) mocked. Nothing here is
 * mocked at the module level -- this is the closest we get to "load the
 * actual page in a browser" without a browser.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

function setLocation(pathname) {
  delete window.location;
  window.location = { pathname, href: '' };
}

function clearBrowserState() {
  localStorage.clear();
  ['pdas_session_token', 'pdas_user'].forEach((name) => {
    document.cookie = `${name}=; path=/; max-age=0`;
  });
}

let init;

beforeAll(async () => {
  window.__PDAS_SKIP_AUTO_INIT__ = true;
  ({ init } = await import('../pdas_app.js'));
});

describe('pdas_app.js entrypoint (system)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    clearBrowserState();
  });

  afterEach(() => {
    clearBrowserState();
  });

  it('renders the full citizen dashboard page: user badge, docket list, and reauth modal chrome', async () => {
    document.body.dataset.role = 'citizen';
    document.body.innerHTML = `
      <div class="user-badge" id="userBadge">Authenticated User</div>
      <div id="citizenDockets"></div>
      <div id="reauthModal" class="hidden"><button data-close-reauth>Cancel</button></div>
      <button data-open-reauth>Flag</button>
    `;
    setLocation('/citizen');

    localStorage.setItem('pdasToken', 'tok-citizen');
    localStorage.setItem('pdasUser', JSON.stringify({ full_name: 'Jane Citizen', role: 'citizen' }));

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([{ case_reference: 'CD-1', title: 'Broken window', status: 'REGISTERED' }]),
    });
    vi.stubGlobal('fetch', fetchMock);

    await init();

    // Authenticated fetch actually carried the Bearer token end-to-end.
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/citizen/dockets',
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer tok-citizen' }) })
    );
    // Role module hydrated the dashboard.
    expect(document.getElementById('citizenDockets').textContent).toContain('CD-1');
    // Shared user badge chrome updated.
    expect(document.getElementById('userBadge').textContent).toBe('Jane Citizen • citizen');
    // Reauth modal wiring is live.
    document.querySelector('[data-open-reauth]').click();
    expect(document.getElementById('reauthModal').classList.contains('hidden')).toBe(false);

    vi.unstubAllGlobals();
  });

  it('drives the login -> session -> redirect flow end to end through the real auth+api modules', async () => {
    document.body.dataset.role = '';
    document.body.innerHTML = `
      <form id="loginForm"><input id="testId" value="2200223333116" /></form>
      <div id="loginError" class="hidden"></div>
    `;
    setLocation('/login');

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            access_token: 'tok-sc',
            full_name: 'Station Commander One',
            role: 'station_commander',
            test_id: '2200223333116',
          }),
      })
    );

    await init();
    document.getElementById('loginForm').dispatchEvent(new window.Event('submit', { cancelable: true }));

    await vi.waitFor(() => expect(window.location.href).toBe('/station-commander'));
    expect(localStorage.getItem('pdasToken')).toBe('tok-sc');

    vi.unstubAllGlobals();
  });

  it('loads only the shared module (no role module) for an unauthenticated/roleless page', async () => {
    document.body.dataset.role = '';
    document.body.innerHTML = '<div id="activeCaseList"></div>';
    setLocation('/active-cases');

    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
    vi.stubGlobal('fetch', fetchMock);

    await init();

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/station-commander/dockets', expect.any(Object));

    vi.unstubAllGlobals();
  });
});
