/**
 * Station Commander oversight dashboard and docket detail view.
 */

import { fetchJson } from '../core/api.js';
import { bindCaseLinks, buildStatusBadge, flashToast, populateSelect, renderDocketCardList, renderSlaMeter, renderTimelineList, setEmptyState, showToast } from '../core/ui.js';

export function getStationCommanderCaseReference() {
  const match = window.location.pathname.match(/\/station-commander\/dockets\/([^/]+)/);
  return match ? match[1] : null;
}

function getInvestigationEffectiveStatus(item) {
  const investigationStatus = String(item?.investigation?.status || item?.investigation_status || '').trim().toUpperCase();
  return investigationStatus === 'COMPLETED' ? 'COMPLETED' : null;
}

function formatElapsedDuration(startIso, endIso) {
  if (!startIso || !endIso) {
    return 'N/A';
  }

  const start = new Date(startIso);
  const end = new Date(endIso);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return 'N/A';
  }

  const elapsedMs = Math.max(0, end.getTime() - start.getTime());
  const totalSeconds = Math.floor(elapsedMs / 1000);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);

  if (days > 0) {
    return `${days}d ${hours}h ${minutes}m`;
  }
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m`;
  }
  return `${totalSeconds}s`;
}

export async function hydrateStationCommanderDashboard() {
  const container = document.getElementById('stationCommanderCaseList');
  if (!container) {
    return;
  }

  try {
    const dockets = await fetchJson('/api/v1/station-commander/dockets');
    const activeDockets = (dockets || []).filter((item) => getInvestigationEffectiveStatus(item) !== 'COMPLETED');
    const completedDockets = (dockets || []).filter((item) => getInvestigationEffectiveStatus(item) === 'COMPLETED');

    container.innerHTML = `
      <div class="stack-list">
        <div class="panel-head"><h3>Active Cases</h3></div>
        ${activeDockets.length
          ? activeDockets.map((item) => `
              <article class="docket-card">
                <div class="meta-wrap">
                  <strong>${item.case_reference}</strong>
                  <span>${item.location || item.title || 'Operational review required'}</span>
                </div>
                <div class="stack-row">
                  <span class="${buildStatusBadge(item.status || 'ACTIVE')}">${item.status || 'ACTIVE'}</span>
                  <button class="secondary-btn small-btn" type="button" data-case-link="/station-commander/dockets/${item.case_reference}">Open</button>
                </div>
              </article>
            `).join('')
          : '<div class="empty-state">No active dockets are currently tracked by the station commander.</div>'}
      </div>
      <div class="stack-list" style="margin-top:18px;">
        <div class="panel-head"><h3>Completed Cases</h3></div>
        ${completedDockets.length
          ? completedDockets.map((item) => {
              const completedAt = item?.investigation?.completed_at || item?.completed_at || null;
              const startedAt = item?.investigation?.started_at || item?.investigation?.opened_at || item?.investigation?.created_at || item?.created_at || null;
              return `
                <article class="docket-card">
                  <div class="meta-wrap">
                    <strong>${item.case_reference}</strong>
                    <span>${item.location || item.title || 'Completed investigation'}</span>
                  </div>
                  <div class="stack-row">
                    <span class="${buildStatusBadge('COMPLETED')}">Completed</span>
                    <span class="badge badge-muted">${completedAt ? new Date(completedAt).toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, ' UTC') : 'Completion pending'}</span>
                    <button class="secondary-btn small-btn" type="button" data-case-link="/station-commander/dockets/${item.case_reference}">Open</button>
                  </div>
                  <div class="field-hint" style="margin-top:8px;">Time to Completion: ${formatElapsedDuration(startedAt, completedAt)}</div>
                </article>
              `;
            }).join('')
          : '<div class="empty-state">No completed cases are currently tracked by the station commander.</div>'}
      </div>
    `;
    bindCaseLinks(container);
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load station commander queue.');
  }

  const breachContainer = document.getElementById('stationCommanderSlaBreachList');
  if (breachContainer) {
    try {
      const breaches = await fetchJson('/api/v1/station-commander/sla/breaches');
      renderDocketCardList(breachContainer, breaches, {
        reference: (item) => item.case_reference,
        linkPrefix: '/station-commander/dockets/',
        title: (item) => `${item.elapsed_hours != null ? item.elapsed_hours : '?'}h elapsed of the 72-hour SLA`,
        status: 'BREACHED',
        actionLabel: 'Open',
        emptyMessage: 'No dockets have breached the 72-hour SLA (NI 3/2011).',
      });
    } catch (error) {
      setEmptyState(breachContainer, error.message || 'Unable to load SLA breach summary.');
    }
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

  const assignableStatuses = new Set(['REGISTERED', 'AWAITING_CONSTABLE_REGISTRATION']);
  const canReassign = assignableStatuses.has(docket.status) && !docket.is_frozen;

  if (blockedNotice) {
    if (docket.is_frozen) {
      blockedNotice.textContent = 'This docket is frozen; reassignment is restricted until it is released.';
    } else if (docket.status === 'AWAITING_CONSTABLE_REGISTRATION') {
      blockedNotice.textContent = 'This docket has not been registered yet — a constable can be assigned to take hold of it.';
    } else if (!assignableStatuses.has(docket.status)) {
      blockedNotice.textContent = 'Reassignment is available once the citizen has submitted this docket for review.';
    } else {
      blockedNotice.textContent = '';
    }
  }

  if (!canReassign) {
    if (select) {
      select.innerHTML = '<option value="">Unavailable</option>';
      select.disabled = true;
    }
    if (reasonField) reasonField.disabled = true;
    if (confirmButton) confirmButton.disabled = true;
    return;
  }

  // Only a constable can take hold of a docket before it's registered; once
  // registered either role is a valid target (matches the backend's rule).
  const roleFilter = docket.status === 'AWAITING_CONSTABLE_REGISTRATION' ? 'constable' : null;
  const officersUrl = roleFilter
    ? `/api/v1/station-commander/officers?role=${roleFilter}`
    : '/api/v1/station-commander/officers';

  fetchJson(officersUrl)
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
      flashToast('Docket reassigned successfully.');
      window.location.reload();
    } catch (error) {
      errorEl.textContent = error.message || 'Unable to reassign docket.';
      errorEl.classList.remove('hidden');
      showToast(error.message || 'Unable to reassign docket.', { type: 'error' });
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
  const frozenNotice = document.getElementById('stationCommanderFrozenNotice');
  const frozenReason = document.getElementById('stationCommanderFrozenReason');
  const docketContent = document.getElementById('stationCommanderDocketContent');
  const slaContainer = document.getElementById('stationCommanderSlaMeter');
  const timeline = document.getElementById('stationCommanderAuditList');
  const investigationInfo = document.getElementById('stationCommanderInvestigationInfo');

  let isFrozen = false;
  try {
    const docket = await fetchJson(`/api/v1/station-commander/dockets/${caseReference}`);
    isFrozen = Boolean(docket.is_frozen);
    const investigationStatus = String(docket.investigation?.status || docket.investigation_status || docket.status || 'UNKNOWN').toUpperCase();
    const effectiveStatus = investigationStatus === 'COMPLETED' ? 'COMPLETED' : (docket.status || 'UNKNOWN');
    const completedAt = docket.investigation?.completed_at || docket.sla?.completed_at || null;
    const completedAtText = completedAt ? new Date(completedAt).toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, ' UTC') : 'Not recorded';
    const startedAt = docket.investigation?.started_at || docket.investigation?.opened_at || docket.investigation?.created_at || docket.created_at || null;
    const timeToCompletion = investigationStatus === 'COMPLETED' ? formatElapsedDuration(startedAt, completedAt) : 'N/A';

    if (freezeBadge) {
      freezeBadge.className = isFrozen ? 'badge badge-warning' : 'badge badge-verified';
      freezeBadge.textContent = isFrozen ? `Frozen${docket.freeze_reason ? `: ${docket.freeze_reason}` : ''}` : 'Active';
    }

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
        <dt>Assigned Officer</dt><dd>${docket.assigned_officer_id || 'Not assigned'}</dd>
        <dt>Current Status</dt><dd>${effectiveStatus}</dd>
        <dt>Completion Timestamp</dt><dd>${completedAtText}</dd>
        <dt>Time to Completion</dt><dd>${timeToCompletion}</dd>
        <dt>Freeze Status</dt><dd>${docket.freeze_status || 'NOT_FROZEN'}</dd>
      `;
    }
    renderSlaMeter(slaContainer, { ...(docket.sla || {}), status: investigationStatus === 'COMPLETED' ? 'COMPLETED' : (docket.sla?.status || 'ACTIVE'), completed_at: completedAt });
    if (investigationInfo) {
      if (docket.investigation) {
        const investigation = docket.investigation;
        const outcome = investigation.outcome || 'OUTCOME_PENDING';
        const notes = investigation.final_notes || investigation.notes || 'No final reasoning was recorded.';
        investigationInfo.innerHTML = investigationStatus === 'COMPLETED'
          ? `<p><strong>Investigation completed</strong> — Outcome: ${outcome}. ${notes}</p><p>Completed at ${completedAtText}</p>`
          : `<p><strong>Investigation ${investigation.investigation_id || 'record'}</strong>: ${investigation.status || 'OPEN'}</p><p>${notes}</p>`;
      } else {
        investigationInfo.innerHTML = '<p>No investigation has been opened for this docket yet.</p>';
      }
    }
    bindReassignment(caseReference, docket);
  } catch (error) {
    if (meta) {
      meta.innerHTML = `<dt>Status</dt><dd>Unavailable</dd><dt>Message</dt><dd>${error.message}</dd>`;
    }
    return;
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
