/**
 * Constable triage queue and individual docket review workspace.
 */

import { fetchJson } from '../core/api.js';
import { buildStatusBadge, setEmptyState, bindCaseLinks } from '../core/ui.js';

export function getConstableCaseReference() {
  const match = window.location.pathname.match(/\/constable\/dockets\/([^/]+)/);
  return match ? match[1] : null;
}

export async function hydrateConstableDashboard() {
  const container = document.getElementById('constableQueueState');
  if (!container) {
    return;
  }

  try {
    const queue = await fetchJson('/api/v1/constable/dockets/unregistered');
    if (!queue.length) {
      setEmptyState(container, 'No unregistered dockets are currently waiting for triage.');
      return;
    }

    container.innerHTML = queue
      .map((item) => `
        <article class="docket-card">
          <div class="meta-wrap">
            <strong>${item.case_reference}</strong>
            <span>${item.location || 'Location unavailable'}</span>
          </div>
          <div class="stack-row">
            <span class="${buildStatusBadge(item.status)}">${item.status || 'AWAITING_CONSTABLE_REGISTRATION'}</span>
            <button class="secondary-btn small-btn" type="button" data-case-link="/constable/dockets/${item.case_reference}">Review</button>
          </div>
        </article>
      `)
      .join('');

    bindCaseLinks(container);
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load constable queue.');
  }
}

export async function hydrateConstableReview() {
  const caseReference = getConstableCaseReference();
  if (!caseReference) {
    return;
  }

  try {
    const docket = await fetchJson(`/api/v1/constable/dockets/${caseReference}`);
    const meta = document.getElementById('constableCaseMeta');
    const timeline = document.getElementById('constableCaseTimeline');
    const evidence = document.getElementById('constableCaseEvidence');
    if (meta) {
      meta.innerHTML = `
        <dt>Title</dt><dd>${docket.title || 'Unspecified'}</dd>
        <dt>Location</dt><dd>${docket.location || 'Not provided'}</dd>
        <dt>Incident Date</dt><dd>${docket.incident_date || 'Not provided'}</dd>
        <dt>Status</dt><dd>${docket.status || 'AWAITING_CONSTABLE_REGISTRATION'}</dd>
      `;
    }
    if (timeline) {
      const items = Array.isArray(docket.timeline) && docket.timeline.length ? docket.timeline : [{ event_type: 'case_received', timestamp: 'Pending', details: {} }];
      timeline.innerHTML = items
        .map((event) => `<li><span class="timeline-dot"></span><div><strong>${event.event_type || 'Case Event'}</strong><small>${event.timestamp || 'No timestamp'}</small></div></li>`)
        .join('');
    }
    if (evidence) {
      const items = Array.isArray(docket.evidence) && docket.evidence.length ? docket.evidence : [{ description: 'No evidence submitted yet.' }];
      evidence.innerHTML = items
        .map((item) => `<li><span class="timeline-dot"></span><div><strong>${item.evidence_type || 'Evidence Record'}</strong><small>${item.description || 'No description provided.'}</small></div></li>`)
        .join('');
    }

    const continueButton = document.getElementById('continueToInterview');
    if (continueButton) {
      continueButton.addEventListener('click', async () => {
        await fetchJson(`/api/v1/constable/dockets/${caseReference}/interview`, { method: 'POST' });
        window.location.href = `/constable/dockets/${caseReference}`;
      });
    }
  } catch (error) {
    const meta = document.getElementById('constableCaseMeta');
    if (meta) {
      meta.innerHTML = `<dt>Status</dt><dd>Unavailable</dd><dt>Message</dt><dd>${error.message}</dd>`;
    }
  }
}

export function init() {
  if (document.body.dataset.role === 'constable' && document.getElementById('constableQueueState')) {
    hydrateConstableDashboard();
  }
  if (window.location.pathname.startsWith('/constable/dockets/')) {
    hydrateConstableReview();
  }
}
