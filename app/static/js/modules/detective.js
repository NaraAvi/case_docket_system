/**
 * Detective investigation list and individual case workspace.
 */

import { fetchJson } from '../core/api.js';
import { buildStatusBadge, flashToast, renderDocketCardList, renderEvidenceTable, renderTimelineList, setEmptyState, showToast } from '../core/ui.js';

export function getDetectiveCaseReference() {
  const match = window.location.pathname.match(/\/detective\/dockets\/([^/]+)/);
  return match ? match[1] : null;
}

export async function hydrateDetectiveDashboard() {
  const container = document.getElementById('detectiveInvestigationList');
  if (!container) {
    return;
  }

  try {
    const allCases = await fetchJson('/api/v1/station-commander/dockets');
    const registeredCases = allCases.filter((item) => (item.status || '').toUpperCase() === 'REGISTERED');
    renderDocketCardList(container, registeredCases, {
      linkPrefix: '/detective/dockets/',
      title: (item) => item.location,
      status: 'REGISTERED',
      actionLabel: 'Open',
      emptyMessage: 'No registered detective cases are available yet.',
    });
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load detective queue.');
  }
}

function renderFindings(container, findings) {
  if (!container) {
    return;
  }
  if (!findings.length) {
    container.innerHTML = '<div class="empty-state">No findings have been recorded yet.</div>';
    return;
  }
  container.innerHTML = findings
    .map(
      (finding) => `
        <article class="mini-case-card">
          <div class="stack-row" style="justify-content:space-between;">
            <strong>${finding.finding_type}</strong>
            <span>${finding.created_at || ''}</span>
          </div>
          <p>${finding.notes}</p>
        </article>
      `
    )
    .join('');
}

function bindFindingModal(investigationId, { onSaved } = {}) {
  const modal = document.getElementById('findingModal');
  const openButton = document.getElementById('openFindingModal');
  const closeButton = document.getElementById('closeFindingModal');
  const submitButton = document.getElementById('submitFindingModal');
  const typeSelect = document.getElementById('findingType');
  const notesField = document.getElementById('findingNotes');
  const errorEl = document.getElementById('findingModalError');

  if (!openButton) {
    return;
  }

  if (!investigationId) {
    openButton.disabled = true;
    return;
  }
  openButton.disabled = false;

  if (!modal) {
    return;
  }

  openButton.addEventListener('click', () => {
    typeSelect.value = 'VALID';
    notesField.value = '';
    errorEl.classList.add('hidden');
    modal.classList.remove('hidden');
  });
  closeButton?.addEventListener('click', () => modal.classList.add('hidden'));

  submitButton?.addEventListener('click', async () => {
    const notes = notesField.value.trim();
    if (!notes) {
      errorEl.textContent = 'Finding notes are required.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      await fetchJson(`/api/v1/detective/investigations/${investigationId}/findings`, {
        method: 'POST',
        body: { finding_type: typeSelect.value, notes },
      });
      modal.classList.add('hidden');
      if (onSaved) {
        await onSaved();
      }
      showToast('Finding recorded.');
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to save finding.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to save finding.', { type: 'error' });
    }
  });
}

function bindNoteSaving(investigationId) {
  const notesField = document.getElementById('investigationNotes');
  const saveButton = document.getElementById('saveInvestigationNote');
  const errorEl = document.getElementById('investigationNotesError');
  if (!notesField || !saveButton) {
    return;
  }
  if (!investigationId) {
    saveButton.disabled = true;
    return;
  }
  saveButton.addEventListener('click', async () => {
    const notes = notesField.value.trim();
    errorEl.classList.add('hidden');
    if (!notes) {
      errorEl.textContent = 'Notes cannot be empty.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      await fetchJson(`/api/v1/detective/investigations/${investigationId}/notes`, {
        method: 'PATCH',
        body: { notes },
      });
      saveButton.textContent = 'Saved';
      setTimeout(() => {
        saveButton.textContent = 'Save Note';
      }, 1500);
      showToast('Investigation notes saved.');
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to save notes.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to save notes.', { type: 'error' });
    }
  });
}

