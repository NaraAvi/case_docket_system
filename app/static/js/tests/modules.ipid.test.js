import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/auth.js', () => ({
  getToken: vi.fn().mockReturnValue(null),
  getUser: vi.fn(),
}));

import { getIpidDisciplinaryCaseId, getIpidEscalationId, hydrateDisciplinaryCaseDetail, hydrateIpidDashboard, hydrateIpidDetail, init } from '../modules/ipid.js';


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

  it('hydrateIpidDashboard renders the disciplinary cases panel with a working link', async () => {
    document.body.innerHTML = '<div id="ipidQueueList"></div><div id="ipidDisciplinaryCasesList"></div>';
    setLocation('/ipid');
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url.includes('disciplinary-cases')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve([{ disciplinary_case_id: 'DIC-000001', source_case_reference: 'CD-1', status: 'OPEN' }]),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      })
    );

    await hydrateIpidDashboard();

    const container = document.getElementById('ipidDisciplinaryCasesList');
    expect(container.textContent).toContain('DIC-000001');
    container.querySelector('[data-case-link]').click();
    expect(window.location.href).toBe('/ipid/disciplinary-cases/DIC-000001');
  });

  it('hydrateIpidDashboard renders the Cases in Custody panel, linked by escalation id', async () => {
    document.body.innerHTML = '<div id="ipidQueueList"></div><div id="ipidCustodyCasesList"></div>';
    setLocation('/ipid');
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url.includes('custody-cases')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve([{ case_reference: 'CD-1', escalation_id: 'ESC-1', title: 'Vandalism', escalation_status: 'UNDER_REVIEW' }]),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      })
    );

    await hydrateIpidDashboard();

    const container = document.getElementById('ipidCustodyCasesList');
    expect(container.textContent).toContain('CD-1');
    expect(container.textContent).toContain('FROZEN');
    container.querySelector('[data-case-link]').click();
    expect(window.location.href).toBe('/ipid/escalations/ESC-1');
  });

  it('hydrateIpidDashboard shows an empty state when nothing is in custody', async () => {
    document.body.innerHTML = '<div id="ipidQueueList"></div><div id="ipidCustodyCasesList"></div>';
    setLocation('/ipid');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) }));

    await hydrateIpidDashboard();

    expect(document.getElementById('ipidCustodyCasesList').textContent).toContain('No cases are currently in IPID custody.');
  });

  it('getIpidDisciplinaryCaseId extracts the id from the detail URL', () => {
    setLocation('/ipid/disciplinary-cases/DIC-000001');
    expect(getIpidDisciplinaryCaseId()).toBe('DIC-000001');
  });

  it('hydrateDisciplinaryCaseDetail renders the flat case record', async () => {
    document.body.innerHTML = `
      <dl id="disciplinaryCaseMeta"></dl>
      <dl id="disciplinaryCaseReasonMeta"></dl>
      <div id="disciplinaryCaseReasonBox"></div>
      <span id="disciplinaryCaseStatusBadge"></span>
    `;
    setLocation('/ipid/disciplinary-cases/DIC-000001');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            disciplinary_case_id: 'DIC-000001',
            source_case_reference: 'CD-1',
            escalation_id: 'ESC-1',
            implicated_officer_id: 'OFF-2',
            status: 'OPEN',
            category: 'OFFICER_CONDUCT',
            reason: 'Corroborated bribery allegation.',
            created_by: 'IPID-1',
            created_by_role: 'ipid',
            created_at: '2026-01-01T00:00:00Z',
          }),
      })
    );

    await hydrateDisciplinaryCaseDetail();

    expect(document.getElementById('disciplinaryCaseMeta').textContent).toContain('CD-1');
    expect(document.getElementById('disciplinaryCaseMeta').textContent).toContain('OFF-2');
    expect(document.getElementById('disciplinaryCaseReasonBox').textContent).toContain('Corroborated bribery allegation.');
  });

  it('hydrateIpidDetail renders escalation meta, statement/evidence/timeline, review notes, findings, and audit history from the review workspace', async () => {
    document.body.innerHTML = `
      <dl id="ipidEscalationMeta"></dl>
      <dl id="ipidAssignmentMeta"></dl>
      <span id="ipidStatusBadge"></span>
      <div id="ipidStatementsList"></div>
      <button id="openIpidStatementModal"></button>
      <div class="reauth-modal hidden" id="ipidStatementModal">
        <textarea id="ipidStatementText"></textarea>
        <p id="ipidStatementModalError" class="hidden"></p>
        <button id="closeIpidStatementModal"></button>
        <button id="submitIpidStatementModal"></button>
      </div>
      <table><tbody id="ipidCaseEvidence"></tbody></table>
      <ul id="ipidCaseTimeline"></ul>
      <ul id="ipidReviewNotes"></ul>
      <div id="ipidReviewFindings"></div>
      <ul id="ipidAuditList"></ul>
      <button id="dismissEscalationBtn"></button>
      <button id="upholdEscalationBtn"></button>
      <button id="takeCustodyBtn"></button>
      <p id="ipidDecisionNotice"></p>
    `;
    setLocation('/ipid/escalations/ESC-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/review-workspace')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              case_reference: 'CD-1',
              category: 'IPID.SEC28.CORRUPTION',
              status: 'UNDER_REVIEW',
              case_context: {
                citizen_id: 'CIT-1',
                assigned_officer_id: 'OFF-2',
                freeze_status: 'FROZEN',
                is_frozen: true,
                statements: [{ statement_text: 'Officer demanded a bribe to proceed.' }],
                evidence: [{ description: 'Voice recording', evidence_type: 'AUDIO' }],
                timeline: [{ event_type: 'docket_created', timestamp: '2026-01-01T00:00:00Z' }],
              },
              review_notes: [{ author_role: 'ipid', note_text: 'Independent finding recorded.' }],
              review_findings: [{ finding_type: 'SUBSTANTIATED', summary: 'Officer conduct confirmed.' }],
              audit_history: [{ action: 'Escalation received', timestamp: '2026-01-01T00:00:00Z' }],
            }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ escalation_id: 'ESC-1', status: 'UNDER_REVIEW' }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateIpidDetail();

    expect(document.getElementById('ipidEscalationMeta').textContent).toContain('IPID.SEC28.CORRUPTION');
    expect(document.getElementById('ipidAssignmentMeta').textContent).toContain('OFF-2');
    expect(document.getElementById('ipidStatementsList').textContent).toContain('Officer demanded a bribe to proceed.');
    expect(document.getElementById('ipidCaseEvidence').textContent).toContain('Voice recording');
    expect(document.getElementById('ipidCaseTimeline').textContent).toContain('docket_created');
    expect(document.getElementById('ipidReviewNotes').textContent).toContain('Independent finding recorded.');
    expect(document.getElementById('ipidReviewFindings').textContent).toContain('Officer conduct confirmed.');
    expect(document.getElementById('ipidAuditList').textContent).toContain('Escalation received');
    expect(document.getElementById('takeCustodyBtn').disabled).toBe(false);
  });

  it('adds a victim statement and shows it in the statements list', async () => {
    document.body.innerHTML = `
      <dl id="ipidEscalationMeta"></dl>
      <dl id="ipidAssignmentMeta"></dl>
      <span id="ipidStatusBadge"></span>
      <div id="ipidStatementsList"></div>
      <button id="openIpidStatementModal"></button>
      <div class="reauth-modal hidden" id="ipidStatementModal">
        <textarea id="ipidStatementText"></textarea>
        <p id="ipidStatementModalError" class="hidden"></p>
        <button id="closeIpidStatementModal"></button>
        <button id="submitIpidStatementModal"></button>
      </div>
      <table><tbody id="ipidCaseEvidence"></tbody></table>
      <ul id="ipidCaseTimeline"></ul>
      <ul id="ipidReviewNotes"></ul>
      <div id="ipidReviewFindings"></div>
      <ul id="ipidAuditList"></ul>
      <button id="dismissEscalationBtn"></button>
      <button id="upholdEscalationBtn"></button>
      <button id="takeCustodyBtn"></button>
      <p id="ipidDecisionNotice"></p>
      <div id="toastContainer"></div>
    `;
    setLocation('/ipid/escalations/ESC-1');
    let statementAdded = false;
    const fetchMock = vi.fn((url, options = {}) => {
      if (url.endsWith('/dockets/CD-1/statements') && options.method === 'POST') {
        statementAdded = true;
        expect(JSON.parse(options.body)).toEqual({ statement_text: 'Independently interviewed the victim.' });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ statement_id: 2, recorded_by_role: 'ipid' }) });
      }
      if (url.endsWith('/review-workspace')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              case_reference: 'CD-1',
              status: 'UNDER_REVIEW',
              case_context: {
                statements: statementAdded
                  ? [{ statement_text: 'Officer demanded a bribe.' }, { statement_text: 'Independently interviewed the victim.', recorded_by: 'IPID-1', recorded_by_role: 'ipid' }]
                  : [{ statement_text: 'Officer demanded a bribe.' }],
              },
            }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ escalation_id: 'ESC-1', status: 'UNDER_REVIEW' }) });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateIpidDetail();
    expect(document.getElementById('ipidStatementsList').textContent).toContain('Officer demanded a bribe.');

    document.getElementById('openIpidStatementModal').click();
    document.getElementById('ipidStatementText').value = 'Independently interviewed the victim.';
    document.getElementById('submitIpidStatementModal').click();

    await vi.waitFor(() => expect(document.getElementById('ipidStatementsList').textContent).toContain('Independently interviewed the victim.'));
    expect(document.getElementById('toastContainer').textContent).toContain('Statement recorded');
  });

  it('take-custody button posts to the take-custody endpoint via the reauth modal and reloads', async () => {
    document.body.innerHTML = `
      <dl id="ipidEscalationMeta"></dl>
      <dl id="ipidAssignmentMeta"></dl>
      <span id="ipidStatusBadge"></span>
      <ul id="ipidReviewNotes"></ul>
      <div id="ipidReviewFindings"></div>
      <ul id="ipidAuditList"></ul>
      <button id="dismissEscalationBtn"></button>
      <button id="upholdEscalationBtn"></button>
      <button id="takeCustodyBtn" data-open-reauth></button>
      <p id="ipidDecisionNotice"></p>
      <div id="toastContainer"></div>
      <div id="reauthModal" class="hidden">
        <div class="field-row"><label>Target Record</label><div data-reauth-target></div></div>
        <div data-reauth-action></div>
        <p data-reauth-subtitle></p>
        <textarea data-reauth-reason></textarea>
        <p data-reauth-error class="hidden"></p>
        <button data-close-reauth>Cancel</button>
        <button data-reauth-confirm>Confirm</button>
      </div>
    `;
    setLocation('/ipid/escalations/ESC-1');
    const fetchMock = vi.fn((url, options) => {
      if (url.endsWith('/review-workspace')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ case_reference: 'CD-1', status: 'UNDER_REVIEW', case_context: {} }) });
      }
      if (url.endsWith('/take-custody')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ACTIVE' }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ escalation_id: 'ESC-1', status: 'UNDER_REVIEW' }) });
    });
    vi.stubGlobal('fetch', fetchMock);
    delete window.location;
    window.location = { pathname: '/ipid/escalations/ESC-1', href: '', reload: vi.fn() };

    const { bindReauthModal } = await import('../core/ui.js');
    bindReauthModal();

    await hydrateIpidDetail();

    document.getElementById('takeCustodyBtn').click();
    document.querySelector('[data-reauth-reason]').value = 'Preventing tampering while reviewing.';
    document.querySelector('[data-reauth-confirm]').click();

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/ipid/escalations/ESC-1/take-custody',
        expect.objectContaining({ method: 'POST' })
      )
    );
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
