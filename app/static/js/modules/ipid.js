/**
 * IPID escalation review queue and independent escalation detail view.
 */

import { fetchJson } from '../core/api.js';
import { buildStatusBadge, configureReauthModal, flashToast, renderDocketCardList, renderEvidenceTable, renderStatementList, renderTimelineList, setEmptyState, showToast } from '../core/ui.js';

const STATUTORY_SOURCE = 'IPID_STATUTORY_MANDATE';

function statutoryBadges(item) {
  if (item && item.source === STATUTORY_SOURCE) {
    return [{ label: 'STATUTORY §28', className: 'badge-statute', title: item.statutory_basis || 'IPID Act s28(1) mandatory referral' }];
  }
  return [];
}

export function getIpidEscalationId() {
  const match = window.location.pathname.match(/\/ipid\/escalations\/([^/]+)/);
  return match ? match[1] : null;
}

export async function hydrateIpidDashboard() {
  const container = document.getElementById('ipidQueueList');
  if (!container) {
    return;
  }

  try {
    const escalations = await fetchJson('/api/v1/ipid/escalations');
    renderDocketCardList(container, escalations, {
      reference: (item) => item.escalation_id,
      title: (item) => item.case_reference || 'Case reference unavailable',
      status: (item) => item.status || 'RECEIVED',
      linkPrefix: '/ipid/escalations/',
      badges: statutoryBadges,
      actionLabel: 'Review',
      emptyMessage: 'No escalations are awaiting IPID review.',
    });
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load IPID review queue.');
  }

  const custodyContainer = document.getElementById('ipidCustodyCasesList');
  if (custodyContainer) {
    try {
      const cases = await fetchJson('/api/v1/ipid/custody-cases');
      renderDocketCardList(custodyContainer, cases, {
        reference: (item) => item.escalation_id,
        title: (item) => item.case_reference || 'Case reference unavailable',
        status: () => 'FROZEN',
        linkPrefix: '/ipid/escalations/',
        badges: statutoryBadges,
        actionLabel: 'Open',
        emptyMessage: 'No cases are currently in IPID custody.',
      });
    } catch (error) {
      setEmptyState(custodyContainer, error.message || 'Unable to load cases in custody.');
    }
  }

  const disciplinaryContainer = document.getElementById('ipidDisciplinaryCasesList');
  if (disciplinaryContainer) {
    try {
      const cases = await fetchJson('/api/v1/ipid/disciplinary-cases');
      renderDocketCardList(disciplinaryContainer, cases, {
        reference: (item) => item.disciplinary_case_id,
        title: (item) => item.source_case_reference || 'Case reference unavailable',
        status: (item) => item.status || 'OPEN',
        linkPrefix: '/ipid/disciplinary-cases/',
        badges: (item) => (item.misconduct_tier ? [{ label: `TIER ${item.misconduct_tier}`, className: 'badge-warning', title: item.mandatory_sanction || '' }] : []),
        actionLabel: 'View',
        emptyMessage: 'No disciplinary cases have been opened.',
      });
    } catch (error) {
      setEmptyState(disciplinaryContainer, error.message || 'Unable to load disciplinary cases.');
    }
  }
}

export function getIpidDisciplinaryCaseId() {
  const match = window.location.pathname.match(/\/ipid\/disciplinary-cases\/([^/]+)/);
  return match ? match[1] : null;
}

function bindDisciplinaryClose(record, disciplinaryCaseId) {
  const panel = document.getElementById('disciplinaryClosePanel');
  const form = document.getElementById('disciplinaryCloseForm');
  if (!panel || !form) {
    return;
  }
  const closed = String(record.status || '').toUpperCase() === 'CLOSED';
  panel.hidden = closed;
  if (closed) {
    return;
  }
  const sanction = document.getElementById('disciplinaryFinalSanction');
  if (sanction && record.mandatory_sanction && !sanction.value) {
    sanction.value = record.mandatory_sanction;
  }
  form.onsubmit = async (event) => {
    event.preventDefault();
    const justification = (document.getElementById('disciplinaryJustification')?.value || '').trim();
    const finalSanction = sanction?.value || record.mandatory_sanction;
    if (record.mandatory_sanction && finalSanction !== record.mandatory_sanction && !justification) {
      showToast('A written justification is required to depart from the mandatory sanction.', { type: 'error' });
      return;
    }
    try {
      await fetchJson(`/api/v1/ipid/disciplinary-cases/${disciplinaryCaseId}/close`, {
        method: 'POST',
        body: { final_sanction: finalSanction, justification },
      });
      showToast('Disciplinary case closed.');
      await hydrateDisciplinaryCaseDetail();
    } catch (error) {
      showToast(error.message || 'Unable to close disciplinary case.', { type: 'error' });
    }
  };
}