export async function hydrateDetectiveCase() {
  const caseReference = getDetectiveCaseReference();
  if (!caseReference) {
    return;
  }
  const meta = document.getElementById('detectiveCaseMeta');
  const timeline = document.getElementById('detectiveCaseTimeline');
  const evidence = document.getElementById('detectiveCaseEvidence');
  const deposition = document.getElementById('detectiveDeposition');
  const statementBox = document.getElementById('detectiveStatementBox');
  const statusBadge = document.getElementById('detectiveStatusBadge');
  const findingsList = document.getElementById('detectiveFindingsList');
  const startInvestigation = document.getElementById('startInvestigation');
  const notesField = document.getElementById('investigationNotes');

  try {
    const docket = await fetchJson(`/api/v1/detective/dockets/${caseReference}`);
    const investigation = docket.investigation;

    if (meta) {
      meta.innerHTML = `
        <dt>Incident Location</dt><dd>${docket.location || 'Not provided'}</dd>
        <dt>Incident Date</dt><dd>${docket.incident_date || 'Not provided'}</dd>
        <dt>Assigned Officer</dt><dd>${investigation ? investigation.detective_id : 'Not yet assigned'}</dd>
        <dt>Status</dt><dd>${docket.status || 'REGISTERED'}</dd>
      `;
    }
    if (statusBadge) {
      statusBadge.className = buildStatusBadge(docket.status);
      statusBadge.textContent = docket.status || 'REGISTERED';
    }
    if (deposition) {
      deposition.innerHTML = `<p>${docket.description || 'No incident description was provided.'}</p>`;
    }
    if (statementBox) {
      const statements = Array.isArray(docket.statements) ? docket.statements : [];
      const latest = statements[statements.length - 1];
      statementBox.innerHTML = `
        <strong>Citizen Statement</strong>
        <p>${latest ? latest.statement_text : 'No citizen statement has been submitted yet.'}</p>
      `;
    }
    renderTimelineList(timeline, docket.timeline, { titleKey: 'event_type', fallbackTitle: 'Case Event' });
    renderEvidenceTable(evidence, docket.evidence);

    if (notesField && investigation) {
      notesField.value = investigation.notes || '';
    }
    bindNoteSaving(investigation ? investigation.investigation_id : null);

    if (startInvestigation) {
      if (investigation) {
        startInvestigation.disabled = true;
        startInvestigation.textContent = `Investigation ${investigation.status}`;
      } else {
        startInvestigation.addEventListener('click', async () => {
          const notes = notesField ? notesField.value.trim() : '';
          try {
            await fetchJson(`/api/v1/detective/dockets/${caseReference}/investigation`, {
              method: 'POST',
              body: { notes: notes || 'Investigation opened from the browser workflow.' },
            });
            flashToast('Investigation started.');
            window.location.href = `/detective/dockets/${caseReference}`;
          } catch (error) {
            showToast(error.message || 'Unable to start investigation.', { type: 'error' });
          }
        });
      }
    }

    const refreshFindings = async () => {
      if (!investigation) {
        renderFindings(findingsList, []);
        return;
      }
      try {
        const findings = await fetchJson(`/api/v1/detective/investigations/${investigation.investigation_id}/findings`);
        renderFindings(findingsList, findings);
      } catch (error) {
        setEmptyState(findingsList, error.message || 'Unable to load findings.');
      }
    };
    bindFindingModal(investigation ? investigation.investigation_id : null, { onSaved: refreshFindings });
    await refreshFindings();
  } catch (error) {
    if (meta) {
      meta.innerHTML = `<dt>Status</dt><dd>Unavailable</dd><dt>Message</dt><dd>${error.message}</dd>`;
    }
  }
}

export function init() {
  if (document.body.dataset.role === 'detective' && document.getElementById('detectiveInvestigationList')) {
    hydrateDetectiveDashboard();
  }
  if (window.location.pathname.startsWith('/detective/dockets/')) {
    hydrateDetectiveCase();
  }
}
