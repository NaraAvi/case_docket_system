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

  it('hydrateStationCommanderDetail renders assignment/freeze/SLA metadata and audit timeline', async () => {
    document.body.innerHTML = `
      <dl id="stationCommanderCaseMeta"></dl>
      <ul id="stationCommanderAuditList"></ul>
    `;
    setLocation('/station-commander/dockets/CD-5');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            assigned_officer_id: 'OFF-1',
            status: 'SLA_BREACHED',
            freeze_status: 'FROZEN',
            sla_status: 'Breached at 74h',
            audit: [{ action: 'Reassigned', timestamp: '2026-01-01T00:00:00Z' }],
          }),
      })
    );

    await hydrateStationCommanderDetail();

    expect(document.getElementById('stationCommanderCaseMeta').textContent).toContain('OFF-1');
    expect(document.getElementById('stationCommanderCaseMeta').textContent).toContain('FROZEN');
    expect(document.getElementById('stationCommanderAuditList').textContent).toContain('Reassigned');
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
