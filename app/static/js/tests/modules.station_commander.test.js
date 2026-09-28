import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/auth.js', () => ({
  getToken: vi.fn().mockReturnValue(null),
  getUser: vi.fn(),
}));

import {
  getStationCommanderCaseReference,
  hydrateStationCommanderDashboard,
  hydrateStationCommanderDetail,
  init,
} from '../modules/station_commander.js';

function setLocation(pathname) {
  delete window.location;
  window.location = { pathname, href: '' };
}

describe('modules/station_commander.js (integration)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.body.dataset.role = 'station_commander';
  });

  it('getStationCommanderCaseReference extracts the reference', () => {
    setLocation('/station-commander/dockets/CD-5');
    expect(getStationCommanderCaseReference()).toBe('CD-5');
  });

  it('hydrateStationCommanderDashboard renders every docket with a status badge', async () => {
    document.body.innerHTML = '<div id="stationCommanderCaseList"></div>';
    setLocation('/station-commander');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([{ case_reference: 'CD-5', location: 'Main St', status: 'PENDING_REVIEW' }]),
      })
    );

    await hydrateStationCommanderDashboard();

    const container = document.getElementById('stationCommanderCaseList');
    expect(container.textContent).toContain('CD-5');
    expect(container.querySelector('.badge-warning')).not.toBeNull();
  });

  it('hydrateStationCommanderDashboard renders the SLA breach panel with a working link', async () => {
    document.body.innerHTML = '<div id="stationCommanderCaseList"></div><div id="stationCommanderSlaBreachList"></div>';
    setLocation('/station-commander');
    const fetchMock = vi.fn((url) => {
      if (url.includes('/sla/breaches')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ case_reference: 'CD-9', status: 'BREACHED', elapsed_hours: 80, remaining_hours: 0 }]),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateStationCommanderDashboard();

    const container = document.getElementById('stationCommanderSlaBreachList');
    expect(container.textContent).toContain('CD-9');
    expect(container.querySelector('.badge-breach')).not.toBeNull();
    container.querySelector('[data-case-link]').click();
    expect(window.location.href).toBe('/station-commander/dockets/CD-9');
  });

  it('hydrateStationCommanderDashboard keeps completed investigations visible in their own section', async () => {
    document.body.innerHTML = '<div id="stationCommanderCaseList"></div><div id="stationCommanderSlaBreachList"></div>';
    setLocation('/station-commander');
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url.includes('/sla/breaches')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([
            { case_reference: 'CD-7', location: 'Main St', status: 'REGISTERED', investigation_status: 'COMPLETED' },
            { case_reference: 'CD-8', location: 'Park Ave', status: 'AWAITING_CONSTABLE_REGISTRATION', investigation_status: null },
          ]),
        });
      })
    );

    await hydrateStationCommanderDashboard();

    const container = document.getElementById('stationCommanderCaseList');
    expect(container.textContent).toContain('CD-8');
    expect(container.textContent).toContain('CD-7');
    expect(container.textContent).toContain('Completed Cases');
  });

  it('hydrateStationCommanderDashboard shows an empty state when there are no SLA breaches', async () => {
    document.body.innerHTML = '<div id="stationCommanderCaseList"></div><div id="stationCommanderSlaBreachList"></div>';
    setLocation('/station-commander');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) }));

    await hydrateStationCommanderDashboard();

    expect(document.getElementById('stationCommanderSlaBreachList').textContent).toContain('No dockets have breached');
  });

  it('hydrateStationCommanderDetail renders assignment/freeze/SLA metadata and audit timeline for an unfrozen docket', async () => {
    document.body.innerHTML = `
      <dl id="stationCommanderCaseMeta"></dl>
      <span id="stationCommanderFreezeBadge"></span>
      <div id="stationCommanderFrozenNotice" class="hidden"><p id="stationCommanderFrozenReason"></p></div>
      <div id="stationCommanderDocketContent">
        <div id="stationCommanderSlaMeter"></div>
        <ul id="stationCommanderAuditList"></ul>
        <div id="stationCommanderInvestigationInfo"></div>
        <p id="reassignmentBlockedNotice"></p>
        <input id="currentOfficerField" />
        <select id="targetOfficerSelect"></select>
        <textarea id="reassignmentReason"></textarea>
        <p id="reassignmentError" class="hidden"></p>
        <button id="confirmReassignment"></button>
      </div>
    `;
    setLocation('/station-commander/dockets/CD-5');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/audit')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ action: 'Reassigned', timestamp: '2026-01-01T00:00:00Z' }]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            assigned_officer_id: 'OFF-1',
            status: 'REGISTERED',
            freeze_status: 'NOT_FROZEN',
            is_frozen: false,
            sla: { sla_due_at: '2026-01-04T00:00:00Z', elapsed_hours: 20, remaining_hours: 52 },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateStationCommanderDetail();

    expect(document.getElementById('stationCommanderCaseMeta').textContent).toContain('OFF-1');
    expect(document.getElementById('stationCommanderAuditList').textContent).toContain('Reassigned');
    expect(document.getElementById('stationCommanderDocketContent').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('stationCommanderFrozenNotice').classList.contains('hidden')).toBe(true);
  });

  it('hydrateStationCommanderDetail shows the "Case Frozen" notice and withholds case content while frozen', async () => {
    document.body.innerHTML = `
      <dl id="stationCommanderCaseMeta"></dl>
      <span id="stationCommanderFreezeBadge"></span>
      <div id="stationCommanderFrozenNotice" class="hidden"><p id="stationCommanderFrozenReason"></p></div>
      <div id="stationCommanderDocketContent">
        <div id="stationCommanderSlaMeter"></div>
        <ul id="stationCommanderAuditList"></ul>
        <div id="stationCommanderInvestigationInfo"></div>
        <p id="reassignmentBlockedNotice"></p>
        <input id="currentOfficerField" />
        <select id="targetOfficerSelect"></select>
        <textarea id="reassignmentReason"></textarea>
        <p id="reassignmentError" class="hidden"></p>
        <button id="confirmReassignment"></button>
      </div>
    `;
    setLocation('/station-commander/dockets/CD-5');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/audit')) {
        throw new Error(`unexpected fetch to ${url} for a frozen docket`);
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            case_reference: 'CD-5',
            status: 'REGISTERED',
            is_frozen: true,
            freeze_status: 'FROZEN',
            freeze_reason: 'IPID uphold decision for escalation ESC-1',
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateStationCommanderDetail();

    expect(document.getElementById('stationCommanderFrozenNotice').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('stationCommanderFrozenReason').textContent).toContain('IPID uphold decision');
    expect(document.getElementById('stationCommanderDocketContent').classList.contains('hidden')).toBe(true);
    expect(document.getElementById('stationCommanderCaseMeta').textContent).toBe('');
    expect(document.getElementById('stationCommanderFreezeBadge').textContent).toContain('Frozen');
  });

  it('surfaces a persisted completed investigation and freezes SLA display on the station-commander detail page', async () => {
    document.body.innerHTML = `
      <dl id="stationCommanderCaseMeta"></dl>
      <span id="stationCommanderFreezeBadge"></span>
      <div id="stationCommanderFrozenNotice" class="hidden"><p id="stationCommanderFrozenReason"></p></div>
      <div id="stationCommanderDocketContent">
        <div id="stationCommanderSlaMeter"></div>
        <ul id="stationCommanderAuditList"></ul>
        <div id="stationCommanderInvestigationInfo"></div>
        <p id="reassignmentBlockedNotice"></p>
        <input id="currentOfficerField" />
        <select id="targetOfficerSelect"></select>
        <textarea id="reassignmentReason"></textarea>
        <p id="reassignmentError" class="hidden"></p>
        <button id="confirmReassignment"></button>
      </div>
    `;
    setLocation('/station-commander/dockets/CD-5');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/audit')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          case_reference: 'CD-5',
          assigned_officer_id: 'OFF-1',
          status: 'REGISTERED',
          is_frozen: false,
          freeze_status: 'NOT_FROZEN',
          sla: {
            sla_due_at: '2026-01-04T00:00:00Z',
            elapsed_hours: 24,
            remaining_hours: 0,
            status: 'COMPLETED_WITHIN_SLA',
            completed_at: '2026-01-02T12:00:00Z',
          },
          investigation: {
            investigation_id: 'INV-1',
            status: 'COMPLETED',
            outcome: 'VALID',
            final_notes: 'Evidence supports the account.',
            completed_at: '2026-01-02T12:00:00Z',
          },
        }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateStationCommanderDetail();

    expect(document.getElementById('stationCommanderCaseMeta').textContent).toContain('COMPLETED');
    expect(document.getElementById('stationCommanderCaseMeta').textContent).toContain('2026-01-02');
    expect(document.getElementById('stationCommanderInvestigationInfo').textContent).toContain('Investigation completed');
    expect(document.getElementById('stationCommanderSlaMeter').textContent).toContain('completed');
  });

  function reassignmentMarkup() {
    return `
      <dl id="stationCommanderCaseMeta"></dl>
      <span id="stationCommanderFreezeBadge"></span>
      <div id="stationCommanderSlaMeter"></div>
      <ul id="stationCommanderAuditList"></ul>
      <div id="stationCommanderInvestigationInfo"></div>
      <p id="reassignmentBlockedNotice"></p>
      <input id="currentOfficerField" />
      <select id="targetOfficerSelect"><option value="">Loading officers…</option></select>
      <textarea id="reassignmentReason"></textarea>
      <p id="reassignmentError" class="hidden"></p>
      <button id="confirmReassignment"></button>
    `;
  }

  it('populates the officer dropdown filtered to constables for a docket awaiting registration, instead of leaving it stuck on "Loading officers…"', async () => {
    document.body.innerHTML = reassignmentMarkup();
    setLocation('/station-commander/dockets/CD-5');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/audit')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (url.includes('/officers')) {
        expect(url).toContain('role=constable');
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ test_id: 'CON-1', full_name: 'Constable One', role: 'constable' }]),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            assigned_officer_id: null,
            status: 'AWAITING_CONSTABLE_REGISTRATION',
            freeze_status: 'NOT_FROZEN',
            is_frozen: false,
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateStationCommanderDetail();

    const select = document.getElementById('targetOfficerSelect');
    await vi.waitFor(() => expect(select.options.length).toBeGreaterThan(1));
    expect(select.disabled).toBe(false);
    expect(document.getElementById('confirmReassignment').disabled).toBeFalsy();
    expect(document.getElementById('reassignmentBlockedNotice').textContent).toContain('not been registered yet');
  });

  it('disables reassignment with an "Unavailable" dropdown for a docket that is neither registered nor awaiting registration', async () => {
    document.body.innerHTML = reassignmentMarkup();
    setLocation('/station-commander/dockets/CD-5');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/audit')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ assigned_officer_id: null, status: 'DRAFT', freeze_status: 'NOT_FROZEN', is_frozen: false }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateStationCommanderDetail();

    const select = document.getElementById('targetOfficerSelect');
    expect(select.disabled).toBe(true);
    expect(select.textContent).toContain('Unavailable');
    expect(select.textContent).not.toContain('Loading officers');
    expect(document.getElementById('confirmReassignment').disabled).toBe(true);
  });

  it('init does not hydrate the dashboard for a different role', () => {
    document.body.innerHTML = '<div id="stationCommanderCaseList"></div>';
    document.body.dataset.role = 'ipid';
    setLocation('/somewhere');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    init();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
