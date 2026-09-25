import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/auth.js', () => ({
  getToken: vi.fn().mockReturnValue(null),
  getUser: vi.fn(),
}));

import { getDetectiveCaseReference, hydrateDetectiveCase, hydrateDetectiveDashboard, init } from '../modules/detective.js';

function setLocation(pathname) {
  delete window.location;
  window.location = { pathname, href: '', reload: vi.fn() };
}

describe('modules/detective.js (integration)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.body.dataset.role = 'detective';
  });

  it('getDetectiveCaseReference extracts the reference', () => {
    setLocation('/detective/dockets/CD-2');
    expect(getDetectiveCaseReference()).toBe('CD-2');
  });

  it('hydrateDetectiveDashboard filters to REGISTERED cases only', async () => {
    document.body.innerHTML = '<div id="detectiveInvestigationList"></div>';
    setLocation('/detective');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve([
            { case_reference: 'CD-1', status: 'REGISTERED', location: 'Main St' },
            { case_reference: 'CD-2', status: 'DRAFT', location: 'Elm St' },
          ]),
      })
    );

    await hydrateDetectiveDashboard();

    const container = document.getElementById('detectiveInvestigationList');
    expect(container.textContent).toContain('CD-1');
    expect(container.textContent).not.toContain('CD-2');
  });

  it('hydrateDetectiveCase renders detail and wires Start Investigation when no investigation exists yet', async () => {
    document.body.innerHTML = `
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <div id="detectiveDeposition"></div>
      <div id="detectiveStatementBox"></div>
      <ul id="detectiveCaseTimeline"></ul>
      <ul id="detectiveCaseEvidence"></ul>
      <textarea id="investigationNotes"></textarea>
      <button id="saveInvestigationNote"></button>
      <p id="investigationNotesError" class="hidden"></p>
      <div id="detectiveFindingsList"></div>
      <button id="openFindingModal"></button>
      <button id="startInvestigation"></button>
    `;
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/investigation')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ investigation_id: 'INV-1' }) });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ location: 'Main St', status: 'REGISTERED', timeline: [], evidence: [], statements: [], investigation: null }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();
    expect(document.getElementById('detectiveCaseMeta').textContent).toContain('Main St');
    expect(document.getElementById('detectiveCaseMeta').textContent).toContain('Not yet assigned');
    expect(document.getElementById('openFindingModal').disabled).toBe(true);

    document.getElementById('startInvestigation').click();
    await vi.waitFor(() => expect(window.location.href).toBe('/detective/dockets/CD-1'));
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/detective/dockets/CD-1/investigation',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('hydrateDetectiveCase disables Start Investigation and loads findings when an investigation already exists', async () => {
    document.body.innerHTML = `
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <div id="detectiveDeposition"></div>
      <div id="detectiveStatementBox"></div>
      <ul id="detectiveCaseTimeline"></ul>
      <ul id="detectiveCaseEvidence"></ul>
      <textarea id="investigationNotes"></textarea>
      <button id="saveInvestigationNote"></button>
      <p id="investigationNotesError" class="hidden"></p>
      <div id="detectiveFindingsList"></div>
      <div id="detectiveFlagsList"></div>
      <div id="detectiveRelatedCases"></div>
      <button id="openFindingModal"></button>
      <button id="startInvestigation"></button>
    `;
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ finding_type: 'VALID', notes: 'Consistent with evidence.' }]) });
      }
      if (url.endsWith('/flags')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ category: 'INSUFFICIENT_INFORMATION', status: 'OPEN', notes: 'Missing detail from constable.' }]),
        });
      }
      if (url.endsWith('/related')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ relationship_type: 'RELATED_CASE', source_case_reference: 'CD-1', related_case_reference: 'CD-2' }]),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            location: 'Main St',
            status: 'REGISTERED',
            timeline: [],
            evidence: [],
            statements: [],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'OPEN', notes: 'Initial notes.' },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    expect(document.getElementById('detectiveCaseMeta').textContent).toContain('DET-1');
    expect(document.getElementById('investigationNotes').value).toBe('Initial notes.');
    expect(document.getElementById('startInvestigation').disabled).toBe(true);
    expect(document.getElementById('openFindingModal').disabled).toBe(false);
    expect(document.getElementById('detectiveFindingsList').textContent).toContain('Consistent with evidence.');
    await vi.waitFor(() => expect(document.getElementById('detectiveFlagsList').textContent).toContain('Missing detail from constable.'));
    expect(document.getElementById('detectiveRelatedCases').textContent).toContain('CD-2');
  });

  it('shows placeholder copy for flags/related when no investigation has started yet, without fetching them', async () => {
    document.body.innerHTML = `
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <div id="detectiveDeposition"></div>
      <div id="detectiveStatementBox"></div>
      <ul id="detectiveCaseTimeline"></ul>
      <ul id="detectiveCaseEvidence"></ul>
      <textarea id="investigationNotes"></textarea>
      <button id="saveInvestigationNote"></button>
      <p id="investigationNotesError" class="hidden"></p>
      <div id="detectiveFindingsList"></div>
      <div id="detectiveFlagsList">Start the investigation to review constable-raised flags.</div>
      <div id="detectiveRelatedCases">Start the investigation to review related case links.</div>
      <button id="openFindingModal"></button>
      <button id="startInvestigation"></button>
    `;
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.includes('/flags') || url.includes('/related')) {
        throw new Error(`unexpected pre-investigation fetch to ${url}`);
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ location: 'Main St', status: 'REGISTERED', timeline: [], evidence: [], statements: [], investigation: null }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    expect(document.getElementById('detectiveFlagsList').textContent).toContain('Start the investigation');
    expect(document.getElementById('detectiveRelatedCases').textContent).toContain('Start the investigation');
  });

  function activeInvestigationMarkup() {
    return `
      <span id="detectiveStatusBadge"></span>
      <span id="detectiveFreezeBadge" class="hidden"></span>
      <div id="detectiveFrozenNotice" class="hidden"><p id="detectiveFrozenReason"></p></div>
      <div id="detectiveDocketContent">
        <dl id="detectiveCaseMeta"></dl>
        <div id="detectiveDeposition"></div>
        <div id="detectiveStatementsList"></div>
        <button id="openStatementModal"></button>
        <ul id="detectiveCaseTimeline"></ul>
        <table><tbody id="detectiveCaseEvidence"></tbody></table>
        <textarea id="investigationNotes"></textarea>
        <button id="saveInvestigationNote"></button>
        <p id="investigationNotesError" class="hidden"></p>
        <div id="detectiveFindingsList"></div>
        <div id="detectiveFlagsList"></div>
        <div id="detectiveRelatedCases"></div>
        <div id="detectiveNoteEntriesList"></div>
        <button id="openFindingModal"></button>
        <button id="openCompleteInvestigationModal"></button>
        <button id="openNoteEntryModal"></button>
        <button id="startInvestigation"></button>
      </div>
      <div id="toastContainer"></div>
      <div class="reauth-modal hidden" id="statementModal">
        <textarea id="statementText"></textarea>
        <p id="statementModalError" class="hidden"></p>
        <button id="closeStatementModal"></button>
        <button id="submitStatementModal"></button>
      </div>
      <div class="reauth-modal hidden" id="completeInvestigationModal">
        <select id="completeInvestigationOutcome">
          <option value="VALID">Valid</option>
          <option value="INVALID">Invalid</option>
          <option value="GUILTY">Guilty</option>
          <option value="NOT_GUILTY">Not Guilty</option>
        </select>
        <textarea id="completeInvestigationNotes"></textarea>
        <p id="completeInvestigationModalError" class="hidden"></p>
        <button id="closeCompleteInvestigationModal"></button>
        <button id="submitCompleteInvestigationModal"></button>
      </div>
      <div class="reauth-modal hidden" id="noteEntryModal">
        <select id="noteEntryEvidence"></select>
        <textarea id="noteEntryText"></textarea>
        <p id="noteEntryModalError" class="hidden"></p>
        <button id="closeNoteEntryModal"></button>
        <button id="submitNoteEntryModal"></button>
      </div>
    `;
  }

  it('the Complete Investigation modal posts outcome + final notes and reloads', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            location: 'Main St',
            status: 'REGISTERED',
            timeline: [],
            evidence: [],
            statements: [],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: 'Working notes.' },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();
    expect(document.getElementById('openCompleteInvestigationModal').disabled).toBe(false);

    document.getElementById('openCompleteInvestigationModal').click();
    expect(document.getElementById('completeInvestigationModal').classList.contains('hidden')).toBe(false);

    document.getElementById('completeInvestigationOutcome').value = 'GUILTY';
    document.getElementById('completeInvestigationNotes').value = 'Evidence and testimony are conclusive.';
    document.getElementById('submitCompleteInvestigationModal').click();

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/detective/investigations/INV-1/complete',
        expect.objectContaining({ method: 'POST' })
      )
    );
    const [, options] = fetchMock.mock.calls.find(([url]) => url.endsWith('/complete'));
    expect(JSON.parse(options.body)).toEqual({ outcome: 'GUILTY', final_notes: 'Evidence and testimony are conclusive.' });
    await vi.waitFor(() => expect(sessionStorage.getItem('pdasFlashMessage')).toContain('Investigation completed'));
  });

  it('the Complete Investigation modal requires final reasoning before submitting', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'REGISTERED',
            timeline: [],
            evidence: [],
            statements: [],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: '' },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();
    document.getElementById('openCompleteInvestigationModal').click();
    document.getElementById('submitCompleteInvestigationModal').click();

    expect(document.getElementById('completeInvestigationModalError').classList.contains('hidden')).toBe(false);
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining('/complete'), expect.anything());
  });

  it('adds a note entry optionally linked to an evidence item, and lists it grouped by evidence', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    let noteAdded = false;
    const fetchMock = vi.fn((url, options = {}) => {
      if (url.endsWith('/note-entries') && options.method === 'POST') {
        noteAdded = true;
        expect(JSON.parse(options.body)).toEqual({ note_text: 'Zoomed crop shows forced entry.', evidence_reference: '1' });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ note_id: 'NOTE-1' }) });
      }
      if (url.endsWith('/note-entries')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve(
              noteAdded ? [{ note_id: 'NOTE-1', evidence_reference: '1', note_text: 'Zoomed crop shows forced entry.', created_at: '2026-01-01' }] : []
            ),
        });
      }
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'REGISTERED',
            timeline: [],
            evidence: [{ evidence_id: 1, description: 'Broken window photo' }],
            statements: [],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: '' },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();
    expect(document.getElementById('detectiveNoteEntriesList').textContent).toContain('No notes have been recorded');

    document.getElementById('openNoteEntryModal').click();
    expect(document.getElementById('noteEntryEvidence').options.length).toBeGreaterThan(1);
    document.getElementById('noteEntryEvidence').value = '1';
    document.getElementById('noteEntryText').value = 'Zoomed crop shows forced entry.';
    document.getElementById('submitNoteEntryModal').click();

    await vi.waitFor(() => expect(document.getElementById('detectiveNoteEntriesList').textContent).toContain('Broken window photo'));
    expect(document.getElementById('toastContainer').textContent).toContain('Note recorded');
  });

  it('shows the freeze badge with a reason when the docket is frozen, and hides it otherwise', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'REGISTERED',
            timeline: [],
            evidence: [],
            statements: [],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: '' },
            is_frozen: true,
            freeze_reason: 'IPID took custody of the docket while reviewing escalation ESC-1',
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    const badge = document.getElementById('detectiveFreezeBadge');
    expect(badge.classList.contains('hidden')).toBe(false);
    expect(badge.textContent).toContain('IPID took custody');
  });

  it('shows a completed investigation read-only: findings/notes still load, but the write controls stay disabled', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ finding_type: 'VALID', notes: 'Consistent with evidence.' }]) });
      }
      if (url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ note_id: 'NOTE-1', evidence_reference: null, note_text: 'Witness confirmed.', created_at: '2026-01-01' }]) });
      }
      if (url.endsWith('/flags') || url.endsWith('/related')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'REGISTERED',
            timeline: [],
            evidence: [],
            statements: [],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'COMPLETED', notes: 'Working notes.', outcome: 'VALID' },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    expect(document.getElementById('detectiveFindingsList').textContent).toContain('Consistent with evidence.');
    expect(document.getElementById('detectiveNoteEntriesList').textContent).toContain('Witness confirmed.');
    expect(document.getElementById('startInvestigation').textContent).toContain('COMPLETED');
    expect(document.getElementById('openFindingModal').disabled).toBe(true);
    expect(document.getElementById('openCompleteInvestigationModal').disabled).toBe(true);
    expect(document.getElementById('openNoteEntryModal').disabled).toBe(true);
    expect(document.getElementById('saveInvestigationNote').disabled).toBe(true);
  });

  it('adds a victim statement and shows it alongside the existing ones', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    let statementAdded = false;
    const fetchMock = vi.fn((url, options = {}) => {
      if (url.endsWith('/statements') && options.method === 'POST') {
        statementAdded = true;
        expect(JSON.parse(options.body)).toEqual({ statement_text: 'Witness confirms seeing the suspect flee northbound.' });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ statement_id: 2, recorded_by_role: 'detective' }) });
      }
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'REGISTERED',
            timeline: [],
            evidence: [],
            statements: statementAdded
              ? [
                  { statement_text: 'Someone broke my window.', created_at: '2026-01-01' },
                  { statement_text: 'Witness confirms seeing the suspect flee northbound.', recorded_by: 'DET-1', recorded_by_role: 'detective' },
                ]
              : [{ statement_text: 'Someone broke my window.', created_at: '2026-01-01' }],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: '' },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();
    expect(document.getElementById('detectiveStatementsList').textContent).toContain('Someone broke my window.');

    document.getElementById('openStatementModal').click();
    document.getElementById('statementText').value = 'Witness confirms seeing the suspect flee northbound.';
    document.getElementById('submitStatementModal').click();

    await vi.waitFor(() => expect(document.getElementById('detectiveStatementsList').textContent).toContain('Witness confirms seeing the suspect flee northbound.'));
    expect(document.getElementById('detectiveStatementsList').textContent).toContain('detective');
    expect(document.getElementById('toastContainer').textContent).toContain('Statement recorded');
  });

  it('shows the "Case Frozen" notice and withholds case content while the docket is frozen', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        throw new Error(`unexpected fetch to ${url} for a frozen docket`);
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            case_reference: 'CD-1',
            status: 'REGISTERED',
            is_frozen: true,
            freeze_status: 'FROZEN',
            freeze_reason: 'IPID uphold decision for escalation ESC-1',
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    expect(document.getElementById('detectiveFrozenNotice').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('detectiveFrozenReason').textContent).toContain('IPID uphold decision');
    expect(document.getElementById('detectiveDocketContent').classList.contains('hidden')).toBe(true);
    expect(document.getElementById('detectiveCaseMeta').textContent).toBe('');
    expect(document.getElementById('detectiveFreezeBadge').classList.contains('hidden')).toBe(false);
  });

  it('init does nothing on a page with no detective containers or matching path', () => {
    document.body.innerHTML = '<div id="somethingElse"></div>';
    setLocation('/citizen');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    init();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
