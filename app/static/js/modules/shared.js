/**
 * Cross-role widgets that appear on pages reachable by more than one role
 * (Active Cases, Evidence Vault) and are not gated by `data-role`.
 */

import { fetchJson } from '../core/api.js';
import { bindCaseLinks, renderDocketCardList, setEmptyState } from '../core/ui.js';

function getInvestigationEffectiveStatus(item) {
  const investigationStatus = String(item?.investigation?.status || item?.investigation_status || item?.status || '').trim().toUpperCase();
  return investigationStatus === 'COMPLETED' ? 'COMPLETED' : null;
}

export async function hydrateActiveCases() {
  const container = document.getElementById('activeCaseList');
  if (!container) {
    return;
  }

  try {
    const dockets = await fetchJson('/api/v1/station-commander/dockets');
    const activeDockets = (dockets || []).filter((item) => getInvestigationEffectiveStatus(item) !== 'COMPLETED').slice(0, 6);
    const completedDockets = (dockets || []).filter((item) => getInvestigationEffectiveStatus(item) === 'COMPLETED').slice(0, 6);

    container.innerHTML = `
      <div class="stack-list">
        <div class="panel-head"><h3>Active Cases</h3></div>
        ${activeDockets.length ? activeDockets.map((item) => `
          <article class="docket-card">
            <div class="meta-wrap">
              <strong>${item.case_reference}</strong>
              <span>${item.title || item.location || 'Operational review required'}</span>
            </div>
            <div class="stack-row">
              <span class="badge badge-verified">${item.status || 'ACTIVE'}</span>
              <button class="secondary-btn small-btn" type="button" data-case-link="/station-commander/dockets/${item.case_reference}">Open</button>
            </div>
          </article>
        `).join('') : '<div class="empty-state">No active cases are currently tracked.</div>'}
      </div>
      <div class="stack-list" style="margin-top:18px;">
        <div class="panel-head"><h3>Completed Cases</h3></div>
        ${completedDockets.length ? completedDockets.map((item) => `
          <article class="docket-card">
            <div class="meta-wrap">
              <strong>${item.case_reference}</strong>
              <span>${item.title || item.location || 'Completed case'}</span>
            </div>
            <div class="stack-row">
              <span class="badge badge-verified">Completed</span>
              <button class="secondary-btn small-btn" type="button" data-case-link="/station-commander/dockets/${item.case_reference}">Open</button>
            </div>
          </article>
        `).join('') : '<div class="empty-state">No completed cases are currently available.</div>'}
      </div>
    `;
    bindCaseLinks(container);
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load active case inventory.');
  }
}

export async function hydrateEvidenceVault() {
  const container = document.getElementById('evidenceVaultList');
  if (!container) {
    return;
  }

  try {
    const dockets = await fetchJson('/api/v1/station-commander/dockets');
    const evidence = dockets.flatMap((item) => (Array.isArray(item.evidence) ? item.evidence.map((record) => ({ ...record, case_reference: item.case_reference })) : []));
    if (!evidence.length) {
      setEmptyState(container, 'No evidence records are available in the vault.');
      return;
    }
    container.innerHTML = evidence
      .slice(0, 6)
      .map((item) => `
        <article class="docket-card">
          <div class="meta-wrap">
            <strong>${item.filename || item.evidence_type || 'Evidence Record'}</strong>
            <span>${item.case_reference}</span>
          </div>
          <div class="stack-row">
            <span class="badge badge-muted">${item.evidence_type || 'Record'}</span>
          </div>
        </article>
      `)
      .join('');
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load evidence vault.');
  }
}

export function init() {
  hydrateActiveCases();
  hydrateEvidenceVault();
}
