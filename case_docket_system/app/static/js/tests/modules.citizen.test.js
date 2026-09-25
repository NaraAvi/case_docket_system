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

function setFileInputValue(inputId, filename, content = 'file bytes', type = 'image/jpeg') {
  const input = document.getElementById(inputId);
  const file = new File([content], filename, { type });
  // jsdom has no DataTransfer constructor; override the read-only `files`
  // property directly instead (a standard jsdom testing workaround).
  Object.defineProperty(input, 'files', { value: [file], writable: false, configurable: true });
  input.dispatchEvent(new Event('change', { bubbles: true }));
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

    function draftDetailMarkup() {
      return `
        <dl id="citizenCaseMeta"></dl>
        <span id="citizenStatusBadge"></span>
        <span id="citizenFreezeBadge" class="hidden"></span>
        <ul id="citizenCaseTimeline"></ul>
        <textarea id="citizenStatementText"></textarea>
        <button id="saveCitizenStatement"></button>
        <p id="citizenStatementError" class="hidden"></p>
        <div id="citizenStatementsList"></div>
        <table><tbody id="citizenCaseEvidence"></tbody></table>
        <select id="citizenEvidenceType"><option value="PHOTO">Photo</option></select>
        <input type="file" id="citizenEvidenceFile" />
        <p id="citizenEvidenceFilePreview" class="hidden"></p>
        <textarea id="citizenEvidenceDescription"></textarea>
        <button id="addCitizenEvidence"></button>
        <p id="citizenEvidenceError" class="hidden"></p>
        <button id="submitCitizenDocketForReview"></button>
        <p id="submitDocketHint"></p>
        <button id="escalateCaseBtn"></button>
        <div id="escalateModal" class="hidden">
          <select id="escalateCategory"><option value="OFFICER_CONDUCT">Officer Conduct</option></select>
          <textarea id="escalateDescription"></textarea>
          <p id="escalateModalError" class="hidden"></p>
          <button id="closeEscalateModal"></button>
          <button id="submitEscalateModal"></button>
        </div>
        <div id="citizenInterviewPanel" class="hidden">
          <div id="citizenInterviewStatus"></div>
          <input type="file" id="citizenRecordingFile" />
          <p id="citizenRecordingFilePreview" class="hidden"></p>
          <button id="submitCitizenRecording"></button>
          <p id="citizenRecordingError" class="hidden"></p>
        </div>
        <div id="citizenEscalationsList"></div>
        <div class="toast-container" id="toastContainer"></div>
      `;
    }

    it('disables submit until a statement is saved, then enables it once one exists', async () => {
      document.body.innerHTML = draftDetailMarkup();
      setLocation('/citizen/dockets/CD-1');
      let statementSaved = false;
      const fetchMock = vi.fn((url, options = {}) => {
        if (url.endsWith('/statements') && options.method === 'POST') {
          statementSaved = true;
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ statement_id: 1, statement_text: 'It happened.' }) });
        }
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              status: 'DRAFT',
              location: 'Main St',
              incident_date: '2026-01-01',
              title: 'Broken window',
              timeline: [],
              statements: statementSaved ? [{ statement_text: 'It happened.' }] : [],
              evidence: [],
            }),
        });
      });
      vi.stubGlobal('fetch', fetchMock);

      await hydrateCitizenDetail();
      expect(document.getElementById('submitCitizenDocketForReview').disabled).toBe(true);

      document.getElementById('citizenStatementText').value = 'It happened.';
      document.getElementById('saveCitizenStatement').click();

      await vi.waitFor(() => expect(document.getElementById('submitCitizenDocketForReview').disabled).toBe(false));
      expect(document.getElementById('toastContainer').textContent).toContain('Statement saved');
    });

    it('uploads a real evidence file and re-renders the evidence table, showing a confirmation toast', async () => {
      document.body.innerHTML = draftDetailMarkup();
      setLocation('/citizen/dockets/CD-1');
      let evidenceAdded = false;
      const fetchMock = vi.fn((url, options = {}) => {
        if (url.endsWith('/evidence') && options.method === 'POST') {
          evidenceAdded = true;
          expect(options.body).toBeInstanceOf(FormData);
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ evidence_id: 1 }) });
        }
        if (url.endsWith('/evidence')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(evidenceAdded ? [{ description: 'Broken window photo', evidence_type: 'PHOTO' }] : []),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'DRAFT', timeline: [], statements: [], evidence: [] }),
        });
      });
      vi.stubGlobal('fetch', fetchMock);

      await hydrateCitizenDetail();
      setFileInputValue('citizenEvidenceFile', 'window.jpg');
      expect(document.getElementById('citizenEvidenceFilePreview').classList.contains('hidden')).toBe(false);
      document.getElementById('citizenEvidenceDescription').value = 'Broken window photo';
      document.getElementById('addCitizenEvidence').click();

      await vi.waitFor(() => expect(document.getElementById('citizenCaseEvidence').textContent).toContain('Broken window photo'));
      expect(document.getElementById('toastContainer').textContent).toContain('uploaded');
    });

    it('rejects adding evidence with no file selected', async () => {
      document.body.innerHTML = draftDetailMarkup();
      setLocation('/citizen/dockets/CD-1');
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ status: 'DRAFT', timeline: [], statements: [], evidence: [] }),
      });
      vi.stubGlobal('fetch', fetchMock);

      await hydrateCitizenDetail();
      document.getElementById('citizenEvidenceDescription').value = 'Broken window photo';
      document.getElementById('addCitizenEvidence').click();

      expect(document.getElementById('citizenEvidenceError').classList.contains('hidden')).toBe(false);
      expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining('/evidence'), expect.objectContaining({ method: 'POST' }));
    });

    it('submits the docket for review and reloads', async () => {
      document.body.innerHTML = draftDetailMarkup();
      setLocation('/citizen/dockets/CD-1');
      const fetchMock = vi.fn((url, options = {}) => {
        if (url.endsWith('/submit')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'AWAITING_CONSTABLE_REGISTRATION' }) });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'DRAFT', timeline: [], statements: [{ statement_text: 'It happened.' }], evidence: [] }),
        });
      });
      vi.stubGlobal('fetch', fetchMock);

      await hydrateCitizenDetail();
      expect(document.getElementById('submitCitizenDocketForReview').disabled).toBe(false);

      document.getElementById('submitCitizenDocketForReview').click();

      await vi.waitFor(() =>
        expect(fetchMock).toHaveBeenCalledWith('/api/v1/citizen/dockets/CD-1/submit', expect.objectContaining({ method: 'POST' }))
      );
      await vi.waitFor(() => expect(sessionStorage.getItem('pdasFlashMessage')).toContain('submitted for constable review'));
    });

    it('disables statement editing and submit once the docket has left DRAFT', async () => {
      document.body.innerHTML = draftDetailMarkup();
      setLocation('/citizen/dockets/CD-1');
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: () =>
            Promise.resolve({
              status: 'AWAITING_CONSTABLE_REGISTRATION',
              timeline: [],
              statements: [{ statement_text: 'It happened.' }],
              evidence: [],
            }),
        })
      );

      await hydrateCitizenDetail();

      expect(document.getElementById('citizenStatementText').disabled).toBe(true);
      expect(document.getElementById('submitCitizenDocketForReview').disabled).toBe(true);
      expect(document.getElementById('submitCitizenDocketForReview').textContent).toContain('AWAITING_CONSTABLE_REGISTRATION');
    });

    it('shows the freeze badge with a reason when the docket is frozen, and hides it otherwise', async () => {
      document.body.innerHTML = draftDetailMarkup();
      setLocation('/citizen/dockets/CD-1');
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: () =>
            Promise.resolve({
              status: 'REGISTERED',
              timeline: [],
              statements: [],
              evidence: [],
              is_frozen: true,
              freeze_reason: 'IPID took custody of the docket while reviewing escalation ESC-1',
            }),
        })
      );

      await hydrateCitizenDetail();

      const badge = document.getElementById('citizenFreezeBadge');
      expect(badge.classList.contains('hidden')).toBe(false);
      expect(badge.textContent).toContain('IPID took custody');
    });

    it('renders the "My Escalations" panel with status and decision once resolved', async () => {
      document.body.innerHTML = draftDetailMarkup();
      setLocation('/citizen/dockets/CD-1');
      const fetchMock = vi.fn((url, options = {}) => {
        if (url.endsWith('/escalations') && !options.method) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve([
                {
                  escalation_id: 'ESC-1',
                  category: 'OFFICER_CONDUCT',
                  description: 'Officer refused to register this docket.',
                  status: 'RESOLVED',
                  decision: 'UPHELD',
                  decision_reason: 'Corroborated by audio evidence.',
                  decision_at: '2026-01-03T00:00:00Z',
                },
              ]),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'DRAFT', timeline: [], statements: [], evidence: [] }),
        });
      });
      vi.stubGlobal('fetch', fetchMock);

      await hydrateCitizenDetail();

      const panel = document.getElementById('citizenEscalationsList');
      expect(panel.textContent).toContain('OFFICER_CONDUCT');
      expect(panel.textContent).toContain('UPHELD');
      expect(panel.textContent).toContain('Corroborated by audio evidence.');
    });

    it('shows a placeholder when the citizen has not escalated this docket', async () => {
      document.body.innerHTML = draftDetailMarkup();
      setLocation('/citizen/dockets/CD-1');
      vi.stubGlobal(
        'fetch',
        vi.fn((url, options = {}) => {
          if (url.endsWith('/escalations') && !options.method) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
          }
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ status: 'DRAFT', timeline: [], statements: [], evidence: [] }),
          });
        })
      );

      await hydrateCitizenDetail();

      expect(document.getElementById('citizenEscalationsList').textContent).toContain('You have not escalated');
    });

    it('shows the full mixed-author statement history, while the editable textarea only ever reflects the citizen\'s own latest statement', async () => {
      document.body.innerHTML = draftDetailMarkup();
      setLocation('/citizen/dockets/CD-1');
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: () =>
            Promise.resolve({
              status: 'REGISTERED',
              timeline: [],
              evidence: [],
              statements: [
                { statement_text: 'Someone broke my window.', created_at: '2026-01-01' },
                { statement_text: 'Witness confirms seeing the suspect flee northbound.', recorded_by: 'DET-1', recorded_by_role: 'detective' },
              ],
            }),
        })
      );

      await hydrateCitizenDetail();

      const panel = document.getElementById('citizenStatementsList');
      expect(panel.textContent).toContain('Someone broke my window.');
      expect(panel.textContent).toContain('Witness confirms seeing the suspect flee northbound.');
      expect(panel.textContent).toContain('detective');
      // The detective-authored statement is the *last* array item, but the
      // editable textarea must still seed from the citizen's own statement.
      expect(document.getElementById('citizenStatementText').value).toBe('Someone broke my window.');
    });

    it('the escalate modal submits a category and description', async () => {
      document.body.innerHTML = draftDetailMarkup();
      setLocation('/citizen/dockets/CD-1');
      const fetchMock = vi.fn((url, options = {}) => {
        if (url.endsWith('/escalations')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ escalation_id: 'ESC-1' }) });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'DRAFT', timeline: [], statements: [], evidence: [] }),
        });
      });
      vi.stubGlobal('fetch', fetchMock);

      await hydrateCitizenDetail();
      document.getElementById('escalateCaseBtn').click();
      expect(document.getElementById('escalateModal').classList.contains('hidden')).toBe(false);

      document.getElementById('escalateDescription').value = 'Officer refused to register this docket.';
      document.getElementById('submitEscalateModal').click();

      await vi.waitFor(() =>
        expect(fetchMock).toHaveBeenCalledWith(
          '/api/v1/citizen/dockets/CD-1/escalations',
          expect.objectContaining({ method: 'POST' })
        )
      );
    });

    it('shows the interview panel and lets the citizen submit their recording once the constable has started an interview', async () => {
      document.body.innerHTML = draftDetailMarkup();
      setLocation('/citizen/dockets/CD-1');
      let citizenSubmitted = false;
      const fetchMock = vi.fn((url, options = {}) => {
        if (url.endsWith('/interviews/INT-1/recording')) {
          citizenSubmitted = true;
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ recording_id: 'REC-1' }) });
        }
        if (url.endsWith('/interviews/INT-1')) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                status: citizenSubmitted ? 'AWAITING_AUDIO' : 'STARTED',
                citizen_recording: citizenSubmitted ? { status: 'SUBMITTED', storage_reference: 'recordings/abc_my_statement.wav' } : null,
                constable_recording: null,
              }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              status: 'AWAITING_CONSTABLE_REGISTRATION',
              timeline: [],
              statements: [{ statement_text: 'It happened.' }],
              evidence: [],
              interview_id: 'INT-1',
            }),
        });
      });
      vi.stubGlobal('fetch', fetchMock);

      await hydrateCitizenDetail();

      expect(document.getElementById('citizenInterviewPanel').classList.contains('hidden')).toBe(false);
      expect(document.getElementById('citizenInterviewStatus').textContent).toContain('Submit your recording below');

      setFileInputValue('citizenRecordingFile', 'my_statement.wav', 'audio bytes', 'audio/wav');
      document.getElementById('submitCitizenRecording').click();

      await vi.waitFor(() => expect(document.getElementById('submitCitizenRecording').disabled).toBe(true));
      expect(document.getElementById('citizenInterviewStatus').textContent).toContain('Waiting on the constable');
      expect(document.getElementById('toastContainer').textContent).toContain('Recording submitted');
      expect(document.getElementById('citizenInterviewStatus').querySelector('[data-view-media="recordings/abc_my_statement.wav"]')).not.toBeNull();
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
        <p id="citizenFormError" class="hidden"></p>
      `;
      setLocation('/citizen/dockets/new');
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({ ok: false, status: 400, json: () => Promise.resolve({ error: 'Description is required.' }) })
      );

      hydrateCitizenForm();
      document.getElementById('submitCitizenDocket').click();

      await vi.waitFor(() => expect(document.getElementById('citizenFormError').classList.contains('hidden')).toBe(false));
      expect(document.getElementById('citizenFormError').textContent).toBe('Description is required.');
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
