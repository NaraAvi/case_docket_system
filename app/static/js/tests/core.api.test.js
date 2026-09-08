import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/auth.js', () => ({
  getToken: vi.fn(),
}));

import { getToken } from '../core/auth.js';
import { fetchJson, openMediaFile, postForm } from '../core/api.js';

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

describe('core/api.js postForm (unit, auth.js mocked)', () => {
  beforeEach(() => {
    getToken.mockReturnValue(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the FormData body untouched with a Bearer header, no Content-Type override', async () => {
    getToken.mockReturnValue('secret-token');
    const fetchMock = mockFetchResponse({ ok: true, json: { evidence_id: 1 } });
    vi.stubGlobal('fetch', fetchMock);

    const formData = new FormData();
    formData.append('file', new File(['bytes'], 'evidence.jpg'));

    await postForm('/api/v1/citizen/dockets/CD-1/evidence', formData);

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/citizen/dockets/CD-1/evidence');
    expect(options.method).toBe('POST');
    expect(options.body).toBe(formData);
    expect(options.headers.Authorization).toBe('Bearer secret-token');
    expect(options.headers['Content-Type']).toBeUndefined();
  });

  it('rejects using the server-provided error message on failure', async () => {
    vi.stubGlobal('fetch', mockFetchResponse({ ok: false, status: 400, json: { error: 'A file is required.' } }));

    await expect(postForm('/api/v1/x', new FormData())).rejects.toThrow('A file is required.');
  });
});

describe('core/api.js openMediaFile (unit, auth.js mocked)', () => {
  beforeEach(() => {
    getToken.mockReturnValue(null);
    if (!globalThis.URL.createObjectURL) {
      globalThis.URL.createObjectURL = () => 'blob:mock';
      globalThis.URL.revokeObjectURL = () => {};
    }
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('fetches the file with a Bearer header and opens a blob URL in a new tab', async () => {
    getToken.mockReturnValue('secret-token');
    const blob = new Blob(['bytes']);
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: () => Promise.resolve(blob) });
    vi.stubGlobal('fetch', fetchMock);
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-url');
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => {});

    await openMediaFile('/api/v1/media/evidence/abc.jpg');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/media/evidence/abc.jpg',
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer secret-token' }) })
    );
    expect(openSpy).toHaveBeenCalledWith('blob:mock-url', '_blank');
    createObjectURLSpy.mockRestore();
    openSpy.mockRestore();
  });

  it('throws the server error message when the file cannot be loaded', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve({ error: 'Forbidden.' }) })
    );

    await expect(openMediaFile('/api/v1/media/evidence/abc.jpg')).rejects.toThrow('Forbidden.');
  });
});
