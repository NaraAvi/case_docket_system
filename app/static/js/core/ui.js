/**
 * Shared DOM helpers: status badges, empty states, the user badge and the
 * high-accountability re-authorization modal used across every dashboard.
 */

import { getUser } from './auth.js';
import { openMediaFile } from './api.js';

const FLASH_STORAGE_KEY = 'pdasFlashMessage';

/**
 * Show a transient toast notification (base.html#toastContainer). Used for
 * immediate confirmation of an action taken on the current page.
 */
export function showToast(message, { type = 'success', duration = 4000 } = {}) {
  const container = document.getElementById('toastContainer');
  if (!container || !message) {
    return;
  }
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add('toast-visible'));
  setTimeout(() => {
    toast.classList.remove('toast-visible');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

/**
 * Queue a toast to show after a redirect/reload (sessionStorage survives
 * navigation within the tab). Call showFlashedToast() on the next page's
 * load to display and clear it -- pdas_app.js does this automatically.
 */
export function flashToast(message, { type = 'success' } = {}) {
  try {
    sessionStorage.setItem(FLASH_STORAGE_KEY, JSON.stringify({ message, type }));
  } catch (error) {
    // sessionStorage unavailable (private mode, etc.) -- the toast is skipped, not fatal.
  }
}

export function showFlashedToast() {
  let stored;
  try {
    stored = sessionStorage.getItem(FLASH_STORAGE_KEY);
    if (stored) {
      sessionStorage.removeItem(FLASH_STORAGE_KEY);
    }
  } catch (error) {
    return;
  }
  if (!stored) {
    return;
  }
  try {
    const { message, type } = JSON.parse(stored);
    showToast(message, { type });
  } catch (error) {
    // malformed stored value -- nothing to show.
  }
}

export function buildStatusBadge(status) {
  const value = (status || 'UNKNOWN').toString().toUpperCase();
  if (value.includes('BREACHED')) {
    return 'badge badge-breach';
  }
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

let activeReauthHandler = null;

/**
 * Populate the shared high-accountability modal (base.html #reauthModal) for
 * one specific action and register what happens on confirm. The modal itself
 * stays generic; callers (e.g. modules/ipid.js) supply the target/action
 * copy and an async onConfirm(reason) that performs the real request.
 */
export function configureReauthModal({ targetLabel, targetValue, actionLabel, subtitle, confirmLabel = 'Confirm Decision', onConfirm }) {
  const modal = document.getElementById('reauthModal');
  if (!modal) {
    return;
  }

  const targetRow = modal.querySelector('.field-row label');
  if (targetRow && targetLabel !== undefined) {
    targetRow.textContent = targetLabel;
  }
  const targetValueEl = modal.querySelector('[data-reauth-target]');
  if (targetValueEl && targetValue !== undefined) {
    targetValueEl.textContent = targetValue;
  }
  const actionEl = modal.querySelector('[data-reauth-action]');
  if (actionEl && actionLabel !== undefined) {
    actionEl.textContent = actionLabel;
  }
  const subtitleEl = modal.querySelector('[data-reauth-subtitle]');
  if (subtitleEl && subtitle !== undefined) {
    subtitleEl.textContent = subtitle;
  }
  const confirmBtn = modal.querySelector('[data-reauth-confirm]');
  if (confirmBtn) {
    confirmBtn.textContent = confirmLabel;
  }
  const textarea = modal.querySelector('[data-reauth-reason]');
  if (textarea) {
    textarea.value = '';
  }
  const errorEl = modal.querySelector('[data-reauth-error]');
  if (errorEl) {
    errorEl.textContent = '';
    errorEl.classList.add('hidden');
  }

  activeReauthHandler = async () => {
    const reason = textarea ? textarea.value.trim() : '';
    if (!reason) {
      if (errorEl) {
        errorEl.textContent = 'A reason is required.';
        errorEl.classList.remove('hidden');
      }
      return;
    }
    try {
      await onConfirm(reason);
      modal.classList.add('hidden');
    } catch (error) {
      if (errorEl) {
        errorEl.textContent = error.message || 'Action failed.';
        errorEl.classList.remove('hidden');
      }
      showToast(error.message || 'Action failed.', { type: 'error' });
    }
  };
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

  const confirmButton = reauthModal ? reauthModal.querySelector('[data-reauth-confirm]') : null;
  if (confirmButton) {
    confirmButton.addEventListener('click', () => {
      if (activeReauthHandler) {
        activeReauthHandler();
      }
    });
  }
}

/**
 * Render one docket/case card matching the markup every dashboard queue
 * (constable, detective, station commander, IPID, active cases) previously
 * duplicated inline as its own template literal.
 */
function resolveOption(value, item, fallback) {
  if (typeof value === 'function') {
    return value(item) ?? fallback;
  }
  return value ?? fallback;
}

export function renderDocketCard(item, { reference, title, linkPrefix, actionLabel = 'Open', status, badges } = {}) {
  const referenceValue = resolveOption(reference, item, item.case_reference ?? item.escalation_id ?? '');
  const titleValue = resolveOption(title, item, item.location ?? item.title ?? 'Details unavailable');
  const statusValue = resolveOption(status, item, item.status ?? 'UNKNOWN');
  const link = linkPrefix ? `${linkPrefix}${referenceValue}` : null;
  // `is_frozen` is only present on payloads that already carry freeze state
  // (e.g. the shared station-commander docket list); anything else (an
  // escalation, a disciplinary case, an SLA-breach row) simply omits it.
  const frozenBadge = item.is_frozen ? '<span class="badge badge-warning">FROZEN</span>' : '';
  // Optional extra badges (e.g. the statutory-mandate marker); each entry is
  // `{ label, className?, title? }`, supplied per item by the caller.
  const extraBadges = (resolveOption(badges, item, []) || [])
    .map((badge) => `<span class="badge ${badge.className || 'badge-statute'}"${badge.title ? ` title="${badge.title}"` : ''}>${badge.label}</span>`)
    .join('');

  return `
    <article class="docket-card">
      <div class="meta-wrap">
        <strong>${referenceValue}</strong>
        <span>${titleValue}</span>
      </div>
      <div class="stack-row">
        <span class="${buildStatusBadge(statusValue)}">${statusValue}</span>
        ${frozenBadge}
        ${extraBadges}
        ${link ? `<button class="secondary-btn small-btn" type="button" data-case-link="${link}">${actionLabel}</button>` : ''}
      </div>
    </article>
  `;
}

/**
 * Render a list of docket cards into a container and wire up navigation,
 * or fall back to an empty-state message.
 */
export function renderDocketCardList(container, items, options = {}) {
  if (!container) {
    return;
  }
  if (!items || !items.length) {
    setEmptyState(container, options.emptyMessage || 'No records are currently available.');
    return;
  }
  container.innerHTML = items.map((item) => renderDocketCard(item, options)).join('');
  bindCaseLinks(container);
}

/**
 * Render every statement recorded on a docket -- the citizen's own plus any
 * added by a detective or IPID reviewer -- as a list, newest first isn't
 * assumed; items render in the order the API returns them. Shared by every
 * role's docket detail view so a statement recorded by one role is visible
 * to every other role handling the case.
 */
export function renderStatementList(container, statements) {
  if (!container) {
    return;
  }
  const items = Array.isArray(statements) ? statements : [];
  if (!items.length) {
    container.innerHTML = '<div class="empty-state">No statements have been recorded yet.</div>';
    return;
  }
  container.innerHTML = items
    .map((statement) => {
      const recordedBy = statement.recorded_by_role ? `${statement.recorded_by_role} (${statement.recorded_by})` : 'Citizen';
      return `
        <article class="mini-case-card">
          <div class="stack-row" style="justify-content:space-between;">
            <strong>${recordedBy}</strong>
            <span>${statement.created_at || ''}</span>
          </div>
          <p>${statement.statement_text}</p>
        </article>
      `;
    })
    .join('');
}

/**
 * Render a chronological event list (audit trail, case timeline) into a
 * `<ul class="timeline-list">` container, matching the structure produced by
 * components/_timeline.html.
 */
export function renderTimelineList(container, items, { titleKey = 'event_type', detailKey = 'timestamp', fallbackTitle = 'Event', fallbackDetail = 'No timestamp' } = {}) {
  if (!container) {
    return;
  }
  const rows = Array.isArray(items) && items.length ? items : [{}];
  container.innerHTML = rows
    .map((event) => `<li><span class="timeline-dot"></span><div><strong>${event[titleKey] || fallbackTitle}</strong><small>${event[detailKey] || fallbackDetail}</small></div></li>`)
    .join('');
}

/**
 * Render evidence rows into a `<tbody>` container, matching the table
 * structure produced by components/_evidence_table.html. SHA-256 hashing is
 * Milestone 6 scope, so the hash column reads a placeholder until then.
 */

/**
 * A small "View" link for one uploaded file (evidence or a recording),
 * given its `storage_reference` (e.g. "recordings/<uuid>_name.wav"). Pair
 * with bindMediaViewButtons() after inserting the returned HTML into the DOM.
 */
export function renderMediaViewButton(storageReference, label = 'View recording') {
  if (!storageReference) {
    return '';
  }
  return `<button type="button" class="link-btn" data-view-media="${storageReference}">${label}</button>`;
}

export function bindMediaViewButtons(container) {
  if (!container) {
    return;
  }
  container.querySelectorAll('[data-view-media]').forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        await openMediaFile(`/api/v1/media/${button.dataset.viewMedia}`);
      } catch (error) {
        showToast(error.message || 'Unable to open file.', { type: 'error' });
      }
    });
  });
}

