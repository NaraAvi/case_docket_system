/**
 * Shared DOM helpers: status badges, empty states, the user badge and the
 * high-accountability re-authorization modal used across every dashboard.
 */

import { getUser } from './auth.js';

export function buildStatusBadge(status) {
  const value = (status || 'UNKNOWN').toString().toUpperCase();
  if (value.includes('REGISTERED') || value.includes('VERIFIED') || value.includes('ACTIVE')) {
    return 'badge badge-verified';
  }
  if (value.includes('FROZEN') || value.includes('AWAITING') || value.includes('PENDING') || value.includes('REVIEW')) {
    return 'badge badge-warning';
  }
  return 'badge badge-muted';
}

export function setEmptyState(container, message) {
  if (!container) {
    return;
  }
  container.innerHTML = `<div class="empty-state">${message}</div>`;
}

export function bindCaseLinks(container) {
  if (!container) {
    return;
  }
  container.querySelectorAll('[data-case-link]').forEach((button) => {
    button.addEventListener('click', () => {
      window.location.href = button.dataset.caseLink;
    });
  });
}

export function refreshUserBadge() {
  const user = getUser();
  const badge = document.getElementById('userBadge');
  if (badge && user) {
    badge.textContent = `${user.full_name || user.role || 'User'} • ${user.role}`;
  }
}

export function bindReauthModal() {
  const reauthModal = document.getElementById('reauthModal');
  document.querySelectorAll('[data-open-reauth]').forEach((button) => {
    button.addEventListener('click', () => {
      if (reauthModal) {
        reauthModal.classList.remove('hidden');
      }
    });
  });

  const closeButton = document.querySelector('[data-close-reauth]');
  if (closeButton && reauthModal) {
    closeButton.addEventListener('click', () => reauthModal.classList.add('hidden'));
  }
}
