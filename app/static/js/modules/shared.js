/**
 * Cross-role widgets that appear on pages reachable by more than one role
 * (Active Cases, Evidence Vault) and are not gated by `data-role`.
 */

import { fetchJson } from '../core/api.js';
import { buildStatusBadge, setEmptyState } from '../core/ui.js';

export async function hydrateActiveCases() {
  const container = document.getElementById('activeCaseList');
  if (!container) {
    return;
  }

  try {
    const dockets = await fetchJson('/api/v1/station-commander/dockets');
    container.innerHTML = dockets
      .slice(0, 6)
      .map((item) => `
        <article class="docket-card">
          <div class="meta-wrap">
            <strong>${item.case_reference}</strong>
            <span>${item.title || 'Operational review required'}</span>
          </div>
          <div class="stack-row">
            <span class="${buildStatusBadge(item.status)}">${item.status || 'UNKNOWN'}</span>
          </div>
        </article>
      `)
      .join('');
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
