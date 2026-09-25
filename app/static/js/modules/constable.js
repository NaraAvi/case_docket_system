/**
 * Constable triage queue and individual docket review workspace.
 */

import { fetchJson, postForm } from '../core/api.js';
import { bindFilePreview, bindMediaViewButtons, buildStatusBadge, flashToast, renderDocketCardList, renderEvidenceTable, renderMediaViewButton, renderStatementList, renderWorkflowRail, setEmptyState, showToast } from '../core/ui.js';

export function getConstableCaseReference() {
  const match = window.location.pathname.match(/\/constable\/dockets\/([^/]+)/);
  return match ? match[1] : null;
}

async function loadConstableQueue(container, query) {
  try {
    const queue = query
      ? await fetchJson(`/api/v1/constable/dockets/search?q=${encodeURIComponent(query)}`)
      : await fetchJson('/api/v1/constable/dockets/unregistered');
    renderDocketCardList(container, queue, {
      linkPrefix: '/constable/dockets/',
      title: (item) => item.location,
      status: (item) => item.status || 'AWAITING_CONSTABLE_REGISTRATION',
      emptyMessage: query ? `No dockets match "${query}".` : 'No unregistered dockets are currently waiting for triage.',
    });
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load constable queue.');
  }
}

function bindConstableSearch(container) {
  const input = document.getElementById('constableSearch');
  const button = document.getElementById('constableSearchBtn');
  if (!input || !button) {
    return;
  }
  const runSearch = () => loadConstableQueue(container, input.value.trim());
  button.addEventListener('click', runSearch);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      runSearch();
    }
  });
}

export async function hydrateConstableDashboard() {
  const container = document.getElementById('constableQueueState');
  if (!container) {
    return;
  }

  await loadConstableQueue(container, '');
  bindConstableSearch(container);
}

