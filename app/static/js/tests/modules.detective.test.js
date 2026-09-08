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

  it('hydrateDetectiveCase renders detail and wires Start Investigation', async () => {
    document.body.innerHTML = `
      <dl id="detectiveCaseMeta"></dl>
      <ul id="detectiveCaseTimeline"></ul>
      <ul id="detectiveCaseEvidence"></ul>
      <button id="startInvestigation"></button>
    `;
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/investigation')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ investigation_id: 'INV-1' }) });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ title: 'Assault case', status: 'REGISTERED', timeline: [], evidence: [] }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();
    expect(document.getElementById('detectiveCaseMeta').textContent).toContain('Assault case');

    document.getElementById('startInvestigation').click();
    await vi.waitFor(() => expect(window.location.href).toBe('/detective/dockets/CD-1'));
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/detective/dockets/CD-1/investigation',
      expect.objectContaining({ method: 'POST' })
    );
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
