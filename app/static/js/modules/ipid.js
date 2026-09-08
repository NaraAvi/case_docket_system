/**
 * IPID escalation review queue and independent escalation detail view.
 */

import { fetchJson } from '../core/api.js';
import { buildStatusBadge, setEmptyState, bindCaseLinks } from '../core/ui.js';

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
    if (!escalations.length) {
      setEmptyState(container, 'No escalations are awaiting IPID review.');
      return;
    }

    container.innerHTML = escalations
      .map((item) => `
        <article class="docket-card">
          <div class="meta-wrap">
            <strong>${item.escalation_id}</strong>
            <span>${item.case_reference || 'Case reference unavailable'}</span>
          </div>
          <div class="stack-row">
            <span class="${buildStatusBadge(item.status)}">${item.status || 'RECEIVED'}</span>
            <button class="secondary-btn small-btn" type="button" data-case-link="/ipid/escalations/${item.escalation_id}">Review</button>
          </div>
        </article>
      `)
      .join('');

    bindCaseLinks(container);
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load IPID review queue.');
  }
}

export async function hydrateIpidDetail() {
  const escalationId = getIpidEscalationId();
  if (!escalationId) {
    return;
  }
  try {
    const escalation = await fetchJson(`/api/v1/ipid/escalations/${escalationId}`);
    const meta = document.getElementById('ipidEscalationMeta');
    const notes = document.getElementById('ipidReviewNotes');
    const audit = document.getElementById('ipidAuditList');
    if (meta) {
      meta.innerHTML = `
        <dt>Case Reference</dt><dd>${escalation.case_reference || 'Unavailable'}</dd>
        <dt>Category</dt><dd>${escalation.category || 'Unspecified'}</dd>
        <dt>Status</dt><dd>${escalation.status || 'RECEIVED'}</dd>
        <dt>Assigned Officer</dt><dd>${escalation.assigned_officer_id || 'Not assigned'}</dd>
      `;
    }
    if (notes) {
      const items = Array.isArray(escalation.review_notes) && escalation.review_notes.length ? escalation.review_notes : [{ note_text: 'No review notes have yet been added.' }];
      notes.innerHTML = items
        .map((note) => `<li><span class="timeline-dot"></span><div><strong>${note.author_role || 'Reviewer'}</strong><small>${note.note_text || 'No details supplied.'}</small></div></li>`)
        .join('');
    }
    if (audit) {
      const items = Array.isArray(escalation.audit_summary) && escalation.audit_summary.length ? escalation.audit_summary : [{ action: 'Escalation logged', timestamp: 'Pending' }];
      audit.innerHTML = items
        .map((item) => `<li><span class="timeline-dot"></span><div><strong>${item.action || 'Audit Event'}</strong><small>${item.timestamp || 'No timestamp'}</small></div></li>`)
        .join('');
    }
  } catch (error) {
    const meta = document.getElementById('ipidEscalationMeta');
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
