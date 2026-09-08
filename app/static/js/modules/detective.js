/**
 * Detective investigation list and individual case workspace.
 */

import { fetchJson } from '../core/api.js';
import { setEmptyState, bindCaseLinks } from '../core/ui.js';

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
    if (!registeredCases.length) {
      setEmptyState(container, 'No registered detective cases are available yet.');
      return;
    }

    container.innerHTML = registeredCases
      .map((item) => `
        <article class="docket-card">
          <div class="meta-wrap">
            <strong>${item.case_reference}</strong>
            <span>${item.location || 'Location unavailable'}</span>
          </div>
          <div class="stack-row">
            <span class="badge badge-verified">REGISTERED</span>
            <button class="secondary-btn small-btn" type="button" data-case-link="/detective/dockets/${item.case_reference}">Open</button>
          </div>
        </article>
      `)
      .join('');

    bindCaseLinks(container);
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load detective queue.');
  }
}

export async function hydrateDetectiveCase() {
  const caseReference = getDetectiveCaseReference();
  if (!caseReference) {
    return;
  }
  try {
    const docket = await fetchJson(`/api/v1/detective/dockets/${caseReference}`);
    const meta = document.getElementById('detectiveCaseMeta');
    const timeline = document.getElementById('detectiveCaseTimeline');
    const evidence = document.getElementById('detectiveCaseEvidence');
    if (meta) {
      meta.innerHTML = `
        <dt>Case Title</dt><dd>${docket.title || 'Unspecified'}</dd>
        <dt>Location</dt><dd>${docket.location || 'Not provided'}</dd>
        <dt>Incident Date</dt><dd>${docket.incident_date || 'Not provided'}</dd>
        <dt>Status</dt><dd>${docket.status || 'REGISTERED'}</dd>
      `;
    }
    if (timeline) {
      const items = Array.isArray(docket.timeline) && docket.timeline.length ? docket.timeline : [{ event_type: 'docket_registered', timestamp: 'Pending' }];
      timeline.innerHTML = items
        .map((event) => `<li><span class="timeline-dot"></span><div><strong>${event.event_type || 'Case Event'}</strong><small>${event.timestamp || 'No timestamp'}</small></div></li>`)
        .join('');
    }
    if (evidence) {
      const items = Array.isArray(docket.evidence) && docket.evidence.length ? docket.evidence : [{ description: 'No evidence yet.' }];
      evidence.innerHTML = items
        .map((item) => `<li><span class="timeline-dot"></span><div><strong>${item.evidence_type || 'Evidence Item'}</strong><small>${item.description || 'No description provided.'}</small></div></li>`)
        .join('');
    }

    const startInvestigation = document.getElementById('startInvestigation');
    if (startInvestigation) {
      startInvestigation.addEventListener('click', async () => {
        const payload = { notes: 'Investigation opened from the browser workflow.' };
        await fetchJson(`/api/v1/detective/dockets/${caseReference}/investigation`, {
          method: 'POST',
          body: payload,
        });
        window.location.href = `/detective/dockets/${caseReference}`;
      });
    }
  } catch (error) {
    const meta = document.getElementById('detectiveCaseMeta');
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
