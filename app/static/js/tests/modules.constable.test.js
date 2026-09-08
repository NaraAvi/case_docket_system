import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/auth.js', () => ({
  getToken: vi.fn().mockReturnValue(null),
  getUser: vi.fn(),
}));

import { getConstableCaseReference, hydrateConstableDashboard, hydrateConstableReview, init } from '../modules/constable.js';

function setLocation(pathname) {
  delete window.location;
  window.location = { pathname, href: '' };
}

describe('modules/constable.js (integration)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.body.dataset.role = 'constable';
  });

  it('getConstableCaseReference extracts the reference from the review URL', () => {
    setLocation('/constable/dockets/CD-1');
    expect(getConstableCaseReference()).toBe('CD-1');
  });

  it('hydrateConstableDashboard renders the unregistered queue with a working Review button', async () => {
    document.body.innerHTML = '<div id="constableQueueState"></div>';
    setLocation('/constable');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([{ case_reference: 'CD-9', location: 'Main St', status: 'AWAITING_CONSTABLE_REGISTRATION' }]),
      })
    );

    await hydrateConstableDashboard();

    const container = document.getElementById('constableQueueState');
    expect(container.textContent).toContain('CD-9');
    container.querySelector('[data-case-link]').click();
    expect(window.location.href).toBe('/constable/dockets/CD-9');
  });

  it('hydrateConstableDashboard shows an empty state with no queue items', async () => {
    document.body.innerHTML = '<div id="constableQueueState"></div>';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) }));

    await hydrateConstableDashboard();

    expect(document.getElementById('constableQueueState').textContent).toContain('No unregistered dockets');
  });

  it('hydrateConstableReview renders meta/timeline/evidence and wires Continue to Interview', async () => {
    document.body.innerHTML = `
      <dl id="constableCaseMeta"></dl>
      <ul id="constableCaseTimeline"></ul>
      <ul id="constableCaseEvidence"></ul>
      <button id="continueToInterview"></button>
    `;
    setLocation('/constable/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/interview')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ interview_id: 'INT-1' }) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            title: 'Vandalism',
            location: 'Main St',
            status: 'AWAITING_CONSTABLE_REGISTRATION',
            timeline: [],
            evidence: [{ evidence_type: 'photo', description: 'Broken window photo' }],
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateConstableReview();

    expect(document.getElementById('constableCaseMeta').textContent).toContain('Vandalism');
    expect(document.getElementById('constableCaseEvidence').textContent).toContain('Broken window photo');

    document.getElementById('continueToInterview').click();
    await vi.waitFor(() => expect(window.location.href).toBe('/constable/dockets/CD-1'));
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/constable/dockets/CD-1/interview', expect.objectContaining({ method: 'POST' }));
  });

  it('init only hydrates the dashboard when both the role and container match', () => {
    document.body.innerHTML = '<div id="constableQueueState"></div>';
    document.body.dataset.role = 'detective';
    setLocation('/some-other-page');
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
    vi.stubGlobal('fetch', fetchMock);

    init();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
