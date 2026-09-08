import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/auth.js', () => ({
  getToken: vi.fn().mockReturnValue(null),
  getUser: vi.fn(),
}));

import { getDetectiveCaseReference, hydrateDetectiveCase, hydrateDetectiveDashboard, init } from '../modules/detective.js';

function setLocation(pathname) {
  delete window.location;
  window.location = { pathname, href: '' };
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
      <button id="openFindingModal"></button>
      <button id="startInvestigation"></button>
    `;
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ finding_type: 'VALID', notes: 'Consistent with evidence.' }]) });
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