function formatProtectedSourceValue(value) {
  if (value === undefined || value === null || value === '') {
    return 'Not provided';
  }
  if (Array.isArray(value)) {
    return value.filter((item) => item !== undefined && item !== null && item !== '').map((item) => String(item)).join(', ') || 'Not provided';
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}

function renderProtectedSource(container, docket) {
  if (!container) {
    return;
  }
  const originalContent = docket?.citizen_submission?.original_content && typeof docket.citizen_submission.original_content === 'object'
    ? docket.citizen_submission.original_content
    : {};
  const sourceEntries = Array.isArray(Object.entries(originalContent)) ? Object.entries(originalContent) : [];
  const rows = sourceEntries.filter(([, value]) => value !== undefined && value !== null && value !== '');

  if (!rows.length) {
    container.innerHTML = '<div class="empty-state">No preserved citizen source details are available for this docket.</div>';
    return;
  }

  const renderedRows = rows
    .map(([key, value]) => `<dt>${key.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())}</dt><dd>${formatProtectedSourceValue(value)}</dd>`)
    .join('');

  container.innerHTML = `
    <article class="mini-case-card">
      <div class="stack-row" style="justify-content:space-between;">
        <strong>Protected citizen source (read-only)</strong>
        <span class="badge badge-muted">immutable</span>
      </div>
      <dl class="meta-list compact">${renderedRows}</dl>
    </article>
  `;
}

function renderProtectedSourceProvenance(container, docket) {
  if (!container) {
    return;
  }
  const blocks = [];

  const assertions = Array.isArray(docket?.citizen_assertions) ? docket.citizen_assertions : [];
  if (assertions.length) {
    blocks.push(`
      <article class="mini-case-card">
        <strong>Citizen assertions</strong>
        ${assertions
          .map((item) => `
            <p>
              <span class="badge badge-muted">${item.provenance || 'CITIZEN_ASSERTED'}</span>
              <strong>${item.assertion_id || 'Assertion'}</strong>
            </p>
            <p>${item.assertion_text || 'No assertion text provided.'}</p>
          `)
          .join('')}
      </article>
    `);
  }

  const claims = Array.isArray(docket?.citizen_claims) ? docket.citizen_claims : [];
  if (claims.length) {
    blocks.push(`
      <article class="mini-case-card">
        <strong>Citizen claims</strong>
        ${claims
          .map((item) => `
            <p>
              <strong>${item.claim_id || 'Claim'}</strong>
              <span class="badge badge-muted">${item.assessment_state || item.provenance || 'CITIZEN_ASSERTED'}</span>
            </p>
            <p>${item.subject || 'report'} ${item.predicate || 'asserted'} ${item.object_value || ''}</p>
          `)
          .join('')}
      </article>
    `);
  }

  const candidate = docket?.incident_candidate;
  if (candidate) {
    blocks.push(`
      <article class="mini-case-card">
        <strong>System-derived incident candidate</strong>
        <p>${candidate.candidate_id || 'Candidate'} • ${candidate.gate_decision || 'UNSPECIFIED'}</p>
      </article>
    `);
  }

  if (!blocks.length) {
    container.innerHTML = '<div class="empty-state">No protected source provenance has been preserved for this docket.</div>';
    return;
  }

  container.innerHTML = blocks.join('');
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

function renderProceduralAssessment(container, docket) {
  if (!container) {
    return;
  }

  const assessment = docket?.procedural_assessment;
  if (!assessment || !Array.isArray(assessment.indicator_codes)) {
    container.innerHTML = '<div class="empty-state">No system procedural assessment is available for this docket.</div>';
    return;
  }

  const indicatorBadges = assessment.indicator_codes.map((code) => `<span class="badge badge-muted">${code}</span>`).join('');
  container.innerHTML = `
    <article class="mini-case-card">
      <div class="stack-row" style="justify-content:space-between;">
        <strong>SYSTEM PROCEDURAL ASSESSMENT</strong>
        <span class="badge badge-muted">${assessment.attention_level || 'ROUTINE'}</span>
      </div>
      <p style="margin-top:10px;">Read-only system-generated assessment.</p>
      <p>${assessment.summary || 'The system generated a procedural assessment using the protected case source. No legal conclusion has been made.'}</p>
      <div class="stack-row" style="flex-wrap:wrap; margin-top:10px; gap:6px;">${indicatorBadges || '<span class="badge badge-muted">NO_INDICATORS</span>'}</div>
    </article>
  `;
}

function renderInterviewStatus(container, interview) {
  if (!container) {
    return;
  }
  const citizenDone = Boolean(interview.citizen_recording && interview.citizen_recording.status === 'SUBMITTED');
  const constableDone = Boolean(interview.constable_recording && interview.constable_recording.status === 'SUBMITTED');

  let summary;
  if (interview.status === 'COMPLETED') {
    summary = '✓ Both recordings submitted. You can now register the docket below.';
  } else if (constableDone && !citizenDone) {
    summary = '✓ Your recording is submitted. Waiting on the citizen to submit theirs before you can register this docket.';
  } else if (!constableDone && citizenDone) {
    summary = 'The citizen has submitted their recording. Submit yours below to complete the interview.';
  } else {
    summary = 'Submit your recording below. The citizen will submit theirs separately from their docket page.';
  }

  container.innerHTML = `
    <p>${summary}</p>
    <p><strong>Interview status:</strong> ${interview.status}</p>
    <p>Citizen recording: ${citizenDone ? 'Submitted' : 'Awaiting citizen'} ${citizenDone ? renderMediaViewButton(interview.citizen_recording?.storage_reference) : ''}</p>
    <p>Constable recording: ${constableDone ? 'Submitted' : 'Awaiting constable'} ${constableDone ? renderMediaViewButton(interview.constable_recording?.storage_reference) : ''}</p>
  `;
  bindMediaViewButtons(container);
}

async function hydrateInterview(caseReference, interviewId) {
  const panel = document.getElementById('constableInterviewPanel');
  const continueButton = document.getElementById('continueToInterview');
  const statusBox = document.getElementById('constableInterviewStatus');
  const fileInput = document.getElementById('constableRecordingFile');
  const submitButton = document.getElementById('submitConstableRecording');
  const errorEl = document.getElementById('constableRecordingError');
  const registerButton = document.getElementById('registerDocketBtn');
  if (!panel) {
    return;
  }

  panel.classList.remove('hidden');
  if (continueButton) {
    continueButton.classList.add('hidden');
  }
  bindFilePreview('constableRecordingFile', 'constableRecordingFilePreview');

  async function refreshInterview() {
    const interview = await fetchJson(`/api/v1/constable/interviews/${interviewId}`);
    renderInterviewStatus(statusBox, interview);
    const constableDone = Boolean(interview.constable_recording && interview.constable_recording.status === 'SUBMITTED');
    if (submitButton) {
      submitButton.disabled = constableDone;
    }
    if (fileInput) {
      fileInput.disabled = constableDone;
    }
    if (registerButton) {
      registerButton.disabled = interview.status !== 'COMPLETED';
    }
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
      formData.append('recording_type', 'constable_recording');
      await postForm(`/api/v1/constable/interviews/${interviewId}/recording`, formData);
      await refreshInterview();
      showToast('Recording submitted.');
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to submit recording.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to submit recording.', { type: 'error' });
    }
  });

  registerButton?.addEventListener('click', async () => {
    try {
      await fetchJson(`/api/v1/constable/interviews/${interviewId}/register`, { method: 'POST' });
      // The docket is REGISTERED now, which constable/open_docket rejects
      // (constable access is scoped to AWAITING_CONSTABLE_REGISTRATION) --
      // send the constable back to their queue instead of this now-inaccessible page.
      flashToast(`Docket ${caseReference} registered successfully.`);
      window.location.href = '/constable';
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to register docket.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to register docket.', { type: 'error' });
    }
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
      showToast(editingFlagId ? 'Flag updated.' : 'Flag recorded.');
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to save flag.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to save flag.', { type: 'error' });
    }
  });

  return { openForEdit: openModal };
}

