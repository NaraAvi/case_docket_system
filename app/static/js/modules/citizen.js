/**
 * Citizen dashboard, docket detail timeline, and new-docket submission form.
 */

import { fetchJson, postForm } from '../core/api.js';
import { bindCaseLinks, bindFilePreview, bindMediaViewButtons, buildStatusBadge, flashToast, renderEvidenceTable, renderMediaViewButton, renderStatementList, renderWorkflowRail, setEmptyState, showToast } from '../core/ui.js';

export function getCitizenCaseReference() {
  const match = window.location.pathname.match(/^\/citizen\/(?:dockets|submissions)\/(?!new(?:\/)?$)([^/]+)/);
  return match ? match[1] : null;
}

export async function hydrateCitizenDashboard() {
  const container = document.getElementById('citizenDockets');
  if (!container) {
    return;
  }

  try {
    const submissions = await fetchJson('/api/v1/citizen/submissions');
    if (!submissions.length) {
      setEmptyState(container, 'No submissions yet. Create your first protected report to begin the workflow.');
      return;
    }

    container.innerHTML = submissions
      .map((item) => `
        <article class="docket-card">
          <div class="meta-wrap">
            <strong>${item.submission_id}</strong>
            <span>${item.title || 'No title provided'}</span>
          </div>
          <div class="stack-row">
            <span class="${buildStatusBadge(item.status)}">${item.status || 'RECEIVED'}</span>
            <button class="secondary-btn small-btn" type="button" data-case-link="/citizen/dockets/${item.submission_id}">Open</button>
          </div>
        </article>
      `)
      .join('');

    bindCaseLinks(container);
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load submissions.');
  }
}

function isProtectedSubmissionReference(reference) {
  return /^SUB-/i.test(String(reference || ''));
}

function renderSubmissionAssertions(container, assertions = []) {
  if (!container) {
    return;
  }
  const items = Array.isArray(assertions) ? assertions : [];
  if (!items.length) {
    container.innerHTML = '<div class="empty-state">No additional information has been recorded yet.</div>';
    return;
  }
  container.innerHTML = items
    .map((assertion) => `
      <article class="mini-case-card">
        <div class="stack-row" style="justify-content:space-between;">
          <strong>${assertion.provenance || 'CITIZEN_ASSERTED'}</strong>
          <span>${assertion.created_at || 'No timestamp'}</span>
        </div>
        <p>${assertion.assertion_text || assertion.statement_text || 'No assertion text recorded.'}</p>
      </article>
    `)
    .join('');
}

function renderAssertionOptions(assertions = []) {
  const select = document.getElementById('citizenCorrectionAssertion');
  if (!select) {
    return;
  }
  const items = Array.isArray(assertions) ? assertions : [];
  if (!items.length) {
    select.innerHTML = '<option value="">No assertions available</option>';
    select.disabled = true;
    return;
  }
  select.disabled = false;
  select.innerHTML = items
    .map((assertion) => `<option value="${assertion.assertion_id}">${(assertion.assertion_text || 'Assertion').slice(0, 80)}</option>`)
    .join('');
}

