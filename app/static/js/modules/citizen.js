/**
 * Citizen dashboard, docket detail timeline, and new-docket submission form.
 */

import { fetchJson } from '../core/api.js';
import { buildStatusBadge, renderEvidenceTable, setEmptyState, bindCaseLinks } from '../core/ui.js';

export function getCitizenCaseReference() {
  const match = window.location.pathname.match(/^\/citizen\/dockets\/(?!new(?:\/)?$)([^/]+)/);
  return match ? match[1] : null;
}

export async function hydrateCitizenDashboard() {
  const container = document.getElementById('citizenDockets');
  if (!container) {
    return;
  }

  try {
    const dockets = await fetchJson('/api/v1/citizen/dockets');
    if (!dockets.length) {
      setEmptyState(container, 'No dockets yet. Submit your first report to begin the workflow.');
      return;
    }

    container.innerHTML = dockets
      .map((item) => `
        <article class="docket-card">
          <div class="meta-wrap">
            <strong>${item.case_reference}</strong>
            <span>${item.title || 'No title provided'}</span>
          </div>
          <div class="stack-row">
            <span class="${buildStatusBadge(item.status)}">${item.status || 'DRAFT'}</span>
            <button class="secondary-btn small-btn" type="button" data-case-link="/citizen/dockets/${item.case_reference}">Open</button>
          </div>
        </article>
      `)
      .join('');

    bindCaseLinks(container);
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load dockets.');
  }
}

function bindCitizenStatement(caseReference, existingStatement) {
  const textarea = document.getElementById('citizenStatementText');
  const saveButton = document.getElementById('saveCitizenStatement');
  const errorEl = document.getElementById('citizenStatementError');
  if (!textarea || !saveButton) {
    return;
  }

  let hasStatement = Boolean(existingStatement);
  textarea.value = existingStatement ? existingStatement.statement_text : '';

  saveButton.addEventListener('click', async () => {
    const statementText = textarea.value.trim();
    errorEl.classList.add('hidden');
    if (!statementText) {
      errorEl.textContent = 'Statement text is required.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      if (hasStatement) {
        await fetchJson(`/api/v1/citizen/dockets/${caseReference}/statements`, {
          method: 'PUT',
          body: { statement_text: statementText },
        });
      } else {
        await fetchJson(`/api/v1/citizen/dockets/${caseReference}/statements`, {
          method: 'POST',
          body: { statement_text: statementText },
        });
        hasStatement = true;
      }
      saveButton.textContent = 'Saved';
      setTimeout(() => {
        saveButton.textContent = 'Save Statement';
      }, 1500);
      updateSubmitAvailability(true);
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to save statement.';
      errorEl.classList.remove('hidden');
    }
  });
}

function updateSubmitAvailability(hasStatement) {
  const submitButton = document.getElementById('submitCitizenDocketForReview');
  const hint = document.getElementById('submitDocketHint');
  if (!submitButton) {
    return;
  }
  submitButton.disabled = !hasStatement;
  if (hint) {
    hint.textContent = hasStatement ? '' : 'Save a statement above before submitting.';
  }
}

function bindCitizenEvidence(caseReference) {
  const addButton = document.getElementById('addCitizenEvidence');
  const errorEl = document.getElementById('citizenEvidenceError');
  const evidenceBody = document.getElementById('citizenCaseEvidence');
  if (!addButton) {
    return;
  }

  addButton.addEventListener('click', async () => {
    const evidenceType = document.getElementById('citizenEvidenceType')?.value;
    const filename = document.getElementById('citizenEvidenceFilename')?.value.trim();
    const description = document.getElementById('citizenEvidenceDescription')?.value.trim();
    errorEl.classList.add('hidden');
    if (!filename || !description) {
      errorEl.textContent = 'File name and description are required.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      const evidence = await fetchJson(`/api/v1/citizen/dockets/${caseReference}/evidence`, {
        method: 'POST',
        body: { evidence_type: evidenceType, filename, description },
      });
      document.getElementById('citizenEvidenceFilename').value = '';
      document.getElementById('citizenEvidenceDescription').value = '';
      const items = await fetchJson(`/api/v1/citizen/dockets/${caseReference}/evidence`);
      renderEvidenceTable(evidenceBody, items);
      void evidence;
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to add evidence.';
      errorEl.classList.remove('hidden');
    }
  });
}

