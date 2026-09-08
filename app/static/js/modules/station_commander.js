/**
 * Station Commander oversight dashboard and docket detail view.
 */

import { fetchJson } from '../core/api.js';
import { buildStatusBadge, setEmptyState, bindCaseLinks } from '../core/ui.js';

export function getStationCommanderCaseReference() {
  const match = window.location.pathname.match(/\/station-commander\/dockets\/([^/]+)/);
  return match ? match[1] : null;
}

export async function hydrateStationCommanderDashboard() {
  const container = document.getElementById('stationCommanderCaseList');
  if (!container) {
    return;
  }

  try {
    const dockets = await fetchJson('/api/v1/station-commander/dockets');
    if (!dockets.length) {
      setEmptyState(container, 'No dockets are currently tracked by the station commander.');
      return;
    }
    container.innerHTML = dockets
      .map((item) => `
        <article class="docket-card">
          <div class="meta-wrap">
            <strong>${item.case_reference}</strong>
            <span>${item.location || 'Location unavailable'}</span>
          </div>
          <div class="stack-row">
            <span class="${buildStatusBadge(item.status)}">${item.status || 'UNKNOWN'}</span>
            <button class="secondary-btn small-btn" type="button" data-case-link="/station-commander/dockets/${item.case_reference}">Open</button>
          </div>
        </article>
      `)
      .join('');

    bindCaseLinks(container);
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load station commander queue.');
  }
}

export async function hydrateStationCommanderDetail() {
  const caseReference = getStationCommanderCaseReference();
  if (!caseReference) {
    return;
  }
  try {
    const docket = await fetchJson(`/api/v1/station-commander/dockets/${caseReference}`);
    const meta = document.getElementById('stationCommanderCaseMeta');
    const timeline = document.getElementById('stationCommanderAuditList');
    if (meta) {
      meta.innerHTML = `
        <dt>Assigned Officer</dt><dd>${docket.assigned_officer_id || 'Not assigned'}</dd>
        <dt>Current Status</dt><dd>${docket.status || 'UNKNOWN'}</dd>
        <dt>Freeze Status</dt><dd>${docket.freeze_status || 'NOT_FROZEN'}</dd>
        <dt>SLA</dt><dd>${docket.sla_status || 'Within threshold'}</dd>
      `;
    }
    if (timeline) {
      const items = Array.isArray(docket.audit) && docket.audit.length ? docket.audit : [{ action: 'Case recorded', timestamp: 'Pending' }];
      timeline.innerHTML = items
        .map((event) => `<li><span class="timeline-dot"></span><div><strong>${event.action || 'Audit Event'}</strong><small>${event.timestamp || 'No timestamp'}</small></div></li>`)
        .join('');
    }
  } catch (error) {
    const meta = document.getElementById('stationCommanderCaseMeta');
    if (meta) {
      meta.innerHTML = `<dt>Status</dt><dd>Unavailable</dd><dt>Message</dt><dd>${error.message}</dd>`;
    }
  }
}

export function init() {
  if (document.body.dataset.role === 'station_commander' && document.getElementById('stationCommanderCaseList')) {
    hydrateStationCommanderDashboard();
  }
  if (window.location.pathname.startsWith('/station-commander/dockets/')) {
    hydrateStationCommanderDetail();
  }
}
