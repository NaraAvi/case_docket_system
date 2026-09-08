import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/auth.js', () => ({
  getUser: vi.fn(),
}));

import { getUser } from '../core/auth.js';
import { bindCaseLinks, bindReauthModal, buildStatusBadge, refreshUserBadge, setEmptyState } from '../core/ui.js';

describe('core/ui.js', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  describe('buildStatusBadge (unit)', () => {
    it.each([
      ['REGISTERED', 'badge badge-verified'],
      ['VERIFIED', 'badge badge-verified'],
      ['ACTIVE', 'badge badge-verified'],
      ['FROZEN', 'badge badge-warning'],
      ['AWAITING_CONSTABLE_REGISTRATION', 'badge badge-warning'],
      ['PENDING_REVIEW', 'badge badge-warning'],
      ['DRAFT', 'badge badge-muted'],
      [undefined, 'badge badge-muted'],
      [null, 'badge badge-muted'],
    ])('maps status %s -> %s', (status, expected) => {
      expect(buildStatusBadge(status)).toBe(expected);
    });

    it('is case-insensitive', () => {
      expect(buildStatusBadge('registered')).toBe('badge badge-verified');
    });
  });

  describe('setEmptyState (unit)', () => {
    it('renders the message into the container', () => {
      const container = document.createElement('div');
      setEmptyState(container, 'Nothing here yet.');
      expect(container.innerHTML).toContain('Nothing here yet.');
      expect(container.querySelector('.empty-state')).not.toBeNull();
    });

    it('is a no-op when the container is missing', () => {
      expect(() => setEmptyState(null, 'ignored')).not.toThrow();
    });
  });

  describe('bindCaseLinks (integration: click -> navigation)', () => {
    it('navigates to the data-case-link target when clicked', () => {
      document.body.innerHTML = `
        <div id="list">
          <button data-case-link="/citizen/dockets/CD-1">Open</button>
        </div>
      `;
      delete window.location;
      window.location = { href: '' };

      bindCaseLinks(document.getElementById('list'));
      document.querySelector('[data-case-link]').click();

      expect(window.location.href).toBe('/citizen/dockets/CD-1');
    });
  });

  describe('refreshUserBadge (integration with auth.getUser)', () => {
    it('renders the name and role when a user is present', () => {
      document.body.innerHTML = '<div id="userBadge"></div>';
      getUser.mockReturnValue({ full_name: 'Jane Citizen', role: 'citizen' });

      refreshUserBadge();

      expect(document.getElementById('userBadge').textContent).toBe('Jane Citizen • citizen');
    });

    it('leaves the badge untouched when there is no user', () => {
      document.body.innerHTML = '<div id="userBadge">Authenticated User</div>';
      getUser.mockReturnValue(null);

      refreshUserBadge();

      expect(document.getElementById('userBadge').textContent).toBe('Authenticated User');
    });
  });

  describe('bindReauthModal (system-ish: full modal open/close cycle)', () => {
    it('opens the modal on a trigger click and closes it on the close button', () => {
      document.body.innerHTML = `
        <button data-open-reauth>Flag Concern</button>
        <div id="reauthModal" class="hidden">
          <button data-close-reauth>Cancel</button>
        </div>
      `;

      bindReauthModal();

      document.querySelector('[data-open-reauth]').click();
      expect(document.getElementById('reauthModal').classList.contains('hidden')).toBe(false);

      document.querySelector('[data-close-reauth]').click();
      expect(document.getElementById('reauthModal').classList.contains('hidden')).toBe(true);
    });
  });
});