export function renderEvidenceTable(body, items) {
  if (!body) {
    return;
  }
  if (!Array.isArray(items) || !items.length) {
    body.innerHTML = '<tr><td colspan="6">No evidence has been submitted yet.</td></tr>';
    return;
  }
  body.innerHTML = items
    .map((item, index) => {
      const hasFile = Boolean(item.storage_reference);
      return `
        <tr>
          <td>${item.description || item.filename || 'Evidence record'}</td>
          <td>${item.evidence_type || 'Unspecified'}</td>
          <td>${item.source || item.submitted_by_role || 'Unknown'}</td>
          <td><span class="${buildStatusBadge(item.status)}">${item.status || 'SUBMITTED'}</span></td>
          <td class="hash-cell">${item.sha256_hash ? item.sha256_hash.slice(0, 16) + '…' : 'Not yet computed'}</td>
          <td>${hasFile ? `<button type="button" class="link-btn" data-view-evidence-index="${index}">View</button>` : '—'}</td>
        </tr>
      `;
    })
    .join('');

  body.querySelectorAll('[data-view-evidence-index]').forEach((button) => {
    button.addEventListener('click', async () => {
      const item = items[Number(button.dataset.viewEvidenceIndex)];
      try {
        await openMediaFile(`/api/v1/media/${item.storage_reference}`);
      } catch (error) {
        showToast(error.message || 'Unable to open file.', { type: 'error' });
      }
    });
  });
}