function renderConstableWorkflow(docket, interview) {
  const rail = document.getElementById('constableWorkflowRail');
  if (!rail) {
    return;
  }
  const status = (docket.status || '').toUpperCase();
  const hasInterview = Boolean(interview);
  const citizenDone = Boolean(interview && interview.citizen_recording && interview.citizen_recording.status === 'SUBMITTED');
  const constableDone = Boolean(interview && interview.constable_recording && interview.constable_recording.status === 'SUBMITTED');
  const isRegistered = status === 'REGISTERED';

  const steps = [
    { label: 'Review Docket', state: 'complete', detail: 'Case opened and reviewed' },
    { label: 'Interview', state: 'upcoming', detail: 'Start interview' },
    { label: 'Recordings', state: 'upcoming', detail: 'Awaiting recording submission' },
    { label: 'Registration', state: 'upcoming', detail: 'Backend registration required' },
  ];

  if (!hasInterview) {
    steps[1].state = 'current';
  } else {
    steps[1].state = 'complete';
    steps[1].detail = 'Interview initialized';
    if (!(citizenDone && constableDone)) {
      steps[2].state = 'current';
    }
  }

  if (citizenDone && constableDone) {
    steps[2].state = 'complete';
    steps[2].detail = 'Both recordings submitted';
    steps[3].state = isRegistered ? 'complete' : 'current';
    steps[3].detail = isRegistered ? 'Docket registered' : 'Awaiting backend registration';
  } else if (isRegistered) {
    steps[2].state = 'complete';
    steps[2].detail = 'Both recordings submitted';
    steps[3].state = 'complete';
    steps[3].detail = 'Docket registered';
  }

  renderWorkflowRail(rail, { title: 'Constable workflow', steps, locked: Boolean(docket.is_frozen) });
}

