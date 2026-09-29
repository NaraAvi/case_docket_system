/**
 * Detective investigation list and individual case workspace.
 */

import { fetchJson, fetchMediaBlobUrl } from '../core/api.js';
import { buildStatusBadge, flashToast, populateSelect, renderDocketCardList, renderEvidenceTable, renderStatementList, renderTimelineList, renderWorkflowRail, setEmptyState, showToast } from '../core/ui.js';

const DETECTIVE_EVIDENCE_TYPES = ['PHOTO', 'VIDEO', 'DOCUMENT', 'AUDIO', 'WITNESS_STATEMENT', 'OTHER'];

function renderReadOnlyFlags(container, flags) {
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
        </article>
      `
    )
    .join('');
}

function renderProtectedSubmission(container, docket) {
  if (!container) {
    return;
  }
  const originalContent = docket?.citizen_submission?.original_content && typeof docket.citizen_submission.original_content === 'object'
    ? docket.citizen_submission.original_content
    : {};
  const flattenedEntries = Object.entries(originalContent).filter(([, value]) => value !== undefined && value !== null && value !== '');

  if (!flattenedEntries.length) {
    container.innerHTML = '<div class="empty-state">No original protected citizen submission is available for this docket.</div>';
    return;
  }

  const entries = flattenedEntries
    .map(([key, value]) => `<dt>${String(key).replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())}</dt><dd>${String(Array.isArray(value) ? value.join(', ') : value)}</dd>`)
    .join('');

  container.innerHTML = `
    <article class="mini-case-card">
      <div class="stack-row" style="justify-content:space-between; align-items:center;">
        <strong>Original protected citizen submission</strong>
        <span class="badge badge-muted">read-only</span>
      </div>
      <dl class="meta-list compact">${entries}</dl>
    </article>
  `;
}

function resolveTranscriptText(recording) {
  if (!recording) {
    return '';
  }
  if (typeof recording.transcript_text === 'string' && recording.transcript_text.trim()) {
    return recording.transcript_text.trim();
  }
  if (recording.transcript && typeof recording.transcript === 'string' && recording.transcript.trim()) {
    return recording.transcript.trim();
  }
  if (recording.transcript && typeof recording.transcript === 'object') {
    if (typeof recording.transcript.text === 'string' && recording.transcript.text.trim()) {
      return recording.transcript.text.trim();
    }
    if (typeof recording.transcript.content === 'string' && recording.transcript.content.trim()) {
      return recording.transcript.content.trim();
    }
  }
  return '';
}

function resolveTranscriptError(recording) {
  if (!recording) {
    return '';
  }

  const transcript = recording.transcript;
  if (transcript && typeof transcript === 'object') {
    const directError = transcript.error || transcript.message;
    if (typeof directError === 'string' && directError.trim()) {
      return directError.trim();
    }
  }

  const altError = recording.transcript_error || recording.transcript_message || recording.error;
  if (typeof altError === 'string' && altError.trim()) {
    return altError.trim();
  }

  const status = String(recording.transcript_status || '').toUpperCase();
  if (['BLOCKED', 'FAILED', 'ERROR'].includes(status)) {
    return 'Transcription could not be completed for this recording.';
  }

  return '';
}

function renderRecordingComparison(container, report) {
  if (!container) {
    return;
  }

  const isWaitingForBoth = report?.status === 'WAITING_FOR_BOTH_TRANSCRIPTS';
  if (!report || report.status === 'COMPARISON_UNAVAILABLE' || isWaitingForBoth) {
    const message = isWaitingForBoth
      ? (report?.error || 'Waiting for both transcripts before comparison can run.')
      : (report?.error || 'No transcript comparison is available yet.');
    container.innerHTML = `
      <strong>Recording consistency check</strong>
      <p>${message}</p>
    `;
    return;
  }

  const findings = Array.isArray(report.findings) && report.findings.length
    ? report.findings.map((finding) => `<li><strong>${finding.category}</strong> — ${finding.summary}</li>`).join('')
    : '<li>No material differences detected in the current transcript comparison.</li>';

  container.innerHTML = `
    <strong>Recording consistency check</strong>
    <p>Overall similarity: ${report.overall_similarity ?? 'n/a'}%</p>
    <ul>${findings}</ul>
  `;
}

async function renderDetectiveInterviewDetails(container, docket, interview, comparisonReport = null) {
  if (!container) {
    return;
  }

  container.innerHTML = '';
  const sectionWrap = document.createElement('div');
  sectionWrap.className = 'stack-list';

  const hasInterviewRecordings = Boolean(interview && (interview.citizen_recording || interview.constable_recording));
  if (hasInterviewRecordings) {
    const mediaHolder = document.createElement('div');
    mediaHolder.className = 'interview-media-holder';

    const renderRecording = async (key, label) => {
      const rec = interview?.[key];
      const block = document.createElement('section');
      block.className = 'mini-case-card';

      const title = document.createElement('div');
      title.className = 'stack-row';
      title.innerHTML = `<strong>${label}</strong><span>${rec ? (rec.submitted_at || rec.created_at || '') : 'No recording'}</span>`;
      block.appendChild(title);

      if (rec && rec.storage_reference) {
        const audio = document.createElement('audio');
        audio.controls = true;
        audio.preload = 'metadata';
        block.appendChild(audio);

        try {
          audio.src = await fetchMediaBlobUrl(`/api/v1/media/${rec.storage_reference}`);
        } catch (error) {
          const fallback = document.createElement('p');
          fallback.textContent = 'Unable to load audio.';
          block.appendChild(fallback);
        }

        const transcriptBox = document.createElement('div');
        transcriptBox.className = 'transcript-box';
        const transcriptText = resolveTranscriptText(rec);
        const transcriptError = resolveTranscriptError(rec);
        const status = rec.transcript_status || (transcriptText ? 'COMPLETED' : 'MISSING');
        transcriptBox.innerHTML = `<p><strong>Transcript status:</strong> ${status}</p>`;

        if (transcriptText) {
          const pre = document.createElement('pre');
          pre.textContent = transcriptText;
          transcriptBox.appendChild(pre);
        } else if (transcriptError) {
          const message = document.createElement('p');
          message.textContent = transcriptError;
          transcriptBox.appendChild(message);
        } else {
          const message = document.createElement('p');
          message.textContent = 'No transcript is available for this recording yet.';
          transcriptBox.appendChild(message);
        }
        block.appendChild(transcriptBox);
      } else {
        const message = document.createElement('p');
        message.textContent = 'No recording file available.';
        block.appendChild(message);
      }

      mediaHolder.appendChild(block);
    };

    await renderRecording('citizen_recording', 'Citizen recording');
    await renderRecording('constable_recording', 'Constable recording');
    sectionWrap.appendChild(mediaHolder);

    const comparisonBox = document.createElement('div');
    comparisonBox.className = 'mini-case-card';
    renderRecordingComparison(comparisonBox, comparisonReport);
    sectionWrap.appendChild(comparisonBox);
  }

  const statementsWrap = document.createElement('div');
  statementsWrap.className = 'statement-list';
  renderStatementList(statementsWrap, Array.isArray(docket?.statements) ? docket.statements : []);
  sectionWrap.appendChild(statementsWrap);

  container.appendChild(sectionWrap);
}

export function getDetectiveCaseReference() {
  const match = window.location.pathname.match(/\/detective\/dockets\/([^/]+)/);
  return match ? match[1] : null;
}

function getInvestigationEffectiveStatus(item) {
  const investigationStatus = String(item?.investigation?.status || item?.investigation_status || '').trim().toUpperCase();
  return investigationStatus === 'COMPLETED' ? 'COMPLETED' : null;
}

export async function hydrateDetectiveDashboard() {
  const container = document.getElementById('detectiveInvestigationList');
  if (!container) {
    return;
  }

  try {
    const allCases = await fetchJson('/api/v1/station-commander/dockets');
    const registeredCases = (Array.isArray(allCases) ? allCases : []).filter((item) => {
      const isRegistered = (item.status || '').toUpperCase() === 'REGISTERED';
      return isRegistered && getInvestigationEffectiveStatus(item) !== 'COMPLETED';
    });
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

function buildInvestigationActionReferenceOptions(actions = []) {
  const countsByType = {};
  return (Array.isArray(actions) ? actions : []).map((action) => {
    const actionType = String(action?.action_type || '').trim().toUpperCase();
    const occurrence = (countsByType[actionType] || 0) + 1;
    countsByType[actionType] = occurrence;

    const label = (() => {
      switch (actionType) {
        case 'WITNESS_CONTACT':
          return `Witness Contact #${occurrence}`;
        case 'INTERVIEW':
          return `Interview #${occurrence}`;
        case 'EVIDENCE_REVIEW':
          return `Evidence Review #${occurrence}`;
        case 'EVIDENCE_COLLECTION':
          return `Evidence Collection #${occurrence}`;
        case 'RECORD_REQUEST':
          return `Record Request #${occurrence}`;
        case 'SCENE_REVIEW':
          return `Scene Review #${occurrence}`;
        default:
          return `${formatRequiredActionLabel(actionType) || 'Investigation Record'} #${occurrence}`;
      }
    })();

    return {
      value: String(action?.action_id || ''),
      label,
      detail: action?.purpose || action?.result || action?.description || '',
    };
  }).filter((option) => option.value);
}

function buildFindingReferenceOptions(findings = []) {
  return (Array.isArray(findings) ? findings : []).map((finding, index) => ({
    value: String(finding?.finding_id || ''),
    label: `Finding #${index + 1}`,
    detail: String(finding?.notes || finding?.finding_text || '').trim() || 'Saved finding without text.',
  })).filter((option) => option.value);
}

function getSelectedValuesFromContainer(container, { type = 'checkbox' } = {}) {
  if (!container) {
    return [];
  }
  const fromCheckboxes = Array.from(container.querySelectorAll(`input[type="${type}"]:checked`)).map((checkbox) => checkbox.value).filter(Boolean);
  if (fromCheckboxes.length) {
    return fromCheckboxes;
  }
  const fromSelections = Array.from(container.querySelectorAll('option:checked')).map((option) => option.value).filter(Boolean);
  if (fromSelections.length) {
    return fromSelections;
  }
  return [];
}

