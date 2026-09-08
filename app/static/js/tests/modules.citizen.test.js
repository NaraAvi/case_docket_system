import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/auth.js', () => ({
  getToken: vi.fn().mockReturnValue(null),
  getUser: vi.fn(),
}));

import {
  bindCitizenNavigationShortcuts,
  getCitizenCaseReference,
  hydrateCitizenDashboard,
  hydrateCitizenDetail,
  hydrateCitizenForm,
  init,
} from '../modules/citizen.js';

function setLocation(pathname) {
  delete window.location;
  window.location = { pathname, href: '' };
}

describe('modules/citizen.js (integration: module + core/api + core/ui + DOM)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.body.dataset.role = 'citizen';
  });

  describe('getCitizenCaseReference', () => {
    it('extracts the case reference from a detail URL', () => {
      setLocation('/citizen/dockets/CD-2026-000123');
      expect(getCitizenCaseReference()).toBe('CD-2026-000123');
    });

    it('returns null on the "new docket" route', () => {
      setLocation('/citizen/dockets/new');
      expect(getCitizenCaseReference()).toBeNull();
    });

    it('returns null on the dashboard route', () => {
      setLocation('/citizen');
      expect(getCitizenCaseReference()).toBeNull();
    });
  });

  describe('hydrateCitizenDashboard', () => {
    it('renders docket cards and wires the Open button to navigate', async () => {
      document.body.innerHTML = '<div id="citizenDockets"></div>';
      setLocation('/citizen');
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: () => Promise.resolve([{ case_reference: 'CD-1', title: 'Broken window', status: 'REGISTERED' }]),
        })
      );

      await hydrateCitizenDashboard();

      const container = document.getElementById('citizenDockets');
      expect(container.textContent).toContain('CD-1');
      expect(container.querySelector('.badge-verified')).not.toBeNull();

      container.querySelector('[data-case-link]').click();
      expect(window.location.href).toBe('/citizen/dockets/CD-1');
    });

    it('shows an empty state when there are no dockets', async () => {
      document.body.innerHTML = '<div id="citizenDockets"></div>';
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) }));

      await hydrateCitizenDashboard();

      expect(document.getElementById('citizenDockets').textContent).toContain('Submit your first report');
    });

    it('shows an error message when the API call fails', async () => {
      document.body.innerHTML = '<div id="citizenDockets"></div>';
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({ ok: false, status: 500, json: () => Promise.resolve({ error: 'Server exploded.' }) })
      );

      await hydrateCitizenDashboard();

      expect(document.getElementById('citizenDockets').textContent).toContain('Server exploded.');
    });
  });

  describe('hydrateCitizenDetail', () => {
    it('renders docket metadata and timeline events', async () => {
      document.body.innerHTML = `
        <dl id="citizenCaseMeta"></dl>
        <ul id="citizenCaseTimeline"></ul>
      `;
      setLocation('/citizen/dockets/CD-1');
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: () =>
            Promise.resolve({
              status: 'REGISTERED',
              location: 'Main St',
              incident_date: '2026-01-01',
              title: 'Broken window',
              timeline: [{ event_type: 'docket_registered', timestamp: '2026-01-02T00:00:00Z', details: { status: 'REGISTERED' } }],
            }),
        })
      );

      await hydrateCitizenDetail();

      expect(document.getElementById('citizenCaseMeta').textContent).toContain('Broken window');
      expect(document.getElementById('citizenCaseTimeline').textContent).toContain('docket_registered');
    });
  });

  describe('hydrateCitizenForm', () => {
    it('submits the form fields and redirects to the new docket detail page', async () => {
      document.body.innerHTML = `
        <input id="crimeType" value="Theft" />
        <textarea id="description">A long enough description of the incident.</textarea>
        <input id="incidentDate" value="2026-01-01" />
        <input id="incidentLocation" value="Main St" />
        <button id="submitCitizenDocket"></button>
      `;
      setLocation('/citizen/dockets/new');
      const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ case_reference: 'CD-NEW-1' }) });
      vi.stubGlobal('fetch', fetchMock);

      hydrateCitizenForm();
      document.getElementById('submitCitizenDocket').click();

      await vi.waitFor(() => expect(window.location.href).toBe('/citizen/dockets/CD-NEW-1'));

      const [, options] = fetchMock.mock.calls[0];
      expect(JSON.parse(options.body)).toEqual({
        title: 'Theft',
        description: 'A long enough description of the incident.',
        incident_date: '2026-01-01',
        location: 'Main St',
      });
    });

    it('surfaces a validation error from the API without redirecting', async () => {
      document.body.innerHTML = `
        <input id="crimeType" value="" />
        <textarea id="description"></textarea>
        <input id="incidentDate" value="" />
        <input id="incidentLocation" value="" />
        <button id="submitCitizenDocket"></button>
        <div id="formError" class="hidden"></div>
      `;
      setLocation('/citizen/dockets/new');
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({ ok: false, status: 400, json: () => Promise.resolve({ error: 'Description is required.' }) })
      );

      hydrateCitizenForm();
      document.getElementById('submitCitizenDocket').click();

      await vi.waitFor(() => expect(document.getElementById('formError').classList.contains('hidden')).toBe(false));
      expect(document.getElementById('formError').textContent).toBe('Description is required.');
      expect(window.location.href).toBe('');
    });
  });

  describe('bindCitizenNavigationShortcuts', () => {
    it('wires the new-docket and back-to-dashboard buttons', () => {
      document.body.innerHTML = `
        <button id="newCitizenDocketBtn"></button>
        <button id="backToCitizenDashboard"></button>
      `;
      setLocation('/citizen');

      bindCitizenNavigationShortcuts();

      document.getElementById('newCitizenDocketBtn').click();
      expect(window.location.href).toBe('/citizen/dockets/new');

      setLocation('/citizen/dockets/new');
      bindCitizenNavigationShortcuts();
      document.getElementById('backToCitizenDashboard').click();
      expect(window.location.href).toBe('/citizen');
    });
  });

  describe('init (system-ish: full page wiring for each citizen page shape)', () => {
    it('does nothing when the page role is not citizen', () => {
      document.body.dataset.role = 'constable';
      document.body.innerHTML = '<div id="citizenDockets"></div>';
      const fetchMock = vi.fn();
      vi.stubGlobal('fetch', fetchMock);

      init();

      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('hydrates the dashboard when citizenDockets is present on a citizen page', () => {
      document.body.innerHTML = '<div id="citizenDockets"></div>';
      setLocation('/citizen');
      const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
      vi.stubGlobal('fetch', fetchMock);

      init();

      expect(fetchMock).toHaveBeenCalledWith('/api/v1/citizen/dockets', expect.any(Object));
    });
  });
});