export async function hydrateDisciplinaryCaseDetail() {
  const disciplinaryCaseId = getIpidDisciplinaryCaseId();
  if (!disciplinaryCaseId) {
    return;
  }
  const meta = document.getElementById('disciplinaryCaseMeta');
  const reasonMeta = document.getElementById('disciplinaryCaseReasonMeta');
  const reasonBox = document.getElementById('disciplinaryCaseReasonBox');
  const statusBadge = document.getElementById('disciplinaryCaseStatusBadge');

  try {
    const record = await fetchJson(`/api/v1/ipid/disciplinary-cases/${disciplinaryCaseId}`);
    if (meta) {
      meta.innerHTML = `
        <dt>Source Docket</dt><dd>${record.source_case_reference || 'Unavailable'}</dd>
        <dt>Escalation</dt><dd>${record.escalation_id || 'Unavailable'}</dd>
        <dt>Implicated Officer</dt><dd>${record.implicated_officer_id || 'Unavailable'}</dd>
        <dt>Status</dt><dd>${record.status || 'OPEN'}</dd>
      `;
    }
    const determinationMeta = document.getElementById('disciplinaryDeterminationMeta');
    if (determinationMeta) {
      determinationMeta.innerHTML = record.misconduct_tier
        ? `
        <dt>Misconduct Tier</dt><dd>Tier ${record.misconduct_tier}</dd>
        <dt>Infraction</dt><dd>${record.infraction_type || 'Unspecified'}</dd>
        <dt>Mandatory Sanction</dt><dd>${record.mandatory_sanction || 'Unavailable'}</dd>
        ${record.final_sanction ? `<dt>Final Sanction</dt><dd>${record.final_sanction}</dd>` : ''}
        ${record.deviation_justification ? `<dt>Deviation Justification</dt><dd>${record.deviation_justification}</dd>` : ''}
      `
        : '<dt>Determination</dt><dd>No automated determination was recorded for this case.</dd>';
    }
    bindDisciplinaryClose(record, disciplinaryCaseId);
    if (statusBadge) {
      statusBadge.className = buildStatusBadge(record.status);
      statusBadge.textContent = record.status || 'OPEN';
    }
    if (reasonMeta) {
      reasonMeta.innerHTML = `
        <dt>Category</dt><dd>${record.category || 'Unspecified'}</dd>
        <dt>Created By</dt><dd>${record.created_by || 'Unavailable'} (${record.created_by_role || 'ipid'})</dd>
        <dt>Created At</dt><dd>${record.created_at || 'Unavailable'}</dd>
      `;
    }
    if (reasonBox) {
      reasonBox.innerHTML = `<p>${record.reason || 'No reason was recorded.'}</p>`;
    }
  } catch (error) {
    if (meta) {
      meta.innerHTML = `<dt>Status</dt><dd>Unavailable</dd><dt>Message</dt><dd>${error.message}</dd>`;
    }
    showToast(error.message || 'Unable to load disciplinary case.', { type: 'error' });
  }
}

function renderFindings(container, findings) {
  if (!container) {
    return;
  }
  if (!findings.length) {
    container.innerHTML = '<div class="empty-state">No internal findings have been recorded.</div>';
    return;
  }
  container.innerHTML = findings
    .map(
      (finding) => `
        <article class="mini-case-card">
          <strong>${finding.finding_type}</strong>
          <p>${finding.summary}</p>
        </article>
      `
    )
    .join('');
}

