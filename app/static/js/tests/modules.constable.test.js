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

  it('hydrateConstableReview renders meta/statement/evidence/flags/related and wires Continue to Interview', async () => {
    document.body.innerHTML = `
      <dl id="constableCaseMeta"></dl>
      <span id="constableStatusBadge"></span>
      <div id="constableStatementBox"></div>
      <ul id="constableCaseEvidence"></ul>
      <div id="constableFlagList"></div>
      <div id="constableRelatedCases"></div>
      <button id="continueToInterview"></button>
      <button id="openFlagModal"></button>
      <div id="flagModal" class="hidden">
        <span id="flagModalTitle"></span>
        <select id="flagCategory"></select>
        <select id="flagStatus"></select>
        <textarea id="flagNotes"></textarea>
        <p id="flagModalError" class="hidden"></p>
        <button id="closeFlagModal"></button>
        <button id="submitFlagModal"></button>
      </div>
    `;
    setLocation('/constable/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/interview')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ interview_id: 'INT-1' }) });
      }
      if (url.endsWith('/flags')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ flag_id: 'FLG-1', category: 'INSUFFICIENT_INFORMATION', status: 'OPEN', notes: 'Missing detail.' }]),
        });
      }
      if (url.endsWith('/related')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            title: 'Vandalism',
            location: 'Main St',
            status: 'AWAITING_CONSTABLE_REGISTRATION',
            timeline: [],
            statements: [{ statement_text: 'Someone broke my window.' }],
            evidence: [{ evidence_type: 'photo', description: 'Broken window photo' }],
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateConstableReview();

    expect(document.getElementById('constableCaseMeta').textContent).toContain('Vandalism');
    expect(document.getElementById('constableCaseEvidence').textContent).toContain('Broken window photo');
    expect(document.getElementById('constableStatementBox').textContent).toContain('Someone broke my window.');
    expect(document.getElementById('constableFlagList').textContent).toContain('Missing detail.');
    expect(document.getElementById('constableRelatedCases').textContent).toContain('No direct related case links');

    document.getElementById('continueToInterview').click();
    await vi.waitFor(() => expect(window.location.href).toBe('/constable/dockets/CD-1'));
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/constable/dockets/CD-1/interview', expect.objectContaining({ method: 'POST' }));
  });

  it('the flag modal creates a new flag and refreshes the list', async () => {
    document.body.innerHTML = `
      <dl id="constableCaseMeta"></dl>
      <span id="constableStatusBadge"></span>
      <div id="constableStatementBox"></div>
      <ul id="constableCaseEvidence"></ul>
      <div id="constableFlagList"></div>
      <div id="constableRelatedCases"></div>
      <button id="continueToInterview"></button>
      <button id="openFlagModal"></button>
      <div id="flagModal" class="hidden">
        <span id="flagModalTitle"></span>
        <select id="flagCategory"><option value="OTHER">Other</option></select>
        <select id="flagStatus"><option value="OPEN">Open</option></select>
        <textarea id="flagNotes"></textarea>
        <p id="flagModalError" class="hidden"></p>
        <button id="closeFlagModal"></button>
        <button id="submitFlagModal"></button>
      </div>
    `;
    setLocation('/constable/dockets/CD-1');
    let flagCreated = false;
    const fetchMock = vi.fn((url, options = {}) => {
      if (url.endsWith('/flags') && options.method === 'POST') {
        flagCreated = true;
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ flag_id: 'FLG-1' }) });
      }
      if (url.endsWith('/flags')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(flagCreated ? [{ flag_id: 'FLG-1', category: 'OTHER', status: 'OPEN', notes: 'New concern.' }] : []),
        });
      }
      if (url.endsWith('/related')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ title: 'Vandalism', status: 'AWAITING_CONSTABLE_REGISTRATION', statements: [], evidence: [], timeline: [] }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateConstableReview();
    expect(document.getElementById('constableFlagList').textContent).toContain('No potential invalidity flags');

    document.getElementById('openFlagModal').click();
    expect(document.getElementById('flagModal').classList.contains('hidden')).toBe(false);

    document.getElementById('flagNotes').value = 'New concern.';
    document.getElementById('submitFlagModal').click();

    await vi.waitFor(() => expect(document.getElementById('constableFlagList').textContent).toContain('New concern.'));
    expect(document.getElementById('flagModal').classList.contains('hidden')).toBe(true);
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