function renderCheckboxList(container, items = [], { emptyText = 'No selection available.', fieldName = 'selection' } = {}) {
  if (!container) {
    return;
  }
  const options = Array.isArray(items) ? items : [];
  if (!options.length) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(emptyText)}</div>`;
    return;
  }

  container.innerHTML = options
    .map((item) => `
      <label class="checkbox-row" style="display:flex; align-items:flex-start; gap:10px; margin:8px 0; cursor:pointer;">
        <input type="checkbox" name="${escapeHtml(fieldName)}" value="${escapeHtml(item.value || '')}" />
        <span>
          <strong>${escapeHtml(item.label || 'Selection')}</strong>
          ${item.detail ? `<span class="field-hint" style="display:block; margin-top:4px;">${escapeHtml(item.detail)}</span>` : ''}
        </span>
      </label>
    `)
    .join('');
}

function renderFindings(container, findings, actions = []) {
  if (!container) {
    return;
  }
  if (!findings.length) {
    container.innerHTML = '<div class="empty-state">No findings have been recorded yet.</div>';
    return;
  }

  const actionLookup = {};
  buildInvestigationActionReferenceOptions(actions).forEach((option) => {
    actionLookup[option.value] = option.label;
  });

  container.innerHTML = findings
    .map((finding, index) => {
      const noteText = String(finding?.notes || finding?.finding_text || '').trim() || 'No finding text recorded.';
      const refs = Array.isArray(finding?.action_ids) && finding.action_ids.length
        ? finding.action_ids.map((actionId) => actionLookup[String(actionId)] || `Record ${String(actionId)}`).filter(Boolean)
        : [];
      const refsMarkup = refs.length
        ? `<ul style="margin:8px 0 0 18px; padding:0;">${refs.map((label) => `<li>${escapeHtml(label)}</li>`).join('')}</ul>`
        : '<div class="field-hint" style="margin-top:8px;">No investigation records referenced.</div>';
      return `
        <article class="mini-case-card">
          <div class="stack-row" style="justify-content:space-between; align-items:flex-start;">
            <strong>Finding #${index + 1}</strong>
            <span>${finding.created_at || ''}</span>
          </div>
          <p style="margin-top:8px;">${escapeHtml(noteText)}</p>
          <div style="margin-top:10px;">
            <strong>Investigation records referenced:</strong>
            ${refsMarkup}
          </div>
        </article>
      `;
    })
    .join('');
}

function renderInvestigationTimer(container, investigation) {
  if (!container) {
    return;
  }
  if (!investigation) {
    container.innerHTML = '<div class="empty-state">Investigation has not started.</div>';
    return;
  }

  const startedAtIso = investigation.created_at || investigation.started_at || investigation.opened_at || investigation.updated_at;
  const startedAt = startedAtIso ? new Date(startedAtIso) : null;
  const elapsedMs = startedAt && !Number.isNaN(startedAt.getTime()) ? Date.now() - startedAt.getTime() : null;

  const elapsedText = elapsedMs === null
    ? 'Awaiting server timestamp.'
    : (() => {
        const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
        const days = Math.floor(totalSeconds / 86400);
        const hours = Math.floor((totalSeconds % 86400) / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        if (days > 0) {
          return `${days}d ${hours}h ${minutes}m`;
        }
        if (hours > 0) {
          return `${hours}h ${minutes}m ${seconds}s`;
        }
        if (minutes > 0) {
          return `${minutes}m ${seconds}s`;
        }
        return `${seconds}s`;
      })();

  container.innerHTML = `
    <article class="mini-case-card">
      <div class="stack-row" style="justify-content:space-between; align-items:center;">
        <strong>Investigation Started</strong>
        <span class="badge badge-muted">${startedAtIso ? new Date(startedAtIso).toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, ' UTC') : 'Not recorded'}</span>
      </div>
      <div class="stack-row" style="justify-content:space-between; align-items:center; margin-top:6px;">
        <span>Elapsed Investigation Time</span>
        <strong>${elapsedText}</strong>
      </div>
    </article>
  `;
}

const REQUIRED_ACTION_SEQUENCE = [
  'WITNESS_CONTACT',
  'INTERVIEW',
  'EVIDENCE_REVIEW',
  'EVIDENCE_COLLECTION',
  'RECORD_REQUEST',
  'SCENE_REVIEW',
];

const ACTION_RECORD_SECTIONS = {
  WITNESS_CONTACT: [
    ['Witness', 'witness_name'],
    ['Relationship to incident', 'relationship_to_incident'],
    ['Known contact information', 'known_contact_information'],
    ['How identified', 'how_witness_was_identified'],
    ['Contact date', 'contact_date'],
    ['Contact time', 'contact_time'],
    ['Contact method', 'contact_method'],
    ['Result', 'result'],
    ['Information obtained', 'information_obtained'],
    ['Lead generated', 'lead_generated'],
    ['Lead description', 'lead_description'],
    ['Explanation', 'explanation'],
  ],
  INTERVIEW: [
    ['Person interviewed', 'person_name'],
    ['Role', 'role'],
    ['Interview date', 'interview_date'],
    ['Interview time', 'interview_time'],
    ['Location / method', 'location_method'],
    ['Interview type', 'interview_type'],
    ['Recording uploads', 'recording_uploads'],
    ['Interview notes uploads', 'interview_notes_uploads'],
    ['Information obtained', 'information_obtained'],
    ['Contradictions / inconsistencies', 'contradictions'],
    ['Contradiction explanation', 'contradiction_explanation'],
    ['Follow-up lead', 'follow_up_lead'],
    ['Lead description', 'lead_description'],
    ['Outcome', 'outcome'],
    ['Outcome explanation', 'outcome_explanation'],
  ],
  EVIDENCE_REVIEW: [
    ['Evidence reviewed', 'selected_evidence_ids'],
    ['Observation', 'observation'],
    ['Interpretation', 'interpretation'],
    ['Unknown / limitation', 'unknown_limitation'],
    ['Consistency', 'consistency'],
  ],
  EVIDENCE_COLLECTION: [
    ['Evidence type', 'evidence_type'],
    ['Description', 'description'],
    ['Source', 'source'],
    ['Where obtained', 'where_obtained'],
    ['Date / time obtained', 'date_time_obtained'],
    ['Provider', 'provider'],
    ['Collection method', 'collection_method'],
    ['Result', 'result'],
    ['Explanation', 'explanation'],
    ['Uploads', 'uploads'],
  ],
  RECORD_REQUEST: [
    ['Record type', 'record_type'],
    ['Record holder', 'record_holder'],
    ['Specific record requested', 'specific_record_requested'],
    ['Date range from', 'date_range_from'],
    ['Date range to', 'date_range_to'],
    ['Reason relevant', 'reason_relevant'],
    ['Date requested', 'date_requested'],
    ['Request reference', 'request_reference'],
    ['Request method', 'request_method'],
    ['Response', 'response'],
    ['Explanation', 'response_explanation'],
    ['Uploaded records', 'uploaded_records'],
  ],
  SCENE_REVIEW: [
    ['Location', 'location'],
    ['Scene date', 'scene_date'],
    ['Scene time', 'scene_time'],
    ['Persons present', 'persons_present'],
    ['Scene condition', 'scene_condition'],
    ['Observations', 'observations'],
    ['Consistent with incident', 'consistent_with_incident'],
    ['What differed', 'differed'],
    ['Not established', 'not_established'],
    ['Scene material', 'scene_material'],
    ['Visibility', 'visibility'],
    ['Lighting', 'lighting'],
    ['Access points', 'access_points'],
    ['Distances', 'distances'],
    ['Obstructions', 'obstructions'],
    ['Limitations', 'limitations'],
  ],
};

function formatRequiredActionLabel(actionType) {
  return String(actionType || '')
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function getInterviewCount(actions = []) {
  return Array.isArray(actions)
    ? actions.filter((action) => String(action?.action_type || '').trim().toUpperCase() === 'INTERVIEW').length
    : 0;
}

function getInterviewLabel(actions = []) {
  return `Interview ${Math.max(1, getInterviewCount(actions) + 1)}`;
}

function renderActionHeader(actionType, actions = []) {
  const label = actionType === 'INTERVIEW' ? getInterviewLabel(actions) : formatRequiredActionLabel(actionType);
  return `<div class="action-form-header">${escapeHtml(label)}</div>`;
}

function getCompletedRequiredActions(actions = []) {
  const completed = new Set();
  for (const action of Array.isArray(actions) ? actions : []) {
    const normalized = String(action?.action_type || action?.type || '').trim().toUpperCase();
    if (!normalized || !REQUIRED_ACTION_SEQUENCE.includes(normalized)) {
      continue;
    }
    completed.add(normalized);
  }
  return completed;
}

function syncFindingsGateState(investigationId, actions = [], procedureState = {}) {
  const openButton = document.getElementById('openFindingModal');
  const proceedButton = document.getElementById('proceedToFindingsButton') || document.querySelector('[data-proceed-to-findings]');
  const currentStage = String((procedureState?.current_stage || '')).toUpperCase();
  const nextAction = String((procedureState?.next_permitted_action || '')).trim();
  const requiredActionsComplete = REQUIRED_ACTION_SEQUENCE.every((actionType) => getCompletedRequiredActions(actions).has(actionType));
  const findingsUnlocked = Boolean(investigationId) && (requiredActionsComplete || currentStage === 'FINDINGS_READY' || nextAction.toLowerCase() === 'document finding');

  if (openButton) {
    openButton.hidden = !findingsUnlocked;
    openButton.disabled = !findingsUnlocked;
  }
  if (proceedButton) {
    proceedButton.hidden = !findingsUnlocked;
    proceedButton.disabled = !findingsUnlocked;
  }

  return findingsUnlocked;
}

function getNextRequiredAction(actions = []) {
  const completed = getCompletedRequiredActions(actions);
  return REQUIRED_ACTION_SEQUENCE.find((actionType) => !completed.has(actionType)) || null;
}

function isCompletedAction(actionType, actions = []) {
  return getCompletedRequiredActions(actions).has(String(actionType || '').trim().toUpperCase());
}

function summariseActionValue(value) {
  if (Array.isArray(value)) {
    return value.filter((entry) => entry !== undefined && entry !== null && entry !== '').map((entry) => String(entry)).join(', ') || 'Not recorded';
  }
  if (value === undefined || value === null || value === '') {
    return 'Not recorded';
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}

function renderActionRecordEntries(action) {
  if (!action) {
    return [];
  }
  const data = action.record_data && typeof action.record_data === 'object' ? action.record_data : {};
  const preferredKeys = ACTION_RECORD_SECTIONS[action.action_type] || [];
  const entries = [];
  for (const [label, key] of preferredKeys) {
    if (key in data) {
      entries.push([label, summariseActionValue(data[key])]);
    }
  }
  if (!entries.length) {
    const fallbackEntries = [
      ['Purpose', action.purpose],
      ['Description', action.description],
      ['Result', action.result_observation ?? action.result],
    ];
    for (const [label, value] of fallbackEntries) {
      if (value !== undefined && value !== null && value !== '') {
        entries.push([label, summariseActionValue(value)]);
      }
    }
  }
  return entries;
}

function renderActionModalReadOnly(action) {
  const entries = renderActionRecordEntries(action);
  if (!entries.length) {
    return '<div class="empty-state">No record content has been stored for this action.</div>';
  }
  const detailList = entries.map(([label, value]) => `
    <div>
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(value)}</dd>
    </div>
  `).join('');
  return `
    <dl class="meta-list compact" style="margin-top:8px;">${detailList}</dl>
  `;
}

function renderEvidenceCollectionItemMarkup(index) {
  return `
    <div data-evidence-collection-item="${index}" data-evidence-collection-index="${index}" style="border:1px solid rgba(148,163,184,0.35); border-radius:10px; padding:12px; margin-bottom:12px;">
      <label class="input-label" style="margin-top:0; display:block;">Description</label>
      <textarea rows="3" data-action-field="description" data-evidence-collection-index="${index}" placeholder="Describe the evidence item"></textarea>
      <label class="input-label" style="margin-top:12px; display:block;">Evidence type</label>
      <select class="field-select" data-action-field="evidence_type" data-evidence-collection-index="${index}">
        <option value="">Select evidence type</option>
        <option value="PHOTO">Photo</option>
        <option value="VIDEO">Video</option>
        <option value="DOCUMENT">Document</option>
        <option value="AUDIO">Audio</option>
        <option value="WITNESS_STATEMENT">Witness statement</option>
        <option value="OTHER">Other</option>
      </select>
      <label class="input-label" style="margin-top:12px; display:block;">Source</label>
      <input class="field-input" data-action-field="source" data-evidence-collection-index="${index}" type="text" placeholder="Source of the evidence" />
      <label class="input-label" style="margin-top:12px; display:block;">Date / time obtained</label>
      <input class="field-input" data-action-field="date_time_obtained" data-evidence-collection-index="${index}" type="datetime-local" />
      <label class="input-label" style="margin-top:12px; display:block;">Person / institution providing it</label>
      <input class="field-input" data-action-field="provider" data-evidence-collection-index="${index}" type="text" placeholder="Provider or custodian" />
      <label class="input-label" style="margin-top:12px; display:block;">Collection method</label>
      <select class="field-select" data-action-field="collection_method" data-evidence-collection-index="${index}">
        <option value="">Select method</option>
        <option value="PHYSICAL_COLLECTION">PHYSICAL_COLLECTION</option>
        <option value="ELECTRONIC_FILE_RECEIVED">ELECTRONIC_FILE_RECEIVED</option>
        <option value="CCTV_EXPORT">CCTV_EXPORT</option>
        <option value="DOCUMENT_SUPPLIED">DOCUMENT_SUPPLIED</option>
        <option value="PHOTOGRAPH_VIDEO">PHOTOGRAPH_VIDEO</option>
        <option value="OTHER">OTHER</option>
      </select>
      <label class="input-label" style="margin-top:12px; display:block;">Collection result</label>
      <select class="field-select" data-action-field="result" data-evidence-collection-index="${index}">
        <option value="">Select result</option>
        <option value="OBTAINED">OBTAINED</option>
        <option value="PARTIALLY_OBTAINED">PARTIALLY_OBTAINED</option>
        <option value="REQUESTED_BUT_UNAVAILABLE">REQUESTED_BUT_UNAVAILABLE</option>
        <option value="REFUSED">REFUSED</option>
        <option value="NO_LONGER_AVAILABLE">NO_LONGER_AVAILABLE</option>
        <option value="OTHER">OTHER</option>
      </select>
      <label class="input-label" style="margin-top:12px; display:block;">Explanation</label>
      <textarea rows="3" data-action-field="explanation" data-evidence-collection-index="${index}" placeholder="Required if the evidence was not fully obtained"></textarea>
      <label class="input-label" style="margin-top:12px; display:block;">Upload(s)</label>
      <input class="field-input" data-action-field="uploads" data-evidence-collection-index="${index}" type="file" multiple accept="image/*,video/*,.pdf,.doc,.docx,.mp4,.mov" />
    </div>
  `;
}

function bindEvidenceCollectionControls(form) {
  if (!form || form.dataset.evidenceCollectionBound === 'true') {
    return;
  }

  form.dataset.evidenceCollectionBound = 'true';
  form.addEventListener('click', (event) => {
    const addButton = event.target.closest('[data-add-evidence-collection-item]');
    if (!addButton) {
      return;
    }

    const nextIndex = form.querySelectorAll('[data-evidence-collection-item]').length;
    const container = form.querySelector('[data-evidence-collection-container]');
    if (container) {
      container.insertAdjacentHTML('beforeend', renderEvidenceCollectionItemMarkup(nextIndex));
      return;
    }

    const buttonRow = addButton.closest('.stack-row');
    if (buttonRow && buttonRow.parentElement) {
      buttonRow.insertAdjacentHTML('beforeend', renderEvidenceCollectionItemMarkup(nextIndex));
    }
  });
}

function populateActionFormOptions(actionType, evidenceItems = [], form = document.getElementById('actionModalFields')) {
  if (!form) {
    return;
  }
  if (actionType === 'EVIDENCE_REVIEW') {
    const select = form.querySelector('[data-action-field="selected_evidence_ids"]');
    if (select) {
      populateSelect(select, evidenceItems || [], {
        valueKey: 'evidence_id',
        labelKey: 'description',
        describeKey: 'evidence_type',
        placeholder: 'Select case evidence…',
      });
    }
  }
}

function renderActionFormForType(actionType, actions = []) {
  const header = renderActionHeader(actionType, actions);
  switch (actionType) {
    case 'WITNESS_CONTACT':
      return `
        ${header}
        <label class="input-label" style="margin-top:12px; display:block;">Witness</label>
        <input class="field-input" data-action-field="witness_name" type="text" placeholder="Witness name or identifier" />
        <label class="input-label" style="margin-top:12px; display:block;">Relationship to incident</label>
        <input class="field-input" data-action-field="relationship_to_incident" type="text" placeholder="Relationship" />
        <label class="input-label" style="margin-top:12px; display:block;">Known contact information</label>
        <input class="field-input" data-action-field="known_contact_information" type="text" placeholder="Phone, email, address, or known contact details" />
        <label class="input-label" style="margin-top:12px; display:block;">How witness was identified</label>
        <textarea rows="3" data-action-field="how_witness_was_identified" placeholder="Describe how the witness was identified"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Contact date</label>
        <input class="field-input" data-action-field="contact_date" type="date" />
        <label class="input-label" style="margin-top:12px; display:block;">Contact time</label>
        <input class="field-input" data-action-field="contact_time" type="time" />
        <label class="input-label" style="margin-top:12px; display:block;">Contact method</label>
        <select class="field-select" data-action-field="contact_method">
          <option value="">Select contact method</option>
          <option value="PHONE">PHONE</option>
          <option value="IN_PERSON">IN_PERSON</option>
          <option value="EMAIL">EMAIL</option>
          <option value="OTHER">OTHER</option>
        </select>
        <label class="input-label" style="margin-top:12px; display:block;">Result</label>
        <select class="field-select" data-action-field="result">
          <option value="">Select result</option>
          <option value="PROVIDED_INFORMATION">PROVIDED_INFORMATION</option>
          <option value="AGREED_TO_INTERVIEW">AGREED_TO_INTERVIEW</option>
          <option value="UNAVAILABLE">UNAVAILABLE</option>
          <option value="DECLINED">DECLINED</option>
          <option value="NO_RELEVANT_INFORMATION">NO_RELEVANT_INFORMATION</option>
          <option value="REFERRED_TO_PERSON_OR_EVIDENCE">REFERRED_TO_PERSON_OR_EVIDENCE</option>
          <option value="OTHER">OTHER</option>
        </select>
        <label class="input-label" style="margin-top:12px; display:block;">Information obtained</label>
        <textarea rows="4" data-action-field="information_obtained" placeholder="What was actually learned?"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Lead generated</label>
        <select class="field-select" data-action-field="lead_generated">
          <option value="">Select</option>
          <option value="true">YES</option>
          <option value="false">NO</option>
        </select>
        <label class="input-label" style="margin-top:12px; display:block;">Lead description</label>
        <textarea rows="3" data-action-field="lead_description" placeholder="If a lead was generated, describe it"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Explanation</label>
        <textarea rows="3" data-action-field="explanation" placeholder="Required for unsuccessful, unavailable, declined, or similar outcomes"></textarea>
      `;
    case 'INTERVIEW':
      return `
        ${header}
        <label class="input-label" style="margin-top:12px; display:block;">Person interviewed</label>
        <input class="field-input" data-action-field="person_name" type="text" placeholder="Name or identifier" />
        <label class="input-label" style="margin-top:12px; display:block;">Role</label>
        <select class="field-select" data-action-field="role">
          <option value="">Select role</option>
          <option value="COMPLAINANT">COMPLAINANT</option>
          <option value="VICTIM">VICTIM</option>
          <option value="WITNESS">WITNESS</option>
          <option value="POLICE_OFFICIAL">POLICE_OFFICIAL</option>
          <option value="IMPLICATED_PERSON">IMPLICATED_PERSON</option>
          <option value="OTHER">OTHER</option>
        </select>
        <label class="input-label" style="margin-top:12px; display:block;">Interview date</label>
        <input class="field-input" data-action-field="interview_date" type="date" />
        <label class="input-label" style="margin-top:12px; display:block;">Interview time</label>
        <input class="field-input" data-action-field="interview_time" type="time" />
        <label class="input-label" style="margin-top:12px; display:block;">Location / method</label>
        <input class="field-input" data-action-field="location_method" type="text" placeholder="Interview location or method" />
        <label class="input-label" style="margin-top:12px; display:block;">Interview type</label>
        <select class="field-select" data-action-field="interview_type">
          <option value="">Select interview type</option>
          <option value="INITIAL">INITIAL</option>
          <option value="FOLLOW_UP">FOLLOW_UP</option>
          <option value="FORMAL">FORMAL</option>
          <option value="OTHER">OTHER</option>
        </select>
        <label class="input-label" style="margin-top:12px; display:block;">Recording upload(s)</label>
        <input class="field-input" data-action-field="recordings" type="file" multiple accept="audio/*,video/*,.mp3,.wav,.m4a,.m4v,.mp4,.mov" />
        <p class="field-hint">Attach the actual audio or video recording(s) captured for this interview.</p>
        <label class="input-label" style="margin-top:12px; display:block;">Interview notes / document upload(s)</label>
        <input class="field-input" data-action-field="interview_notes_uploads" type="file" multiple accept=".pdf,.doc,.docx,.txt,image/*" />
        <p class="field-hint">Attach notes, transcripts, or supporting documents created during the interview.</p>
        <label class="input-label" style="margin-top:12px; display:block;">Information obtained</label>
        <textarea rows="4" data-action-field="information_obtained" placeholder="What did the person say happened? What did they observe? What did they identify?"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Contradictions / inconsistencies</label>
        <select class="field-select" data-action-field="contradictions">
          <option value="">Select contradiction status</option>
          <option value="NONE_IDENTIFIED">NONE_IDENTIFIED</option>
          <option value="IDENTIFIED">IDENTIFIED</option>
        </select>
        <label class="input-label" style="margin-top:12px; display:block;">Contradiction explanation</label>
        <textarea rows="3" data-action-field="contradiction_explanation" placeholder="Explain any contradiction found"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Follow-up lead</label>
        <select class="field-select" data-action-field="follow_up_lead">
          <option value="">Select</option>
          <option value="true">YES</option>
          <option value="false">NO</option>
        </select>
        <label class="input-label" style="margin-top:12px; display:block;">Lead description</label>
        <textarea rows="3" data-action-field="lead_description" placeholder="Describe the follow-up line of inquiry"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Outcome</label>
        <select class="field-select" data-action-field="outcome">
          <option value="">Select outcome</option>
          <option value="INFORMATION_OBTAINED">INFORMATION_OBTAINED</option>
          <option value="NO_MATERIAL_INFORMATION">NO_MATERIAL_INFORMATION</option>
          <option value="PERSON_DISPUTED_ALLEGATION">PERSON_DISPUTED_ALLEGATION</option>
          <option value="INTERVIEW_UNSUCCESSFUL">INTERVIEW_UNSUCCESSFUL</option>
          <option value="OTHER">OTHER</option>
        </select>
        <label class="input-label" style="margin-top:12px; display:block;">Outcome explanation</label>
        <textarea rows="3" data-action-field="outcome_explanation" placeholder="Explain the unsuccessful or materially limited outcome"></textarea>
      `;
    case 'EVIDENCE_REVIEW':
      return `
        ${header}
        <label class="input-label" style="margin-top:12px; display:block;">Existing evidence to review</label>
        <select class="field-select" data-action-field="selected_evidence_ids">
          <option value="">Select case evidence…</option>
        </select>
        <label class="input-label" style="margin-top:12px; display:block;">Observation</label>
        <textarea rows="4" data-action-field="observation" placeholder="What was actually observed?"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Interpretation</label>
        <textarea rows="4" data-action-field="interpretation" placeholder="What might the observation indicate?"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Unknown / limitation</label>
        <textarea rows="4" data-action-field="unknown_limitation" placeholder="What does the evidence not establish or leave unresolved?"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Consistency</label>
        <select class="field-select" data-action-field="consistency">
          <option value="">Select consistency</option>
          <option value="SUPPORTS_EXISTING_INFORMATION">SUPPORTS_EXISTING_INFORMATION</option>
          <option value="CONTRADICTS_EXISTING_INFORMATION">CONTRADICTS_EXISTING_INFORMATION</option>
          <option value="PROVIDES_NEW_INFORMATION">PROVIDES_NEW_INFORMATION</option>
          <option value="INCONCLUSIVE">INCONCLUSIVE</option>
        </select>
      `;
    case 'EVIDENCE_COLLECTION':
      return `
        ${header}
        <div data-evidence-collection-container="true">
          ${renderEvidenceCollectionItemMarkup(0)}
        </div>
        <div class="stack-row" style="justify-content:flex-end; margin-top:8px;">
          <button type="button" class="secondary-btn" data-add-evidence-collection-item="0">Add another evidence item</button>
        </div>
      `;
    case 'RECORD_REQUEST':
      return `
        ${header}
        <label class="input-label" style="margin-top:12px; display:block;">Record type</label>
        <input class="field-input" data-action-field="record_type" type="text" placeholder="CCTV, medical record, duty roster, etc." />
        <label class="input-label" style="margin-top:12px; display:block;">Institution / person holding the record</label>
        <input class="field-input" data-action-field="record_holder" type="text" placeholder="Institution, business, or person" />
        <label class="input-label" style="margin-top:12px; display:block;">Specific record requested</label>
        <textarea rows="3" data-action-field="specific_record_requested" placeholder="Describe the document or record being sought"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Relevant date range (from)</label>
        <input class="field-input" data-action-field="date_range_from" type="date" />
        <label class="input-label" style="margin-top:12px; display:block;">Relevant date range (to)</label>
        <input class="field-input" data-action-field="date_range_to" type="date" />
        <label class="input-label" style="margin-top:12px; display:block;">Reason it is relevant</label>
        <textarea rows="3" data-action-field="reason_relevant" placeholder="Why is this record significant to the case?"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Date requested</label>
        <input class="field-input" data-action-field="date_requested" type="date" />
        <label class="input-label" style="margin-top:12px; display:block;">Request / reference number</label>
        <input class="field-input" data-action-field="request_reference" type="text" placeholder="Reference or case note number" />
        <label class="input-label" style="margin-top:12px; display:block;">Request method</label>
        <select class="field-select" data-action-field="request_method">
          <option value="">Select request method</option>
          <option value="EMAIL">EMAIL</option>
          <option value="PHONE">PHONE</option>
          <option value="IN_PERSON">IN_PERSON</option>
          <option value="PORTAL">PORTAL</option>
          <option value="OTHER">OTHER</option>
        </select>
        <label class="input-label" style="margin-top:12px; display:block;">Response</label>
        <select class="field-select" data-action-field="response">
          <option value="">Select response</option>
          <option value="RECEIVED">RECEIVED</option>
          <option value="PARTIALLY_RECEIVED">PARTIALLY_RECEIVED</option>
          <option value="NO_RESPONSE">NO_RESPONSE</option>
          <option value="REFUSED">REFUSED</option>
          <option value="UNAVAILABLE">UNAVAILABLE</option>
          <option value="PENDING">PENDING</option>
        </select>
        <label class="input-label" style="margin-top:12px; display:block;">Explanation</label>
        <textarea rows="3" data-action-field="response_explanation" placeholder="Explain a no-response, refusal, or unavailable outcome"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Uploaded response records</label>
        <input class="field-input" data-action-field="uploaded_records" type="file" multiple accept=".pdf,.doc,.docx,.txt,image/*" />
      `;
    case 'SCENE_REVIEW':
      return `
        ${header}
        <label class="input-label" style="margin-top:12px; display:block;">Location</label>
        <input class="field-input" data-action-field="location" type="text" placeholder="Scene location" />
        <label class="input-label" style="margin-top:12px; display:block;">Date</label>
        <input class="field-input" data-action-field="scene_date" type="date" />
        <label class="input-label" style="margin-top:12px; display:block;">Time</label>
        <input class="field-input" data-action-field="scene_time" type="time" />
        <label class="input-label" style="margin-top:12px; display:block;">Persons present</label>
        <input class="field-input" data-action-field="persons_present" type="text" placeholder="Who was present at the scene?" />
        <label class="input-label" style="margin-top:12px; display:block;">Scene condition</label>
        <textarea rows="3" data-action-field="scene_condition" placeholder="Describe the scene condition"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Observations</label>
        <textarea rows="3" data-action-field="observations" placeholder="What was observed?"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Consistent with the reported incident</label>
        <textarea rows="3" data-action-field="consistent_with_incident" placeholder="What was consistent with the reported incident?"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">What differed</label>
        <textarea rows="3" data-action-field="differed" placeholder="What differed from the report or expectation?"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">What could not be established</label>
        <textarea rows="3" data-action-field="not_established" placeholder="What could not be established or confirmed?"></textarea>
        <label class="input-label" style="margin-top:12px; display:block;">Scene material</label>
        <input class="field-input" data-action-field="scene_material" type="file" multiple accept="image/*,video/*,.pdf,.doc,.docx,.mp4,.mov" />
        <p class="field-hint">Attach photographs, video stills, plan diagrams, or scene documentation collected during the review.</p>
        <label class="input-label" style="margin-top:12px; display:block;">Visibility</label>
        <input class="field-input" data-action-field="visibility" type="text" placeholder="Visibility" />
        <label class="input-label" style="margin-top:12px; display:block;">Lighting</label>
        <input class="field-input" data-action-field="lighting" type="text" placeholder="Lighting conditions" />
        <label class="input-label" style="margin-top:12px; display:block;">Access points</label>
        <input class="field-input" data-action-field="access_points" type="text" placeholder="Access points or entry routes" />
        <label class="input-label" style="margin-top:12px; display:block;">Distances</label>
        <input class="field-input" data-action-field="distances" type="text" placeholder="Distances or positioning" />
        <label class="input-label" style="margin-top:12px; display:block;">Obstructions</label>
        <input class="field-input" data-action-field="obstructions" type="text" placeholder="Obstructions or barriers" />
        <label class="input-label" style="margin-top:12px; display:block;">Limitations</label>
        <textarea rows="3" data-action-field="limitations" placeholder="What could not be assessed and why?"></textarea>
      `;
    default:
      return '<div class="empty-state">No action-specific form is currently configured for this required action.</div>';
  }
}

function extractActionFormValue(field) {
  if (!field) {
    return '';
  }
  const hasMultiple = field.multiple && field.tagName === 'SELECT';
  if (hasMultiple) {
    return Array.from(field.selectedOptions).map((option) => option.value).filter(Boolean);
  }
  if (field.type === 'checkbox') {
    return field.checked;
  }
  if (field.type === 'file') {
    if (field.multiple && field.files && field.files.length) {
      return Array.from(field.files).map((file) => file.name || '').filter(Boolean);
    }
    if (field.files && field.files.length) {
      return field.files[0].name || '';
    }
    return field.value || '';
  }
  return field.value;
}

function readLegacyActionPayload(actionType) {
  const legacyType = document.getElementById('investigativeActionType');
  const legacyPurpose = document.getElementById('investigativeActionPurpose');
  const legacyDescription = document.getElementById('investigativeActionDescription');
  const legacyResult = document.getElementById('investigativeActionResult');
  const legacyEvidence = document.getElementById('investigativeActionEvidence');
  if (!legacyType && !legacyPurpose && !legacyDescription && !legacyResult && !legacyEvidence) {
    return {};
  }

  const payload = {};
  const resolvedActionType = String((legacyType && legacyType.value) || actionType || '').trim().toUpperCase();
  if (resolvedActionType) {
    payload.action_type = resolvedActionType;
  }
  if (legacyPurpose && legacyPurpose.value && legacyPurpose.value.trim()) {
    payload.purpose = legacyPurpose.value.trim();
  }
  if (legacyDescription && legacyDescription.value && legacyDescription.value.trim()) {
    payload.description = legacyDescription.value.trim();
  }
  if (legacyResult && legacyResult.value && legacyResult.value.trim()) {
    payload.result = legacyResult.value.trim();
  }
  if (legacyEvidence && legacyEvidence.value) {
    payload.evidence_id = legacyEvidence.value;
  }
  return payload;
}

function buildActionModalPayload(actionType) {
  const form = document.getElementById('actionModalFields');
  const legacyPayload = readLegacyActionPayload(actionType);
  const payload = { action_type: actionType };
  if (legacyPayload.action_type) {
    payload.action_type = legacyPayload.action_type;
  }
  if (legacyPayload.purpose) {
    payload.purpose = legacyPayload.purpose;
  }
  if (legacyPayload.description) {
    payload.description = legacyPayload.description;
  }
  if (legacyPayload.result) {
    payload.result = legacyPayload.result;
  }
  if (legacyPayload.evidence_id) {
    payload.evidence_id = legacyPayload.evidence_id;
  }
  const fields = form ? form.querySelectorAll('[data-action-field]') : [];
  for (const field of fields) {
    const key = field.dataset.actionField;
    if (!key) {
      continue;
    }
    const value = extractActionFormValue(field);
    if (value === '' || value === null || value === undefined) {
      continue;
    }
    payload[key] = value;
  }

  if (actionType === 'WITNESS_CONTACT') {
    payload.lead_generated = payload.lead_generated === 'true' || payload.lead_generated === true;
  }
  if (actionType === 'INTERVIEW') {
    payload.follow_up_lead = payload.follow_up_lead === 'true' || payload.follow_up_lead === true;
    const recordingRefs = Array.isArray(payload.recordings)
      ? payload.recordings
      : (typeof payload.recordings === 'string'
        ? payload.recordings.split(',').map((item) => item.trim()).filter(Boolean)
        : []);
    if (recordingRefs.length) {
      payload.recordings = recordingRefs.map((reference) => ({
        storage_reference: reference,
        filename: reference.split('/').pop() || reference,
        recording_type: 'audio',
      }));
      payload.recording_uploads = recordingRefs;
    }
    const noteRefs = Array.isArray(payload.interview_notes_uploads)
      ? payload.interview_notes_uploads
      : (typeof payload.interview_notes_uploads === 'string'
        ? payload.interview_notes_uploads.split(',').map((item) => item.trim()).filter(Boolean)
        : []);
    if (noteRefs.length) {
      payload.interview_notes_uploads = noteRefs;
    }
  }
  if (actionType === 'EVIDENCE_REVIEW') {
    if (typeof payload.selected_evidence_ids === 'string') {
      payload.selected_evidence_ids = payload.selected_evidence_ids.split(',').map((item) => item.trim()).filter(Boolean);
    }
    if (typeof payload.related_evidence_ids === 'string') {
      payload.related_evidence_ids = payload.related_evidence_ids.split(',').map((item) => item.trim()).filter(Boolean);
    }
  }
  if (actionType === 'EVIDENCE_COLLECTION') {
    const evidenceCollectionBlocks = form ? form.querySelectorAll('[data-evidence-collection-index]') : [];
    if (evidenceCollectionBlocks.length) {
      const groupedBlocks = {};
      for (const field of evidenceCollectionBlocks) {
        const index = field.dataset.evidenceCollectionIndex;
        if (!index) {
          continue;
        }
        const key = field.dataset.actionField;
        if (!key) {
          continue;
        }
        if (!groupedBlocks[index]) {
          groupedBlocks[index] = {};
        }
        groupedBlocks[index][key] = extractActionFormValue(field);
      }
      const collectionItems = Object.values(groupedBlocks)
        .map((item) => {
          const normalised = {};
          for (const [key, value] of Object.entries(item)) {
            if (value === '' || value === null || value === undefined) {
              continue;
            }
            normalised[key] = value;
          }
          return Object.keys(normalised).length ? normalised : null;
        })
        .filter(Boolean);
      if (collectionItems.length) {
        payload.collected_evidence_items = collectionItems;
        const primaryItem = collectionItems[0];
        for (const key of ['description', 'evidence_type', 'source', 'date_time_obtained', 'provider', 'collection_method', 'result', 'explanation', 'uploads']) {
          if (primaryItem[key] !== undefined) {
            payload[key] = primaryItem[key];
          }
        }
      }
    }
    if (typeof payload.uploads === 'string') {
      payload.uploads = payload.uploads.split(',').map((item) => item.trim()).filter(Boolean);
    }
  }
  if (actionType === 'RECORD_REQUEST') {
    if (typeof payload.uploaded_records === 'string') {
      payload.uploaded_records = payload.uploaded_records.split(',').map((item) => item.trim()).filter(Boolean);
    }
  }
  if (actionType === 'SCENE_REVIEW') {
    if (typeof payload.scene_material === 'string') {
      payload.scene_material = payload.scene_material.split(',').map((item) => item.trim()).filter(Boolean);
    }
  }
  return payload;
}

function validateActionModalPayload(actionType, payload) {
  const errors = [];
  const form = document.getElementById('actionModalFields');
  const structuredFields = form ? form.querySelectorAll('[data-action-field]') : [];
  const hasStructuredFields = structuredFields.length > 0;
  const legacyActionFields = Boolean(
    document.getElementById('investigativeActionType')
    || document.getElementById('investigativeActionPurpose')
    || document.getElementById('investigativeActionDescription')
    || document.getElementById('investigativeActionResult')
    || document.getElementById('investigativeActionEvidence')
  );
  const legacyPayloadPresent = Boolean(payload.purpose || payload.description || payload.result || payload.result_observation || payload.evidence_id);
  const hasStructuredValues = Array.from(structuredFields).some((field) => {
    const value = extractActionFormValue(field);
    if (Array.isArray(value)) {
      return value.length > 0;
    }
    return value !== '' && value !== null && value !== undefined;
  });
  if (legacyActionFields && legacyPayloadPresent && !hasStructuredValues) {
    return errors;
  }
  if (actionType === 'WITNESS_CONTACT') {
    if (!payload.witness_name) errors.push('Witness name is required.');
    if (!payload.contact_date) errors.push('Witness contact date is required.');
    if (!payload.contact_time) errors.push('Witness contact time is required.');
    if (!payload.contact_method) errors.push('Witness contact method is required.');
    if (!payload.result) errors.push('Witness contact result is required.');
    if (!payload.information_obtained) errors.push('Information obtained is required.');
    if (payload.lead_generated && !payload.lead_description) errors.push('Lead description is required when a lead was generated.');
    if (['UNAVAILABLE', 'DECLINED', 'NO_RELEVANT_INFORMATION', 'REFERRED_TO_PERSON_OR_EVIDENCE', 'OTHER'].includes(payload.result) && !payload.explanation) {
      errors.push('An explanation is required for the selected witness contact outcome.');
    }
  }
  if (actionType === 'INTERVIEW') {
    if (!payload.person_name) errors.push('Person interviewed is required.');
    if (!payload.role) errors.push('Interviewee role is required.');
    if (!payload.interview_date) errors.push('Interview date is required.');
    if (!payload.interview_time) errors.push('Interview time is required.');
    if (!payload.location_method) errors.push('Interview location or method is required.');
    if (!payload.interview_type) errors.push('Interview type is required.');
    if ((!payload.recording_uploads || payload.recording_uploads.length === 0) && (!payload.interview_notes_uploads || payload.interview_notes_uploads.length === 0)) {
      errors.push('At least one recording upload or interview notes/document upload is required.');
    }
    if (!payload.information_obtained) errors.push('Information obtained is required.');
    if (!payload.contradictions) errors.push('Contradictions or inconsistencies status is required.');
    if (payload.contradictions === 'IDENTIFIED' && !payload.contradiction_explanation) errors.push('Contradiction explanation is required when inconsistencies were identified.');
    if (payload.follow_up_lead && !payload.lead_description) errors.push('Lead description is required when a follow-up lead exists.');
    if (!payload.outcome) errors.push('Interview outcome is required.');
    if (['NO_MATERIAL_INFORMATION', 'PERSON_DISPUTED_ALLEGATION', 'INTERVIEW_UNSUCCESSFUL', 'OTHER'].includes(payload.outcome) && !payload.outcome_explanation) {
      errors.push('An explanation is required for unsuccessful or materially limited interview outcomes.');
    }
  }
  if (actionType === 'EVIDENCE_REVIEW') {
    if (!payload.selected_evidence_ids || payload.selected_evidence_ids.length === 0) errors.push('At least one existing evidence item must be selected.');
    if (!payload.observation) errors.push('Observation is required.');
    if (!payload.interpretation) errors.push('Interpretation is required.');
    if (!payload.unknown_limitation) errors.push('Unknown or limitation is required.');
    if (!payload.consistency) errors.push('Consistency status is required.');
  }
  if (actionType === 'EVIDENCE_COLLECTION') {
    const collectionItems = Array.isArray(payload.collected_evidence_items) && payload.collected_evidence_items.length
      ? payload.collected_evidence_items
      : [];
    const primaryItem = collectionItems[0] || payload;
    if (!primaryItem.evidence_type) errors.push('Evidence type is required.');
    else if (!DETECTIVE_EVIDENCE_TYPES.includes(primaryItem.evidence_type)) {
      errors.push('Evidence type must be one of: PHOTO, VIDEO, DOCUMENT, AUDIO, WITNESS_STATEMENT, OTHER.');
    }
    if (!primaryItem.description) errors.push('Evidence description is required.');
    if (!primaryItem.source) errors.push('Evidence source is required.');
    if (!primaryItem.date_time_obtained) errors.push('Date and time obtained is required.');
    if (!primaryItem.provider) errors.push('Provider is required.');
    if (!primaryItem.collection_method) errors.push('Collection method is required.');
    if (!primaryItem.result) errors.push('Collection result is required.');
    if (['PARTIALLY_OBTAINED', 'REQUESTED_BUT_UNAVAILABLE', 'REFUSED', 'NO_LONGER_AVAILABLE', 'OTHER'].includes(primaryItem.result) && !primaryItem.explanation) {
      errors.push('An explanation is required when the evidence was not fully obtained.');
    }
  }
  if (actionType === 'RECORD_REQUEST') {
    if (!payload.record_type) errors.push('Record type is required.');
    if (!payload.record_holder) errors.push('Record holder is required.');
    if (!payload.specific_record_requested) errors.push('Specific record requested is required.');
    if (!payload.date_range_from && !payload.date_range_to) errors.push('A relevant date or date range is required.');
    if (!payload.reason_relevant) errors.push('The record\'s relevance is required.');
    if (!payload.date_requested) errors.push('Date requested is required.');
    if (!payload.request_reference) errors.push('Request reference is required.');
    if (!payload.request_method) errors.push('Request method is required.');
    if (!payload.response) errors.push('Response status is required.');
    if (['NO_RESPONSE', 'REFUSED', 'UNAVAILABLE'].includes(payload.response) && !payload.response_explanation) {
      errors.push('An explanation is required for the selected response outcome.');
    }
  }
  if (actionType === 'SCENE_REVIEW') {
    if (!payload.location) errors.push('Scene location is required.');
    if (!payload.scene_date) errors.push('Scene date is required.');
    if (!payload.scene_time) errors.push('Scene time is required.');
    if (!payload.persons_present) errors.push('Persons present is required.');
    if (!payload.scene_condition) errors.push('Scene condition is required.');
    if (!payload.observations) errors.push('Observations are required.');
    if (!payload.consistent_with_incident) errors.push('What was consistent with the incident is required.');
    if (!payload.differed) errors.push('What differed is required.');
    if (!payload.not_established) errors.push('What could not be established is required.');
    if (!payload.visibility) errors.push('Visibility is required.');
    if (!payload.lighting) errors.push('Lighting is required.');
    if (!payload.access_points) errors.push('Access points are required.');
    if (!payload.distances) errors.push('Distances are required.');
    if (!payload.obstructions) errors.push('Obstructions are required.');
    if (!payload.limitations) errors.push('Limitations are required.');
  }
  return errors;
}

function renderInvestigationOrder(container, actions = [], evidenceItems = []) {
  if (!container) {
    return;
  }
  const completed = getCompletedRequiredActions(actions);
  const completedCount = completed.size;
  const totalRequired = REQUIRED_ACTION_SEQUENCE.length;
  const remainingCount = Math.max(0, totalRequired - completedCount);
  const findingsLocked = remainingCount > 0;
  const summaryText = findingsLocked
    ? `${remainingCount} required investigative action${remainingCount === 1 ? '' : 's'} remain. Findings cannot begin until all six required actions are complete.`
    : 'All required investigative actions are complete. Findings may proceed.';

  const markup = `
    <div class="mini-case-card">
      <div class="stack-row" style="justify-content:space-between; align-items:center;">
        <strong>Required investigative actions: ${completedCount} / ${totalRequired} complete</strong>
        <span class="${findingsLocked ? 'badge badge-warning' : 'badge badge-success'}">${findingsLocked ? 'Findings locked' : 'Findings available'}</span>
      </div>
      <p class="field-hint">${escapeHtml(summaryText)}</p>
      ${findingsLocked ? '' : '<div class="stack-row" style="justify-content:flex-end; margin-top:10px;"><button type="button" class="primary-btn" data-proceed-to-findings>Proceed to findings</button></div>'}
    </div>
    ${REQUIRED_ACTION_SEQUENCE.map((actionType) => {
      const isCompleted = completed.has(actionType);
      const actionLabel = formatRequiredActionLabel(actionType);
      const statusText = isCompleted ? 'COMPLETED' : 'NOT COMPLETED';
      const badgeClass = isCompleted ? 'badge badge-success' : 'badge badge-muted';
      const interviewCount = actionType === 'INTERVIEW' ? getInterviewCount(actions) : 0;
      const buttonLabel = actionType === 'INTERVIEW'
        ? (isCompleted ? `Add Interview ${interviewCount + 1}` : 'Complete Interview')
        : `${isCompleted ? 'Add another' : 'Complete'} ${actionLabel}`;
      const buttonClass = 'primary-btn';
      return `
        <article class="mini-case-card">
          <div class="stack-row" style="justify-content:space-between; align-items:center;">
            <strong>${escapeHtml(actionLabel)}</strong>
            <span class="${badgeClass}">${escapeHtml(statusText)}</span>
          </div>
          <p class="field-hint">Status: ${escapeHtml(statusText)}</p>
          <div class="stack-row" style="justify-content:flex-end; margin-top:8px;">
            <button type="button" class="${buttonClass}" data-required-action-type="${actionType}" style="padding:6px 10px; font-size:12px;">${escapeHtml(buttonLabel)}</button>
          </div>
        </article>
      `;
    }).join('')}
  `;

  container.innerHTML = markup;

  container.querySelectorAll('[data-required-action-type]').forEach((button) => {
    button.addEventListener('click', () => {
      const actionType = button.getAttribute('data-required-action-type');
      const modal = document.getElementById('actionModal');
      const modalContext = document.getElementById('actionModalContext');
      const actionLabel = formatRequiredActionLabel(actionType);
      if (!modal) {
        return;
      }
      modal.dataset.requiredActionType = actionType || '';
      modal.classList.remove('hidden');
      const fields = document.getElementById('actionModalFields');
      if (fields) {
        fields.innerHTML = renderActionFormForType(actionType, actions);
        if (actionType === 'EVIDENCE_COLLECTION') {
          bindEvidenceCollectionControls(fields);
        }
        populateActionFormOptions(actionType, evidenceItems, fields);
      }
      modal.dataset.viewMode = 'edit';
      if (modalContext) {
        if (actionType === 'INTERVIEW') {
          modalContext.textContent = `Record the next interview step. This entry will be numbered as ${getInterviewLabel(actions)}.`;
        } else {
          modalContext.textContent = `Record the ${actionLabel.toLowerCase()} investigation task. Any remaining required action may be completed in any order.`;
        }
      }
      const submitButton = document.getElementById('submitActionModal');
      if (submitButton) {
        submitButton.hidden = false;
        submitButton.disabled = false;
      }
    });
  });

  const proceedButton = container.querySelector('[data-proceed-to-findings]');
  if (proceedButton) {
    proceedButton.addEventListener('click', () => {
      const openFindingButton = document.getElementById('openFindingModal');
      if (openFindingButton) {
        openFindingButton.click();
      }
    });
  }
}

function renderInvestigationActions(container, actions) {
  if (!container) {
    return;
  }
  const items = Array.isArray(actions) ? actions : [];
  if (!items.length) {
    container.innerHTML = '<div class="empty-state">No investigative actions have been recorded yet. The required order remains open.</div>';
    return;
  }
  container.innerHTML = items
    .map((action) => {
      const recordedBy = action.detective_id || action.detective_name || 'Unknown detective';
      const timestamp = action.performed_at || action.created_at || 'Not recorded';
      const summaryEntries = renderActionRecordEntries(action).slice(0, 3);
      const summaryHtml = summaryEntries.length
        ? `<div class="field-hint">${summaryEntries.map(([label, value]) => `<div><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</div>`).join('')}</div>`
        : '<div class="field-hint">Action recorded without the structured summary fields.</div>';
      return `
        <article class="mini-case-card">
          <div class="stack-row" style="justify-content:space-between; align-items:center;">
            <strong>${escapeHtml(action.action_type || 'INVESTIGATIVE_ACTION')}</strong>
            <span class="badge badge-muted">${escapeHtml(timestamp)}</span>
          </div>
          ${summaryHtml}
          <p><strong>Recorded by:</strong> ${escapeHtml(recordedBy)}</p>
          <p><strong>Timestamp:</strong> ${escapeHtml(timestamp)}</p>
          <div class="stack-row" style="justify-content:flex-end; margin-top:8px;">
            <button type="button" class="secondary-btn" data-view-record-action-id="${escapeHtml(action.action_id || '')}" style="padding:6px 10px; font-size:12px;">View Record</button>
          </div>
        </article>
      `;
    })
    .join('');

  container.querySelectorAll('[data-view-record-action-id]').forEach((button) => {
    button.addEventListener('click', () => {
      const actionId = button.getAttribute('data-view-record-action-id');
      const action = items.find((item) => String(item.action_id || '') === String(actionId || ''));
      if (!action) {
        return;
      }
      const modal = document.getElementById('actionModal');
      const modalContext = document.getElementById('actionModalContext');
      const fields = document.getElementById('actionModalFields');
      if (!modal || !fields) {
        return;
      }
      modal.dataset.requiredActionType = action.action_type || '';
      modal.dataset.viewMode = 'view';
      fields.innerHTML = renderActionModalReadOnly(action);
      if (modalContext) {
        modalContext.textContent = `${formatRequiredActionLabel(action.action_type)} record view. This entry is read-only.`;
      }
      const submitButton = document.getElementById('submitActionModal');
      if (submitButton) {
        submitButton.hidden = true;
        submitButton.disabled = true;
      }
      modal.classList.remove('hidden');
    });
  });
}

function renderCaseFactsComparisonResults(container, comparisons = []) {
  if (!container) {
    return;
  }
  const items = Array.isArray(comparisons) ? comparisons : [];
  if (!items.length) {
    container.innerHTML = '<div class="empty-state">No case-fact comparison result is available yet.</div>';
    return;
  }

  container.innerHTML = items.map((item) => {
    const field = item?.field || 'Unknown field';
    const sourceValue = Array.isArray(item?.source_value) ? item.source_value.join(', ') : (item?.source_value ?? 'Not established');
    const observedValue = Array.isArray(item?.observed_value) ? item.observed_value.join(', ') : (item?.observed_value ?? 'Not established');
    const status = item?.comparison_status || item?.status || 'NOT_ESTABLISHED';
    const resolutionStatus = item?.resolution_status || (item?.resolved ? 'ADDRESSED' : 'UNRESOLVED');
    const badgeClass = status === 'MATCH' ? 'badge badge-success' : (status === 'NOT_ESTABLISHED' ? 'badge badge-muted' : 'badge badge-warning');
    return `
      <article class="mini-case-card">
        <div class="stack-row" style="justify-content:space-between; align-items:center;">
          <strong>${escapeHtml(field)}</strong>
          <span class="${badgeClass}">${escapeHtml(status)}</span>
        </div>
        <p><strong>Protected source:</strong> ${escapeHtml(String(sourceValue))}</p>
        <p><strong>Detective record:</strong> ${escapeHtml(String(observedValue))}</p>
        <p><strong>Resolution:</strong> ${escapeHtml(String(resolutionStatus))}</p>
        <p><strong>Basis:</strong> ${escapeHtml(item?.basis || 'No basis recorded.')}</p>
      </article>
    `;
  }).join('');
}

function renderCaseFactsDiscrepancies(container, discrepancies = []) {
  if (!container) {
    return;
  }
  const items = Array.isArray(discrepancies) ? discrepancies : [];
  if (!items.length) {
    container.innerHTML = '<div class="empty-state">No case-fact discrepancies are currently logged.</div>';
    return;
  }

  container.innerHTML = items.map((item) => {
    const field = item?.field || 'Unknown field';
    const original = Array.isArray(item?.original_value) ? item.original_value.join(', ') : (item?.original_value ?? 'Not provided');
    const observed = Array.isArray(item?.observed_value) ? item.observed_value.join(', ') : (item?.observed_value ?? 'Not provided');
    const basis = item?.basis || item?.explanation || 'No basis recorded.';
    const status = item?.status || 'OPEN';
    return `
      <article class="mini-case-card">
        <div class="stack-row" style="justify-content:space-between; align-items:center;">
          <strong>${escapeHtml(field)}</strong>
          <span class="badge badge-muted">${escapeHtml(status)}</span>
        </div>
        <p><strong>Citizen source:</strong> ${escapeHtml(String(original))}</p>
        <p><strong>Detective record:</strong> ${escapeHtml(String(observed))}</p>
        <p><strong>Basis:</strong> ${escapeHtml(String(basis))}</p>
      </article>
    `;
  }).join('');
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[character]));
}

function renderProcedureBoard(container, procedureState = {}, { caseReference = null } = {}) {
  if (!container) {
    return;
  }
  const requirements = Array.isArray(procedureState.requirements) ? procedureState.requirements : [];
  const blockingRequirements = Array.isArray(procedureState.blocking_requirements) ? procedureState.blocking_requirements : [];
  const procedureStatus = procedureState.procedure_status || procedureState.status || 'ACTIVE';
  const nextAction = procedureState.next_permitted_action || 'Start investigation';
  const blockingReason = procedureState.blocking_reason || (blockingRequirements.length ? 'One or more procedure requirements remain unsatisfied.' : 'No blocking requirements remain.');

  const requirementMarkup = requirements.length
    ? requirements.map((requirement, index) => {
      const isSatisfied = Boolean(requirement.satisfied);
      const badgeClass = isSatisfied ? buildStatusBadge('ACTIVE') : buildStatusBadge(requirement.requires_review ? 'REVIEW_REQUIRED' : 'BLOCKED');
      const summary = requirement.blocking_reason || requirement.description || 'No further detail supplied.';
      const ruleBadge = requirement.rule_classification || requirement.category || 'SYSTEM_CONTROL';
      const stateLabel = isSatisfied ? 'Satisfied' : (requirement.requires_review ? 'Review required' : 'Blocked');
      return `
        <article class="mini-case-card">
          <div class="stack-row" style="justify-content:space-between; align-items:center;">
            <strong>${escapeHtml(requirement.title || requirement.rule_code || 'Procedure requirement')}</strong>
            <span class="${badgeClass}">${escapeHtml(stateLabel)}</span>
          </div>
          <p>${escapeHtml(requirement.description || summary)}</p>
          <p class="field-hint">${escapeHtml(summary)}</p>
          <div class="stack-row" style="justify-content:space-between; align-items:center; margin-top:8px;">
            <span class="badge badge-muted">${escapeHtml(ruleBadge)}</span>
            <button type="button" class="secondary-btn" data-procedure-toggle="${index}" style="padding:6px 10px; font-size:12px;">Why is this required?</button>
          </div>
          <div class="hidden" data-procedure-detail="${index}" style="margin-top:8px; padding-top:8px; border-top: 1px solid rgba(148, 163, 184, 0.3);">
            <p><strong>Rule:</strong> ${escapeHtml(requirement.rule_code || 'PROCEDURE.UNKNOWN')}</p>
            <p><strong>Required action:</strong> ${escapeHtml(requirement.required_action || 'Unknown')}</p>
            <p><strong>Required records:</strong> ${escapeHtml((requirement.required_records || []).join(', ') || 'Not specified')}</p>
            <p><strong>Legal basis:</strong> ${escapeHtml(requirement.legal_basis || 'System control')}</p>
            <p><strong>Trigger:</strong> ${escapeHtml(requirement.trigger || 'Procedure evaluation')}</p>
            <p><strong>Source:</strong> ${escapeHtml(requirement.source_reference || 'Protected citizen submission')}</p>
          </div>
        </article>
      `;
    }).join('')
    : '<div class="empty-state">No active procedure requirements are being evaluated for this case.</div>';

  const blockingMarkup = blockingRequirements.length
    ? blockingRequirements.map((requirement) => `
        <div class="mini-case-card">
          <strong>${escapeHtml(requirement.title || requirement.rule_code || 'Blocking requirement')}</strong>
          <p>${escapeHtml(requirement.blocking_reason || requirement.description || 'Outstanding requirement remains unsatisfied.')}</p>
        </div>
      `).join('')
    : '<div class="empty-state">No blocking requirements remain.</div>';

  container.innerHTML = `
    <div class="stack-row" style="justify-content:space-between; align-items:flex-start;">
      <div>
        <p class="eyebrow">Procedure Control</p>
        <h3>Investigation Control Board</h3>
      </div>
      <span class="${buildStatusBadge(procedureStatus)}">${escapeHtml(procedureStatus)}</span>
    </div>
    <div class="detail-grid">
      <div class="detail-card">
        <h4>Procedure Summary</h4>
        <dl class="meta-list">
          <dt>Case</dt><dd>${escapeHtml(caseReference || procedureState.case_reference || 'Unknown')}</dd>
          <dt>Assigned Detective</dt><dd>${escapeHtml(procedureState.assigned_detective_id || procedureState.detective_id || 'Not assigned')}</dd>
          <dt>Procedure Profile</dt><dd>${escapeHtml(procedureState.profile_name || 'DEFAULT')}</dd>
          <dt>Ruleset</dt><dd>${escapeHtml(procedureState.ruleset_version || 'procedure-v1')}</dd>
        </dl>
      </div>
      <div class="detail-card">
        <h4>Current Gate</h4>
        <dl class="meta-list">
          <dt>Current Stage</dt><dd>${escapeHtml(procedureState.current_stage || 'CASE_REVIEW')}</dd>
          <dt>Procedure Status</dt><dd>${escapeHtml(procedureStatus)}</dd>
          <dt>Next permitted action</dt><dd>${escapeHtml(nextAction)}</dd>
          <dt>Blocking reason</dt><dd>${escapeHtml(blockingReason)}</dd>
        </dl>
      </div>
    </div>
    <div style="margin-top: 16px;">
      <h4>Blocking requirements</h4>
      <div class="stack-list">${blockingMarkup}</div>
    </div>
    <div style="margin-top: 16px;">
      <h4>Requirements</h4>
      <div class="stack-list">${requirementMarkup}</div>
    </div>
  `;

  container.querySelectorAll('[data-procedure-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const index = Number(button.getAttribute('data-procedure-toggle'));
      const detail = container.querySelector(`[data-procedure-detail="${index}"]`);
      if (!detail) {
        return;
      }
      const isHidden = detail.classList.toggle('hidden');
      button.textContent = isHidden ? 'Why is this required?' : 'Hide reason';
    });
  });
}

function bindFindingModal(investigationId, { onSaved, actions = [] } = {}) {
  const modal = document.getElementById('findingModal');
  const openButton = document.getElementById('openFindingModal');
  const closeButton = document.getElementById('closeFindingModal');
  const submitButton = document.getElementById('submitFindingModal');
  const notesField = document.getElementById('findingNotes');
  const actionRefsContainer = document.getElementById('findingActionReferences');
  const errorEl = document.getElementById('findingModalError');

  if (!openButton) {
    return;
  }

  if (!investigationId) {
    openButton.disabled = true;
    openButton.hidden = true;
    return;
  }

  syncFindingsGateState(investigationId, actions);

  if (!modal) {
    return;
  }

  openButton.addEventListener('click', () => {
    if (notesField) {
      notesField.value = '';
    }
    if (actionRefsContainer) {
      renderCheckboxList(actionRefsContainer, buildInvestigationActionReferenceOptions(actions), {
        emptyText: 'No investigation records are available for this case yet.',
        fieldName: 'finding_action_reference',
      });
    }
    if (errorEl) {
      errorEl.classList.add('hidden');
    }
    modal.classList.remove('hidden');
  });
  closeButton?.addEventListener('click', () => modal.classList.add('hidden'));

  submitButton?.addEventListener('click', async () => {
    const notes = notesField ? notesField.value.trim() : '';
    const selectedActionIds = getSelectedValuesFromContainer(actionRefsContainer, { type: 'checkbox' });

    if (!notes) {
      errorEl.textContent = 'Finding text is required.';
      errorEl.classList.remove('hidden');
      return;
    }
    if (!selectedActionIds.length) {
      errorEl.textContent = 'Select at least one investigation record that supports this finding.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      await fetchJson(`/api/v1/detective/investigations/${investigationId}/findings`, {
        method: 'POST',
        body: { notes, action_ids: selectedActionIds },
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

function bindActionModal(investigationId, evidenceItems = [], { onSaved, actions = [] } = {}) {
  const modal = document.getElementById('actionModal');
  const openButton = document.getElementById('openActionModal');
  const closeButton = document.getElementById('closeActionModal');
  const submitButton = document.getElementById('submitActionModal');
  const errorEl = document.getElementById('actionModalError');
  const modalContext = document.getElementById('actionModalContext');
  const actionFields = document.getElementById('actionModalFields');

  if (!modal || !submitButton) {
    return;
  }

  if (!investigationId) {
    return;
  }

  const renderLegacyForm = (selectedActionType = '') => {
    const legacyPurpose = document.getElementById('investigativeActionPurpose');
    const legacyDescription = document.getElementById('investigativeActionDescription');
    const legacyResult = document.getElementById('investigativeActionResult');
    const legacyEvidence = document.getElementById('investigativeActionEvidence');
    if (legacyPurpose && legacyDescription && legacyResult && legacyEvidence) {
      legacyPurpose.value = '';
      legacyDescription.value = '';
      legacyResult.value = '';
      legacyEvidence.value = '';
      if (modalContext) {
        const actionLabel = formatRequiredActionLabel(selectedActionType);
        modalContext.textContent = selectedActionType
          ? `Record the ${actionLabel.toLowerCase()} investigation task. Any remaining required action may be completed in any order.`
          : 'Complete any remaining investigative action. The six required tasks are independent and may be recorded in any order.';
      }
    }
  };

  const resetActionForm = (selectedActionType = '') => {
    modal.dataset.requiredActionType = selectedActionType || '';
    modal.dataset.viewMode = 'edit';
    if (errorEl) {
      errorEl.textContent = '';
      errorEl.classList.add('hidden');
    }
    if (actionFields) {
      actionFields.innerHTML = selectedActionType ? renderActionFormForType(selectedActionType, actions) : '<div class="empty-state">Select an investigative action to begin.</div>';
      if (selectedActionType === 'EVIDENCE_COLLECTION') {
        bindEvidenceCollectionControls(actionFields);
      }
      populateActionFormOptions(selectedActionType, evidenceItems, actionFields);
    }
    if (modalContext) {
      const actionLabel = formatRequiredActionLabel(selectedActionType);
      modalContext.textContent = selectedActionType
        ? `Record the ${actionLabel.toLowerCase()} investigation task. Any remaining required action may be completed in any order.`
        : 'Complete any remaining investigative action. The six required tasks are independent and may be recorded in any order.';
    }
    submitButton.hidden = false;
    submitButton.disabled = false;
    renderLegacyForm(selectedActionType);
  };

  resetActionForm();

  openButton?.addEventListener('click', () => {
    const nextRequired = getNextRequiredAction(actions);
    resetActionForm(nextRequired || '');
    modal.classList.remove('hidden');
  });

  closeButton?.addEventListener('click', () => {
    modal.classList.add('hidden');
    modal.dataset.viewMode = 'edit';
    submitButton.hidden = false;
    submitButton.disabled = false;
  });

  submitButton.addEventListener('click', async () => {
    const actionType = String(modal.dataset.requiredActionType || '').trim().toUpperCase();
    if (!actionType) {
      if (errorEl) {
        errorEl.textContent = 'A specific required action is required.';
        errorEl.classList.remove('hidden');
      }
      return;
    }

    const payload = buildActionModalPayload(actionType);
    const validationErrors = validateActionModalPayload(actionType, payload);
    if (validationErrors.length > 0) {
      if (errorEl) {
        errorEl.textContent = validationErrors[0];
        errorEl.classList.remove('hidden');
      }
      return;
    }

    try {
      const legacySelection = document.getElementById('investigativeActionType');
      const inferredActionType = legacySelection && legacySelection.value ? String(legacySelection.value).trim().toUpperCase() : actionType;
      const finalPayload = {
        action_type: inferredActionType || actionType,
        ...payload,
      };
      if (finalPayload.result === undefined && typeof finalPayload.outcome === 'string') {
        finalPayload.result = finalPayload.outcome;
      }
      await fetchJson(`/api/v1/detective/investigations/${investigationId}/actions`, {
        method: 'POST',
        body: finalPayload,
      });
      modal.classList.add('hidden');
      if (onSaved) {
        await onSaved();
      }
      showToast('Investigative action recorded.');
    } catch (error) {
      if (errorEl) {
        errorEl.textContent = error.message || 'Unable to save the investigative action.';
        errorEl.classList.remove('hidden');
      }
      showToast(error.message || 'Unable to save the investigative action.', { type: 'error' });
    }
  });
}

function syncCompletionGateState(investigationId, { findings = [], actions = [] } = {}) {
  const openButton = document.getElementById('openCompleteInvestigationModal');
  if (!openButton) {
    return false;
  }

  if (!investigationId) {
    openButton.disabled = true;
    openButton.hidden = true;
    return false;
  }

  const hasRequiredActions = REQUIRED_ACTION_SEQUENCE.every((actionType) => getCompletedRequiredActions(actions).has(actionType));
  const hasFindings = Array.isArray(findings) && findings.length > 0;
  const isEnabled = hasRequiredActions && hasFindings;
  openButton.disabled = !isEnabled;
  openButton.hidden = !isEnabled;
  return isEnabled;
}

function bindCompleteInvestigationModal(investigationId, { onCompleted, findings = [], actions = [] } = {}) {
  const modal = document.getElementById('completeInvestigationModal');
  const openButton = document.getElementById('openCompleteInvestigationModal');
  const closeButton = document.getElementById('closeCompleteInvestigationModal');
  const submitButton = document.getElementById('submitCompleteInvestigationModal');
  const outcomeSelect = document.getElementById('completeInvestigationOutcome');
  const notesField = document.getElementById('completeInvestigationNotes');
  const findingRefsContainer = document.getElementById('completeInvestigationFindingReferences');
  const errorEl = document.getElementById('completeInvestigationModalError');

  if (!openButton) {
    return;
  }

  if (!investigationId) {
    openButton.disabled = true;
    openButton.hidden = true;
    return;
  }

  syncCompletionGateState(investigationId, { findings, actions });

  if (!modal) {
    return;
  }

  openButton.addEventListener('click', () => {
    if (outcomeSelect) {
      outcomeSelect.value = 'VALID';
    }
    if (notesField) {
      notesField.value = '';
    }
    if (findingRefsContainer) {
      renderCheckboxList(findingRefsContainer, buildFindingReferenceOptions(findings), {
        emptyText: 'No saved findings are available yet.',
        fieldName: 'finding_reference',
      });
    }
    if (errorEl) {
      errorEl.classList.add('hidden');
    }
    modal.classList.remove('hidden');
  });
  closeButton?.addEventListener('click', () => modal.classList.add('hidden'));

  submitButton?.addEventListener('click', async () => {
    const finalNotes = notesField ? notesField.value.trim() : '';
    const selectedFindingIds = getSelectedValuesFromContainer(findingRefsContainer, { type: 'checkbox' });

    if (!finalNotes) {
      errorEl.textContent = 'Final reasoning is required.';
      errorEl.classList.remove('hidden');
      return;
    }
    if (!selectedFindingIds.length) {
      errorEl.textContent = 'Select at least one finding that supports the final reasoning.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      await fetchJson(`/api/v1/detective/investigations/${investigationId}/complete`, {
        method: 'POST',
        body: { outcome: outcomeSelect ? outcomeSelect.value : 'VALID', final_notes: finalNotes, finding_ids: selectedFindingIds },
      });
      modal.classList.add('hidden');
      flashToast('Investigation completed.');
      if (onCompleted) {
        await onCompleted();
      } else {
        window.location.reload();
      }
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to complete investigation.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to complete investigation.', { type: 'error' });
    }
  });
}

function bindStatementModal(caseReference, { onSaved } = {}) {
  const modal = document.getElementById('statementModal');
  const openButton = document.getElementById('openStatementModal');
  const closeButton = document.getElementById('closeStatementModal');
  const submitButton = document.getElementById('submitStatementModal');
  const textField = document.getElementById('statementText');
  const errorEl = document.getElementById('statementModalError');

  if (!openButton || !modal) {
    return;
  }

  openButton.addEventListener('click', () => {
    textField.value = '';
    errorEl.classList.add('hidden');
    modal.classList.remove('hidden');
  });
  closeButton?.addEventListener('click', () => modal.classList.add('hidden'));

  submitButton?.addEventListener('click', async () => {
    const statementText = textField.value.trim();
    if (!statementText) {
      errorEl.textContent = 'Statement text is required.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      await fetchJson(`/api/v1/detective/dockets/${caseReference}/statements`, {
        method: 'POST',
        body: { statement_text: statementText },
      });
      modal.classList.add('hidden');
      if (onSaved) {
        await onSaved();
      }
      showToast('Statement recorded.');
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to save statement.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to save statement.', { type: 'error' });
    }
  });
}

function buildCompletedInvestigationSummary(investigation) {
  if (!investigation || String(investigation.status || '').toUpperCase() !== 'COMPLETED') {
    return '';
  }

  const outcome = String(investigation.outcome || 'UNKNOWN').toUpperCase();
  const finalNotes = String(investigation.final_notes || investigation.notes || '').trim() || 'No final reasoning was recorded.';
  const completedAt = investigation.completed_at ? new Date(investigation.completed_at) : null;
  const completedText = completedAt && !Number.isNaN(completedAt.getTime())
    ? completedAt.toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, ' UTC')
    : 'Not recorded';

  return `
    <article class="mini-case-card">
      <div class="stack-row" style="justify-content:space-between; align-items:flex-start;">
        <strong>Investigation completed</strong>
        <span class="badge badge-success">${escapeHtml(outcome)}</span>
      </div>
      <p style="margin-top:8px;"><strong>Final reasoning:</strong> ${escapeHtml(finalNotes)}</p>
      <div class="field-hint" style="margin-top:8px;">Completed: ${escapeHtml(completedText)}</div>
    </article>
  `;
}

function renderNoteEntries(container, notes, evidenceItems, completedInvestigationSummary = '') {
  if (!container) {
    return;
  }
  const normalizedNotes = Array.isArray(notes) ? notes : [];
  const summaryMarkup = completedInvestigationSummary || '';
  if (!normalizedNotes.length && !summaryMarkup) {
    container.innerHTML = '<div class="empty-state">No notes have been recorded yet.</div>';
    return;
  }

  const evidenceByRef = new Map((evidenceItems || []).map((item) => [String(item.evidence_id), item]));
  const noteMarkup = normalizedNotes
    .map((note) => {
      const evidence = note.evidence_reference ? evidenceByRef.get(String(note.evidence_reference)) : null;
      const label = evidence ? `Evidence: ${evidence.description || evidence.filename || note.evidence_reference}` : 'General note';
      return `
        <article class="mini-case-card">
          <div class="stack-row" style="justify-content:space-between;">
            <strong>${label}</strong>
            <span>${note.created_at || ''}</span>
          </div>
          <p>${note.note_text}</p>
        </article>
      `;
    })
    .join('');

  container.innerHTML = `${summaryMarkup}${noteMarkup}`;
}

function bindNoteEntryModal(investigationId, evidenceItems, { onSaved } = {}) {
  const modal = document.getElementById('noteEntryModal');
  const openButton = document.getElementById('openNoteEntryModal');
  const closeButton = document.getElementById('closeNoteEntryModal');
  const submitButton = document.getElementById('submitNoteEntryModal');
  const evidenceSelect = document.getElementById('noteEntryEvidence');
  const notesField = document.getElementById('noteEntryText');
  const errorEl = document.getElementById('noteEntryModalError');

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
    populateSelect(evidenceSelect, evidenceItems || [], {
      valueKey: 'evidence_id',
      labelKey: 'description',
      placeholder: 'General note (no evidence)',
    });
    notesField.value = '';
    errorEl.classList.add('hidden');
    modal.classList.remove('hidden');
  });
  closeButton?.addEventListener('click', () => modal.classList.add('hidden'));

  submitButton?.addEventListener('click', async () => {
    const noteText = notesField.value.trim();
    if (!noteText) {
      errorEl.textContent = 'Note text is required.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      await fetchJson(`/api/v1/detective/investigations/${investigationId}/note-entries`, {
        method: 'POST',
        body: { note_text: noteText, evidence_reference: evidenceSelect.value || undefined },
      });
      modal.classList.add('hidden');
      if (onSaved) {
        await onSaved();
      }
      showToast('Note recorded.');
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to save note.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to save note.', { type: 'error' });
    }
  });
}

const DETECTIVE_ACCESS_RESTRICTED_MESSAGE = 'Detective access requires an active assignment to this docket.';

function renderDetectiveAccessRestricted({
  rail = document.getElementById('detectiveWorkflowRail'),
  statusBadge = document.getElementById('detectiveStatusBadge'),
  meta = document.getElementById('detectiveCaseMeta'),
  deposition = document.getElementById('detectiveDeposition'),
  statementsList = document.getElementById('detectiveStatementsList'),
  timeline = document.getElementById('detectiveCaseTimeline'),
  evidence = document.getElementById('detectiveCaseEvidence'),
  findingsList = document.getElementById('detectiveFindingsList'),
  flagsList = document.getElementById('detectiveFlagsList'),
  relatedBox = document.getElementById('detectiveRelatedCases'),
  noteEntriesList = document.getElementById('detectiveNoteEntriesList'),
  startInvestigation = document.getElementById('startInvestigation'),
  notesField = document.getElementById('investigationNotes'),
  saveInvestigationNote = document.getElementById('saveInvestigationNote'),
  openStatementModal = document.getElementById('openStatementModal'),
  openNoteEntryModal = document.getElementById('openNoteEntryModal'),
  openFindingModal = document.getElementById('openFindingModal'),
  openCompleteInvestigationModal = document.getElementById('openCompleteInvestigationModal'),
} = {}) {
  const message = DETECTIVE_ACCESS_RESTRICTED_MESSAGE;

  if (rail) {
    renderWorkflowRail(rail, {
      title: 'Detective workflow',
      steps: [{ label: 'Access restricted', state: 'current', detail: message }],
      locked: true,
    });
  }

  if (statusBadge) {
    statusBadge.className = 'badge badge-warning';
    statusBadge.textContent = 'Access restricted';
  }

  if (meta) {
    meta.innerHTML = `
      <dt>Status</dt><dd>Access restricted</dd>
      <dt>Message</dt><dd>${message}</dd>
    `;
  }

  if (deposition) {
    deposition.innerHTML = `<p>${message}</p>`;
  }
  if (statementsList) {
    statementsList.innerHTML = `<div class="empty-state">${message}</div>`;
  }
  if (timeline) {
    timeline.innerHTML = `<li><span class="timeline-dot"></span><div><strong>Access restricted</strong><small>${message}</small></div></li>`;
  }
  if (evidence) {
    evidence.innerHTML = `<tr><td colspan="6">${message}</td></tr>`;
  }
  if (findingsList) {
    setEmptyState(findingsList, message);
  }
  if (flagsList) {
    setEmptyState(flagsList, message);
  }
  if (relatedBox) {
    relatedBox.innerHTML = `<p>${message}</p>`;
  }
  if (noteEntriesList) {
    setEmptyState(noteEntriesList, message);
  }

  if (notesField) {
    notesField.value = '';
    notesField.disabled = true;
  }
  if (saveInvestigationNote) {
    saveInvestigationNote.disabled = true;
  }
  [startInvestigation, openStatementModal, openNoteEntryModal, openFindingModal, openCompleteInvestigationModal].forEach((button) => {
    if (button) {
      button.disabled = true;
    }
  });
}

function renderDetectiveWorkflow(docket, investigation, procedureState = {}) {
  const rail = document.getElementById('detectiveWorkflowRail');
  if (!rail) {
    return;
  }
  const status = (docket.status || '').toUpperCase();
  const hasInvestigation = Boolean(investigation);
  const findings = Array.isArray(investigation?.findings) ? investigation.findings : [];
  const hasFindings = findings.length > 0;
  const stageIsComplete = String(procedureState.current_stage || '').toUpperCase() === 'INVESTIGATION_COMPLETE';
  const isCompleted = (investigation && investigation.status && investigation.status.toUpperCase() === 'COMPLETED') || status === 'COMPLETED' || stageIsComplete;
  const currentStage = String(procedureState.current_stage || (hasInvestigation ? 'INVESTIGATION_OPEN' : 'CASE_REVIEW')).toUpperCase();

  const steps = [
    { label: 'Case Review', state: 'complete', detail: 'Reference and case record reviewed' },
    { label: 'Case Facts Verification', state: 'upcoming', detail: 'Confirm core incident facts' },
    { label: 'Investigation', state: 'upcoming', detail: 'Complete the six required actions' },
    { label: 'Findings', state: 'upcoming', detail: 'Document the investigative finding' },
    { label: 'Final Reasoning', state: 'upcoming', detail: 'Record final outcome' },
    { label: 'Completion', state: 'upcoming', detail: 'Close the investigation' },
  ];

  if (isCompleted) {
    steps[0].state = 'complete';
    steps[1].state = 'complete';
    steps[2].state = 'complete';
    steps[3].state = 'complete';
    steps[4].state = 'complete';
    steps[5].state = 'complete';
    steps[0].detail = 'Reference and case record reviewed';
    steps[1].detail = 'Case facts verified';
    steps[2].detail = 'Six required investigative actions complete';
    steps[3].detail = 'Investigative findings documented';
    steps[4].detail = 'Final reasoning recorded';
    steps[5].detail = 'Investigation completed';
    return renderWorkflowRail(rail, { title: 'Detective workflow', steps, locked: Boolean(docket.is_frozen) });
  }

  const findingsGateOpen = currentStage === 'FINDINGS_READY' || String(procedureState.next_permitted_action || '').trim() === 'Document finding';

  if (currentStage === 'CASE_REVIEW') {
    steps[0].state = 'current';
  } else if (currentStage === 'CASE_FACTS_VERIFICATION') {
    steps[0].state = 'complete';
    steps[1].state = 'current';
    steps[1].detail = 'Resolve the preserved fact discrepancies';
  } else if (currentStage === 'INVESTIGATION_OPEN') {
    steps[0].state = 'complete';
    steps[1].state = 'complete';
    if (findingsGateOpen) {
      steps[2].state = 'complete';
      steps[2].detail = 'Required investigative actions complete';
      steps[3].state = 'current';
      steps[3].detail = 'Document or review the investigation finding';
    } else {
      steps[2].state = 'current';
      steps[2].detail = 'Complete the six required investigative actions';
    }
  } else if (currentStage === 'FINDINGS_READY') {
    steps[0].state = 'complete';
    steps[1].state = 'complete';
    steps[2].state = 'complete';
    steps[2].detail = 'Required investigative actions complete';
    steps[3].state = 'current';
    steps[3].detail = 'Document or review the investigation finding';
  } else if (hasFindings) {
    steps[0].state = 'complete';
    steps[1].state = 'complete';
    steps[2].state = 'complete';
    steps[3].state = 'current';
    steps[3].detail = 'Review and finalise the investigation finding';
  } else {
    steps[0].state = 'complete';
    steps[1].state = 'complete';
    steps[2].state = 'current';
    steps[2].detail = 'Complete the six required investigative actions';
  }

  if (hasFindings && currentStage !== 'CASE_FACTS_VERIFICATION' && !isCompleted) {
    steps[2].state = 'complete';
    steps[2].detail = 'Required investigative actions complete';
    steps[3].state = 'current';
    steps[3].detail = 'Prepare the final investigation finding';
  }

  renderWorkflowRail(rail, { title: 'Detective workflow', steps, locked: Boolean(docket.is_frozen) });
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
  const statementsList = document.getElementById('detectiveStatementsList');
  const statusBadge = document.getElementById('detectiveStatusBadge');
  const freezeBadge = document.getElementById('detectiveFreezeBadge');
  const frozenNotice = document.getElementById('detectiveFrozenNotice');
  const frozenReason = document.getElementById('detectiveFrozenReason');
  const docketContent = document.getElementById('detectiveDocketContent');
  const findingsList = document.getElementById('detectiveFindingsList');
  const flagsList = document.getElementById('detectiveFlagsList');
  const relatedBox = document.getElementById('detectiveRelatedCases');
  const noteEntriesList = document.getElementById('detectiveNoteEntriesList');
  const startInvestigation = document.getElementById('startInvestigation');
  const notesField = document.getElementById('investigationNotes');
  const procedureBoard = document.getElementById('detectiveProcedureBoard');
  const investigationPanels = document.getElementById('detectiveInvestigationPanels');
  const investigationStateText = document.getElementById('detectiveInvestigationStateText');
  const investigationActions = document.getElementById('detectiveInvestigationActions');

  try {
    const docket = await fetchJson(`/api/v1/detective/dockets/${caseReference}`);
    const investigation = docket.investigation;
    renderProtectedSubmission(document.getElementById('detectiveProtectedSubmission'), docket);
    let procedureState = {};
    try {
      procedureState = await fetchJson(`/api/v1/detective/dockets/${caseReference}/procedure-state`);
      renderProcedureBoard(procedureBoard, procedureState, { caseReference });
      if (startInvestigation && procedureState.allowed === false) {
        startInvestigation.disabled = true;
        startInvestigation.textContent = procedureState.next_permitted_action || 'Procedure gate pending';
      }
    } catch (procedureError) {
      renderProcedureBoard(procedureBoard, { error: procedureError.message || 'Procedure state unavailable.', requirements: [], blocking_requirements: [], current_stage: 'CASE_REVIEW', procedure_status: 'BLOCKED', next_permitted_action: 'Start investigation' }, { caseReference });
    }
    renderDetectiveWorkflow(docket, investigation, procedureState);

    if (statusBadge) {
      statusBadge.className = buildStatusBadge(docket.status);
      statusBadge.textContent = docket.status || 'REGISTERED';
    }
    if (freezeBadge) {
      if (docket.is_frozen) {
        freezeBadge.textContent = `Frozen — under IPID review${docket.freeze_reason ? `: ${docket.freeze_reason}` : ''}`;
        freezeBadge.classList.remove('hidden');
      } else {
        freezeBadge.classList.add('hidden');
      }
    }

    if (docket.is_frozen) {
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
        <dt>Case Reference</dt><dd>${docket.case_reference || caseReference}</dd>
        <dt>Incident Location</dt><dd>${docket.location || 'Not provided'}</dd>
        <dt>Incident Date</dt><dd>${docket.incident_date || 'Not provided'}</dd>
        <dt>Assigned Detective</dt><dd>${investigation ? investigation.detective_id : (docket.detective_id || 'Not yet assigned')}</dd>
        <dt>Status</dt><dd>${docket.status || 'REGISTERED'}</dd>
      `;
    }
    if (deposition) {
      deposition.innerHTML = `<p>${docket.description || 'No incident description was provided.'}</p>`;
    }
    const stageName = String((procedureState.current_stage || 'CASE_REVIEW')).toUpperCase();
    const shouldRevealInvestigationStage = Boolean(investigation) && ['INVESTIGATION_OPEN', 'FINDINGS_READY', 'INVESTIGATION_COMPLETE'].includes(stageName);

    if (investigationStateText) {
      const normalizedStatus = investigation ? String(investigation.status || '').toUpperCase() : '';
      investigationStateText.textContent = normalizedStatus === 'COMPLETED'
        ? 'Investigation is complete.'
        : (investigation ? 'Investigation is active.' : 'Investigation has not started.');
    }
    if (investigationPanels) {
      investigationPanels.classList.toggle('hidden', !shouldRevealInvestigationStage);
    }
    if (investigationActions) {
      investigationActions.classList.toggle('hidden', !shouldRevealInvestigationStage);
    }
    let interview = null;
    let comparisonReport = null;
    if (docket.interview_id) {
      try {
        interview = await fetchJson(`/api/v1/constable/interviews/${docket.interview_id}`);
        try {
          comparisonReport = await fetchJson(`/api/v1/constable/interviews/${docket.interview_id}/recording-comparison`);
        } catch (comparisonError) {
          comparisonReport = {
            status: 'COMPARISON_UNAVAILABLE',
            error: comparisonError.message || 'Unable to load recording comparison.',
          };
        }
      } catch (interviewError) {
        showToast(interviewError.message || 'Unable to load interview recordings.', { type: 'error' });
      }
    }

    const refreshStatements = async () => {
      const refreshed = await fetchJson(`/api/v1/detective/dockets/${caseReference}`);
      let refreshedInterview = null;
      let refreshedComparison = null;
      if (refreshed.interview_id) {
        try {
          refreshedInterview = await fetchJson(`/api/v1/constable/interviews/${refreshed.interview_id}`);
          refreshedComparison = await fetchJson(`/api/v1/constable/interviews/${refreshed.interview_id}/recording-comparison`);
        } catch (error) {
          refreshedComparison = {
            status: 'COMPARISON_UNAVAILABLE',
            error: error.message || 'Unable to load interview data.',
          };
        }
      }
      await renderDetectiveInterviewDetails(statementsList, refreshed, refreshedInterview, refreshedComparison);
    };
    await renderDetectiveInterviewDetails(statementsList, docket, interview, comparisonReport);
    bindStatementModal(caseReference, {
      onSaved: refreshStatements,
    });
    renderTimelineList(timeline, docket.timeline, { titleKey: 'event_type', fallbackTitle: 'Case Event' });
    const evidenceItems = Array.isArray(docket.citizen_evidence) && docket.citizen_evidence.length
      ? docket.citizen_evidence
      : Array.isArray(docket.evidence)
        ? docket.evidence
        : [];
    renderEvidenceTable(evidence, evidenceItems);
    renderInvestigationTimer(document.getElementById('detectiveInvestigationTimer'), investigation);

    if (notesField) {
      notesField.value = investigation ? investigation.notes || '' : '';
      notesField.disabled = !investigation;
      notesField.hidden = !investigation;
    }
    if (document.getElementById('saveInvestigationNote')) {
      document.getElementById('saveInvestigationNote').hidden = !investigation;
      document.getElementById('saveInvestigationNote').disabled = !investigation;
    }
    if (document.getElementById('openStatementModal')) {
      document.getElementById('openStatementModal').hidden = true;
      document.getElementById('openStatementModal').disabled = true;
    }
    if (document.getElementById('openNoteEntryModal')) {
      document.getElementById('openNoteEntryModal').hidden = !shouldRevealInvestigationStage;
      document.getElementById('openNoteEntryModal').disabled = !shouldRevealInvestigationStage;
    }
    if (document.getElementById('openFindingModal')) {
      document.getElementById('openFindingModal').hidden = !shouldRevealInvestigationStage;
      document.getElementById('openFindingModal').disabled = !shouldRevealInvestigationStage;
    }
    if (document.getElementById('openCompleteInvestigationModal')) {
      document.getElementById('openCompleteInvestigationModal').hidden = !shouldRevealInvestigationStage;
      document.getElementById('openCompleteInvestigationModal').disabled = !shouldRevealInvestigationStage;
    }
    // Findings/notes/completion can still be *viewed* once an investigation
    // is COMPLETED, but not mutated further -- gate the write controls on a
    // still-open investigation while read-side fetches below keep using the
    // real investigation_id regardless of status.
    const mutableInvestigationId = investigation && investigation.status !== 'COMPLETED' ? investigation.investigation_id : null;
    bindNoteSaving(mutableInvestigationId);

    const openCompleteInvestigationModal = document.getElementById('openCompleteInvestigationModal');
    const canStartInvestigation = !investigation;
    const canCompleteInvestigation = Boolean(investigation) && investigation.status !== 'COMPLETED' && ['INVESTIGATION_OPEN', 'FINDINGS_READY'].includes(stageName);
    const startIsBlocked = Boolean(procedureState && procedureState.allowed === false);

    const caseFactsPanel = document.getElementById('caseFactsVerificationPanel');
    const caseFactsStatusBadge = document.getElementById('caseFactsStatusBadge');
    const caseFactsComparisonResults = document.getElementById('caseFactsComparisonResults');
    const caseFactsDiscrepancies = document.getElementById('caseFactsDiscrepancies');
    const factsRecord = docket.case_facts_verification || docket.procedural_assessment?.case_facts_verification || {};
    const currentFacts = factsRecord.facts || {};
    const comparisonEntries = Array.isArray(factsRecord.comparison_results)
      ? factsRecord.comparison_results
      : (factsRecord.comparison ? Object.values(factsRecord.comparison) : []);

    if (caseFactsPanel) {
      const isCaseFactsStage = String((procedureState.current_stage || 'CASE_REVIEW')).toUpperCase() === 'CASE_FACTS_VERIFICATION';
      caseFactsPanel.classList.toggle('hidden', !investigation && !isCaseFactsStage);
      if (caseFactsStatusBadge) {
        caseFactsStatusBadge.textContent = isCaseFactsStage ? 'Pending' : (factsRecord.verified ? 'Verified' : 'Open');
      }
    }

    if (caseFactsComparisonResults) {
      renderCaseFactsComparisonResults(caseFactsComparisonResults, comparisonEntries);
    }

    if (caseFactsDiscrepancies) {
      renderCaseFactsDiscrepancies(caseFactsDiscrepancies, Array.isArray(factsRecord.discrepancies) ? factsRecord.discrepancies : []);
    }

    const setCaseFactValue = (elementId, value) => {
      const input = document.getElementById(elementId);
      if (!input) {
        return;
      }
      if (Array.isArray(value)) {
        input.value = value.join(', ');
        return;
      }
      input.value = value ?? '';
    };

    setCaseFactValue('caseFactsIncidentDate', currentFacts.incident_date || '');
    setCaseFactValue('caseFactsIncidentTime', currentFacts.incident_time || '');
    setCaseFactValue('caseFactsLocation', currentFacts.location || '');
    setCaseFactValue('caseFactsPeopleInvolved', currentFacts.people_involved || '');
    setCaseFactValue('caseFactsWitnesses', currentFacts.witnesses || '');
    setCaseFactValue('caseFactsHarmTypes', currentFacts.harm_types || '');
    setCaseFactValue('caseFactsInjuryTypes', currentFacts.injury_types || '');
    const policeInput = document.getElementById('caseFactsPoliceInvolvement');
    if (policeInput) {
      policeInput.value = currentFacts.police_involvement === true ? 'true' : (currentFacts.police_involvement === false ? 'false' : '');
    }
    setCaseFactValue('caseFactsCircumstances', currentFacts.relevant_circumstances || '');

    if (startInvestigation) {
      if (investigation) {
        startInvestigation.hidden = true;
        startInvestigation.disabled = true;
        startInvestigation.textContent = `Investigation ${investigation.status}`;
      } else {
        startInvestigation.hidden = false;
        startInvestigation.disabled = startIsBlocked;
        startInvestigation.textContent = 'Start Investigation';
        if (canStartInvestigation) {
          startInvestigation.onclick = async () => {
            const notes = notesField ? notesField.value.trim() : '';
            try {
              const procedureState = await fetchJson(`/api/v1/detective/dockets/${caseReference}/procedure-state`);
              if (procedureState.allowed === false) {
                showToast(procedureState.blocking_reason || 'Procedure requirements are not yet satisfied.', { type: 'error' });
                return;
              }
              await fetchJson(`/api/v1/detective/dockets/${caseReference}/investigation`, {
                method: 'POST',
                body: { notes: notes || 'Investigation opened from the browser workflow.' },
              });
              flashToast('Investigation started.');
              window.location.href = `/detective/dockets/${caseReference}`;
            } catch (error) {
              showToast(error.message || 'Unable to start investigation.', { type: 'error' });
            }
          };
        }
      }
    }

    const submitCaseFactsVerification = document.getElementById('submitCaseFactsVerification');
    if (submitCaseFactsVerification) {
      submitCaseFactsVerification.disabled = !investigation;
      submitCaseFactsVerification.addEventListener('click', async () => {
        if (!investigation) {
          showToast('Open an investigation before recording case facts.', { type: 'error' });
          return;
        }

        const parseCommaSeparated = (value) => String(value || '')
          .split(',')
          .map((entry) => entry.trim())
          .filter(Boolean);

        const facts = {
          incident_date: document.getElementById('caseFactsIncidentDate')?.value || '',
          incident_time: document.getElementById('caseFactsIncidentTime')?.value || '',
          location: document.getElementById('caseFactsLocation')?.value || '',
          people_involved: parseCommaSeparated(document.getElementById('caseFactsPeopleInvolved')?.value),
          witnesses: parseCommaSeparated(document.getElementById('caseFactsWitnesses')?.value),
          harm_types: parseCommaSeparated(document.getElementById('caseFactsHarmTypes')?.value),
          injury_types: parseCommaSeparated(document.getElementById('caseFactsInjuryTypes')?.value),
          police_involvement: document.getElementById('caseFactsPoliceInvolvement')?.value === 'true',
          relevant_circumstances: document.getElementById('caseFactsCircumstances')?.value || '',
        };

        const discrepancyBasis = document.getElementById('caseFactsDiscrepancyBasis')?.value?.trim() || '';
        const discrepancyStatus = String(document.getElementById('caseFactsDiscrepancyStatus')?.value || 'OPEN').toUpperCase();
        const discrepancyEntries = Array.isArray(factsRecord.discrepancies)
          ? factsRecord.discrepancies
              .filter((item) => !item?.resolved)
              .map((item) => ({
                field: item?.field || 'unknown_field',
                original_value: item?.original_value,
                observed_value: item?.observed_value,
                basis: item?.basis || item?.explanation || discrepancyBasis || 'Investigative basis recorded by the detective.',
                status: item?.status || discrepancyStatus || 'OPEN',
                resolved: item?.status ? ['ADDRESSED', 'RESOLVED', 'CLOSED', 'SATISFIED'].includes(String(item.status).toUpperCase()) : (discrepancyStatus === 'ADDRESSED' || discrepancyStatus === 'RESOLVED' || discrepancyStatus === 'CLOSED' || discrepancyStatus === 'SATISFIED'),
              }))
          : [];

        if (discrepancyBasis && discrepancyEntries.length === 0 && discrepancyStatus !== 'OPEN') {
          discrepancyEntries.push({
            field: 'case_facts',
            original_value: 'Protected record',
            observed_value: 'Detective case facts review',
            basis: discrepancyBasis,
            status: discrepancyStatus,
            resolved: ['ADDRESSED', 'RESOLVED', 'CLOSED', 'SATISFIED'].includes(discrepancyStatus),
          });
        }

        try {
          const result = await fetchJson(`/api/v1/detective/dockets/${caseReference}/case-facts-verification`, {
            method: 'POST',
            body: {
              facts,
              discrepancies: discrepancyEntries,
              notes: discrepancyBasis || 'Detective verification record captured for this docket.',
            },
          });
          if (result && result.verified) {
            flashToast('Case facts verified.');
          } else {
            flashToast('Case facts recorded; discrepancies remain open.', { type: 'warning' });
          }
          window.location.reload();
        } catch (error) {
          showToast(error.message || 'Unable to record case facts verification.', { type: 'error' });
        }
      });
    }
    if (openCompleteInvestigationModal) {
      openCompleteInvestigationModal.hidden = !canCompleteInvestigation;
      openCompleteInvestigationModal.disabled = !canCompleteInvestigation;
    }

    let actionsSnapshot = [];
    let findingsSnapshot = [];
    const refreshProcedureState = async () => {
      if (!caseReference) {
        return procedureState;
      }
      try {
        const refreshedProcedureState = await fetchJson(`/api/v1/detective/dockets/${caseReference}/procedure-state`);
        procedureState = refreshedProcedureState;
        renderProcedureBoard(procedureBoard, refreshedProcedureState, { caseReference });
        renderDetectiveWorkflow(docket, investigation, refreshedProcedureState);
        syncFindingsGateState(investigation?.investigation_id || null, actionsSnapshot || [], refreshedProcedureState);
        syncCompletionGateState(investigation?.investigation_id || null, { findings: findingsSnapshot || [], actions: actionsSnapshot || [] });
        return refreshedProcedureState;
      } catch (error) {
        console.warn('Unable to refresh detective procedure state.', error);
        return procedureState;
      }
    };

    const refreshInvestigationActions = async () => {
      if (!investigation) {
        renderInvestigationOrder(document.getElementById('detectiveInvestigationOrder'), []);
        renderInvestigationActions(document.getElementById('detectiveActionList'), []);
        syncFindingsGateState(null, [], procedureState);
        return;
      }
      try {
        const actions = await fetchJson(`/api/v1/detective/investigations/${investigation.investigation_id}/actions`);
        actionsSnapshot = actions;
        renderInvestigationOrder(document.getElementById('detectiveInvestigationOrder'), actions, evidenceItems);
        renderInvestigationActions(document.getElementById('detectiveActionList'), actions);
        syncFindingsGateState(investigation.investigation_id, actions, procedureState);
        await refreshProcedureState();
        return actions;
      } catch (error) {
        renderInvestigationOrder(document.getElementById('detectiveInvestigationOrder'), [], evidenceItems);
        setEmptyState(document.getElementById('detectiveActionList'), error.message || 'Unable to load investigative actions.');
        syncFindingsGateState(investigation?.investigation_id || null, [], procedureState);
        return [];
      }
    };
    actionsSnapshot = await refreshInvestigationActions() || [];
    syncFindingsGateState(investigation?.investigation_id, actionsSnapshot || [], procedureState);
    bindActionModal(mutableInvestigationId, evidenceItems, { onSaved: refreshInvestigationActions, actions: actionsSnapshot || [] });

    const refreshFindings = async () => {
      if (!investigation) {
        renderFindings(findingsList, []);
        findingsSnapshot = [];
        return [];
      }
      try {
        const findings = await fetchJson(`/api/v1/detective/investigations/${investigation.investigation_id}/findings`);
        findingsSnapshot = findings;
        renderFindings(findingsList, findings);
        if (investigation) {
          investigation.findings = findings;
        }
        syncCompletionGateState(investigation?.investigation_id || null, { findings: findingsSnapshot || [], actions: actionsSnapshot || [] });
        await refreshProcedureState();
        return findings;
      } catch (error) {
        setEmptyState(findingsList, error.message || 'Unable to load findings.');
        findingsSnapshot = [];
        return [];
      }
    };
    bindFindingModal(mutableInvestigationId, { onSaved: refreshFindings, actions: actionsSnapshot || [] });
    findingsSnapshot = await refreshFindings();

    bindCompleteInvestigationModal(mutableInvestigationId, {
      onCompleted: () => window.location.reload(),
      findings: findingsSnapshot || [],
      actions: actionsSnapshot || [],
    });

    const refreshNotes = async () => {
      if (!investigation) {
        renderNoteEntries(noteEntriesList, [], evidenceItems, '');
        return;
      }
      try {
        const notes = await fetchJson(`/api/v1/detective/investigations/${investigation.investigation_id}/note-entries`);
        renderNoteEntries(noteEntriesList, notes, evidenceItems, buildCompletedInvestigationSummary(investigation));
      } catch (error) {
        const completedSummary = buildCompletedInvestigationSummary(investigation);
        if (completedSummary) {
          renderNoteEntries(noteEntriesList, [], evidenceItems, completedSummary);
          return;
        }
        setEmptyState(noteEntriesList, error.message || 'Unable to load notes.');
      }
    };
    bindNoteEntryModal(mutableInvestigationId, evidenceItems, { onSaved: refreshNotes });
    await refreshNotes();

    if (investigation) {
      try {
        const flags = await fetchJson(`/api/v1/detective/investigations/${investigation.investigation_id}/flags`);
        renderReadOnlyFlags(flagsList, flags);
      } catch (error) {
        setEmptyState(flagsList, error.message || 'Unable to load flags.');
      }
      try {
        const related = await fetchJson(`/api/v1/detective/investigations/${investigation.investigation_id}/related`);
        if (relatedBox) {
          relatedBox.innerHTML = related.length
            ? related.map((item) => `<p><strong>${item.relationship_type}</strong>: ${item.related_case_reference === caseReference ? item.source_case_reference : item.related_case_reference}</p>`).join('')
            : '<p>No direct related case links detected.</p>';
        }
      } catch (error) {
        if (relatedBox) {
          relatedBox.innerHTML = `<p>${error.message}</p>`;
        }
        showToast(error.message || 'Unable to load related cases.', { type: 'error' });
      }
    }
  } catch (error) {
    const message = error && error.message ? error.message : DETECTIVE_ACCESS_RESTRICTED_MESSAGE;

    renderDetectiveAccessRestricted({
      rail: document.getElementById('detectiveWorkflowRail'),
      statusBadge,
      meta,
      deposition,
      statementsList,
      timeline,
      evidence,
      findingsList,
      flagsList,
      relatedBox,
      noteEntriesList,
      startInvestigation,
      notesField,
      saveInvestigationNote: document.getElementById('saveInvestigationNote'),
      openStatementModal: document.getElementById('openStatementModal'),
      openNoteEntryModal: document.getElementById('openNoteEntryModal'),
      openFindingModal: document.getElementById('openFindingModal'),
      openCompleteInvestigationModal: document.getElementById('openCompleteInvestigationModal'),
    });

    if (meta) {
      const normalizedMessage = message || DETECTIVE_ACCESS_RESTRICTED_MESSAGE;
      meta.innerHTML = `<dt>Status</dt><dd>Access restricted</dd><dt>Message</dt><dd>${normalizedMessage}</dd>`;
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
