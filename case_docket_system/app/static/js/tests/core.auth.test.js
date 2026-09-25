import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  bindLoginForm,
  bindLogoutButton,
  clearSession,
  getToken,
  getUser,
  isAuthenticated,
  requireRole,
  routeByRole,
  setSession,
} from '../core/auth.js';

function clearBrowserState() {
  localStorage.clear();
  ['pdas_session_token', 'pdas_user'].forEach((name) => {
    document.cookie = `${name}=; path=/; max-age=0`;
  });
}

describe('core/auth.js', () => {
  beforeEach(() => {
    clearBrowserState();
  });

  afterEach(() => {
    clearBrowserState();
  });

  describe('setSession / getToken / getUser / clearSession (unit)', () => {
    it('stores the token and user in localStorage', () => {
      setSession('token-123', { role: 'citizen', full_name: 'Jane Citizen' });

      expect(getToken()).toBe('token-123');
      expect(getUser()).toEqual({ role: 'citizen', full_name: 'Jane Citizen' });
    });

    it('also mirrors the session into cookies so server-rendered pages can read it', () => {
      setSession('token-456', { role: 'constable' });

      expect(document.cookie).toContain('pdas_session_token=token-456');
      expect(document.cookie).toContain('pdas_user=');
    });

    it('falls back to cookies when localStorage is empty', () => {
      setSession('token-789', { role: 'detective' });
      localStorage.clear();

      expect(getToken()).toBe('token-789');
      expect(getUser()).toEqual({ role: 'detective' });
    });

    it('returns null from getUser when the stored cookie is malformed JSON', () => {
      document.cookie = 'pdas_user=not-json; path=/';

      expect(getUser()).toBeNull();
    });

    it('clearSession removes both localStorage and cookie state', () => {
      setSession('token-abc', { role: 'ipid' });
      clearSession();

      expect(getToken()).toBeNull();
      expect(getUser()).toBeNull();
    });
  });

  describe('isAuthenticated', () => {
    it('is false with no session and true once a token is set', () => {
      expect(isAuthenticated()).toBe(false);
      setSession('tok', { role: 'citizen' });
      expect(isAuthenticated()).toBe(true);
    });
  });

  describe('routeByRole', () => {
    it('routes each known role to its dashboard, and unknown roles to /login', () => {
      const cases = [
        ['citizen', '/citizen'],
        ['constable', '/constable'],
        ['detective', '/detective'],
        ['station_commander', '/station-commander'],
        ['ipid', '/ipid'],
        [undefined, '/login'],
        ['not-a-role', '/login'],
      ];

      for (const [role, expected] of cases) {
        delete window.location;
        window.location = { href: '' };
        routeByRole(role);
        expect(window.location.href).toBe(expected);
      }
    });
  });

  describe('requireRole', () => {
    it('returns true and does not redirect when the session role matches', () => {
      setSession('tok', { role: 'detective' });
      delete window.location;
      window.location = { href: '' };

      expect(requireRole('detective')).toBe(true);
      expect(window.location.href).toBe('');
    });

    it('redirects to the actual role home when roles do not match', () => {
      setSession('tok', { role: 'citizen' });
      delete window.location;
      window.location = { href: '' };

      expect(requireRole('detective')).toBe(false);
      expect(window.location.href).toBe('/citizen');
    });

    it('redirects to /login when there is no session at all', () => {
      delete window.location;
      window.location = { href: '' };

      expect(requireRole('detective')).toBe(false);
      expect(window.location.href).toBe('/login');
    });
  });

  describe('bindLoginForm (integration: form submit -> session -> redirect)', () => {
    function buildLoginDom() {
      document.body.innerHTML = `
        <form id="loginForm">
          <input id="testId" value="2200223333111" />
        </form>
        <div id="loginError" class="hidden"></div>
      `;
      return {
        form: document.getElementById('loginForm'),
        errorBox: document.getElementById('loginError'),
      };
    }

    it('on success: stores the session and routes to the returned role home', async () => {
      const { form, errorBox } = buildLoginDom();
      const login = vi.fn().mockResolvedValue({
        access_token: 'tok-xyz',
        full_name: 'Jane Citizen',
        role: 'citizen',
        test_id: '2200223333111',
      });

      delete window.location;
      window.location = { href: '' };

      bindLoginForm(form, errorBox, { login });
      form.dispatchEvent(new window.Event('submit', { cancelable: true }));
      await vi.waitFor(() => expect(window.location.href).toBe('/citizen'));

      expect(login).toHaveBeenCalledWith('/api/v1/auth/login', {
        method: 'POST',
        body: { test_id: '2200223333111' },
      });
      expect(getToken()).toBe('tok-xyz');
      expect(getUser()).toEqual({ full_name: 'Jane Citizen', role: 'citizen', test_id: '2200223333111' });
    });

    it('on failure: surfaces the error message and does not create a session', async () => {
      const { form, errorBox } = buildLoginDom();
      const login = vi.fn().mockRejectedValue(new Error('Unknown test identity.'));

      bindLoginForm(form, errorBox, { login });
      form.dispatchEvent(new window.Event('submit', { cancelable: true }));

      await vi.waitFor(() => expect(errorBox.classList.contains('hidden')).toBe(false));
      expect(errorBox.textContent).toBe('Unknown test identity.');
      expect(getToken()).toBeNull();
    });
  });

  describe('bindLogoutButton', () => {
    it('clears the session and navigates to /login on click', () => {
      document.body.innerHTML = '<button id="logoutButton"></button>';
      setSession('tok', { role: 'citizen' });
      delete window.location;
      window.location = { href: '' };

      bindLogoutButton(document.getElementById('logoutButton'));
      document.getElementById('logoutButton').click();

      expect(getToken()).toBeNull();
      expect(window.location.href).toBe('/login');
    });
  });
});
