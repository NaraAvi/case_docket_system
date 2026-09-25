import { readFileSync } from 'node:fs';
import path from 'node:path';
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
    it('renders submission cards and wires the Open button to navigate', async () => {
      document.body.innerHTML = '<div id="citizenDockets"></div>';
      setLocation('/citizen');
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: () => Promise.resolve([{ submission_id: 'SUB-1', title: 'Broken window', status: 'REGISTERED' }]),
        })
      );

      await hydrateCitizenDashboard();

      const container = document.getElementById('citizenDockets');
      expect(container.textContent).toContain('SUB-1');
      expect(container.querySelector('.badge-verified')).not.toBeNull();

      container.querySelector('[data-case-link]').click();
      expect(window.location.href).toBe('/citizen/dockets/SUB-1');
    });

    it('shows an empty state when there are no submissions', async () => {
      document.body.innerHTML = '<div id="citizenDockets"></div>';
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) }));

      await hydrateCitizenDashboard();

      expect(document.getElementById('citizenDockets').textContent).toContain('No submissions yet');
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
    it('loads protected submission metadata and history from the submission API contract', async () => {
      document.body.innerHTML = `
        <dl id="citizenCaseMeta"></dl>
        <ul id="citizenCaseTimeline"></ul>
      `;
      setLocation('/citizen/dockets/SUB-000001');
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            submission_id: 'SUB-000001',
            status: 'RECEIVED',
            title: 'Broken gate at school entrance',
            description: 'The gate has been left open and unsecured after hours.',
            location: 'School Entrance',
            incident_date: '2026-09-10',
            event_history: [{ event_type: 'submission_created', timestamp: '2026-09-23T09:04:52.181130+00:00', details: { status: 'RECEIVED' } }],
          }),
      });
      vi.stubGlobal('fetch', fetchMock);

      await hydrateCitizenDetail();

      expect(fetchMock).toHaveBeenCalledWith('/api/v1/citizen/submissions/SUB-000001', expect.any(Object));
      expect(document.getElementById('citizenCaseMeta').textContent).toContain('Broken gate at school entrance');
      expect(document.getElementById('citizenCaseTimeline').textContent).toContain('submission_created');
    });

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

    it('runs the protected submission analysis pipeline and shows the backend review result for a submission', async () => {
      document.body.innerHTML = `
        <dl id="citizenCaseMeta"></dl>
        <ul id="citizenCaseTimeline"></ul>
        <div id="citizenProtectedReview"></div>
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
      setLocation('/citizen/dockets/SUB-000001');
      const fetchMock = vi.fn((url, options = {}) => {
        if (url === '/api/v1/citizen/submissions/SUB-000001') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              submission_id: 'SUB-000001',
              status: 'RECEIVED',
              title: 'Broken gate at school entrance',
              description: 'The gate was left open and unsecured after hours.',
              location: 'School Entrance',
              incident_date: '2026-09-10',
              event_history: [],
              assertions: [],
              claims: [],
              evidence: [],
              statements: [],
            }),
          });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000001/assertions' && options.method === 'POST') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ assertion_id: 'AST-1' }) });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000001/assertions/AST-1/claims' && options.method === 'POST') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([{ claim_id: 'CLM-1' }]) });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000001/analyze' && options.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              status: 'REVIEW_REQUIRED',
              relationship_summary: { duplicate_count: 1, related_submission_ids: ['SUB-000002'], explanation: 'The system saw a possible duplicate cluster.' },
              control_evaluation: { result: 'REVIEW_REQUIRED' },
            }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'RECEIVED', timeline: [], statements: [], evidence: [] }) });
      });
      vi.stubGlobal('fetch', fetchMock);

      await hydrateCitizenDetail();

      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/citizen/submissions/SUB-000001/assertions',
        expect.objectContaining({ method: 'POST' })
      );
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/citizen/submissions/SUB-000001/assertions/AST-1/claims',
        expect.objectContaining({ method: 'POST' })
      );
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/citizen/submissions/SUB-000001/analyze',
        expect.objectContaining({ method: 'POST' })
      );
      expect(document.getElementById('citizenProtectedReview').textContent).toContain('Submission received');
      expect(document.getElementById('citizenProtectedReview').textContent).toContain('Procedural assessment');
      expect(document.getElementById('citizenProtectedReview').textContent).not.toContain('REVIEW_REQUIRED');
      expect(document.getElementById('citizenProtectedReview').textContent).not.toContain('ALLOWED');
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

    it('renders a protected-submission status rail instead of a case workflow ladder', async () => {
      document.body.innerHTML = `
        <div id="citizenWorkflowRail"></div>
        ${draftDetailMarkup()}
      `;
      setLocation('/citizen/dockets/SUB-000003');
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: () =>
            Promise.resolve({
              status: 'RECEIVED',
              is_frozen: false,
              location: 'Main St',
              incident_date: '2026-01-01',
              title: 'Broken window',
              timeline: [],
              statements: [{ statement_text: 'It happened.' }],
              evidence: [{ description: 'Photo of the window', evidence_type: 'PHOTO' }],
              original_content: { title: 'Broken window', reporter_relationship: 'witness' },
            }),
        })
      );

      await hydrateCitizenDetail();

      const rail = document.getElementById('citizenWorkflowRail');
      expect(rail.textContent).toContain('Protected submission');
      expect(rail.textContent).toContain('Status & review');
      expect(rail.textContent).toContain('Information / evidence');
      expect(rail.textContent).toContain('History');
      expect(rail.textContent).not.toContain('Review & Submit');
      expect(rail.querySelectorAll('.workflow-step.complete').length).toBeGreaterThan(0);
      expect(rail.querySelectorAll('.workflow-step.current').length).toBeGreaterThan(0);
    });

    it('uses the protected-submission wording on the detail page headline and status labels', async () => {
      document.body.innerHTML = `
        <div class="page-head-row">
          <div>
            <p class="eyebrow">Submission Reference</p>
            <h1>SUB-000003</h1>
          </div>
          <span id="citizenStatusBadge"></span>
        </div>
        <div id="citizenWorkflowRail"></div>
        <div id="citizenProtectedReview">
          <span id="citizenReviewStatus"></span>
          <p id="citizenReviewSummary"></p>
          <dl class="meta-list">
            <dt>Submission status</dt><dd id="citizenSubmissionStatusText">RECEIVED</dd>
            <dt>Procedural review</dt><dd id="citizenProceduralReviewValue">Pending</dd>
            <dt>Procedural case</dt><dd id="citizenProceduralCaseValue">Not yet created</dd>
          </dl>
        </div>
        <dl id="citizenCaseMeta"></dl>
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
        <div id="citizenStructuredSubmission"></div>
        <div class="toast-container" id="toastContainer"></div>
      `;
      setLocation('/citizen/dockets/SUB-000003');
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          ok: true,
          json: () =>
            Promise.resolve({
              status: 'RECEIVED',
              is_frozen: false,
              location: 'Main St',
              incident_date: '2026-01-01',
              title: 'Broken window',
              timeline: [],
              statements: [],
              evidence: [],
              original_content: { title: 'Broken window', reporter_relationship: 'witness' },
              assertions: [],
              claims: [],
            }),
        })
      );

      await hydrateCitizenDetail();

      expect(document.querySelector('.page-head-row h1').textContent).toContain('View and manage my protected submission');
      expect(document.getElementById('citizenSubmissionStatusText').textContent).toContain('RECEIVED');
      expect(document.getElementById('citizenProceduralCaseValue').textContent).toContain('Not yet created');
    });

    it('renders the structured protected-submission details rather than leaving the review panel blank', async () => {
      document.body.innerHTML = `
        <div class="page-head-row">
          <div><h1>SUB-000003</h1></div>
          <span id="citizenStatusBadge"></span>
        </div>
        <div id="citizenWorkflowRail"></div>
        <div id="citizenProtectedReview"><span id="citizenReviewStatus"></span><p id="citizenReviewSummary"></p></div>
        <dl id="citizenCaseMeta"></dl>
        <ul id="citizenCaseTimeline"></ul>
        <div id="citizenStructuredSubmission"></div>
        <div id="citizenSubmissionSummaryText"></div>
        <button id="citizenSubmissionToggle" type="button"></button>
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
        <div id="citizenEscalationsList"></div>
        <div id="escalateModal" class="hidden"></div>
        <div id="citizenInterviewPanel" class="hidden"></div>
        <div class="toast-container" id="toastContainer"></div>
      `;
      setLocation('/citizen/dockets/SUB-000003');
      vi.stubGlobal(
        'fetch',
        vi.fn((url, options = {}) => {
          if (url === '/api/v1/citizen/submissions/SUB-000003') {
            return Promise.resolve({
              ok: true,
              json: () => Promise.resolve({
                submission_id: 'SUB-000003',
                status: 'RECEIVED',
                title: 'Unsafe gate at station entrance',
                description: 'The gate was left unsecured after hours.',
                location: 'Station Entrance',
                incident_date: '2026-01-15',
                timeline: [],
                evidence: [],
                assertions: [],
                claims: [],
                original_content: {
                  title: 'Unsafe gate at station entrance',
                  reporter_relationship: 'witness',
                  can_contact: 'Yes',
                  incident_type: 'public_safety_hazard',
                  location: 'Station Entrance',
                  was_anyone_harmed: 'Yes',
                  harm_types: ['physical', 'safety'],
                },
              }),
            });
          }
          if (url === '/api/v1/citizen/submissions/SUB-000003/assertions') {
            return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
          }
          if (url === '/api/v1/citizen/submissions/SUB-000003/claims') {
            return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
          }
          if (url === '/api/v1/citizen/submissions/SUB-000003/evidence') {
            return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
          }
          if (url === '/api/v1/citizen/submissions/SUB-000003/relationships') {
            return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
          }
          if (url === '/api/v1/citizen/submissions/SUB-000003/analyze' && options.method === 'POST') {
            return Promise.resolve({
              ok: true,
              json: () => Promise.resolve({
                status: 'ALLOWED',
                case_reference: 'Not yet created',
                relationship_summary: { explanation: 'No duplicate pattern was detected.' },
                control_evaluation: { result: 'ALLOWED', reason: 'No control issue was flagged.' },
              }),
            });
          }
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        })
      );

      await hydrateCitizenDetail();

      const structured = document.getElementById('citizenStructuredSubmission');
      const summary = document.getElementById('citizenSubmissionSummaryText');
      const toggle = document.getElementById('citizenSubmissionToggle');

      expect(summary.textContent).toContain('witness');
      expect(summary.textContent).toContain('Station Entrance');
      expect(structured.classList.contains('hidden')).toBe(true);
      expect(toggle.textContent).toContain('View submitted information');
      expect(document.getElementById('citizenProtectedReview').textContent).toContain('Current status');
      expect(document.getElementById('citizenProtectedReview').textContent).toContain('Submission received');
      expect(document.getElementById('citizenProtectedReview').textContent).toContain('Procedural assessment');
      expect(document.getElementById('citizenProtectedReview').textContent).not.toContain('System review result');
      expect(document.getElementById('citizenProtectedReview').textContent).not.toContain('ALLOWED');
      expect(document.getElementById('citizenProtectedReview').textContent).not.toContain('Repeated or related submissions');
      expect(structured.textContent).toContain('About you');
      expect(structured.textContent).toContain('Incident');
      expect(structured.textContent).toContain('Harm / Injury');
      expect(structured.textContent).toContain('Original submission (immutable)');
    });

    it('shows a neutral "Proceed to procedural case" action when the gate is allowed and creates the case through the guarded route', async () => {
      document.body.innerHTML = `
        <div class="page-head-row">
          <div><h1>SUB-000003</h1></div>
          <span id="citizenStatusBadge"></span>
        </div>
        <div id="citizenWorkflowRail"></div>
        <div id="citizenProtectedReview">
          <span id="citizenReviewStatus"></span>
          <p id="citizenReviewSummary"></p>
          <dl class="meta-list">
            <dt>Submission status</dt><dd id="citizenSubmissionStatusText">RECEIVED</dd>
            <dt>Current procedural stage</dt><dd id="citizenProceduralReviewValue">Procedural assessment</dd>
            <dt>Procedural case</dt><dd id="citizenProceduralCaseValue">Not yet created</dd>
          </dl>
          <div class="stack-row hidden" id="citizenProceduralCaseAction" style="justify-content:flex-end; margin-top:12px;">
            <button class="primary-btn" type="button" id="citizenProceedToProceduralCase">Proceed to procedural case</button>
          </div>
        </div>
        <dl id="citizenCaseMeta"></dl>
        <ul id="citizenCaseTimeline"></ul>
        <div id="citizenStructuredSubmission"></div>
        <div id="citizenSubmissionSummaryText"></div>
        <button id="citizenSubmissionToggle" type="button"></button>
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
        <div id="citizenEscalationsList"></div>
        <div id="escalateModal" class="hidden"></div>
        <div id="citizenInterviewPanel" class="hidden"></div>
        <div class="toast-container" id="toastContainer"></div>
      `;
      setLocation('/citizen/dockets/SUB-000003');
      const fetchMock = vi.fn((url, options = {}) => {
        if (url === '/api/v1/citizen/submissions/SUB-000003') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              submission_id: 'SUB-000003',
              status: 'RECEIVED',
              location: 'Station Entrance',
              incident_date: '2026-01-15',
              title: 'Unsafe gate at station entrance',
              timeline: [],
              evidence: [],
              assertions: [],
              claims: [],
              original_content: { title: 'Unsafe gate at station entrance', reporter_relationship: 'witness' },
            }),
          });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000003/assertions') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000003/claims') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000003/evidence') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000003/relationships') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000003/analyze' && options.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              status: 'ALLOWED',
              candidate: { candidate_id: 'CAND-900', status: 'PROVISIONAL' },
              relationship_summary: { explanation: 'No duplicate pattern was detected.' },
              control_evaluation: { result: 'ALLOWED', reason: 'No control issue was flagged.' },
              case_reference: 'Not yet created',
            }),
          });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000003/incident-candidates/CAND-900/create-case' && options.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              status: 'ALLOWED',
              gate: 'case_creation',
              case_reference: 'CD-2026-000123',
              candidate_id: 'CAND-900',
              submission_id: 'SUB-000003',
            }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      });
      vi.stubGlobal('fetch', fetchMock);

      await hydrateCitizenDetail();

      const button = document.getElementById('citizenProceedToProceduralCase');
      expect(button).not.toBeNull();
      expect(button.textContent).toContain('Proceed to procedural case');

      button.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));

      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/citizen/submissions/SUB-000003/incident-candidates/CAND-900/create-case',
        expect.objectContaining({ method: 'POST' })
      );
      expect(document.getElementById('citizenProceduralCaseValue').textContent).toContain('CD-2026-000123');
    });

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

    it('hydrates the interview panel from the linked procedural case when a protected submission has already advanced', async () => {
      document.body.innerHTML = draftDetailMarkup();
      setLocation('/citizen/dockets/SUB-000003');
      let citizenSubmitted = false;
      const fetchMock = vi.fn((url, options = {}) => {
        if (url === '/api/v1/citizen/submissions/SUB-000003') {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                submission_id: 'SUB-000003',
                status: 'RECEIVED',
                title: 'Unsafe gate at station entrance',
                description: 'The gate was left unsecured after hours.',
                location: 'Station Entrance',
                incident_date: '2026-01-15',
                original_content: { title: 'Unsafe gate at station entrance', reporter_relationship: 'witness' },
                event_history: [],
                assertions: [],
                claims: [],
                evidence: [],
              }),
          });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000003/assertions') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000003/claims') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000003/evidence') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000003/relationships') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }
        if (url === '/api/v1/citizen/submissions/SUB-000003/analyze' && options.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                status: 'ALLOWED',
                candidate: { candidate_id: 'CAND-900' },
                relationship_summary: { explanation: 'No duplicate pattern was detected.' },
                control_evaluation: { result: 'ALLOWED', reason: 'No control issue was flagged.' },
                case_reference: 'CD-2026-000123',
              }),
          });
        }
        if (url === '/api/v1/citizen/dockets') {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve([
                {
                  case_reference: 'CD-2026-000123',
                  source_submission_id: 'SUB-000003',
                  status: 'AWAITING_CONSTABLE_REGISTRATION',
                  interview_id: 'INT-1',
                  timeline: [],
                  statements: [{ statement_text: 'It happened.' }],
                  evidence: [],
                },
              ]),
          });
        }
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
                constable_recording: { status: 'SUBMITTED' },
              }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'DRAFT', timeline: [], statements: [], evidence: [] }),
        });
      });
      vi.stubGlobal('fetch', fetchMock);

      await hydrateCitizenDetail();

      expect(document.getElementById('citizenInterviewPanel').classList.contains('hidden')).toBe(false);
      expect(document.getElementById('citizenInterviewStatus').textContent).toMatch(/Submit .*below|Submit your recording below/i);

      setFileInputValue('citizenRecordingFile', 'my_statement.wav', 'audio bytes', 'audio/wav');
      document.getElementById('submitCitizenRecording').click();

      await vi.waitFor(() => expect(document.getElementById('submitCitizenRecording').disabled).toBe(true));
      expect(document.getElementById('citizenInterviewStatus').textContent).toContain('Both recordings submitted');
      expect(document.getElementById('toastContainer').textContent).toContain('Recording submitted');
      expect(document.getElementById('citizenInterviewStatus').querySelector('[data-view-media="recordings/abc_my_statement.wav"]')).not.toBeNull();
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
    it('submits the protected submission payload and redirects to the submission detail page', async () => {
      document.body.innerHTML = `
        <input id="crimeType" value="Theft" />
        <textarea id="description">A long enough description of the incident.</textarea>
        <input id="incidentDate" value="2026-01-01" />
        <input id="incidentLocation" value="Main St" />
        <button id="submitCitizenDocket"></button>
      `;
      setLocation('/citizen/dockets/new');
      const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ submission_id: 'SUB-000001', status: 'RECEIVED' }) });
      vi.stubGlobal('fetch', fetchMock);

      hydrateCitizenForm();
      document.getElementById('submitCitizenDocket').click();

      await vi.waitFor(() => expect(window.location.href).toBe('/citizen/dockets/SUB-000001'));

      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe('/api/v1/citizen/submissions');
      expect(JSON.parse(options.body)).toEqual({
        title: 'Theft',
        description: 'A long enough description of the incident.',
        incident_date: '2026-01-01',
        location: 'Main St',
      });
    });

    it('keeps the simplified people model at the incident level and omits artificial person records', () => {
      document.body.innerHTML = `
        <div id="citizenSubmissionForm">
          <input id="crimeType" value="Unsafe gate" />
          <textarea id="description">The gate was left open and several people saw it happen.</textarea>
          <select id="reporterRelationship"><option value="witness">Witness</option></select>
          <select id="canContact"><option value="Yes">Yes</option></select>
          <select id="contactMethod"><option value="Phone">Phone</option></select>
          <input id="contactPhone" value="5550102" />
          <select id="otherPeopleInvolved"><option value="Yes">Yes</option></select>
          <select id="peopleCount"><option value="3-5">3–5</option></select>
          <div id="peopleRecords"></div>
          <select id="wasAnyoneInjured"><option value="Yes">Yes</option></select>
          <div id="injuryFields">
            <select id="medicalAttention"><option value="Yes">Yes</option></select>
            <div id="medicalAttentionFields">
              <input id="medicalAttentionDetails" value="Hospital check-up" />
            </div>
          </div>
          <div id="citizenSubmissionReview"></div>
          <button id="submitCitizenDocket"></button>
        </div>
      `;
      setLocation('/citizen/dockets/new');
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ submission_id: 'SUB-000001' }) }));

      hydrateCitizenForm();
      document.getElementById('peopleCount').dispatchEvent(new Event('change', { bubbles: true }));

      expect(document.querySelectorAll('[data-person-index]').length).toBe(0);
      expect(document.getElementById('citizenSubmissionReview').textContent).toContain('People involved: Yes');
      expect(document.getElementById('citizenSubmissionReview').textContent).toContain('Approximate number of people involved: 3–5');
      expect(document.getElementById('citizenSubmissionReview').textContent).not.toContain('Person 1');
    });

    it('renders the structured injury and medical attention values in the review summary', () => {
      document.body.innerHTML = `
        <div id="citizenSubmissionForm">
          <select id="wasAnyoneHarmed"><option value="Yes">Yes</option></select>
          <div id="harmFields">
            <input type="checkbox" name="harmType" value="physical" checked />
            <input type="checkbox" name="harmType" value="safety" checked />
          </div>
          <select id="wasAnyoneInjured"><option value="Yes">Yes</option></select>
          <div id="injuryFields">
            <input type="checkbox" name="injuryType" value="serious" checked />
            <select id="injuryPersonType"><option value="affected_person">Affected person</option></select>
            <select id="medicalAttention"><option value="Yes">Yes</option></select>
            <div id="medicalAttentionFields">
              <textarea id="medicalAttentionDetails">Treatment details provided by citizen</textarea>
            </div>
            <textarea id="injuries">Facial injury with visible bleeding after being struck and falling.</textarea>
          </div>
          <select id="propertyImpactQuestion"><option value="No">No</option></select>
          <div id="citizenSubmissionReview"></div>
          <button id="submitCitizenDocket"></button>
        </div>
      `;
      setLocation('/citizen/dockets/new');
      hydrateCitizenForm();

      expect(document.getElementById('citizenSubmissionReview').textContent).toContain('Harm types: Physical, Safety risk');
      expect(document.getElementById('citizenSubmissionReview').textContent).toContain('Who was injured: Affected person');
      expect(document.getElementById('citizenSubmissionReview').textContent).toContain('Medical attention: Yes');
      expect(document.getElementById('citizenSubmissionReview').textContent).toContain('Medical treatment/details: Treatment details provided by citizen');
      expect(document.getElementById('citizenSubmissionReview').textContent).toContain('Injury details: Facial injury with visible bleeding after being struck and falling.');
      expect(document.getElementById('citizenSubmissionReview').textContent).toContain('Property/financial impact: No');
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

  describe('citizen intake template contract', () => {
    it('renders the structured protected submission fields for the PDAS intake v2 workflow', () => {
      const templatePath = path.resolve(__dirname, '../../../templates/citizen_docket_form.html');
      const template = readFileSync(templatePath, 'utf8');
      const requiredFields = [
        'reporterRelationship',
        'reporterRelationshipOtherWrap',
        'canContact',
        'incidentType',
        'dateCertainty',
        'locationKnown',
        'otherPeopleInvolved',
        'peopleCount',
        'currentSafetyQuestion',
        'citizenSubmissionReview',
        'submitCitizenDocket',
      ];

      for (const field of requiredFields) {
        expect(template).toContain(`id="${field}"`);
      }
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

      expect(fetchMock).toHaveBeenCalledWith('/api/v1/citizen/submissions', expect.any(Object));
    });
  });
});