function bindIpidStatementModal(caseReference, { onSaved } = {}) {
  const modal = document.getElementById('ipidStatementModal');
  const openButton = document.getElementById('openIpidStatementModal');
  const closeButton = document.getElementById('closeIpidStatementModal');
  const submitButton = document.getElementById('submitIpidStatementModal');
  const textField = document.getElementById('ipidStatementText');
  const errorEl = document.getElementById('ipidStatementModalError');

  if (!openButton || !modal || !caseReference) {
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
      await fetchJson(`/api/v1/ipid/dockets/${caseReference}/statements`, {
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

function bindDecisionButtons(escalationId, escalation) {
  const dismissBtn = document.getElementById('dismissEscalationBtn');
  const upholdBtn = document.getElementById('upholdEscalationBtn');
  const custodyBtn = document.getElementById('takeCustodyBtn');
  const notice = document.getElementById('ipidDecisionNotice');

  const status = (escalation.status || '').toUpperCase();
  const isFrozen = (escalation.freeze_status || '').toUpperCase() === 'FROZEN';
  if (custodyBtn) {
    custodyBtn.disabled = status === 'RESOLVED' || isFrozen;
    custodyBtn.textContent = isFrozen ? 'Docket Already Frozen' : 'Take Custody & Freeze Docket';
  }

  if (status === 'RESOLVED') {
    if (dismissBtn) dismissBtn.disabled = true;
    if (upholdBtn) upholdBtn.disabled = true;
    if (notice) {
      notice.textContent = `This escalation was already resolved (${escalation.decision || 'decision recorded'}).`;
    }
    return;
  }

  custodyBtn?.addEventListener('click', () => {
    configureReauthModal({
      targetLabel: 'Escalation',
      targetValue: escalationId,
      actionLabel: 'Take Custody & Freeze Docket',
      subtitle: 'Freezing locks the docket from further mutation by other officers while IPID review is in progress.',
      confirmLabel: 'Confirm Freeze',
      onConfirm: async (reason) => {
        await fetchJson(`/api/v1/ipid/escalations/${escalationId}/take-custody`, { method: 'POST', body: { reason } });
        flashToast('Docket frozen — other officers can no longer mutate it while under review.');
        window.location.reload();
      },
    });
  });

  dismissBtn?.addEventListener('click', () => {
    configureReauthModal({
      targetLabel: 'Escalation',
      targetValue: escalationId,
      actionLabel: 'Dismiss Escalation',
      subtitle: 'Dismissal releases any statutory freeze tied to this escalation and closes the review with no further action.',
      confirmLabel: 'Confirm Dismissal',
      onConfirm: async (reason) => {
        await fetchJson(`/api/v1/ipid/escalations/${escalationId}/dismiss`, { method: 'POST', body: { reason } });
        flashToast('Escalation dismissed.');
        window.location.reload();
      },
    });
  });

  upholdBtn?.addEventListener('click', () => {
    configureReauthModal({
      targetLabel: 'Escalation',
      targetValue: escalationId,
      actionLabel: 'Uphold Escalation',
      subtitle: 'Upholding this escalation freezes the docket, revokes the implicated officer\'s access, and opens a disciplinary case under IPID Act §28.',
      confirmLabel: 'Confirm Uphold',
      onConfirm: async (reason) => {
        await fetchJson(`/api/v1/ipid/escalations/${escalationId}/uphold`, { method: 'POST', body: { reason } });
        flashToast('Escalation upheld — docket frozen and officer access revoked.');
        window.location.reload();
      },
    });
  });
}

export async function hydrateIpidDetail() {
  const escalationId = getIpidEscalationId();
  if (!escalationId) {
    return;
  }
  const meta = document.getElementById('ipidEscalationMeta');
  const assignmentMeta = document.getElementById('ipidAssignmentMeta');
  const statementsList = document.getElementById('ipidStatementsList');
  const evidenceBody = document.getElementById('ipidCaseEvidence');
  const caseTimeline = document.getElementById('ipidCaseTimeline');
  const notes = document.getElementById('ipidReviewNotes');
  const findings = document.getElementById('ipidReviewFindings');
  const audit = document.getElementById('ipidAuditList');
  const statusBadge = document.getElementById('ipidStatusBadge');

  try {
    let escalation = await fetchJson(`/api/v1/ipid/escalations/${escalationId}`);
    if ((escalation.status || '').toUpperCase() === 'OPEN') {
      try {
        await fetchJson(`/api/v1/ipid/escalations/${escalationId}/review`, { method: 'POST' });
        showToast('Escalation opened for review.');
      } catch (reviewError) {
        showToast(reviewError.message || 'Unable to open escalation for review.', { type: 'error' });
      }
    }

    const workspace = await fetchJson(`/api/v1/ipid/escalations/${escalationId}/review-workspace`);
    const caseContext = workspace.case_context || {};

    if (meta) {
      meta.innerHTML = `
        <dt>Case Reference</dt><dd>${workspace.case_reference || 'Unavailable'}</dd>
        <dt>Category</dt><dd>${workspace.category || 'Unspecified'}</dd>
        <dt>Submitted By</dt><dd>${caseContext.citizen_id || 'Unavailable'}</dd>
        <dt>Status</dt><dd>${workspace.status || 'RECEIVED'}</dd>
        ${workspace.source === STATUTORY_SOURCE ? `<dt>Referral</dt><dd>Automatic statutory referral &mdash; ${workspace.statutory_basis || 'IPID Act s28(1)'}</dd>` : ''}
      `;
    }
    if (statusBadge) {
      statusBadge.className = buildStatusBadge(workspace.status);
      statusBadge.textContent = workspace.status || 'RECEIVED';
    }
    if (assignmentMeta) {
      assignmentMeta.innerHTML = `
        <dt>Assigned Officer</dt><dd>${caseContext.assigned_officer_id || 'Not assigned'}</dd>
        ${caseContext.suspended_officer_id ? `<dt>Suspended Officer</dt><dd>${caseContext.suspended_officer_id} (access suspended pending IPID decision)</dd>` : ''}
        <dt>Freeze Status</dt><dd>${caseContext.freeze_status || 'NOT_FROZEN'}</dd>
        <dt>Access State</dt><dd>${caseContext.is_frozen ? 'RESTRICTED' : 'ACTIVE'}</dd>
      `;
    }
    renderStatementList(statementsList, caseContext.statements);
    bindIpidStatementModal(workspace.case_reference, {
      onSaved: async () => {
        const refreshedWorkspace = await fetchJson(`/api/v1/ipid/escalations/${escalationId}/review-workspace`);
        renderStatementList(statementsList, (refreshedWorkspace.case_context || {}).statements);
      },
    });
    renderEvidenceTable(evidenceBody, caseContext.evidence);
    renderTimelineList(caseTimeline, caseContext.timeline, { titleKey: 'event_type', fallbackTitle: 'Case Event' });
    renderTimelineList(notes, workspace.review_notes, { titleKey: 'author_role', detailKey: 'note_text', fallbackTitle: 'Reviewer', fallbackDetail: 'No details supplied.' });
    renderFindings(findings, workspace.review_findings || []);
    renderTimelineList(audit, workspace.audit_history, { titleKey: 'action', detailKey: 'timestamp', fallbackTitle: 'Audit Event' });

    escalation = { ...escalation, status: workspace.status };
    bindDecisionButtons(escalationId, escalation);
  } catch (error) {
    if (meta) {
      meta.innerHTML = `<dt>Status</dt><dd>Unavailable</dd><dt>Message</dt><dd>${error.message}</dd>`;
    }
  }
}

export function init() {
  if (document.body.dataset.role === 'ipid' && document.getElementById('ipidQueueList')) {
    hydrateIpidDashboard();
  }
  if (window.location.pathname.startsWith('/ipid/escalations/')) {
    hydrateIpidDetail();
  }
  if (window.location.pathname.startsWith('/ipid/disciplinary-cases/')) {
    hydrateDisciplinaryCaseDetail();
  }
}
