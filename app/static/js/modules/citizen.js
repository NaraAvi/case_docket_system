/**
 * Citizen dashboard, docket detail timeline, and new-docket submission form.
 */

import { fetchJson } from '../core/api.js';
import { buildStatusBadge, setEmptyState, bindCaseLinks } from '../core/ui.js';

export function getCitizenCaseReference() {
  const match = window.location.pathname.match(/^\/citizen\/dockets\/(?!new(?:\/)?$)([^/]+)/);
  return match ? match[1] : null;
}

export async function hydrateCitizenDashboard() {
  const container = document.getElementById('citizenDockets');
  if (!container) {
    return;
  }

  try {
    const dockets = await fetchJson('/api/v1/citizen/dockets');
    if (!dockets.length) {
      setEmptyState(container, 'No dockets yet. Submit your first report to begin the workflow.');
      return;
    }

    container.innerHTML = dockets
      .map((item) => `
        <article class="docket-card">
          <div class="meta-wrap">
            <strong>${item.case_reference}</strong>
            <span>${item.title || 'No title provided'}</span>
          </div>
          <div class="stack-row">
            <span class="${buildStatusBadge(item.status)}">${item.status || 'DRAFT'}</span>
            <button class="secondary-btn small-btn" type="button" data-case-link="/citizen/dockets/${item.case_reference}">Open</button>
          </div>
        </article>
      `)
      .join('');

    bindCaseLinks(container);
  } catch (error) {
    setEmptyState(container, error.message || 'Unable to load dockets.');
  }
}

export async function hydrateCitizenDetail() {
  const caseReference = getCitizenCaseReference();
  if (!caseReference) {
    return;
  }
  const meta = document.getElementById('citizenCaseMeta');
  const timeline = document.getElementById('citizenCaseTimeline');
  if (!meta && !timeline) {
    return;
  }

  try {
    const docket = await fetchJson(`/api/v1/citizen/dockets/${caseReference}`);
    if (meta) {
      meta.innerHTML = `
        <dt>Status</dt><dd>${docket.status || 'DRAFT'}</dd>
        <dt>Location</dt><dd>${docket.location || 'Not provided'}</dd>
        <dt>Incident Date</dt><dd>${docket.incident_date || 'Not provided'}</dd>
        <dt>Case Title</dt><dd>${docket.title || 'Unspecified'}</dd>
      `;
    }
    if (timeline) {
      const items = Array.isArray(docket.timeline) && docket.timeline.length ? docket.timeline : [{ event_type: 'docket_recorded', timestamp: 'Pending', details: {} }];
      timeline.innerHTML = items
        .map((event) => `<li><span class="timeline-dot"></span><div><strong>${event.event_type || 'Case Event'}</strong><small>${event.timestamp || 'No timestamp'}${event.details && event.details.status ? ` • ${event.details.status}` : ''}</small></div></li>`)
        .join('');
    }
  } catch (error) {
    if (meta) {
      meta.innerHTML = `<dt>Status</dt><dd>Unavailable</dd><dt>Details</dt><dd>${error.message}</dd>`;
    }
    if (timeline) {
      setEmptyState(timeline, error.message || 'Unable to load timeline.');
    }
  }
}

export function hydrateCitizenForm() {
  const formButton = document.getElementById('submitCitizenDocket');
  if (!formButton) {
    return;
  }

  formButton.addEventListener('click', async () => {
    const title = document.getElementById('crimeType')?.value || '';
    const description = document.getElementById('description')?.value || '';
    const incidentDate = document.getElementById('incidentDate')?.value || '';
    const location = document.getElementById('incidentLocation')?.value || '';

    try {
      const result = await fetchJson('/api/v1/citizen/dockets', {
        method: 'POST',
        body: {
          title,
          description,
          incident_date: incidentDate,
          location,
        },
      });
      window.location.href = `/citizen/dockets/${result.case_reference}`;
    } catch (error) {
      const errorBlock = document.getElementById('loginError') || document.getElementById('formError');
      if (errorBlock) {
        errorBlock.textContent = error.message;
        errorBlock.classList.remove('hidden');
      }
    }
  });
}

export function bindCitizenNavigationShortcuts() {
  const newDocketButton = document.getElementById('newCitizenDocketBtn');
  if (newDocketButton) {
    newDocketButton.addEventListener('click', () => {
      window.location.href = '/citizen/dockets/new';
    });
  }

  const backToCitizenDashboard = document.getElementById('backToCitizenDashboard');
  if (backToCitizenDashboard) {
    backToCitizenDashboard.addEventListener('click', () => {
      window.location.href = '/citizen';
    });
  }
}

export function init() {
  if (document.body.dataset.role !== 'citizen') {
    return;
  }
  if (document.getElementById('citizenDockets')) {
    hydrateCitizenDashboard();
  }
  if (getCitizenCaseReference()) {
    hydrateCitizenDetail();
  }
  if (document.getElementById('submitCitizenDocket')) {
    hydrateCitizenForm();
  }
  bindCitizenNavigationShortcuts();
}
