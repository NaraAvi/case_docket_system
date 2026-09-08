import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/auth.js', () => ({
  getToken: vi.fn().mockReturnValue(null),
  getUser: vi.fn(),
}));

import { getIpidEscalationId, hydrateIpidDashboard, hydrateIpidDetail, init } from '../modules/ipid.js';

function setLocation(pathname) {
  delete window.location;
  window.location = { pathname, href: '' };
}

describe('modules/ipid.js (integration)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.body.dataset.role = 'ipid';
  });

  it('getIpidEscalationId extracts the id from the review URL', () => {
    setLocation('/ipid/escalations/ESC-1');
    expect(getIpidEscalationId()).toBe('ESC-1');
  });

  it('hydrateIpidDashboard renders the escalation queue with a working Review button', async () => {
    document.body.innerHTML = '<div id="ipidQueueList"></div>';
    setLocation('/ipid');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([{ escalation_id: 'ESC-1', case_reference: 'CD-1', status: 'RECEIVED' }]),
      })
    );

    await hydrateIpidDashboard();

    const container = document.getElementById('ipidQueueList');
    expect(container.textContent).toContain('ESC-1');
    container.querySelector('[data-case-link]').click();
    expect(window.location.href).toBe('/ipid/escalations/ESC-1');
  });

  it('hydrateIpidDetail renders escalation meta, review notes, and audit summary', async () => {
    document.body.innerHTML = `
      <dl id="ipidEscalationMeta"></dl>
      <ul id="ipidReviewNotes"></ul>
      <ul id="ipidAuditList"></ul>
    `;
    setLocation('/ipid/escalations/ESC-1');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            case_reference: 'CD-1',
            category: 'IPID.SEC28.CORRUPTION',
            status: 'UNDER_REVIEW',
            assigned_officer_id: 'OFF-2',
            review_notes: [{ author_role: 'ipid', note_text: 'Independent finding recorded.' }],
            audit_summary: [{ action: 'Escalation received', timestamp: '2026-01-01T00:00:00Z' }],
          }),
      })
    );

    await hydrateIpidDetail();

    expect(document.getElementById('ipidEscalationMeta').textContent).toContain('IPID.SEC28.CORRUPTION');
    expect(document.getElementById('ipidReviewNotes').textContent).toContain('Independent finding recorded.');
    expect(document.getElementById('ipidAuditList').textContent).toContain('Escalation received');
  });

  it('init skips hydration entirely on a non-IPID page', () => {
    document.body.innerHTML = '<div id="ipidQueueList"></div>';
    document.body.dataset.role = 'citizen';
    setLocation('/citizen');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    init();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