/**
 * Populate a `<select>` with one option per item.
 */
export function populateSelect(select, items, { valueKey = 'test_id', labelKey = 'full_name', placeholder = 'Select an officer…', describeKey } = {}) {
  if (!select) {
    return;
  }
  const options = [`<option value="">${placeholder}</option>`];
  (items || []).forEach((item) => {
    const label = describeKey ? `${item[labelKey]} (${item[describeKey]})` : item[labelKey];
    options.push(`<option value="${item[valueKey]}">${label}</option>`);
  });
  select.innerHTML = options.join('');
}

/**
 * Render a live-updating SLA countdown/progress meter from a deadline
 * timestamp. Returns the interval handle so callers can clear it if the page
 * navigates away, though these pages are single-view and reload on action.
 */
export function renderSlaMeter(container, sla) {
  if (!container || !sla || !sla.sla_due_at) {
    if (container) {
      container.innerHTML = '<div class="field-hint">SLA tracking is unavailable for this docket.</div>';
    }
    return null;
  }

  const dueAt = new Date(sla.sla_due_at).getTime();
  const totalWindowHours = (sla.elapsed_hours || 0) + (sla.remaining_hours || 0);

  const paint = () => {
    const now = Date.now();
    const remainingMs = dueAt - now;
    const breached = remainingMs <= 0;
    const remainingHours = Math.max(remainingMs / 3600000, 0);
    const elapsedHours = totalWindowHours > 0 ? totalWindowHours - remainingHours : 0;
    const percentElapsed = totalWindowHours > 0 ? Math.min((elapsedHours / totalWindowHours) * 100, 100) : 100;

    const hours = Math.floor(Math.max(remainingMs, 0) / 3600000);
    const minutes = Math.floor((Math.max(remainingMs, 0) % 3600000) / 60000);
    const label = breached
      ? `72-hour SLA breached ${Math.abs(hours)}h ago`
      : `${hours}h ${minutes}m remaining of the 72-hour SLA (NI 3/2011)`;

    container.innerHTML = `
      <div class="sla-meter">
        <div class="sla-meter-track"><div class="sla-meter-fill ${breached ? 'sla-breached' : percentElapsed > 75 ? 'sla-warning' : ''}" style="width:${percentElapsed}%"></div></div>
        <span class="sla-meter-label">${label}</span>
      </div>
    `;
  };

  paint();
  return setInterval(paint, 60000);
}

/**
 * Show the chosen file's name/size under a file input as it's picked.
 */
export function bindFilePreview(inputId, previewId) {
  const input = document.getElementById(inputId);
  const preview = document.getElementById(previewId);
  if (!input || !preview) {
    return;
  }
  input.addEventListener('change', () => {
    const file = input.files && input.files[0];
    if (!file) {
      preview.classList.add('hidden');
      return;
    }
    const sizeKb = Math.max(1, Math.round(file.size / 1024));
    preview.textContent = `${file.name} (${sizeKb} KB)`;
    preview.classList.remove('hidden');
  });
}