function bindCitizenSubmit(caseReference) {
  const submitButton = document.getElementById('submitCitizenDocketForReview');
  if (!submitButton) {
    return;
  }
  submitButton.addEventListener('click', async () => {
    try {
      await fetchJson(`/api/v1/citizen/dockets/${caseReference}/submit`, { method: 'POST' });
      window.location.reload();
    } catch (error) {
      const hint = document.getElementById('submitDocketHint');
      if (hint) {
        hint.textContent = error.message || 'Unable to submit docket.';
      }
    }
  });
}

async function hydrateCitizenInterview(caseReference, interviewId) {
  const panel = document.getElementById('citizenInterviewPanel');
  const statusBox = document.getElementById('citizenInterviewStatus');
  const filenameField = document.getElementById('citizenRecordingFilename');
  const submitButton = document.getElementById('submitCitizenRecording');
  const errorEl = document.getElementById('citizenRecordingError');
  if (!panel) {
    return;
  }
  panel.classList.remove('hidden');

  async function refreshInterview() {
    const interview = await fetchJson(`/api/v1/citizen/interviews/${interviewId}`);
    const citizenDone = Boolean(interview.citizen_recording && interview.citizen_recording.status === 'SUBMITTED');
    const constableDone = Boolean(interview.constable_recording && interview.constable_recording.status === 'SUBMITTED');
    if (statusBox) {
      statusBox.innerHTML = `
        <p><strong>Interview status:</strong> ${interview.status}</p>
        <p>Your recording: ${citizenDone ? 'Submitted' : 'Not yet submitted'}</p>
        <p>Constable recording: ${constableDone ? 'Submitted' : 'Awaiting constable'}</p>
      `;
    }
    if (submitButton) submitButton.disabled = citizenDone;
    if (filenameField) filenameField.disabled = citizenDone;
    return interview;
  }

  try {
    await refreshInterview();
  } catch (error) {
    if (statusBox) {
      statusBox.innerHTML = `<p>${error.message || 'Unable to load interview status.'}</p>`;
    }
  }

  submitButton?.addEventListener('click', async () => {
    const filename = filenameField ? filenameField.value.trim() : '';
    errorEl.classList.add('hidden');
    if (!filename) {
      errorEl.textContent = 'A recording file name is required.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      await fetchJson(`/api/v1/citizen/interviews/${interviewId}/recording`, {
        method: 'POST',
        body: { filename },
      });
      await refreshInterview();
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to submit recording.';
      errorEl.classList.remove('hidden');
    }
  });
}

function bindCitizenEscalation(caseReference) {
  const openButton = document.getElementById('escalateCaseBtn');
  const modal = document.getElementById('escalateModal');
  const closeButton = document.getElementById('closeEscalateModal');
  const submitButton = document.getElementById('submitEscalateModal');
  const categorySelect = document.getElementById('escalateCategory');
  const descriptionField = document.getElementById('escalateDescription');
  const errorEl = document.getElementById('escalateModalError');
  if (!openButton || !modal) {
    return;
  }

  openButton.addEventListener('click', () => {
    descriptionField.value = '';
    errorEl.classList.add('hidden');
    modal.classList.remove('hidden');
  });
  closeButton?.addEventListener('click', () => modal.classList.add('hidden'));

  submitButton?.addEventListener('click', async () => {
    const description = descriptionField.value.trim();
    if (description.length < 10) {
      errorEl.textContent = 'Description must be at least 10 characters.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      await fetchJson(`/api/v1/citizen/dockets/${caseReference}/escalations`, {
        method: 'POST',
        body: { category: categorySelect.value, description },
      });
      modal.classList.add('hidden');
      window.location.reload();
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to submit escalation.';
      errorEl.classList.remove('hidden');
    }
  });
}