export async function hydrateConstableReview() {
  const caseReference = getConstableCaseReference();
  if (!caseReference) {
    return;
  }

  const meta = document.getElementById('constableCaseMeta');
  const statementsList = document.getElementById('constableStatementsList');
  const protectedSource = document.getElementById('constableProtectedSource');
  const sourceProvenance = document.getElementById('constableSourceProvenance');
  const evidenceBody = document.getElementById('constableCaseEvidence');
  const flagList = document.getElementById('constableFlagList');
  const relatedBox = document.getElementById('constableRelatedCases');
  const statusBadge = document.getElementById('constableStatusBadge');
  const freezeBadge = document.getElementById('constableFreezeBadge');
  const frozenNotice = document.getElementById('constableFrozenNotice');
  const frozenReason = document.getElementById('constableFrozenReason');
  const docketContent = document.getElementById('constableDocketContent');

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

  let isFrozen = false;
  try {
    const docket = await fetchJson(`/api/v1/constable/dockets/${caseReference}`);
    let interview = null;
    if (docket.interview_id) {
      interview = await fetchJson(`/api/v1/constable/interviews/${docket.interview_id}`);
    }
    renderConstableWorkflow(docket, interview);
    if (statusBadge) {
      statusBadge.className = buildStatusBadge(docket.status);
      statusBadge.textContent = docket.status || 'AWAITING_CONSTABLE_REGISTRATION';
    }
    if (freezeBadge) {
      if (docket.is_frozen) {
        freezeBadge.textContent = `Frozen — under IPID review${docket.freeze_reason ? `: ${docket.freeze_reason}` : ''}`;
        freezeBadge.classList.remove('hidden');
      } else {
        freezeBadge.classList.add('hidden');
      }
    }

    isFrozen = Boolean(docket.is_frozen);
    if (isFrozen) {
      if (frozenReason) {
        frozenReason.textContent = `This docket has been frozen by IPID while under independent review${docket.freeze_reason ? `: ${docket.freeze_reason}` : '.'}`;
      }
      frozenNotice?.classList.remove('hidden');
      docketContent?.classList.add('hidden');
      return;
    }
    frozenNotice?.classList.add('hidden');
    docketContent?.classList.remove('hidden');

    if (meta) {
      meta.innerHTML = `
        <dt>Title</dt><dd>${docket.title || 'Unspecified'}</dd>
        <dt>Location</dt><dd>${docket.location || 'Not provided'}</dd>
        <dt>Incident Date</dt><dd>${docket.incident_date || 'Not provided'}</dd>
        <dt>Status</dt><dd>${docket.status || 'AWAITING_CONSTABLE_REGISTRATION'}</dd>
      `;
    }
    renderStatementList(statementsList, docket.statements);
    renderProtectedSource(protectedSource, docket);
    renderProtectedSourceProvenance(sourceProvenance, docket);
    renderProceduralAssessment(document.getElementById('constableProceduralAssessment'), docket);

    const evidenceItems = Array.isArray(docket.citizen_evidence) && docket.citizen_evidence.length
      ? docket.citizen_evidence
      : Array.isArray(docket.evidence)
        ? docket.evidence
        : [];
    renderEvidenceTable(evidenceBody, evidenceItems);

    if (docket.interview_id) {
      await hydrateInterview(caseReference, docket.interview_id);
    } else {
      const continueButton = document.getElementById('continueToInterview');
      if (continueButton) {
        continueButton.addEventListener('click', async () => {
          try {
            const interview = await fetchJson(`/api/v1/constable/dockets/${caseReference}/interview`, { method: 'POST' });
            await hydrateInterview(caseReference, interview.interview_id);
            showToast('Interview started. Submit your recording below once ready.');
          } catch (error) {
            showToast(error.message || 'Unable to start interview.', { type: 'error' });
          }
        });
      }
    }
  } catch (error) {
    if (meta) {
      meta.innerHTML = `<dt>Status</dt><dd>Unavailable</dd><dt>Message</dt><dd>${error.message}</dd>`;
    }
    return;
  }

  await refreshFlags();
  await refreshRelatedCases(caseReference, relatedBox);
  bindRelatedCaseForm(caseReference, relatedBox);
}

async function refreshRelatedCases(caseReference, relatedBox) {
  try {
    const related = await fetchJson(`/api/v1/constable/dockets/${caseReference}/related`);
    if (relatedBox) {
      relatedBox.innerHTML = related.length
        ? related
            .map((item) => `<p><strong>${item.relationship_type}</strong>: ${item.related_case_reference === caseReference ? item.source_case_reference : item.related_case_reference}${item.notes ? ` — ${item.notes}` : ''}</p>`)
            .join('')
        : '<p>No direct related case links detected.</p>';
    }
  } catch (error) {
    if (relatedBox) {
      relatedBox.innerHTML = `<p>${error.message}</p>`;
    }
    showToast(error.message || 'Unable to load related cases.', { type: 'error' });
  }
}

function bindRelatedCaseForm(caseReference, relatedBox) {
  const referenceField = document.getElementById('relatedCaseReference');
  const notesField = document.getElementById('relatedCaseNotes');
  const submitButton = document.getElementById('addRelatedCaseBtn');
  const errorEl = document.getElementById('relatedCaseError');
  if (!submitButton) {
    return;
  }

  submitButton.addEventListener('click', async () => {
    const relatedCaseReference = referenceField?.value.trim();
    errorEl?.classList.add('hidden');
    if (!relatedCaseReference) {
      if (errorEl) {
        errorEl.textContent = 'A case reference is required.';
        errorEl.classList.remove('hidden');
      }
      return;
    }
    try {
      await fetchJson(`/api/v1/constable/dockets/${caseReference}/related`, {
        method: 'POST',
        body: {
          related_case_reference: relatedCaseReference,
          relationship_type: 'RELATED_CASE',
          notes: notesField?.value.trim() || undefined,
        },
      });
      if (referenceField) referenceField.value = '';
      if (notesField) notesField.value = '';
      await refreshRelatedCases(caseReference, relatedBox);
      showToast('Related case link recorded.');
    } catch (error) {
      if (errorEl) {
        errorEl.textContent = error.message || 'Unable to link related case.';
        errorEl.classList.remove('hidden');
      }
      showToast(error.message || 'Unable to link related case.', { type: 'error' });
    }
  });
}

export function init() {
  if (document.body.dataset.role === 'constable' && document.getElementById('constableQueueState')) {
    hydrateConstableDashboard();
  }
  if (window.location.pathname.startsWith('/constable/dockets/')) {
    hydrateConstableReview();
  }
}
