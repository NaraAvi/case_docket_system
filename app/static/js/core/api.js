/**
 * Thin fetch client shared by every PDAS frontend module.
 */

import { getToken } from './auth.js';

export async function fetchJson(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (options.body && typeof options.body !== 'string') {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }

  const response = await fetch(url, {
    credentials: 'same-origin',
    ...options,
    headers,
    body: options.body && typeof options.body !== 'string' ? JSON.stringify(options.body) : options.body,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const backendMessage = (() => {
      const candidate = payload && (payload.error || payload.message || payload.detail);
      if (typeof candidate === 'string' && candidate.trim()) {
        return candidate.trim();
      }
      if (candidate && typeof candidate === 'object') {
        const nested = candidate.message || candidate.detail || candidate.error;
        if (typeof nested === 'string' && nested.trim()) {
          return nested.trim();
        }
      }
      return 'Request failed.';
    })();
    throw new Error(backendMessage);
  }
  return payload;
}

/**
 * Submit a multipart form (real file upload) with the same JWT/error
 * handling as fetchJson, without JSON-encoding the body.
 */
export async function postForm(url, formData) {
  const headers = {};
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers,
    body: formData,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const backendMessage = (() => {
      const candidate = payload && (payload.error || payload.message || payload.detail);
      if (typeof candidate === 'string' && candidate.trim()) {
        return candidate.trim();
      }
      if (candidate && typeof candidate === 'object') {
        const nested = candidate.message || candidate.detail || candidate.error;
        if (typeof nested === 'string' && nested.trim()) {
          return nested.trim();
        }
      }
      return 'Request failed.';
    })();
    throw new Error(backendMessage);
  }
  return payload;
}

/**
 * Open an authenticated file (evidence/recording) in a new tab. Plain
 * `<a href>` links can't carry the JWT Bearer header, so the file is
 * fetched as a blob and handed to the browser via an object URL instead.
 */
export async function openMediaFile(url) {
  const headers = {};
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(url, { credentials: 'same-origin', headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || 'Unable to load file.');
  }
  const blob = await response.blob();
  const blobUrl = URL.createObjectURL(blob);
  window.open(blobUrl, '_blank');
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
}

export async function fetchMediaBlobUrl(url) {
  const headers = {};
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(url, { credentials: 'same-origin', headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || 'Unable to load media.');
  }
  const blob = await response.blob();
  const blobUrl = URL.createObjectURL(blob);
  // Caller is responsible for revoking the URL when appropriate
  return blobUrl;
}