function bindCitizenStatement(caseReference, existingStatement) {
  const textarea = document.getElementById('citizenStatementText');
  const saveButton = document.getElementById('saveCitizenStatement');
  const errorEl = document.getElementById('citizenStatementError');
  if (!textarea || !saveButton) {
    return;
  }

  if (isProtectedSubmissionReference(caseReference)) {
    textarea.disabled = false;
    textarea.placeholder = 'Add additional facts or context for this protected submission...';
    saveButton.disabled = false;
    saveButton.textContent = 'Add Information';

    saveButton.onclick = async () => {
      const statementText = textarea.value.trim();
      errorEl.classList.add('hidden');
      if (!statementText) {
        errorEl.textContent = 'Additional information is required.';
        errorEl.classList.remove('hidden');
        return;
      }
      try {
        await fetchJson(`/api/v1/citizen/submissions/${caseReference}/assertions`, {
          method: 'POST',
          body: { assertion_text: statementText },
        });
        textarea.value = '';
        const assertions = await fetchJson(`/api/v1/citizen/submissions/${caseReference}/assertions`);
        renderSubmissionAssertions(document.getElementById('citizenStatementsList'), assertions);
        renderAssertionOptions(assertions);
        showToast('Additional information added to the protected submission.');
      } catch (error) {
        errorEl.textContent = error.message || 'Unable to add information.';
        errorEl.classList.remove('hidden');
        showToast(error.message || 'Unable to add information.', { type: 'error' });
      }
    };
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

function normalizeListText(value) {
  if (value === undefined || value === null) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  return String(value)
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function getCitizenStageLabel(reviewStatus) {
  const normalized = String(reviewStatus || '').trim().toUpperCase();
  if (!normalized || normalized === 'PENDING' || normalized === 'REVIEW_PENDING') {
    return 'Procedural assessment';
  }
  if (normalized === 'ALLOWED' || normalized === 'PASS' || normalized === 'CLEAR') {
    return 'Procedural assessment';
  }
  if (normalized === 'RESTRICTED' || normalized === 'NEEDS_INFO' || normalized === 'FURTHER_REVIEW') {
    return 'Additional review required';
  }
  if (normalized === 'REJECTED' || normalized === 'BLOCKED') {
    return 'Follow-up required';
  }
  return 'Procedural assessment';
}

function sanitizeCitizenReviewExplanation(explanation) {
  const value = String(explanation || '').trim();
  if (!value) {
    return 'Your protected submission has been received and is being processed through the PDAS workflow. This status does not determine whether an allegation is true or whether any person is responsible.';
  }
  if (/repeated|related submissions|duplicate|ALLOWED|BLOCKED|REVIEW_REQUIRED|control|rule evaluation|rule|evaluation/i.test(value)) {
    return 'Your protected submission has been received and is being processed through the PDAS workflow. This status does not determine whether an allegation is true or whether any person is responsible.';
  }
  return 'Your protected submission has been received and is being processed through the PDAS workflow. This status does not determine whether an allegation is true or whether any person is responsible.';
}

function bindCitizenProceduralCaseAction(caseReference, reviewResult, linkedCase = null) {
  const container = document.getElementById('citizenProceduralCaseAction');
  const button = document.getElementById('citizenProceedToProceduralCase');
  if (!container || !button || !caseReference || !/^SUB-/i.test(String(caseReference || ''))) {
    return;
  }

  const candidateId = reviewResult?.candidate?.candidate_id || reviewResult?.candidate_id || reviewResult?.details?.candidate_id || null;
  const reviewStatus = String(reviewResult?.control_evaluation?.result || reviewResult?.status || '').toUpperCase();
  const linkedCaseReference = linkedCase?.case_reference ? String(linkedCase.case_reference).trim() : '';
  const hasProceduralCase = Boolean(
    linkedCaseReference && linkedCaseReference.toUpperCase() !== 'NOT YET CREATED'
      || (reviewResult?.case_reference && String(reviewResult.case_reference).trim() && String(reviewResult.case_reference).trim().toUpperCase() !== 'NOT YET CREATED')
  );

  if (!candidateId || reviewStatus !== 'ALLOWED' || hasProceduralCase) {
    container.classList.add('hidden');
    button.disabled = true;
    button.textContent = 'Proceed to procedural case';
    button.onclick = null;
    return;
  }

  container.classList.remove('hidden');
  button.disabled = false;
  button.textContent = 'Proceed to procedural case';
  button.onclick = async () => {
    button.disabled = true;
    button.textContent = 'Creating procedural case…';
    try {
      const result = await fetchJson(`/api/v1/citizen/submissions/${caseReference}/incident-candidates/${candidateId}/create-case`, {
        method: 'POST',
      });
      const caseReferenceValue = result?.case_reference || 'Not yet created';
      const proceduralCaseEl = document.getElementById('citizenProceduralCaseValue');
      const proceduralCaseMetaEl = document.getElementById('citizenProceduralCaseMetaValue');
      const summaryEl = document.getElementById('citizenReviewSummary');
      if (proceduralCaseEl) {
        proceduralCaseEl.textContent = caseReferenceValue;
      }
      if (proceduralCaseMetaEl) {
        proceduralCaseMetaEl.textContent = caseReferenceValue;
      }
      if (summaryEl) {
        summaryEl.textContent = `Current status: Submission received. Current procedural stage: Procedural assessment. Procedural case: ${caseReferenceValue}. The system has advanced this protected submission to the procedural-case boundary.`;
      }
      container.classList.add('hidden');
      showToast('Procedural case created and queued for constable registration.');
      if (window && typeof window.location !== 'undefined' && window.location && typeof window.location.reload === 'function') {
        setTimeout(() => window.location.reload(), 200);
      }
    } catch (error) {
      button.disabled = false;
      button.textContent = 'Proceed to procedural case';
      showToast(error.message || 'Unable to create the procedural case.', { type: 'error' });
    }
  };
}

async function ensureProtectedSubmissionReview(caseReference, docket, linkedCase = null) {
  const panel = document.getElementById('citizenProtectedReview');
  const statusEl = document.getElementById('citizenReviewStatus');
  const summaryEl = document.getElementById('citizenReviewSummary');
  if (!caseReference || !panel || !/^SUB-/i.test(String(caseReference || ''))) {
    return null;
  }

  const reviewSource = [
    docket.title,
    docket.description,
    docket.location,
    docket.incident_date,
    docket.original_content?.incident_type,
    docket.original_content?.reporter_relationship,
    docket.original_content?.people_involved,
  ].filter(Boolean).join('. ');
  const assertionText = reviewSource || 'Protected citizen submission for PDAS review.';

  try {
    const existingAssertions = Array.isArray(docket.assertions) ? docket.assertions : [];
    const existingClaims = Array.isArray(docket.claims) ? docket.claims : [];
    let assertion = existingAssertions[0] || null;

    if (!assertion) {
      assertion = await fetchJson(`/api/v1/citizen/submissions/${caseReference}/assertions`, {
        method: 'POST',
        body: { assertion_text: assertionText },
      });
    }

    const assertionId = assertion?.assertion_id || assertion?.id;
    if (!existingClaims.length && assertionId) {
      await fetchJson(`/api/v1/citizen/submissions/${caseReference}/assertions/${assertionId}/claims`, {
        method: 'POST',
        body: { claim_type: 'asserted_fact', subject: 'report', predicate: 'submitted', object_value: assertionText },
      });
    }

    const result = await fetchJson(`/api/v1/citizen/submissions/${caseReference}/analyze`, {
      method: 'POST',
      body: { source: 'ui_review', assertion_id: assertionId, assertion_text: assertionText },
    });

    const reviewStatus = result?.control_evaluation?.result || result?.status || 'PENDING';
    const proceduralCase = linkedCase?.case_reference || result?.case_reference || 'Not yet created';
    const explanation = sanitizeCitizenReviewExplanation(result?.relationship_summary?.explanation || result?.control_evaluation?.reason || 'The system is reviewing this protected submission.');
    const citizenStage = getCitizenStageLabel(reviewStatus);
    const submissionStatus = docket.status || 'RECEIVED';
    const reviewText = `Current status: Submission received. Current procedural stage: ${citizenStage}. Procedural case: ${proceduralCase}. ${explanation}`;

    try {
      const refreshedAssertions = await fetchJson(`/api/v1/citizen/submissions/${caseReference}/assertions`).catch(() => []);
      if (Array.isArray(refreshedAssertions) && refreshedAssertions.length) {
        const assertionList = document.getElementById('citizenStatementsList');
        if (assertionList) {
          renderSubmissionAssertions(assertionList, refreshedAssertions);
        }
        renderAssertionOptions(refreshedAssertions);
      }
    } catch (error) {
      // Ignore refresh errors here; the review outcome is still authoritative.
    }

    const submissionStatusEl = document.getElementById('citizenSubmissionStatusText');
    const proceduralReviewEl = document.getElementById('citizenProceduralReviewValue');
    const proceduralCaseEl = document.getElementById('citizenProceduralCaseValue');
    const proceduralReviewMetaEl = document.getElementById('citizenProceduralReviewMetaValue');
    const proceduralCaseMetaEl = document.getElementById('citizenProceduralCaseMetaValue');

    if (statusEl) {
      statusEl.className = buildStatusBadge(submissionStatus);
      statusEl.textContent = 'Current status';
    }
    if (submissionStatusEl) {
      submissionStatusEl.textContent = submissionStatus;
    }
    if (proceduralReviewEl) {
      proceduralReviewEl.textContent = citizenStage;
    }
    if (proceduralReviewMetaEl) {
      proceduralReviewMetaEl.textContent = citizenStage;
    }
    if (proceduralCaseEl) {
      proceduralCaseEl.textContent = proceduralCase;
    }
    if (proceduralCaseMetaEl) {
      proceduralCaseMetaEl.textContent = proceduralCase;
    }
    if (summaryEl) {
      summaryEl.textContent = reviewText;
    } else {
      panel.innerHTML = `<div class="stack-row"><span class="${buildStatusBadge(submissionStatus)}">Current status</span></div><p style="margin-top:10px;">${reviewText}</p>`;
    }
    panel.classList.remove('hidden');
    return result;
  } catch (error) {
    const reviewText = error.message || 'Unable to execute the protected review yet.';
    if (statusEl) {
      statusEl.className = 'badge badge-warning';
      statusEl.textContent = 'Current status';
    }
    const submissionStatusEl = document.getElementById('citizenSubmissionStatusText');
    if (submissionStatusEl) {
      submissionStatusEl.textContent = docket.status || 'RECEIVED';
    }
    const proceduralReviewEl = document.getElementById('citizenProceduralReviewValue');
    if (proceduralReviewEl) {
      proceduralReviewEl.textContent = 'Procedural assessment';
    }
    const proceduralCaseEl = document.getElementById('citizenProceduralCaseValue');
    if (proceduralCaseEl) {
      proceduralCaseEl.textContent = 'Not yet created';
    }
    if (summaryEl) {
      summaryEl.textContent = `Current status: Submission received. Current procedural stage: Procedural assessment. Procedural case: Not yet created. ${reviewText}`;
    } else {
      panel.innerHTML = `<div class="stack-row"><span class="badge badge-warning">Current status</span></div><p style="margin-top:10px;">Current status: Submission received. Current procedural stage: Procedural assessment. Procedural case: Not yet created. ${reviewText}</p>`;
    }
    panel.classList.remove('hidden');
    return null;
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

  if (isProtectedSubmissionReference(caseReference)) {
    addButton.disabled = false;
    addButton.textContent = 'Add Evidence';
    fileInput.disabled = false;
  } else {
    addButton.disabled = false;
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
      const endpoint = isProtectedSubmissionReference(caseReference)
        ? `/api/v1/citizen/submissions/${caseReference}/evidence`
        : `/api/v1/citizen/dockets/${caseReference}/evidence`;
      await postForm(endpoint, formData);

      fileInput.value = '';
      const previewEl = document.getElementById('citizenEvidenceFilePreview');
      if (previewEl) {
        previewEl.classList.add('hidden');
      }
      document.getElementById('citizenEvidenceDescription').value = '';
      const items = await fetchJson(isProtectedSubmissionReference(caseReference)
        ? `/api/v1/citizen/submissions/${caseReference}/evidence`
        : `/api/v1/citizen/dockets/${caseReference}/evidence`);
      renderEvidenceTable(evidenceBody, items);
      showToast(`Evidence "${file.name}" uploaded.`);
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to add evidence.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to upload evidence.', { type: 'error' });
    }
  });
}

function bindCitizenCorrection(caseReference) {
  const select = document.getElementById('citizenCorrectionAssertion');
  const text = document.getElementById('citizenCorrectionText');
  const reason = document.getElementById('citizenCorrectionReason');
  const button = document.getElementById('submitCitizenCorrection');
  const errorEl = document.getElementById('citizenCorrectionError');
  if (!button || !text || !reason || !select) {
    return;
  }

  if (!isProtectedSubmissionReference(caseReference)) {
    button.disabled = true;
    select.disabled = true;
    return;
  }

  button.addEventListener('click', async () => {
    const assertionId = select.value;
    const correctedText = text.value.trim();
    const correctionReason = reason.value.trim();
    errorEl.classList.add('hidden');
    if (!assertionId || !correctedText || !correctionReason) {
      errorEl.textContent = 'Choose an assertion, provide corrected wording, and explain the reason.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      await fetchJson(`/api/v1/citizen/submissions/${caseReference}/corrections`, {
        method: 'POST',
        body: {
          assertion_id: assertionId,
          assertion_text: correctedText,
          reason: correctionReason,
        },
      });
      text.value = '';
      reason.value = '';
      const assertions = await fetchJson(`/api/v1/citizen/submissions/${caseReference}/assertions`);
      renderAssertionOptions(assertions);
      renderSubmissionAssertions(document.getElementById('citizenStatementsList'), assertions);
      showToast('Correction request logged. The original assertion remains preserved.');
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to request a correction.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to request a correction.', { type: 'error' });
    }
  });
}

