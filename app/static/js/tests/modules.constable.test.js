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

function setFileInputValue(inputId, filename, content = 'file bytes', type = 'audio/wav') {
  const input = document.getElementById(inputId);
  const file = new File([content], filename, { type });
  Object.defineProperty(input, 'files', { value: [file], writable: false, configurable: true });
  input.dispatchEvent(new Event('change', { bubbles: true }));
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

  it('the Search control queries the search endpoint and renders matches, then reverts to the unregistered queue on an empty query', async () => {
    document.body.innerHTML = `
      <input id="constableSearch" type="search" />
      <button id="constableSearchBtn"></button>
      <div id="constableQueueState"></div>
    `;
    setLocation('/constable');
    const fetchMock = vi.fn((url) => {
      if (url.includes('/search')) {
        expect(url).toBe('/api/v1/constable/dockets/search?q=Main%20St');
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ case_reference: 'CD-9', location: 'Main St', status: 'REGISTERED' }]),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateConstableDashboard();
    expect(document.getElementById('constableQueueState').textContent).toContain('No unregistered dockets');

    document.getElementById('constableSearch').value = 'Main St';
    document.getElementById('constableSearchBtn').click();

    await vi.waitFor(() => expect(document.getElementById('constableQueueState').textContent).toContain('CD-9'));

    document.getElementById('constableSearch').value = '';
    document.getElementById('constableSearch').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/v1/constable/dockets/unregistered', expect.any(Object))
    );
  });

  it('hydrateConstableDashboard shows an empty state with no queue items', async () => {
    document.body.innerHTML = '<div id="constableQueueState"></div>';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) }));

    await hydrateConstableDashboard();

    expect(document.getElementById('constableQueueState').textContent).toContain('No unregistered dockets');
  });

  function reviewMarkup() {
    return `
      <dl id="constableCaseMeta"></dl>
      <span id="constableStatusBadge"></span>
      <div id="constableStatementBox"></div>
      <table><tbody id="constableCaseEvidence"></tbody></table>
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
      <div id="constableInterviewPanel" class="hidden">
        <div id="constableInterviewStatus"></div>
        <input type="file" id="constableRecordingFile" />
        <p id="constableRecordingFilePreview" class="hidden"></p>
        <button id="submitConstableRecording"></button>
        <p id="constableRecordingError" class="hidden"></p>
        <button id="registerDocketBtn" disabled></button>
      </div>
      <div class="toast-container" id="toastContainer"></div>
    `;
  }

  it('hydrateConstableReview renders meta/statement/evidence/flags/related, and Continue to Interview reveals the interview panel in place', async () => {
    document.body.innerHTML = reviewMarkup();
    setLocation('/constable/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/interview')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ interview_id: 'INT-1', status: 'STARTED' }) });
      }
      if (url.endsWith('/interviews/INT-1')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'STARTED', citizen_recording: null, constable_recording: null }),
        });
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
            interview_id: null,
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
    expect(document.getElementById('constableInterviewPanel').classList.contains('hidden')).toBe(true);

    document.getElementById('continueToInterview').click();

    await vi.waitFor(() => expect(document.getElementById('constableInterviewPanel').classList.contains('hidden')).toBe(false));
    expect(document.getElementById('continueToInterview').classList.contains('hidden')).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/constable/dockets/CD-1/interview', expect.objectContaining({ method: 'POST' }));
    expect(document.getElementById('constableInterviewStatus').textContent).toContain('STARTED');
  });

  it('shows the interview panel immediately when the docket already has an interview, submits a recording, and enables Register once complete', async () => {
    document.body.innerHTML = reviewMarkup();
    setLocation('/constable/dockets/CD-1');
    let constableSubmitted = false;
    const fetchMock = vi.fn((url, options = {}) => {
      if (url.endsWith('/interviews/INT-1/recording')) {
        constableSubmitted = true;
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ recording_id: 'REC-1' }) });
      }
      if (url.endsWith('/interviews/INT-1')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              status: constableSubmitted ? 'COMPLETED' : 'STARTED',
              citizen_recording: { status: 'SUBMITTED', storage_reference: 'recordings/xyz_citizen.wav' },
              constable_recording: constableSubmitted ? { status: 'SUBMITTED', storage_reference: 'recordings/xyz_constable.wav' } : null,
            }),
        });
      }
      if (url.endsWith('/flags')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (url.endsWith('/related')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            title: 'Vandalism',
            status: 'AWAITING_CONSTABLE_REGISTRATION',
            timeline: [],
            statements: [],
            evidence: [],
            interview_id: 'INT-1',
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateConstableReview();

    expect(document.getElementById('constableInterviewPanel').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('registerDocketBtn').disabled).toBe(true);

    setFileInputValue('constableRecordingFile', 'constable.wav');
    document.getElementById('submitConstableRecording').click();

    await vi.waitFor(() => expect(document.getElementById('registerDocketBtn').disabled).toBe(false));
    expect(document.getElementById('constableInterviewStatus').textContent).toContain('COMPLETED');
    expect(document.getElementById('toastContainer').textContent).toContain('Recording submitted');
    const statusBox = document.getElementById('constableInterviewStatus');
    expect(statusBox.querySelector('[data-view-media="recordings/xyz_citizen.wav"]')).not.toBeNull();
    expect(statusBox.querySelector('[data-view-media="recordings/xyz_constable.wav"]')).not.toBeNull();
  });

  it('registering the docket redirects to the constable dashboard, not the now-inaccessible detail page', async () => {
    document.body.innerHTML = reviewMarkup();
    setLocation('/constable/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/interviews/INT-1/register')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'REGISTERED' }) });
      }
      if (url.endsWith('/interviews/INT-1')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'COMPLETED', citizen_recording: { status: 'SUBMITTED' }, constable_recording: { status: 'SUBMITTED' } }),
        });
      }
      if (url.endsWith('/flags') || url.endsWith('/related')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ title: 'Vandalism', status: 'AWAITING_CONSTABLE_REGISTRATION', timeline: [], statements: [], evidence: [], interview_id: 'INT-1' }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateConstableReview();
    await vi.waitFor(() => expect(document.getElementById('registerDocketBtn').disabled).toBe(false));

    document.getElementById('registerDocketBtn').click();

    await vi.waitFor(() => expect(window.location.href).toBe('/constable'));
    expect(sessionStorage.getItem('pdasFlashMessage')).toContain('registered successfully');
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
      <div class="toast-container" id="toastContainer"></div>
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
    expect(document.getElementById('toastContainer').textContent).toContain('Flag recorded');
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
