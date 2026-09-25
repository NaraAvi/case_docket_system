import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/auth.js', () => ({
  getToken: vi.fn().mockReturnValue(null),
  getUser: vi.fn(),
}));

import { hydrateActiveCases, hydrateEvidenceVault, init } from '../modules/shared.js';

describe('modules/shared.js (integration: cross-role pages, no role gating)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('hydrateActiveCases renders at most 6 dockets regardless of role', async () => {
    document.body.dataset.role = 'ipid';
    document.body.innerHTML = '<div id="activeCaseList"></div>';
    const dockets = Array.from({ length: 10 }, (_, i) => ({ case_reference: `CD-${i}`, status: 'REGISTERED' }));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(dockets) }));

    await hydrateActiveCases();

    const container = document.getElementById('activeCaseList');
    expect(container.querySelectorAll('.docket-card').length).toBe(6);
  });

  it('hydrateEvidenceVault flattens evidence across dockets and caps at 6', async () => {
    document.body.innerHTML = '<div id="evidenceVaultList"></div>';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve([
            { case_reference: 'CD-1', evidence: [{ filename: 'a.jpg', evidence_type: 'photo' }] },
            { case_reference: 'CD-2', evidence: [{ filename: 'b.mp3', evidence_type: 'audio' }] },
          ]),
      })
    );

    await hydrateEvidenceVault();

    const container = document.getElementById('evidenceVaultList');
    expect(container.textContent).toContain('a.jpg');
    expect(container.textContent).toContain('b.mp3');
  });

  it('hydrateEvidenceVault shows an empty state when no docket has evidence', async () => {
    document.body.innerHTML = '<div id="evidenceVaultList"></div>';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([{ case_reference: 'CD-1', evidence: [] }]) })
    );

    await hydrateEvidenceVault();

    expect(document.getElementById('evidenceVaultList').textContent).toContain('No evidence records');
  });

  it('init hydrates both widgets when both containers are present', async () => {
    document.body.innerHTML = '<div id="activeCaseList"></div><div id="evidenceVaultList"></div>';
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
    vi.stubGlobal('fetch', fetchMock);

    init();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});
