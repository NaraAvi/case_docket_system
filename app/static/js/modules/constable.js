/**
 * Constable triage queue and individual docket review workspace.
 */

import { fetchJson } from '../core/api.js';
import { buildStatusBadge, renderDocketCardList, renderEvidenceTable, setEmptyState } from '../core/ui.js';

export function getConstableCaseReference() {
  const match = window.location.pathname.match(/\/constable\/dockets\/([^/]+)/);
  return match ? match[1] : null;
}

export async function hydrateConstableDashboard() {
  const container = document.getElementById('constableQueueState');
  if (!container) {
    return;
  }

  try {
    const queue = await fetchJson('/api/v1/constable/dockets/unregistered');
    renderDocketCardList(container, queue, {
      linkPrefix: '/constable/dockets/',
      title: (item) => item.location,
      status: (item) => item.status || 'AWAITING_CONSTABLE_REGISTRATION',
      emptyMessage: 'No unregistered dockets are currently waiting for triage.',
    });
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load constable queue.');
  }
}

function renderFlags(container, flags, { onEdit } = {}) {
  if (!container) {
    return;
  }
  if (!flags.length) {
    container.innerHTML = '<div class="empty-state">No potential invalidity flags have been raised.</div>';
    return;
  }
  container.innerHTML = flags
    .map(
      (flag) => `
        <article class="mini-case-card">
          <div class="stack-row" style="justify-content:space-between;">
            <strong>${flag.category}</strong>
            <span class="${buildStatusBadge(flag.status)}">${flag.status}</span>
          </div>
          <p>${flag.notes}</p>
          <button class="secondary-btn small-btn" type="button" data-flag-id="${flag.flag_id}">Update Flag</button>
        </article>
      `
    )
    .join('');

  container.querySelectorAll('[data-flag-id]').forEach((button) => {
    button.addEventListener('click', () => {
      const flag = flags.find((item) => item.flag_id === button.dataset.flagId);
      if (flag && onEdit) {
        onEdit(flag);
      }
    });
  });
}

function bindFlagModal(caseReference, { onSaved } = {}) {
  const modal = document.getElementById('flagModal');
  const openButton = document.getElementById('openFlagModal');
  const closeButton = document.getElementById('closeFlagModal');
  const submitButton = document.getElementById('submitFlagModal');
  const titleEl = document.getElementById('flagModalTitle');
  const categorySelect = document.getElementById('flagCategory');
  const statusSelect = document.getElementById('flagStatus');
  const notesField = document.getElementById('flagNotes');
  const errorEl = document.getElementById('flagModalError');

  if (!modal || !openButton) {
    return { openForEdit: () => {} };
  }

  let editingFlagId = null;

  const openModal = (flag) => {
    editingFlagId = flag ? flag.flag_id : null;
    titleEl.textContent = flag ? `Update Flag ${flag.flag_id}` : 'Flag a Potential Invalidity';
    categorySelect.value = flag ? flag.category : 'INSUFFICIENT_INFORMATION';
    statusSelect.value = flag ? flag.status : 'OPEN';
    notesField.value = flag ? flag.notes : '';
    errorEl.classList.add('hidden');
    modal.classList.remove('hidden');
  };

  openButton.addEventListener('click', () => openModal(null));
  closeButton?.addEventListener('click', () => modal.classList.add('hidden'));

  submitButton?.addEventListener('click', async () => {
    const notes = notesField.value.trim();
    if (!notes) {
      errorEl.textContent = 'Notes are required.';
      errorEl.classList.remove('hidden');
      return;
    }
    const payload = { category: categorySelect.value, status: statusSelect.value, notes };
    try {
      if (editingFlagId) {
        await fetchJson(`/api/v1/constable/flags/${editingFlagId}`, { method: 'PATCH', body: payload });
      } else {
        await fetchJson(`/api/v1/constable/dockets/${caseReference}/flags`, { method: 'POST', body: payload });
      }
      modal.classList.add('hidden');
      if (onSaved) {
        await onSaved();
      }
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to save flag.';
      errorEl.classList.remove('hidden');
    }
  });

  return { openForEdit: openModal };
}

export async function hydrateConstableReview() {
  const caseReference = getConstableCaseReference();
  if (!caseReference) {
    return;
  }

  const meta = document.getElementById('constableCaseMeta');
  const statementBox = document.getElementById('constableStatementBox');
  const evidenceBody = document.getElementById('constableCaseEvidence');
  const flagList = document.getElementById('constableFlagList');
  const relatedBox = document.getElementById('constableRelatedCases');
  const statusBadge = document.getElementById('constableStatusBadge');

  const flagModal = bindFlagModal(caseReference, {
    onSaved: () => refreshFlags(),
  });

  async function refreshFlags() {
    try {
      const flags = await fetchJson(`/api/v1/constable/dockets/${caseReference}/flags`);
      renderFlags(flagList, flags, { onEdit: (flag) => flagModal.openForEdit(flag) });
    } catch (error) {
      setEmptyState(flagList, error.message || 'Unable to load flags.');
    }
  }

  try {
    const docket = await fetchJson(`/api/v1/constable/dockets/${caseReference}`);
    if (meta) {
      meta.innerHTML = `
        <dt>Title</dt><dd>${docket.title || 'Unspecified'}</dd>
        <dt>Location</dt><dd>${docket.location || 'Not provided'}</dd>
        <dt>Incident Date</dt><dd>${docket.incident_date || 'Not provided'}</dd>
        <dt>Status</dt><dd>${docket.status || 'AWAITING_CONSTABLE_REGISTRATION'}</dd>
      `;
    }
    if (statusBadge) {
      statusBadge.className = buildStatusBadge(docket.status);
      statusBadge.textContent = docket.status || 'AWAITING_CONSTABLE_REGISTRATION';
    }
    if (statementBox) {
      const statements = Array.isArray(docket.statements) ? docket.statements : [];
      const latest = statements[statements.length - 1];
      statementBox.innerHTML = `
        <strong>Statement</strong>
        <p>${latest ? latest.statement_text : 'No citizen statement has been submitted yet.'}</p>
      `;
    }
    renderEvidenceTable(evidenceBody, docket.evidence);

    const continueButton = document.getElementById('continueToInterview');
    if (continueButton) {
      continueButton.addEventListener('click', async () => {
        await fetchJson(`/api/v1/constable/dockets/${caseReference}/interview`, { method: 'POST' });
        window.location.href = `/constable/dockets/${caseReference}`;
      });
    }
  } catch (error) {
    if (meta) {
      meta.innerHTML = `<dt>Status</dt><dd>Unavailable</dd><dt>Message</dt><dd>${error.message}</dd>`;
    }
  }

  await refreshFlags();

  try {
    const related = await fetchJson(`/api/v1/constable/dockets/${caseReference}/related`);
    if (relatedBox) {
      relatedBox.innerHTML = related.length
        ? related
            .map((item) => `<p><strong>${item.relationship_type}</strong>: ${item.related_case_reference === caseReference ? item.source_case_reference : item.related_case_reference}</p>`)
            .join('')
        : '<p>No direct related case links detected.</p>';
    }
  } catch (error) {
    if (relatedBox) {
      relatedBox.innerHTML = `<p>${error.message}</p>`;
    }
  }
}

export function init() {
  if (document.body.dataset.role === 'constable' && document.getElementById('constableQueueState')) {
    hydrateConstableDashboard();
  }
  if (window.location.pathname.startsWith('/constable/dockets/')) {
    hydrateConstableReview();
  }
}
