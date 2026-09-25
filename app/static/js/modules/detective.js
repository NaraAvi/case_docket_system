/**
 * Detective investigation list and individual case workspace.
 */

import { fetchJson } from '../core/api.js';
import { buildStatusBadge, flashToast, populateSelect, renderDocketCardList, renderEvidenceTable, renderStatementList, renderTimelineList, renderWorkflowRail, setEmptyState, showToast } from '../core/ui.js';

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

function bindCompleteInvestigationModal(investigationId, { onCompleted } = {}) {
  const modal = document.getElementById('completeInvestigationModal');
  const openButton = document.getElementById('openCompleteInvestigationModal');
  const closeButton = document.getElementById('closeCompleteInvestigationModal');
  const submitButton = document.getElementById('submitCompleteInvestigationModal');
  const outcomeSelect = document.getElementById('completeInvestigationOutcome');
  const notesField = document.getElementById('completeInvestigationNotes');
  const errorEl = document.getElementById('completeInvestigationModalError');

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
    outcomeSelect.value = 'VALID';
    notesField.value = '';
    errorEl.classList.add('hidden');
    modal.classList.remove('hidden');
  });
  closeButton?.addEventListener('click', () => modal.classList.add('hidden'));

  submitButton?.addEventListener('click', async () => {
    const finalNotes = notesField.value.trim();
    if (!finalNotes) {
      errorEl.textContent = 'Final reasoning is required.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      await fetchJson(`/api/v1/detective/investigations/${investigationId}/complete`, {
        method: 'POST',
        body: { outcome: outcomeSelect.value, final_notes: finalNotes },
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

function renderNoteEntries(container, notes, evidenceItems) {
  if (!container) {
    return;
  }
  if (!notes.length) {
    container.innerHTML = '<div class="empty-state">No notes have been recorded yet.</div>';
    return;
  }
  const evidenceByRef = new Map((evidenceItems || []).map((item) => [String(item.evidence_id), item]));
  container.innerHTML = notes
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

function renderDetectiveWorkflow(docket, investigation) {
  const rail = document.getElementById('detectiveWorkflowRail');
  if (!rail) {
    return;
  }
  const status = (docket.status || '').toUpperCase();
  const hasInvestigation = Boolean(investigation);
  const findings = Array.isArray(investigation?.findings) ? investigation.findings : [];
  const hasFindings = findings.length > 0;
  const isCompleted = (investigation && investigation.status && investigation.status.toUpperCase() === 'COMPLETED') || status === 'COMPLETED';

  const steps = [
    { label: 'Case Review', state: 'complete', detail: 'Reference and case record reviewed' },
    { label: 'Statements & Evidence', state: 'complete', detail: 'Statements and evidence reviewed' },
    { label: 'Investigation', state: 'upcoming', detail: 'Open the investigation' },
    { label: 'Findings', state: 'upcoming', detail: 'Investigation Finding' },
    { label: 'Final Reasoning', state: 'upcoming', detail: 'Final Outcome' },
    { label: 'Completion', state: 'upcoming', detail: 'Complete investigation' },
  ];

  if (!hasInvestigation) {
    steps[2].state = 'current';
    return renderWorkflowRail(rail, { title: 'Detective workflow', steps, locked: Boolean(docket.is_frozen) });
  }

  steps[2].state = 'complete';
  steps[2].detail = 'Investigation opened';

  if (hasFindings) {
    steps[3].state = 'complete';
    steps[3].detail = 'Investigation Finding recorded';
    steps[4].state = isCompleted ? 'complete' : 'current';
    steps[4].detail = isCompleted ? 'Final Outcome recorded' : 'Prepare the Final Outcome';
  } else {
    steps[3].state = 'current';
    steps[3].detail = 'Add Investigation Finding';
  }

  if (isCompleted) {
    steps[4].state = 'complete';
    steps[4].detail = 'Final Outcome recorded';
    steps[5].state = 'complete';
    steps[5].detail = 'Investigation completed';
  } else if (hasFindings) {
    steps[5].state = 'upcoming';
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

  try {
    const docket = await fetchJson(`/api/v1/detective/dockets/${caseReference}`);
    const investigation = docket.investigation;
    renderDetectiveWorkflow(docket, investigation);

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
        <dt>Incident Location</dt><dd>${docket.location || 'Not provided'}</dd>
        <dt>Incident Date</dt><dd>${docket.incident_date || 'Not provided'}</dd>
        <dt>Assigned Officer</dt><dd>${investigation ? investigation.detective_id : 'Not yet assigned'}</dd>
        <dt>Status</dt><dd>${docket.status || 'REGISTERED'}</dd>
      `;
    }
    if (deposition) {
      deposition.innerHTML = `<p>${docket.description || 'No incident description was provided.'}</p>`;
    }
    const refreshStatements = () => renderStatementList(statementsList, Array.isArray(docket.statements) ? docket.statements : []);
    refreshStatements();
    bindStatementModal(caseReference, {
      onSaved: async () => {
        const refreshed = await fetchJson(`/api/v1/detective/dockets/${caseReference}`);
        renderStatementList(statementsList, Array.isArray(refreshed.statements) ? refreshed.statements : []);
      },
    });
    renderTimelineList(timeline, docket.timeline, { titleKey: 'event_type', fallbackTitle: 'Case Event' });
    renderEvidenceTable(evidence, docket.evidence);

    if (notesField && investigation) {
      notesField.value = investigation.notes || '';
    }
    // Findings/notes/completion can still be *viewed* once an investigation
    // is COMPLETED, but not mutated further -- gate the write controls on a
    // still-open investigation while read-side fetches below keep using the
    // real investigation_id regardless of status.
    const mutableInvestigationId = investigation && investigation.status !== 'COMPLETED' ? investigation.investigation_id : null;
    bindNoteSaving(mutableInvestigationId);

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
    bindFindingModal(mutableInvestigationId, { onSaved: refreshFindings });
    await refreshFindings();

    bindCompleteInvestigationModal(mutableInvestigationId, {
      onCompleted: () => window.location.reload(),
    });

    const evidenceItems = Array.isArray(docket.evidence) ? docket.evidence : [];
    const refreshNotes = async () => {
      if (!investigation) {
        renderNoteEntries(noteEntriesList, [], evidenceItems);
        return;
      }
      try {
        const notes = await fetchJson(`/api/v1/detective/investigations/${investigation.investigation_id}/note-entries`);
        renderNoteEntries(noteEntriesList, notes, evidenceItems);
      } catch (error) {
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
