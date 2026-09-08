/**
 * Station Commander oversight dashboard and docket detail view.
 */

import { fetchJson } from '../core/api.js';
import { buildStatusBadge, populateSelect, renderDocketCardList, renderSlaMeter, renderTimelineList, setEmptyState } from '../core/ui.js';

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
    renderDocketCardList(container, dockets, {
      linkPrefix: '/station-commander/dockets/',
      title: (item) => item.location,
      emptyMessage: 'No dockets are currently tracked by the station commander.',
    });
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load station commander queue.');
  }
}

function bindReassignment(caseReference, docket) {
  const select = document.getElementById('targetOfficerSelect');
  const currentOfficerField = document.getElementById('currentOfficerField');
  const reasonField = document.getElementById('reassignmentReason');
  const confirmButton = document.getElementById('confirmReassignment');
  const errorEl = document.getElementById('reassignmentError');
  const blockedNotice = document.getElementById('reassignmentBlockedNotice');

  if (currentOfficerField) {
    currentOfficerField.value = docket.assigned_officer_id || 'Not assigned';
  }

  const canReassign = docket.status === 'REGISTERED' && !docket.is_frozen;
  if (!canReassign) {
    if (select) select.disabled = true;
    if (reasonField) reasonField.disabled = true;
    if (confirmButton) confirmButton.disabled = true;
    if (blockedNotice) {
      blockedNotice.textContent = docket.is_frozen
        ? 'This docket is frozen; reassignment is restricted until it is released.'
        : 'Reassignment requires a registered docket.';
    }
    return;
  }

  fetchJson('/api/v1/station-commander/officers')
    .then((officers) => {
      populateSelect(select, officers, {
        valueKey: 'test_id',
        labelKey: 'full_name',
        describeKey: 'role',
        placeholder: 'Select target officer…',
      });
    })
    .catch((error) => {
      if (select) {
        select.innerHTML = `<option value="">${error.message || 'Unable to load officers.'}</option>`;
      }
    });

  confirmButton?.addEventListener('click', async () => {
    errorEl.classList.add('hidden');
    const officerId = select ? select.value : '';
    const reason = reasonField ? reasonField.value.trim() : '';
    if (!officerId) {
      errorEl.textContent = 'Select a target officer.';
      errorEl.classList.remove('hidden');
      return;
    }
    if (!reason) {
      errorEl.textContent = 'A reassignment reason is required.';
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      await fetchJson(`/api/v1/station-commander/dockets/${caseReference}/reassign`, {
        method: 'POST',
        body: { officer_id: officerId, reason },
      });
      window.location.reload();
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to reassign docket.';
      errorEl.classList.remove('hidden');
    }
  });
}

export async function hydrateStationCommanderDetail() {
  const caseReference = getStationCommanderCaseReference();
  if (!caseReference) {
    return;
  }
  const meta = document.getElementById('stationCommanderCaseMeta');
  const freezeBadge = document.getElementById('stationCommanderFreezeBadge');
  const slaContainer = document.getElementById('stationCommanderSlaMeter');
  const timeline = document.getElementById('stationCommanderAuditList');
  const investigationInfo = document.getElementById('stationCommanderInvestigationInfo');

  try {
    const docket = await fetchJson(`/api/v1/station-commander/dockets/${caseReference}`);
    if (meta) {
      meta.innerHTML = `
        <dt>Assigned Officer</dt><dd>${docket.assigned_officer_id || 'Not assigned'}</dd>
        <dt>Current Status</dt><dd>${docket.status || 'UNKNOWN'}</dd>
        <dt>Freeze Status</dt><dd>${docket.freeze_status || 'NOT_FROZEN'}</dd>
      `;
    }
    if (freezeBadge) {
      const isFrozen = Boolean(docket.is_frozen);
      freezeBadge.className = isFrozen ? 'badge badge-warning' : 'badge badge-verified';
      freezeBadge.textContent = isFrozen ? `Frozen${docket.freeze_reason ? `: ${docket.freeze_reason}` : ''}` : 'Active';
    }
    renderSlaMeter(slaContainer, docket.sla);
    if (investigationInfo) {
      investigationInfo.innerHTML = docket.investigation
        ? `<p><strong>Investigation ${docket.investigation.investigation_id}</strong>: ${docket.investigation.status}</p><p>${docket.investigation.notes || ''}</p>`
        : '<p>No investigation has been opened for this docket yet.</p>';
    }
    bindReassignment(caseReference, docket);
  } catch (error) {
    if (meta) {
      meta.innerHTML = `<dt>Status</dt><dd>Unavailable</dd><dt>Message</dt><dd>${error.message}</dd>`;
    }
  }

  try {
    const auditEntries = await fetchJson(`/api/v1/station-commander/dockets/${caseReference}/audit`);
    renderTimelineList(timeline, auditEntries, { titleKey: 'action', detailKey: 'timestamp', fallbackTitle: 'Audit Event' });
  } catch (error) {
    setEmptyState(timeline, error.message || 'Unable to load audit trail.');
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