function bindCitizenWithdrawal(caseReference) {
  const textarea = document.getElementById('citizenWithdrawalReason');
  const button = document.getElementById('requestCitizenWithdrawal');
  const errorEl = document.getElementById('citizenWithdrawalError');
  if (!button || !textarea) {
    return;
  }

  if (!isProtectedSubmissionReference(caseReference)) {
    button.disabled = true;
    return;
  }

  button.addEventListener('click', async () => {
    const reason = textarea.value.trim();
    errorEl.classList.add('hidden');
    if (!reason) {
      errorEl.textContent = 'A withdrawal reason is required.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      await fetchJson(`/api/v1/citizen/submissions/${caseReference}/withdrawal`, {
        method: 'POST',
        body: { reason },
      });
      textarea.value = '';
      showToast('Withdrawal request submitted. The record remains intact.');
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to request withdrawal.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to request withdrawal.', { type: 'error' });
    }
  });
}

function bindCitizenSubmit(caseReference) {
  const submitButton = document.getElementById('submitCitizenDocketForReview');
  if (!submitButton) {
    return;
  }
  if (isProtectedSubmissionReference(caseReference)) {
    submitButton.disabled = true;
    submitButton.textContent = 'Submission received';
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
      showToast(error.message || 'Unable to submit submission.', { type: 'error' });
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
      if (interview.status === 'COMPLETED' || (citizenDone && constableDone)) {
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
  if (isProtectedSubmissionReference(caseReference)) {
    setEmptyState(container, 'Escalations are available only after a submission advances into the formal review process.');
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

function renderCitizenWorkflow(docket, caseReference = '') {
  const rail = document.getElementById('citizenWorkflowRail');
  if (!rail) {
    return;
  }

  const steps = [
    { label: 'Protected submission', state: 'complete', detail: 'Submission received and recorded' },
    { label: 'Status & review', state: 'current', detail: 'Current procedural assessment' },
    { label: 'Information / evidence', state: 'upcoming', detail: 'Citizen facts and optional material' },
    { label: 'History', state: 'upcoming', detail: 'Append-only timeline and provenance' },
  ];

  renderWorkflowRail(rail, { title: 'Protected submission lifecycle', steps, locked: Boolean(docket.is_frozen) });
}

async function getCitizenLinkedProceduralCase(caseReference) {
  if (!caseReference || !/^SUB-/i.test(String(caseReference || ''))) {
    return null;
  }

  try {
    const dockets = await fetchJson('/api/v1/citizen/dockets');
    const linkedCase = Array.isArray(dockets)
      ? dockets.find((entry) => {
          const sourceId = entry?.source_submission_id ?? entry?.source_submission ?? '';
          return String(sourceId).trim() === String(caseReference).trim();
        })
      : null;
    return linkedCase || null;
  } catch (error) {
    return null;
  }
}

function formatStructuredLabel(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatStructuredValue(value) {
  if (value === undefined || value === null || value === '') {
    return 'Not provided';
  }
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean).join(', ') || 'Not provided';
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}

function buildCitizenSubmissionSummaryText(docket) {
  const originalContent = docket.original_content && typeof docket.original_content === 'object' ? docket.original_content : {};
  const getValue = (...keys) => {
    for (const key of keys) {
      const value = originalContent[key];
      if (value !== undefined && value !== null && value !== '') {
        return value;
      }
    }
    return undefined;
  };

  const relationship = formatStructuredValue(getValue('reporter_relationship', 'legacy_reporter_relationship')); 
  const incidentType = formatStructuredValue(getValue('incident_type', 'incident_type_other'));
  const location = formatStructuredValue(getValue('location', 'incident_location'));
  const dateValue = formatStructuredValue([
    getValue('incident_date'),
    getValue('approximate_date'),
    getValue('incident_time'),
    getValue('approximate_time'),
  ].filter((value) => value !== undefined && value !== null && value !== '' && value !== 'Not provided'));
  const peopleCount = formatStructuredValue(getValue('people_count', 'other_people_involved'));
  const harmTypes = formatStructuredValue(getValue('harm_types'));
  const evidenceLabel = formatStructuredValue(getValue('evidence_available', 'evidence_summary'));

  return [
    `Reporting as: ${relationship}`,
    `Location: ${location}`,
    `Incident date: ${dateValue}`,
    `Incident type: ${incidentType}`,
    `Approximate number involved: ${peopleCount}`,
    `Harm types: ${harmTypes}`,
    `Evidence declaration: ${evidenceLabel}`,
  ].join(' • ');
}

function buildStructuredSubmissionMarkup(docket) {
  const originalContent = docket.original_content && typeof docket.original_content === 'object' ? docket.original_content : {};
  const getValue = (...keys) => {
    for (const key of keys) {
      const value = originalContent[key];
      if (value !== undefined && value !== null && value !== '') {
        return value;
      }
    }
    return undefined;
  };

  const sections = [
    {
      title: 'About you',
      rows: [
        ['Relationship', formatStructuredValue(getValue('reporter_relationship', 'legacy_reporter_relationship'))],
        ['Contact consent', formatStructuredValue(getValue('can_contact'))],
        ['Contact method', formatStructuredValue(getValue('preferred_contact_method', 'contact_method'))],
        ['Contact details', formatStructuredValue([
          getValue('contact_phone'),
          getValue('contact_email'),
          getValue('contact_sms')
        ].filter((value) => value !== undefined && value !== null && value !== ''))],
      ],
    },
    {
      title: 'Incident',
      rows: [
        ['Submission title', formatStructuredValue(getValue('title'))],
        ['Incident type', formatStructuredValue(getValue('incident_type', 'incident_type_other'))],
        ['Date / time', formatStructuredValue([
          getValue('incident_date'),
          getValue('date_certainty'),
          getValue('incident_time'),
          getValue('approximate_time'),
          getValue('approximate_date')
        ].filter((value) => value !== undefined && value !== null && value !== ''))],
        ['Location', formatStructuredValue(getValue('location', 'incident_location'))],
        ['Police station / facility', formatStructuredValue(getValue('police_facility_name', 'police_station_or_unit', 'police_facility'))],
        ['Summary', formatStructuredValue(getValue('description'))],
        ['Before the event', formatStructuredValue(getValue('narrative_before_incident', 'before_incident'))],
        ['After the event', formatStructuredValue(getValue('narrative_after_incident', 'after_incident'))],
      ],
    },
    {
      title: 'People',
      rows: [
        ['People involved', formatStructuredValue(getValue('other_people_involved'))],
        ['Approximate number', formatStructuredValue(getValue('people_count'))],
      ],
    },
    {
      title: 'Harm / Injury',
      rows: [
        ['Harmed or at risk', formatStructuredValue(getValue('was_anyone_harmed'))],
        ['Harm types', formatStructuredValue(getValue('harm_types'))],
        ['Harm narrative', formatStructuredValue(getValue('harm_description', 'harm_impact'))],
        ['Injured', formatStructuredValue(getValue('was_anyone_injured'))],
        ['Injury types', formatStructuredValue(getValue('injury_types'))],
        ['Who was injured', formatStructuredValue(getValue('injury_person_type', 'injury_person_other'))],
        ['Medical attention', formatStructuredValue(getValue('medical_attention'))],
        ['Medical details', formatStructuredValue(getValue('medical_attention_details'))],
        ['Injury details', formatStructuredValue(getValue('injury_description', 'injuries'))],
        ['Property / financial impact', formatStructuredValue(getValue('property_impact_question'))],
      ],
    },
    {
      title: 'Evidence declaration',
      rows: [
        ['Evidence available', formatStructuredValue(getValue('evidence_available'))],
        ['Evidence types', formatStructuredValue(getValue('evidence_types'))],
        ['Evidence description', formatStructuredValue(getValue('evidence_summary'))],
      ],
    },
    {
      title: 'Previous report',
      rows: [
        ['Previous report', formatStructuredValue(getValue('previous_report_question'))],
        ['Previous report type', formatStructuredValue(getValue('previous_report_type'))],
        ['Reference / details', formatStructuredValue([getValue('previous_report_reference'), getValue('previous_report_date'), getValue('previous_report_context')].filter((value) => value !== undefined && value !== null && value !== ''))],
      ],
    },
    {
      title: 'Current safety',
      rows: [
        ['Current safety question', formatStructuredValue(getValue('current_safety_question'))],
        ['Risk types', formatStructuredValue(getValue('current_risk_types'))],
        ['Current safety details', formatStructuredValue(getValue('current_safety_summary'))],
      ],
    },
  ];

  const originalSummary = docket.original_content && typeof docket.original_content === 'object'
    ? Object.entries(docket.original_content)
        .filter(([, value]) => value !== undefined && value !== null && value !== '')
        .map(([key, value]) => `${formatStructuredLabel(key)}: ${Array.isArray(value) ? value.join(', ') : String(value)}`)
        .join('; ')
    : 'Original citizen-provided information is not available.';

  return `
    ${sections
      .filter((section) => section.rows.some(([, value]) => value !== 'Not provided'))
      .map((section) => `
        <article class="mini-case-card">
          <strong>${section.title}</strong>
          <dl class="meta-list compact">
            ${section.rows
              .filter(([, value]) => value !== 'Not provided')
              .map(([label, value]) => `<dt>${label}</dt><dd>${value}</dd>`)
              .join('')}
          </dl>
        </article>
      `)
      .join('')}
    <article class="mini-case-card">
      <strong>Original submission (immutable)</strong>
      <p>${originalSummary}</p>
    </article>
  `;
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
  const structuredBody = document.getElementById('citizenStructuredSubmission');
  const detailHeading = document.querySelector('.page-head-row h1');
  if (detailHeading) {
    detailHeading.textContent = 'View and manage my protected submission';
  }
  if (!meta && !timeline) {
    return;
  }

  try {
    const isSubmission = isProtectedSubmissionReference(caseReference);
    const submissionEndpoint = isSubmission ? `/api/v1/citizen/submissions/${caseReference}` : `/api/v1/citizen/dockets/${caseReference}`;
    const docketPromise = fetchJson(submissionEndpoint);
    const [docket, assertions, claims, evidence, relationships] = await Promise.all([
      docketPromise,
      isSubmission ? fetchJson(`/api/v1/citizen/submissions/${caseReference}/assertions`).catch(() => []) : Promise.resolve([]),
      isSubmission ? fetchJson(`/api/v1/citizen/submissions/${caseReference}/claims`).catch(() => []) : Promise.resolve([]),
      isSubmission ? fetchJson(`/api/v1/citizen/submissions/${caseReference}/evidence`).catch(() => []) : Promise.resolve([]),
      isSubmission ? fetchJson(`/api/v1/citizen/submissions/${caseReference}/relationships`).catch(() => []) : Promise.resolve([]),
    ]);
    docket.assertions = assertions;
    docket.claims = claims;
    docket.evidence = isSubmission ? evidence : Array.isArray(docket.evidence) ? docket.evidence : [];
    docket.relationships = relationships;

    const linkedCase = isSubmission ? await getCitizenLinkedProceduralCase(caseReference) : null;
    if (linkedCase) {
      docket.case_reference = linkedCase.case_reference || docket.case_reference || null;
      docket.interview_id = linkedCase.interview_id || docket.interview_id || null;
    }

    renderCitizenWorkflow(docket, caseReference);
    if (meta) {
      const statusValue = docket.status || (isSubmission ? 'RECEIVED' : 'DRAFT');
      const proceduralCaseValue = linkedCase?.case_reference || docket.case_reference || 'Not yet created';
      meta.innerHTML = `
        <dt>Submission status</dt><dd>${statusValue}</dd>
        <dt>Location</dt><dd>${docket.location || 'Not provided'}</dd>
        <dt>Incident Date</dt><dd>${docket.incident_date || 'Not provided'}</dd>
        <dt>Submission title</dt><dd>${docket.title || 'Unspecified'}</dd>
        <dt>Procedural review</dt><dd id="citizenProceduralReviewMetaValue">Pending</dd>
        <dt>Procedural case</dt><dd id="citizenProceduralCaseMetaValue">${proceduralCaseValue}</dd>
      `;
    }
    if (statusBadge) {
      statusBadge.className = buildStatusBadge(docket.status || (isSubmission ? 'RECEIVED' : 'DRAFT'));
      statusBadge.textContent = `Submission ${docket.status || (isSubmission ? 'RECEIVED' : 'DRAFT')}`;
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
      const items = Array.isArray(docket.timeline) && docket.timeline.length
        ? docket.timeline
        : Array.isArray(docket.event_history) && docket.event_history.length
          ? docket.event_history
          : [{ event_type: isSubmission ? 'submission_received' : 'docket_recorded', timestamp: 'Pending', details: {} }];
      timeline.innerHTML = items
        .map((event) => `<li><span class="timeline-dot"></span><div><strong>${event.event_type || (isSubmission ? 'Submission Event' : 'Case Event')}</strong><small>${event.timestamp || 'No timestamp'}${event.details && event.details.status ? ` • ${event.details.status}` : ''}</small></div></li>`)
        .join('');
    }

    const statements = Array.isArray(docket.statements) ? docket.statements : [];
    const isDraft = (docket.status || 'DRAFT') === 'DRAFT';
    const statementTextarea = document.getElementById('citizenStatementText');
    const statementSaveButton = document.getElementById('saveCitizenStatement');
    const submissionAssertionsList = document.getElementById('citizenStatementsList');
    if (statementTextarea && !isDraft && !isSubmission) {
      statementTextarea.disabled = true;
      if (statementSaveButton) statementSaveButton.disabled = true;
    }
    if (isSubmission) {
      renderSubmissionAssertions(submissionAssertionsList, docket.assertions);
      renderAssertionOptions(docket.assertions);
    } else {
      const ownStatements = statements.filter((statement) => !statement.recorded_by_role);
      bindCitizenStatement(caseReference, ownStatements[ownStatements.length - 1]);
      updateSubmitAvailability(ownStatements.length > 0 && isDraft);
      renderStatementList(submissionAssertionsList, statements);
    }
    const submitButton = document.getElementById('submitCitizenDocketForReview');
    if (submitButton && !isDraft) {
      submitButton.disabled = true;
      submitButton.textContent = `Submission ${docket.status}`;
      const hint = document.getElementById('submitDocketHint');
      if (hint) hint.textContent = 'This submission is already in the review pipeline.';
    }
    bindCitizenSubmit(caseReference);
    const reviewResult = await ensureProtectedSubmissionReview(caseReference, docket, linkedCase);
    bindCitizenProceduralCaseAction(caseReference, reviewResult, linkedCase);

    const summaryText = document.getElementById('citizenSubmissionSummaryText');
    const submissionToggle = document.getElementById('citizenSubmissionToggle');
    if (summaryText) {
      summaryText.textContent = buildCitizenSubmissionSummaryText(docket);
    }
    if (submissionToggle && structuredBody) {
      submissionToggle.textContent = 'View submitted information';
      submissionToggle.setAttribute('aria-expanded', 'false');
      submissionToggle.onclick = () => {
        const isHidden = structuredBody.classList.toggle('hidden');
        const expanded = !isHidden;
        submissionToggle.textContent = expanded ? 'Hide submitted information' : 'View submitted information';
        submissionToggle.setAttribute('aria-expanded', String(expanded));
        structuredBody.setAttribute('aria-expanded', String(expanded));
      };
      structuredBody.classList.add('hidden');
      structuredBody.setAttribute('aria-expanded', 'false');
    }
    if (structuredBody) {
      structuredBody.innerHTML = buildStructuredSubmissionMarkup(docket);
    }
    renderEvidenceTable(evidenceBody, docket.evidence);
    bindCitizenEvidence(caseReference);
    bindCitizenCorrection(caseReference);
    bindCitizenWithdrawal(caseReference);

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

function getValueOrEmpty(elementId) {
  const element = document.getElementById(elementId);
  return element ? (element.value || '').trim() : '';
}

function getCheckedValues(name) {
  return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map((input) => input.value);
}

function getSelectedRadioValue(name) {
  const selected = document.querySelector(`input[name="${name}"]:checked`);
  return selected ? selected.value : '';
}

function formatPeopleCountLabel(value) {
  const normalized = String(value || '').trim();
  if (!normalized) {
    return 'Not specified';
  }
  const map = {
    '1': '1',
    '2': '2',
    '3-5': '3–5',
    '6-10': '6–10',
    'more_than_10': 'More than 10',
    'unknown': 'Unknown / Not sure',
  };
  return map[normalized] || normalized;
}

function formatHarmTypeLabel(value) {
  const map = {
    physical: 'Physical',
    psychological: 'Psychological',
    financial: 'Financial',
    reputational: 'Reputational',
    property: 'Property',
    safety: 'Safety risk',
  };
  return map[String(value || '').trim()] || String(value || '').replace(/_/g, ' ');
}

function formatInjuryTypeLabel(value) {
  const map = {
    minor: 'Minor',
    serious: 'Serious',
    emergency: 'Emergency / urgent',
    none: 'None observed',
  };
  return map[String(value || '').trim()] || String(value || '').replace(/_/g, ' ');
}

function formatInjuryPersonLabel(value, otherValue) {
  const map = {
    affected_person: 'Affected person',
    witness: 'Witness',
    police_official: 'Police / official',
    reporting_person: 'Reporting person',
    other: 'Other',
    unknown: 'Unknown / Not sure',
  };
  const normalized = String(value || '').trim();
  if (!normalized) {
    return 'Not specified';
  }
  if (normalized === 'other' && otherValue) {
    return `Other (${otherValue})`;
  }
  return map[normalized] || normalized.replace(/_/g, ' ');
}

function formatPropertyImpactLabel(value) {
  const normalized = String(value || '').trim();
  if (!normalized) {
    return 'Not specified';
  }
  if (normalized === 'Not sure' || normalized === 'Unknown') return 'Not sure';
  return normalized;
}

function renderCitizenReview() {
  const review = document.getElementById('citizenSubmissionReview');
  if (!review) {
    return;
  }

  const reporterRelationship = getValueOrEmpty('reporterRelationship') || getValueOrEmpty('legacyReporterRelationship');
  const reporterRelationshipOther = getValueOrEmpty('reporterRelationshipOther');
  const canContact = getValueOrEmpty('canContact');
  const contactMethod = getValueOrEmpty('contactMethod');
  const title = getValueOrEmpty('crimeType') || getValueOrEmpty('submissionTitle');
  const incidentType = getValueOrEmpty('incidentType') || getValueOrEmpty('incidentClassification');
  const incidentTypeOther = getValueOrEmpty('incidentTypeOther');
  const exactDate = getValueOrEmpty('incidentDate');
  const dateCertainty = getValueOrEmpty('dateCertainty');
  const location = getValueOrEmpty('incidentLocation') || getValueOrEmpty('locationDescription');
  const narrative = getValueOrEmpty('description') || getValueOrEmpty('whatHappened');
  const beforeIncident = getValueOrEmpty('beforeIncident');
  const afterIncident = getValueOrEmpty('afterIncident');
  const otherPeopleInvolved = getValueOrEmpty('otherPeopleInvolved');
  const peopleCount = getValueOrEmpty('peopleCount');
  const peopleSummary = otherPeopleInvolved === 'Yes'
    ? `People involved: Yes • Approximate number of people involved: ${formatPeopleCountLabel(peopleCount)}`
    : otherPeopleInvolved === 'No'
      ? 'People involved: No'
      : otherPeopleInvolved === 'Not sure'
        ? 'People involved: Not sure'
        : 'People involved: Not selected';
  const harmSummary = getValueOrEmpty('harmImpact') || getValueOrEmpty('harmDescription');
  const harmTypes = getCheckedValues('harmType').map(formatHarmTypeLabel);
  const harmTypesSummary = harmTypes.length ? `Harm types: ${harmTypes.join(', ')}` : 'Harm types: Not specified';
  const wasAnyoneHarmed = getValueOrEmpty('wasAnyoneHarmed');
  const wasAnyoneInjured = getValueOrEmpty('wasAnyoneInjured');
  const injuryTypes = getCheckedValues('injuryType').map(formatInjuryTypeLabel);
  const injuryTypeSummary = injuryTypes.length ? `Injury type: ${injuryTypes.join(', ')}` : 'Injury type: Not specified';
  const injuryPersonType = getValueOrEmpty('injuryPersonType');
  const injuryPersonOther = getValueOrEmpty('injuryPersonOther');
  const injuryPersonSummary = `Who was injured: ${formatInjuryPersonLabel(injuryPersonType, injuryPersonOther)}`;
  const medicalAttention = getValueOrEmpty('medicalAttention');
  const medicalAttentionDetails = getValueOrEmpty('medicalAttentionDetails');
  const injuryDescription = getValueOrEmpty('injuries');
  const propertyImpactQuestion = getValueOrEmpty('propertyImpactQuestion');
  const propertyImpactSummary = `Property/financial impact: ${formatPropertyImpactLabel(propertyImpactQuestion)}`;
  const evidenceSummary = getValueOrEmpty('evidenceSummary');
  const previousReport = getValueOrEmpty('previousReportReference');
  const currentSafetySummary = getValueOrEmpty('currentSafetySummary');

  const contactSummary = canContact === 'Yes' ? `${contactMethod || 'No preference'} contact recorded` : 'No contact requested';
  const incidentSummary = [
    reporterRelationship ? `Reporter relationship: ${reporterRelationship === 'other' ? reporterRelationshipOther || 'Other' : reporterRelationship}` : '',
    title ? `Title: ${title}` : '',
    incidentType ? `Incident type: ${incidentType === 'other' ? incidentTypeOther || 'Other' : incidentType}` : '',
    exactDate ? `Incident date: ${exactDate}` : '',
    dateCertainty ? `Date certainty: ${dateCertainty}` : '',
    location ? `Location: ${location}` : '',
    narrative ? `Narrative: ${narrative}` : '',
  ].filter(Boolean).slice(0, 6);

  const harmSummaryText = harmSummary || 'No harm details entered';
  const evidenceSummaryText = evidenceSummary || 'No evidence details entered';
  const previousSummary = previousReport || 'No previous report provided';
  const injurySummary = [
    wasAnyoneHarmed ? `Harmed or at risk: ${wasAnyoneHarmed}` : 'Harmed or at risk: Not specified',
    harmTypesSummary,
    wasAnyoneInjured ? `Injured: ${wasAnyoneInjured}` : 'Injured: Not specified',
    injuryTypeSummary,
    injuryPersonSummary,
    medicalAttention ? `Medical attention: ${medicalAttention}` : 'Medical attention: Not specified',
    medicalAttention === 'Yes' && medicalAttentionDetails ? `Medical treatment/details: ${medicalAttentionDetails}` : '',
    injuryDescription ? `Injury details: ${injuryDescription}` : 'Injury details: Not specified',
    propertyImpactSummary
  ].filter(Boolean).join(' • ');

  review.innerHTML = `
    <div class="stack-list">
      <article class="mini-case-card"><strong>About you</strong><p>${reporterRelationship || 'Not selected'} • ${contactSummary}</p></article>
      <article class="mini-case-card"><strong>Incident</strong><p>${incidentSummary.join(' • ') || 'No incident details entered yet'}</p></article>
      <article class="mini-case-card"><strong>People</strong><p>${peopleSummary}</p></article>
      <article class="mini-case-card"><strong>Harm and injury</strong><p>${injurySummary}</p></article>
      <article class="mini-case-card"><strong>Harm narrative</strong><p>${harmSummaryText}</p></article>
      <article class="mini-case-card"><strong>Evidence</strong><p>${evidenceSummaryText}</p></article>
      <article class="mini-case-card"><strong>Previous report</strong><p>${previousSummary}</p></article>
      <article class="mini-case-card"><strong>Immediate safety</strong><p>${currentSafetySummary || 'No immediate safety details entered yet'}</p></article>
      ${beforeIncident || afterIncident ? `<article class="mini-case-card"><strong>Sequence</strong><p>${beforeIncident ? 'Before: ' + beforeIncident.slice(0, 90) : ''}${afterIncident ? ' After: ' + afterIncident.slice(0, 90) : ''}</p></article>` : ''}
    </div>
  `;
}

function bindConditionalCitizenForm() {
  const reporterRelationship = document.getElementById('reporterRelationship');
  const reporterRelationshipOther = document.getElementById('reporterRelationshipOther');
  const reporterRelationshipOtherWrap = document.getElementById('reporterRelationshipOtherWrap');
  if (reporterRelationship && reporterRelationshipOtherWrap) {
    const syncReporterOther = () => {
      const show = reporterRelationship.value === 'other';
      reporterRelationshipOtherWrap.classList.toggle('hidden', !show);
      if (!show && reporterRelationshipOther) {
        reporterRelationshipOther.value = '';
      }
    };
    reporterRelationship.addEventListener('change', syncReporterOther);
    syncReporterOther();
  }

  const canContact = document.getElementById('canContact');
  const contactFields = document.getElementById('contactFields');
  if (canContact && contactFields) {
    const syncContact = () => {
      const show = canContact.value === 'Yes';
      contactFields.classList.toggle('hidden', !show);
      if (!show) {
        const contactMethod = document.getElementById('contactMethod');
        const contactPhone = document.getElementById('contactPhone');
        const contactEmail = document.getElementById('contactEmail');
        const contactSms = document.getElementById('contactSms');
        if (contactMethod) contactMethod.value = 'No preference';
        if (contactPhone) contactPhone.value = '';
        if (contactEmail) contactEmail.value = '';
        if (contactSms) contactSms.value = '';
      }
    };
    canContact.addEventListener('change', syncContact);
    syncContact();
  }

  const incidentType = document.getElementById('incidentType');
  const incidentTypeOther = document.getElementById('incidentTypeOther');
  const incidentTypeOtherWrap = document.getElementById('incidentTypeOtherWrap');
  if (incidentType && incidentTypeOtherWrap) {
    const syncIncidentTypeOther = () => {
      const show = incidentType.value === 'other';
      incidentTypeOtherWrap.classList.toggle('hidden', !show);
      if (!show && incidentTypeOther) {
        incidentTypeOther.value = '';
      }
    };
    incidentType.addEventListener('change', syncIncidentTypeOther);
    syncIncidentTypeOther();
  }

  const dateCertainty = document.getElementById('dateCertainty');
  const exactDateWrap = document.getElementById('exactDateWrap');
  const approximateDateWrap = document.getElementById('approximateDateWrap');
  const unknownDateWrap = document.getElementById('unknownDateWrap');
  if (dateCertainty) {
    const syncDate = () => {
      const value = dateCertainty.value;
      if (exactDateWrap) exactDateWrap.classList.toggle('hidden', value !== 'exact');
      if (approximateDateWrap) approximateDateWrap.classList.toggle('hidden', value !== 'approximate');
      if (unknownDateWrap) unknownDateWrap.classList.toggle('hidden', value !== 'unknown');
    };
    dateCertainty.addEventListener('change', syncDate);
    syncDate();
  }

  const locationKnown = document.getElementById('locationKnown');
  const locationWrap = document.getElementById('locationKnownFields');
  const policeFacilityWrap = document.getElementById('policeFacilityWrap');
  if (locationKnown) {
    const syncLocation = () => {
      const show = locationKnown.value === 'Yes';
      if (locationWrap) locationWrap.classList.toggle('hidden', !show);
      if (policeFacilityWrap) policeFacilityWrap.classList.toggle('hidden', !show);
    };
    locationKnown.addEventListener('change', syncLocation);
    syncLocation();
  }

  const otherPeopleInvolved = document.getElementById('otherPeopleInvolved');
  const personCountWrap = document.getElementById('personCountWrap');
  const peopleCount = document.getElementById('peopleCount');
  if (otherPeopleInvolved && peopleCount) {
    const syncPeople = () => {
      const show = otherPeopleInvolved.value === 'Yes';
      if (personCountWrap) {
        personCountWrap.classList.toggle('hidden', !show);
      }
      if (!show) {
        peopleCount.value = '';
      }
      renderCitizenReview();
    };
    otherPeopleInvolved.addEventListener('change', syncPeople);
    peopleCount.addEventListener('change', renderCitizenReview);
    syncPeople();
  }

  const harmQuestion = document.getElementById('wasAnyoneHarmed');
  const harmFields = document.getElementById('harmFields');
  const harmFieldsText = document.getElementById('harmFieldsText');
  const harmTypeCheckboxes = Array.from(document.querySelectorAll('input[name="harmType"]'));
  if (harmQuestion && harmFields) {
    const syncHarm = () => {
      const show = harmQuestion.value === 'Yes';
      harmFields.classList.toggle('hidden', !show);
      if (harmFieldsText) {
        harmFieldsText.classList.toggle('hidden', !show);
      }
      if (!show) {
        harmTypeCheckboxes.forEach((checkbox) => {
          checkbox.checked = false;
        });
        const harmImpact = document.getElementById('harmImpact');
        if (harmImpact) harmImpact.value = '';
      }
    };
    harmQuestion.addEventListener('change', syncHarm);
    harmTypeCheckboxes.forEach((checkbox) => {
      checkbox.addEventListener('change', renderCitizenReview);
    });
    syncHarm();
  }

  const injuryQuestion = document.getElementById('wasAnyoneInjured');
  const injuryFields = document.getElementById('injuryFields');
  const medicalAttentionField = document.getElementById('medicalAttention');
  const medicalAttentionDetails = document.getElementById('medicalAttentionFields');
  const injuryPersonType = document.getElementById('injuryPersonType');
  const injuryPersonOtherWrap = document.getElementById('injuryPersonOtherWrap');
  const injuryCheckboxes = Array.from(document.querySelectorAll('input[name="injuryType"]'));
  if (injuryQuestion && injuryFields) {
    const syncInjury = () => {
      injuryFields.classList.toggle('hidden', injuryQuestion.value !== 'Yes');
      if (injuryQuestion.value !== 'Yes') {
        injuryCheckboxes.forEach((checkbox) => {
          checkbox.checked = false;
        });
        if (medicalAttentionField) medicalAttentionField.value = '';
        if (document.getElementById('medicalAttentionDetails')) document.getElementById('medicalAttentionDetails').value = '';
        if (injuryPersonType) injuryPersonType.value = '';
        if (document.getElementById('injuryPersonOther')) document.getElementById('injuryPersonOther').value = '';
        if (document.getElementById('injuries')) document.getElementById('injuries').value = '';
      }
      if (medicalAttentionField && medicalAttentionDetails) {
        const show = medicalAttentionField.value === 'Yes';
        medicalAttentionDetails.classList.toggle('hidden', !show);
        if (!show && document.getElementById('medicalAttentionDetails')) {
          document.getElementById('medicalAttentionDetails').value = '';
        }
      }
      renderCitizenReview();
    };
    injuryQuestion.addEventListener('change', syncInjury);
    if (medicalAttentionField) {
      medicalAttentionField.addEventListener('change', syncInjury);
    }
    if (injuryPersonType) {
      injuryPersonType.addEventListener('change', () => {
        const show = injuryPersonType.value === 'other';
        if (injuryPersonOtherWrap) injuryPersonOtherWrap.classList.toggle('hidden', !show);
        const otherField = document.getElementById('injuryPersonOther');
        if (!show && otherField) otherField.value = '';
        renderCitizenReview();
      });
    }
    injuryCheckboxes.forEach((checkbox) => {
      checkbox.addEventListener('change', () => {
        const noneCheckbox = injuryCheckboxes.find((entry) => entry.value === 'none');
        if (checkbox.value === 'none' && checkbox.checked) {
          injuryCheckboxes.forEach((entry) => {
            if (entry !== checkbox && entry.value !== 'none') {
              entry.checked = false;
            }
          });
        }
        if (checkbox.value !== 'none' && checkbox.checked && noneCheckbox) {
          noneCheckbox.checked = false;
        }
        renderCitizenReview();
      });
    });
    syncInjury();
  }

  const propertyQuestion = document.getElementById('propertyImpactQuestion');
  const propertyFields = document.getElementById('propertyFields');
  if (propertyQuestion && propertyFields) {
    const syncProperty = () => {
      const show = propertyQuestion.value === 'Yes';
      propertyFields.classList.toggle('hidden', !show);
      if (!show) {
        const propertyType = Array.from(document.querySelectorAll('input[name="propertyType"]'));
        propertyType.forEach((checkbox) => {
          checkbox.checked = false;
        });
        const propertyPerson = document.getElementById('propertyPerson');
        const propertyValue = document.getElementById('propertyValue');
        const propertyImpact = document.getElementById('propertyImpact');
        if (propertyPerson) propertyPerson.value = '';
        if (propertyValue) propertyValue.value = '';
        if (propertyImpact) propertyImpact.value = '';
      }
    };
    propertyQuestion.addEventListener('change', syncProperty);
    syncProperty();
  }

  const evidenceQuestion = document.getElementById('evidenceAvailable');
  const evidenceFields = document.getElementById('evidenceFields');
  if (evidenceQuestion && evidenceFields) {
    const syncEvidence = () => {
      evidenceFields.classList.toggle('hidden', evidenceQuestion.value !== 'Yes');
    };
    evidenceQuestion.addEventListener('change', syncEvidence);
    syncEvidence();
  }

  const previousReportQuestion = document.getElementById('previousReportQuestion');
  const previousReportFields = document.getElementById('previousReportFields');
  if (previousReportQuestion && previousReportFields) {
    const syncPreviousReport = () => {
      previousReportFields.classList.toggle('hidden', previousReportQuestion.value !== 'Yes');
    };
    previousReportQuestion.addEventListener('change', syncPreviousReport);
    syncPreviousReport();
  }

  const currentSafetyQuestion = document.getElementById('currentSafetyQuestion');
  const currentSafetyFields = document.getElementById('currentSafetyFields');
  if (currentSafetyQuestion && currentSafetyFields) {
    const syncSafety = () => {
      currentSafetyFields.classList.toggle('hidden', currentSafetyQuestion.value !== 'Yes');
    };
    currentSafetyQuestion.addEventListener('change', syncSafety);
    syncSafety();
  }

  const reviewFields = document.querySelectorAll('#citizenSubmissionForm input, #citizenSubmissionForm textarea, #citizenSubmissionForm select');
  reviewFields.forEach((field) => {
    if (field.dataset.reviewBound === 'true') {
      return;
    }
    field.addEventListener('input', renderCitizenReview);
    field.addEventListener('change', renderCitizenReview);
    field.dataset.reviewBound = 'true';
  });
  if (document.getElementById('peopleRecords')) {
    document.getElementById('peopleRecords').addEventListener('input', renderCitizenReview);
    document.getElementById('peopleRecords').addEventListener('change', renderCitizenReview);
  }
}

function buildStructuredSubmissionPayload() {
  const title = getValueOrEmpty('crimeType') || getValueOrEmpty('submissionTitle');
  const description = getValueOrEmpty('description') || getValueOrEmpty('whatHappened');
  const incidentDate = getValueOrEmpty('incidentDate');
  const location = getValueOrEmpty('incidentLocation') || getValueOrEmpty('locationDescription');
  const reporterRelationship = getValueOrEmpty('reporterRelationship') || getValueOrEmpty('legacyReporterRelationship');
  const reporterRelationshipOther = getValueOrEmpty('reporterRelationshipOther');
  const canContact = getValueOrEmpty('canContact');
  const contactMethod = getValueOrEmpty('contactMethod');
  const phone = getValueOrEmpty('contactPhone');
  const email = getValueOrEmpty('contactEmail');
  const sms = getValueOrEmpty('contactSms');
  const dateCertainty = getValueOrEmpty('dateCertainty');
  const incidentType = getValueOrEmpty('incidentType');
  const incidentTypeOther = getValueOrEmpty('incidentTypeOther');
  const beforeIncident = getValueOrEmpty('beforeIncident');
  const afterIncident = getValueOrEmpty('afterIncident');
  const locationKnown = getValueOrEmpty('locationKnown');
  const area = getValueOrEmpty('locationArea');
  const policeStation = getValueOrEmpty('policeStation');
  const policeFacility = getValueOrEmpty('policeFacility');
  const incidentTime = getValueOrEmpty('incidentTime');
  const approxTime = getValueOrEmpty('approximateTime');
  const otherPeopleInvolved = getValueOrEmpty('otherPeopleInvolved');
  const peopleCount = getValueOrEmpty('peopleCount');

  const wasAnyoneHarmed = getValueOrEmpty('wasAnyoneHarmed');
  const harmTypes = getCheckedValues('harmType');
  const harmDescription = getValueOrEmpty('harmImpact') || getValueOrEmpty('harmDescription');
  const wasAnyoneInjured = getValueOrEmpty('wasAnyoneInjured');
  const injuryType = getCheckedValues('injuryType');
  const injuryPersonType = getValueOrEmpty('injuryPersonType');
  const injuryPersonOther = getValueOrEmpty('injuryPersonOther');
  const medicalAttention = getValueOrEmpty('medicalAttention');
  const medicalAttentionDetails = getValueOrEmpty('medicalAttentionDetails');
  const injuryDescription = getValueOrEmpty('injuries');
  const propertyImpactQuestion = getValueOrEmpty('propertyImpactQuestion');
  const propertyType = getCheckedValues('propertyType');
  const propertyPerson = getValueOrEmpty('propertyPerson');
  const propertyValue = getValueOrEmpty('propertyValue');
  const propertyDescription = getValueOrEmpty('propertyImpact');
  const evidenceAvailable = getValueOrEmpty('evidenceAvailable');
  const evidenceTypes = getCheckedValues('evidenceType');
  const evidenceSummary = getValueOrEmpty('evidenceSummary');
  const previousReportQuestion = getValueOrEmpty('previousReportQuestion');
  const previousReportType = getValueOrEmpty('previousReportType');
  const previousReportReference = getValueOrEmpty('previousReportReference');
  const previousReportDate = getValueOrEmpty('previousReportDate');
  const previousReportContext = getValueOrEmpty('previousReportBelief');
  const currentSafetyQuestion = getValueOrEmpty('currentSafetyQuestion');
  const currentRiskTypes = getCheckedValues('currentRiskType');
  const currentSafetySummary = getValueOrEmpty('currentSafetySummary');

  const payload = {
    title,
    description,
    incident_date: incidentDate,
    location,
    reporter_relationship: reporterRelationship || undefined,
    reporter_relationship_other: reporterRelationshipOther || undefined,
    can_contact: canContact || undefined,
    preferred_contact_method: contactMethod || undefined,
    contact_phone: phone || undefined,
    contact_email: email || undefined,
    contact_sms: sms || undefined,
    incident_type: incidentType || undefined,
    incident_type_other: incidentTypeOther || undefined,
    date_certainty: dateCertainty || undefined,
    incident_time: incidentTime || undefined,
    approximate_time: approxTime || undefined,
    location_known: locationKnown || undefined,
    location_area: area || undefined,
    police_station_or_unit: policeStation || undefined,
    police_facility_name: policeFacility || undefined,
    narrative_before_incident: beforeIncident || undefined,
    narrative_after_incident: afterIncident || undefined,
    other_people_involved: otherPeopleInvolved || undefined,
    people_count: peopleCount || undefined,
    was_anyone_harmed: wasAnyoneHarmed || undefined,
    harm_types: harmTypes.length ? harmTypes : undefined,
    harm_description: harmDescription || undefined,
    was_anyone_injured: wasAnyoneInjured || undefined,
    injury_types: injuryType.length ? injuryType : undefined,
    injury_person_type: injuryPersonType || undefined,
    injury_person_other: injuryPersonOther || undefined,
    medical_attention: medicalAttention || undefined,
    medical_attention_details: medicalAttentionDetails || undefined,
    injury_description: injuryDescription || undefined,
    property_impact_question: propertyImpactQuestion || undefined,
    property_types: propertyType.length ? propertyType : undefined,
    property_affected_person: propertyPerson || undefined,
    property_value: propertyValue || undefined,
    property_description: propertyDescription || undefined,
    evidence_available: evidenceAvailable || undefined,
    evidence_types: evidenceTypes.length ? evidenceTypes : undefined,
    evidence_summary: evidenceSummary || undefined,
    previous_report_question: previousReportQuestion || undefined,
    previous_report_type: previousReportType || undefined,
    previous_report_reference: previousReportReference || undefined,
    previous_report_date: previousReportDate || undefined,
    previous_report_context: previousReportContext || undefined,
    current_safety_question: currentSafetyQuestion || undefined,
    current_risk_types: currentRiskTypes.length ? currentRiskTypes : undefined,
    current_safety_summary: currentSafetySummary || undefined,
  };

  Object.keys(payload).forEach((key) => {
    if (payload[key] === undefined || payload[key] === null || payload[key] === '') {
      delete payload[key];
    }
  });

  if (Object.keys(payload).length && !payload.title && !payload.description) {
    return {};
  }

  return payload;
}

export function hydrateCitizenForm() {
  const formButton = document.getElementById('submitCitizenDocket');
  if (!formButton) {
    return;
  }

  bindConditionalCitizenForm();
  renderCitizenReview();

  formButton.addEventListener('click', async () => {
    const legacyTitle = getValueOrEmpty('crimeType');
    const legacyDescription = getValueOrEmpty('description');
    const legacyIncidentDate = getValueOrEmpty('incidentDate');
    const legacyLocation = getValueOrEmpty('incidentLocation');

    const payload = buildStructuredSubmissionPayload();
    const finalPayload = Object.keys(payload).length
      ? payload
      : {
          title: legacyTitle,
          description: legacyDescription,
          incident_date: legacyIncidentDate,
          location: legacyLocation,
        };

    try {
      const result = await fetchJson('/api/v1/citizen/submissions', {
        method: 'POST',
        body: finalPayload,
      });
      flashToast('Your protected submission has been recorded and will be reviewed before any procedural case is created.');
      window.location.href = `/citizen/dockets/${result.submission_id}`;
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
