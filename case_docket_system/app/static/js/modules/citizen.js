/**
 * Citizen dashboard, docket detail timeline, and new-docket submission form.
 */

import { fetchJson, postForm } from '../core/api.js';
import { bindCaseLinks, bindFilePreview, bindMediaViewButtons, buildStatusBadge, flashToast, renderEvidenceTable, renderMediaViewButton, renderStatementList, setEmptyState, showToast } from '../core/ui.js';

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
      showToast('Statement saved.');
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to save statement.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to save statement.', { type: 'error' });
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
  const fileInput = document.getElementById('citizenEvidenceFile');
  if (!addButton) {
    return;
  }

  bindFilePreview('citizenEvidenceFile', 'citizenEvidenceFilePreview');

  addButton.addEventListener('click', async () => {
    const evidenceType = document.getElementById('citizenEvidenceType')?.value;
    const description = document.getElementById('citizenEvidenceDescription')?.value.trim();
    const file = fileInput?.files && fileInput.files[0];
    errorEl.classList.add('hidden');
    if (!file || !description) {
      errorEl.textContent = 'A file and description are required.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('evidence_type', evidenceType);
      formData.append('description', description);
      await postForm(`/api/v1/citizen/dockets/${caseReference}/evidence`, formData);

      fileInput.value = '';
      document.getElementById('citizenEvidenceFilePreview').classList.add('hidden');
      document.getElementById('citizenEvidenceDescription').value = '';
      const items = await fetchJson(`/api/v1/citizen/dockets/${caseReference}/evidence`);
      renderEvidenceTable(evidenceBody, items);
      showToast(`Evidence "${file.name}" uploaded.`);
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to add evidence.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to upload evidence.', { type: 'error' });
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
      flashToast('Docket submitted for constable review.');
      window.location.reload();
    } catch (error) {
      const hint = document.getElementById('submitDocketHint');
      if (hint) {
        hint.textContent = error.message || 'Unable to submit docket.';
      }
      showToast(error.message || 'Unable to submit docket.', { type: 'error' });
    }
  });
}

async function hydrateCitizenInterview(caseReference, interviewId) {
  const panel = document.getElementById('citizenInterviewPanel');
  const statusBox = document.getElementById('citizenInterviewStatus');
  const fileInput = document.getElementById('citizenRecordingFile');
  const submitButton = document.getElementById('submitCitizenRecording');
  const errorEl = document.getElementById('citizenRecordingError');
  if (!panel) {
    return;
  }
  panel.classList.remove('hidden');
  bindFilePreview('citizenRecordingFile', 'citizenRecordingFilePreview');

  async function refreshInterview() {
    const interview = await fetchJson(`/api/v1/citizen/interviews/${interviewId}`);
    const citizenDone = Boolean(interview.citizen_recording && interview.citizen_recording.status === 'SUBMITTED');
    const constableDone = Boolean(interview.constable_recording && interview.constable_recording.status === 'SUBMITTED');
    if (statusBox) {
      const viewYours = citizenDone ? renderMediaViewButton(interview.citizen_recording?.storage_reference, 'View your recording') : '';
      if (interview.status === 'COMPLETED') {
        statusBox.innerHTML = `<p>✓ Both recordings submitted. The constable can now register this docket. ${viewYours}</p>`;
      } else if (citizenDone && !constableDone) {
        statusBox.innerHTML = `<p>✓ Your recording is submitted. Waiting on the constable to submit theirs — nothing more for you to do here. ${viewYours}</p>`;
      } else if (!citizenDone && constableDone) {
        statusBox.innerHTML = '<p>The constable has submitted their recording. Submit yours below to complete the interview.</p>';
      } else {
        statusBox.innerHTML = '<p>Submit your recording below. The constable will submit theirs separately.</p>';
      }
      bindMediaViewButtons(statusBox);
    }
    if (submitButton) submitButton.disabled = citizenDone;
    if (fileInput) fileInput.disabled = citizenDone;
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
    const file = fileInput?.files && fileInput.files[0];
    errorEl.classList.add('hidden');
    if (!file) {
      errorEl.textContent = 'A recording file is required.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('recording_type', 'citizen_recording');
      await postForm(`/api/v1/citizen/interviews/${interviewId}/recording`, formData);
      await refreshInterview();
      showToast('Recording submitted.');
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to submit recording.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to submit recording.', { type: 'error' });
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
      flashToast('Escalation submitted to IPID for independent review.');
      window.location.reload();
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to submit escalation.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to submit escalation.', { type: 'error' });
    }
  });
}

