import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/auth.js', () => ({
  getUser: vi.fn(),
  getToken: vi.fn().mockReturnValue(null),
}));

import { getUser } from '../core/auth.js';
import {
  bindCaseLinks,
  bindFilePreview,
  bindReauthModal,
  buildStatusBadge,
  configureReauthModal,
  flashToast,
  populateSelect,
  refreshUserBadge,
  renderDocketCardList,
  renderEvidenceTable,
  renderSlaMeter,
  renderTimelineList,
  setEmptyState,
  showFlashedToast,
  showToast,
} from '../core/ui.js';

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
      ['BREACHED', 'badge badge-breach'],
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

  describe('configureReauthModal + bindReauthModal confirm wiring (system-ish)', () => {
    function reauthMarkup() {
      return `
        <button data-open-reauth id="trigger">Dismiss</button>
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
    }

    it('requires a reason before calling onConfirm', () => {
      document.body.innerHTML = reauthMarkup();
      bindReauthModal();
      const onConfirm = vi.fn();
      configureReauthModal({ targetValue: 'ESC-1', actionLabel: 'Dismiss Escalation', onConfirm });

      document.getElementById('trigger').click();
      document.querySelector('[data-reauth-confirm]').click();

      expect(onConfirm).not.toHaveBeenCalled();
      expect(document.querySelector('[data-reauth-error]').classList.contains('hidden')).toBe(false);
    });

    it('calls onConfirm with the typed reason and closes the modal on success', async () => {
      document.body.innerHTML = reauthMarkup();
      bindReauthModal();
      const onConfirm = vi.fn().mockResolvedValue(undefined);
      configureReauthModal({ targetValue: 'ESC-1', actionLabel: 'Dismiss Escalation', onConfirm });

      document.getElementById('trigger').click();
      document.querySelector('[data-reauth-target]').textContent;
      expect(document.querySelector('[data-reauth-target]').textContent).toBe('ESC-1');
      expect(document.querySelector('[data-reauth-action]').textContent).toBe('Dismiss Escalation');

      document.querySelector('[data-reauth-reason]').value = 'Insufficient statutory grounds.';
      document.querySelector('[data-reauth-confirm]').click();

      await vi.waitFor(() => expect(onConfirm).toHaveBeenCalledWith('Insufficient statutory grounds.'));
      await vi.waitFor(() => expect(document.getElementById('reauthModal').classList.contains('hidden')).toBe(true));
    });

    it('shows a toast (in addition to the inline error) when onConfirm rejects', async () => {
      document.body.innerHTML = `${reauthMarkup()}<div id="toastContainer"></div>`;
      bindReauthModal();
      const onConfirm = vi.fn().mockRejectedValue(new Error('Escalation already resolved.'));
      configureReauthModal({ targetValue: 'ESC-1', actionLabel: 'Uphold Escalation', onConfirm });

      document.getElementById('trigger').click();
      document.querySelector('[data-reauth-reason]').value = 'Corroborated allegation.';
      document.querySelector('[data-reauth-confirm]').click();

      await vi.waitFor(() => expect(document.querySelector('[data-reauth-error]').textContent).toBe('Escalation already resolved.'));
      expect(document.getElementById('reauthModal').classList.contains('hidden')).toBe(false);
      const toast = document.querySelector('.toast-error');
      expect(toast).not.toBeNull();
      expect(toast.textContent).toBe('Escalation already resolved.');
    });
  });

  describe('renderDocketCardList (integration: render + navigate)', () => {
    it('renders cards with a working navigation link', () => {
      const container = document.createElement('div');
      renderDocketCardList(container, [{ case_reference: 'CD-1', location: 'Main St', status: 'REGISTERED' }], {
        linkPrefix: '/detective/dockets/',
      });

      delete window.location;
      window.location = { href: '' };
      container.querySelector('[data-case-link]').click();
      expect(window.location.href).toBe('/detective/dockets/CD-1');
    });

    it('falls back to the empty message when there are no items', () => {
      const container = document.createElement('div');
      renderDocketCardList(container, [], { emptyMessage: 'Nothing here.' });
      expect(container.textContent).toContain('Nothing here.');
    });

    it('shows a FROZEN badge only for items carrying is_frozen', () => {
      const container = document.createElement('div');
      renderDocketCardList(container, [
        { case_reference: 'CD-1', location: 'Main St', status: 'REGISTERED', is_frozen: true },
        { case_reference: 'CD-2', location: 'Elm St', status: 'REGISTERED', is_frozen: false },
      ]);
      const cards = container.querySelectorAll('.docket-card');
      expect(cards[0].textContent).toContain('FROZEN');
      expect(cards[1].textContent).not.toContain('FROZEN');
    });
  });

  describe('renderTimelineList (unit)', () => {
    it('renders one row per event using the given keys', () => {
      const container = document.createElement('ul');
      renderTimelineList(container, [{ action: 'Reassigned', timestamp: '2026-01-01' }], { titleKey: 'action', detailKey: 'timestamp' });
      expect(container.textContent).toContain('Reassigned');
      expect(container.textContent).toContain('2026-01-01');
    });
  });

  describe('renderEvidenceTable (unit)', () => {
    it('renders one row per evidence item with a hash placeholder', () => {
      const body = document.createElement('tbody');
      renderEvidenceTable(body, [{ description: 'Broken window photo', evidence_type: 'photo', status: 'SUBMITTED' }]);
      expect(body.textContent).toContain('Broken window photo');
      expect(body.textContent).toContain('Not yet computed');
    });

    it('shows an empty-state row when there is no evidence', () => {
      const body = document.createElement('tbody');
      renderEvidenceTable(body, []);
      expect(body.textContent).toContain('No evidence has been submitted yet.');
    });

    it('shows the real (truncated) hash and a View button for a file-backed item, and "—" without one', () => {
      const body = document.createElement('tbody');
      renderEvidenceTable(body, [
        { description: 'Broken window photo', sha256_hash: 'a'.repeat(64), storage_reference: 'evidence/abc.jpg' },
        { description: 'No file attached', sha256_hash: null, storage_reference: null },
      ]);
      const rows = body.querySelectorAll('tr');
      expect(rows[0].textContent).toContain('a'.repeat(16));
      expect(rows[0].querySelector('[data-view-evidence-index]')).not.toBeNull();
      expect(rows[1].querySelector('[data-view-evidence-index]')).toBeNull();
      expect(rows[1].textContent).toContain('Not yet computed');
    });
  });

  describe('populateSelect (unit)', () => {
    it('renders one option per item plus a placeholder', () => {
      const select = document.createElement('select');
      populateSelect(select, [{ test_id: 'OFF-1', full_name: 'Officer One', role: 'detective' }], { describeKey: 'role' });
      expect(select.options.length).toBe(2);
      expect(select.options[1].value).toBe('OFF-1');
      expect(select.options[1].textContent).toContain('Officer One');
      expect(select.options[1].textContent).toContain('detective');
    });
  });

  describe('renderSlaMeter (unit)', () => {
    it('renders a breached label when the SLA due date has passed', () => {
      const container = document.createElement('div');
      const handle = renderSlaMeter(container, { sla_due_at: '2000-01-01T00:00:00Z', elapsed_hours: 100, remaining_hours: 0 });
      expect(container.textContent).toContain('breached');
      clearInterval(handle);
    });

    it('is a no-op with an unavailable message when SLA data is missing', () => {
      const container = document.createElement('div');
      const handle = renderSlaMeter(container, null);
      expect(handle).toBeNull();
      expect(container.textContent).toContain('unavailable');
    });
  });

  describe('showToast / flashToast / showFlashedToast (integration: DOM + sessionStorage)', () => {
    beforeEach(() => {
      sessionStorage.clear();
    });

    it('appends a toast with the right type class into #toastContainer', () => {
      document.body.innerHTML = '<div id="toastContainer"></div>';
      showToast('Statement saved.', { type: 'success' });
      const toast = document.querySelector('.toast');
      expect(toast.textContent).toBe('Statement saved.');
      expect(toast.classList.contains('toast-success')).toBe(true);
    });

    it('is a no-op when the container is missing', () => {
      document.body.innerHTML = '';
      expect(() => showToast('ignored')).not.toThrow();
    });

    it('flashToast queues a message that showFlashedToast displays and clears exactly once', () => {
      document.body.innerHTML = '<div id="toastContainer"></div>';
      flashToast('Docket registered successfully.', { type: 'success' });
      expect(sessionStorage.getItem('pdasFlashMessage')).toContain('Docket registered successfully.');

      showFlashedToast();
      expect(document.querySelector('.toast').textContent).toBe('Docket registered successfully.');
      expect(sessionStorage.getItem('pdasFlashMessage')).toBeNull();

      document.body.innerHTML = '<div id="toastContainer"></div>';
      showFlashedToast();
      expect(document.querySelector('.toast')).toBeNull();
    });
  });

  describe('bindFilePreview (integration: DOM)', () => {
    it('shows the selected file name and size, and hides the preview when cleared', () => {
      document.body.innerHTML = `
        <input type="file" id="evidenceFile" />
        <p id="evidenceFilePreview" class="hidden"></p>
      `;
      bindFilePreview('evidenceFile', 'evidenceFilePreview');

      const input = document.getElementById('evidenceFile');
      const file = new File(['x'.repeat(2048)], 'window.jpg', { type: 'image/jpeg' });
      Object.defineProperty(input, 'files', { value: [file], writable: false, configurable: true });
      input.dispatchEvent(new Event('change'));

      const preview = document.getElementById('evidenceFilePreview');
      expect(preview.classList.contains('hidden')).toBe(false);
      expect(preview.textContent).toContain('window.jpg');
      expect(preview.textContent).toContain('2 KB');

      Object.defineProperty(input, 'files', { value: [], writable: false, configurable: true });
      input.dispatchEvent(new Event('change'));
      expect(preview.classList.contains('hidden')).toBe(true);
    });
  });
});
