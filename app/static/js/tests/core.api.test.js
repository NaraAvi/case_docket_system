import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/auth.js', () => ({
  getToken: vi.fn(),
}));

import { getToken } from '../core/auth.js';
import { fetchJson } from '../core/api.js';

function mockFetchResponse({ ok, status = 200, json }) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(json),
  });
}

describe('core/api.js fetchJson (unit, auth.js mocked)', () => {
  beforeEach(() => {
    getToken.mockReturnValue(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('injects a Bearer header when a token is present', async () => {
    getToken.mockReturnValue('secret-token');
    const fetchMock = mockFetchResponse({ ok: true, json: { ok: true } });
    vi.stubGlobal('fetch', fetchMock);

    await fetchJson('/api/v1/citizen/dockets');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/citizen/dockets',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer secret-token' }),
      })
    );
  });

  it('omits the Authorization header when there is no token', async () => {
    const fetchMock = mockFetchResponse({ ok: true, json: {} });
    vi.stubGlobal('fetch', fetchMock);

    await fetchJson('/api/v1/citizen/dockets');

    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers.Authorization).toBeUndefined();
  });

  it('JSON-encodes a non-string body and sets Content-Type', async () => {
    const fetchMock = mockFetchResponse({ ok: true, json: { case_reference: 'CD-1' } });
    vi.stubGlobal('fetch', fetchMock);

    await fetchJson('/api/v1/citizen/dockets', { method: 'POST', body: { title: 'Broken window' } });

    const [, options] = fetchMock.mock.calls[0];
    expect(options.body).toBe(JSON.stringify({ title: 'Broken window' }));
    expect(options.headers['Content-Type']).toBe('application/json');
  });

  it('leaves a string body untouched (e.g. FormData-adjacent callers)', async () => {
    const fetchMock = mockFetchResponse({ ok: true, json: {} });
    vi.stubGlobal('fetch', fetchMock);

    await fetchJson('/api/v1/x', { method: 'POST', body: 'raw-string-body' });

    const [, options] = fetchMock.mock.calls[0];
    expect(options.body).toBe('raw-string-body');
  });

  it('resolves with the parsed JSON payload on a 2xx response', async () => {
    vi.stubGlobal('fetch', mockFetchResponse({ ok: true, json: { case_reference: 'CD-1' } }));

    await expect(fetchJson('/api/v1/citizen/dockets')).resolves.toEqual({ case_reference: 'CD-1' });
  });

  it('rejects using the server-provided error message on a non-2xx response', async () => {
    vi.stubGlobal('fetch', mockFetchResponse({ ok: false, status: 400, json: { error: 'Description too short.' } }));

    await expect(fetchJson('/api/v1/citizen/dockets')).rejects.toThrow('Description too short.');
  });

  it('falls back to a generic message when the error body is not JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error('not json')),
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchJson('/api/v1/citizen/dockets')).rejects.toThrow('Request failed.');
  });
});