async function refreshCitizenEscalations(caseReference) {
  const container = document.getElementById('citizenEscalationsList');
  if (!container) {
    return;
  }
  try {
    const escalations = await fetchJson(`/api/v1/citizen/dockets/${caseReference}/escalations`);
    if (!escalations.length) {
      setEmptyState(container, 'You have not escalated this docket.');
      return;
    }
    container.innerHTML = escalations
      .map((item) => {
        const resolved = (item.status || '').toUpperCase() === 'RESOLVED';
        const decisionLine = resolved
          ? `<p><strong>${item.decision || 'RESOLVED'}</strong>${item.decision_reason ? ` — ${item.decision_reason}` : ''}</p>`
          : '<p>Awaiting IPID review.</p>';
        return `
          <article class="mini-case-card">
            <div class="stack-row" style="justify-content:space-between;">
              <strong>${item.category}</strong>
              <span class="${buildStatusBadge(item.status)}">${item.status || 'OPEN'}</span>
            </div>
            <p>${item.description}</p>
            ${decisionLine}
          </article>
        `;
      })
      .join('');
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load your escalations.');
  }
}

export async function hydrateCitizenDetail() {
  const caseReference = getCitizenCaseReference();
  if (!caseReference) {
    return;
  }
  const meta = document.getElementById('citizenCaseMeta');
  const timeline = document.getElementById('citizenCaseTimeline');
  const statusBadge = document.getElementById('citizenStatusBadge');
  const freezeBadge = document.getElementById('citizenFreezeBadge');
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
    if (freezeBadge) {
      if (docket.is_frozen) {
        freezeBadge.textContent = `Frozen — under IPID review${docket.freeze_reason ? `: ${docket.freeze_reason}` : ''}`;
        freezeBadge.classList.remove('hidden');
      } else {
        freezeBadge.classList.add('hidden');
      }
    }
    if (timeline) {
      const items = Array.isArray(docket.timeline) && docket.timeline.length ? docket.timeline : [{ event_type: 'docket_recorded', timestamp: 'Pending', details: {} }];
      timeline.innerHTML = items
        .map((event) => `<li><span class="timeline-dot"></span><div><strong>${event.event_type || 'Case Event'}</strong><small>${event.timestamp || 'No timestamp'}${event.details && event.details.status ? ` • ${event.details.status}` : ''}</small></div></li>`)
        .join('');
    }

    const statements = Array.isArray(docket.statements) ? docket.statements : [];
    // Once a detective or IPID reviewer can also add statements (post-
    // registration), the *last* array item is no longer necessarily the
    // citizen's own -- find their own latest self-authored one specifically
    // for the editable textarea below; the full mixed-author list still
    // renders in the read-only history panel.
    const ownStatements = statements.filter((statement) => !statement.recorded_by_role);
    const isDraft = (docket.status || 'DRAFT') === 'DRAFT';
    const statementTextarea = document.getElementById('citizenStatementText');
    const statementSaveButton = document.getElementById('saveCitizenStatement');
    if (statementTextarea && !isDraft) {
      statementTextarea.disabled = true;
      if (statementSaveButton) statementSaveButton.disabled = true;
    }
    bindCitizenStatement(caseReference, ownStatements[ownStatements.length - 1]);
    updateSubmitAvailability(ownStatements.length > 0 && isDraft);
    renderStatementList(document.getElementById('citizenStatementsList'), statements);
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
    await refreshCitizenEscalations(caseReference);
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
      flashToast('Docket created. Add a statement and evidence, then submit it for review.');
      window.location.href = `/citizen/dockets/${result.case_reference}`;
    } catch (error) {
      const errorBlock = document.getElementById('citizenFormError');
      if (errorBlock) {
        errorBlock.textContent = error.message;
        errorBlock.classList.remove('hidden');
      }
      showToast(error.message || 'Unable to create docket.', { type: 'error' });
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
