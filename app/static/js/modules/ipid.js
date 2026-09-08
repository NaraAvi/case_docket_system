/**
 * IPID escalation review queue and independent escalation detail view.
 */

import { fetchJson } from '../core/api.js';
import { buildStatusBadge, configureReauthModal, renderDocketCardList, renderTimelineList, setEmptyState } from '../core/ui.js';

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
      actionLabel: 'Review',
      emptyMessage: 'No escalations are awaiting IPID review.',
    });
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load IPID review queue.');
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

function bindDecisionButtons(escalationId, escalation) {
  const dismissBtn = document.getElementById('dismissEscalationBtn');
  const upholdBtn = document.getElementById('upholdEscalationBtn');
  const notice = document.getElementById('ipidDecisionNotice');

  const status = (escalation.status || '').toUpperCase();
  if (status === 'RESOLVED') {
    if (dismissBtn) dismissBtn.disabled = true;
    if (upholdBtn) upholdBtn.disabled = true;
    if (notice) {
      notice.textContent = `This escalation was already resolved (${escalation.decision || 'decision recorded'}).`;
    }
    return;
  }

  dismissBtn?.addEventListener('click', () => {
    configureReauthModal({
      targetLabel: 'Escalation',
      targetValue: escalationId,
      actionLabel: 'Dismiss Escalation',
      subtitle: 'Dismissal releases any statutory freeze tied to this escalation and closes the review with no further action.',
      confirmLabel: 'Confirm Dismissal',
      onConfirm: async (reason) => {
        await fetchJson(`/api/v1/ipid/escalations/${escalationId}/dismiss`, { method: 'POST', body: { reason } });
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
  const notes = document.getElementById('ipidReviewNotes');
  const findings = document.getElementById('ipidReviewFindings');
  const audit = document.getElementById('ipidAuditList');
  const statusBadge = document.getElementById('ipidStatusBadge');

  try {
    let escalation = await fetchJson(`/api/v1/ipid/escalations/${escalationId}`);
    if ((escalation.status || '').toUpperCase() === 'OPEN') {
      await fetchJson(`/api/v1/ipid/escalations/${escalationId}/review`, { method: 'POST' });
    }

    const workspace = await fetchJson(`/api/v1/ipid/escalations/${escalationId}/review-workspace`);
    const caseContext = workspace.case_context || {};

    if (meta) {
      meta.innerHTML = `
        <dt>Case Reference</dt><dd>${workspace.case_reference || 'Unavailable'}</dd>
        <dt>Category</dt><dd>${workspace.category || 'Unspecified'}</dd>
        <dt>Submitted By</dt><dd>${caseContext.citizen_id || 'Unavailable'}</dd>
        <dt>Status</dt><dd>${workspace.status || 'RECEIVED'}</dd>
      `;
    }
    if (statusBadge) {
      statusBadge.className = buildStatusBadge(workspace.status);
      statusBadge.textContent = workspace.status || 'RECEIVED';
    }
    if (assignmentMeta) {
      assignmentMeta.innerHTML = `
        <dt>Assigned Officer</dt><dd>${caseContext.assigned_officer_id || 'Not assigned'}</dd>
        <dt>Freeze Status</dt><dd>${caseContext.freeze_status || 'NOT_FROZEN'}</dd>
        <dt>Access State</dt><dd>${caseContext.is_frozen ? 'RESTRICTED' : 'ACTIVE'}</dd>
      `;
    }
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
}