export async function hydrateCitizenDetail() {
  const caseReference = getCitizenCaseReference();
  if (!caseReference) {
    return;
  }
  const meta = document.getElementById('citizenCaseMeta');
  const timeline = document.getElementById('citizenCaseTimeline');
  const statusBadge = document.getElementById('citizenStatusBadge');
  const evidenceBody = document.getElementById('citizenCaseEvidence');
  if (!meta && !timeline) {
    return;
  }

  try {
    const docket = await fetchJson(`/api/v1/citizen/dockets/${caseReference}`);
    if (meta) {
      meta.innerHTML = `
        <dt>Status</dt><dd>${docket.status || 'DRAFT'}</dd>
        <dt>Location</dt><dd>${docket.location || 'Not provided'}</dd>
        <dt>Incident Date</dt><dd>${docket.incident_date || 'Not provided'}</dd>
        <dt>Case Title</dt><dd>${docket.title || 'Unspecified'}</dd>
      `;
    }
    if (statusBadge) {
      statusBadge.className = buildStatusBadge(docket.status);
      statusBadge.textContent = docket.status || 'DRAFT';
    }
    if (timeline) {
      const items = Array.isArray(docket.timeline) && docket.timeline.length ? docket.timeline : [{ event_type: 'docket_recorded', timestamp: 'Pending', details: {} }];
      timeline.innerHTML = items
        .map((event) => `<li><span class="timeline-dot"></span><div><strong>${event.event_type || 'Case Event'}</strong><small>${event.timestamp || 'No timestamp'}${event.details && event.details.status ? ` • ${event.details.status}` : ''}</small></div></li>`)
        .join('');
    }

    const statements = Array.isArray(docket.statements) ? docket.statements : [];
    const isDraft = (docket.status || 'DRAFT') === 'DRAFT';
    const statementTextarea = document.getElementById('citizenStatementText');
    const statementSaveButton = document.getElementById('saveCitizenStatement');
    if (statementTextarea && !isDraft) {
      statementTextarea.disabled = true;
      if (statementSaveButton) statementSaveButton.disabled = true;
    }
    bindCitizenStatement(caseReference, statements[statements.length - 1]);
    updateSubmitAvailability(statements.length > 0 && isDraft);
    const submitButton = document.getElementById('submitCitizenDocketForReview');
    if (submitButton && !isDraft) {
      submitButton.disabled = true;
      submitButton.textContent = `Docket ${docket.status}`;
      const hint = document.getElementById('submitDocketHint');
      if (hint) hint.textContent = 'This docket has already been submitted for review.';
    }
    bindCitizenSubmit(caseReference);

    renderEvidenceTable(evidenceBody, docket.evidence);
    bindCitizenEvidence(caseReference);

    if (docket.interview_id) {
      await hydrateCitizenInterview(caseReference, docket.interview_id);
    }

    bindCitizenEscalation(caseReference);
  } catch (error) {
    if (meta) {
      meta.innerHTML = `<dt>Status</dt><dd>Unavailable</dd><dt>Details</dt><dd>${error.message}</dd>`;
    }
    if (timeline) {
      setEmptyState(timeline, error.message || 'Unable to load timeline.');
    }
  }
}

export function hydrateCitizenForm() {
  const formButton = document.getElementById('submitCitizenDocket');
  if (!formButton) {
    return;
  }

  formButton.addEventListener('click', async () => {
    const title = document.getElementById('crimeType')?.value || '';
    const description = document.getElementById('description')?.value || '';
    const incidentDate = document.getElementById('incidentDate')?.value || '';
    const location = document.getElementById('incidentLocation')?.value || '';

    try {
      const result = await fetchJson('/api/v1/citizen/dockets', {
        method: 'POST',
        body: {
          title,
          description,
          incident_date: incidentDate,
          location,
        },
      });
      window.location.href = `/citizen/dockets/${result.case_reference}`;
    } catch (error) {
      const errorBlock = document.getElementById('citizenFormError');
      if (errorBlock) {
        errorBlock.textContent = error.message;
        errorBlock.classList.remove('hidden');
      }
    }
  });
}

export function bindCitizenNavigationShortcuts() {
  const newDocketButton = document.getElementById('newCitizenDocketBtn');
  if (newDocketButton) {
    newDocketButton.addEventListener('click', () => {
      window.location.href = '/citizen/dockets/new';
    });
  }

  const backToCitizenDashboard = document.getElementById('backToCitizenDashboard');
  if (backToCitizenDashboard) {
    backToCitizenDashboard.addEventListener('click', () => {
      window.location.href = '/citizen';
    });
  }
}

export function init() {
  if (document.body.dataset.role !== 'citizen') {
    return;
  }
  if (document.getElementById('citizenDockets')) {
    hydrateCitizenDashboard();
  }
  if (getCitizenCaseReference()) {
    hydrateCitizenDetail();
  }
  if (document.getElementById('submitCitizenDocket')) {
    hydrateCitizenForm();
  }
  bindCitizenNavigationShortcuts();
}
