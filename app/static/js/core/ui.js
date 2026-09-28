/**
 * Shared DOM helpers: status badges, empty states, the user badge and the
 * high-accountability re-authorization modal used across every dashboard.
 */

import { getUser } from './auth.js';
import { openMediaFile } from './api.js';

const FLASH_STORAGE_KEY = 'pdasFlashMessage';

/**
 * Show a transient toast notification (base.html#toastContainer). Used for
 * immediate confirmation of an action taken on the current page.
 */
export function showToast(message, { type = 'success', duration = 4000 } = {}) {
  const container = document.getElementById('toastContainer');
  if (!container || !message) {
    return;
  }
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add('toast-visible'));
  setTimeout(() => {
    toast.classList.remove('toast-visible');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

/**
 * Queue a toast to show after a redirect/reload (sessionStorage survives
 * navigation within the tab). Call showFlashedToast() on the next page's
 * load to display and clear it -- pdas_app.js does this automatically.
 */
export function flashToast(message, { type = 'success' } = {}) {
  try {
    sessionStorage.setItem(FLASH_STORAGE_KEY, JSON.stringify({ message, type }));
  } catch (error) {
    // sessionStorage unavailable (private mode, etc.) -- the toast is skipped, not fatal.
  }
}

export function showFlashedToast() {
  let stored;
  try {
    stored = sessionStorage.getItem(FLASH_STORAGE_KEY);
    if (stored) {
      sessionStorage.removeItem(FLASH_STORAGE_KEY);
    }
  } catch (error) {
    return;
  }
  if (!stored) {
    return;
  }
  try {
    const { message, type } = JSON.parse(stored);
    showToast(message, { type });
  } catch (error) {
    // malformed stored value -- nothing to show.
  }
}

export function buildStatusBadge(status) {
  const value = (status || 'UNKNOWN').toString().toUpperCase();
  if (value.includes('BREACHED')) {
    return 'badge badge-breach';
  }
  if (value.includes('COMPLETED') || value.includes('CLOSED') || value.includes('RESOLVED')) {
    return 'badge badge-verified';
  }
  if (value.includes('REGISTERED') || value.includes('VERIFIED') || value.includes('ACTIVE')) {
    return 'badge badge-verified';
  }
  if (value.includes('FROZEN') || value.includes('AWAITING') || value.includes('PENDING') || value.includes('REVIEW')) {
    return 'badge badge-warning';
  }
  return 'badge badge-muted';
}

export function renderWorkflowRail(container, { title = 'Workflow', steps = [], locked = false } = {}) {
  if (!container) {
    return;
  }
  if (!Array.isArray(steps) || !steps.length) {
    container.innerHTML = `
      <div class="workflow-rail-header">
        <h3>${title}</h3>
        <span class="workflow-rail-subtitle">Waiting for state</span>
      </div>
      <div class="workflow-rail" role="list" aria-label="${title}">
        <div class="workflow-step upcoming"><span class="workflow-step-number">1</span><div class="workflow-step-copy"><strong>Workflow</strong><small>Waiting for data</small></div></div>
      </div>
    `;
    return;
  }
  container.innerHTML = `
    <div class="workflow-rail-header">
      <h3>${title}</h3>
      <span class="workflow-rail-subtitle">${locked ? 'Blocked by freeze' : 'Current stage'}</span>
    </div>
    <div class="workflow-rail" role="list" aria-label="${title}">
      ${steps
        .map((step, index) => {
          const state = step.state || 'upcoming';
          const classNames = ['workflow-step', state, locked ? 'blocked' : ''].filter(Boolean).join(' ');
          const number = state === 'complete' ? '✓' : index + 1;
          const detailText = step.detail ? `<small>${step.detail}</small>` : '';
          const ariaCurrent = state === 'current' ? 'step' : 'false';
          return `
            <div class="${classNames}" role="listitem" aria-current="${ariaCurrent}">
              <span class="workflow-step-number">${number}</span>
              <div class="workflow-step-copy">
                <strong>${step.label}</strong>
                ${detailText}
              </div>
            </div>
          `;
        })
        .join('')}
    </div>
  `;
}

export function setEmptyState(container, message) {
  if (!container) {
    return;
  }
  container.innerHTML = `<div class="empty-state">${message}</div>`;
}

export function bindCaseLinks(container) {
  if (!container) {
    return;
  }
  container.querySelectorAll('[data-case-link]').forEach((button) => {
    button.addEventListener('click', () => {
      window.location.href = button.dataset.caseLink;
    });
  });
}

export function refreshUserBadge() {
  const user = getUser();
  const badge = document.getElementById('userBadge');
  if (badge && user) {
    badge.textContent = `${user.full_name || user.role || 'User'} • ${user.role}`;
  }
}

let activeReauthHandler = null;

/**
 * Populate the shared high-accountability modal (base.html #reauthModal) for
 * one specific action and register what happens on confirm. The modal itself
 * stays generic; callers (e.g. modules/ipid.js) supply the target/action
 * copy and an async onConfirm(reason) that performs the real request.
 */
export function configureReauthModal({ targetLabel, targetValue, actionLabel, subtitle, confirmLabel = 'Confirm Decision', onConfirm }) {
  const modal = document.getElementById('reauthModal');
  if (!modal) {
    return;
  }

  const targetRow = modal.querySelector('.field-row label');
  if (targetRow && targetLabel !== undefined) {
    targetRow.textContent = targetLabel;
  }
  const targetValueEl = modal.querySelector('[data-reauth-target]');
  if (targetValueEl && targetValue !== undefined) {
    targetValueEl.textContent = targetValue;
  }
  const actionEl = modal.querySelector('[data-reauth-action]');
  if (actionEl && actionLabel !== undefined) {
    actionEl.textContent = actionLabel;
  }
  const subtitleEl = modal.querySelector('[data-reauth-subtitle]');
  if (subtitleEl && subtitle !== undefined) {
    subtitleEl.textContent = subtitle;
  }
  const confirmBtn = modal.querySelector('[data-reauth-confirm]');
  if (confirmBtn) {
    confirmBtn.textContent = confirmLabel;
  }
  const textarea = modal.querySelector('[data-reauth-reason]');
  if (textarea) {
    textarea.value = '';
  }
  const errorEl = modal.querySelector('[data-reauth-error]');
  if (errorEl) {
    errorEl.textContent = '';
    errorEl.classList.add('hidden');
  }

  activeReauthHandler = async () => {
    const reason = textarea ? textarea.value.trim() : '';
    if (!reason) {
      if (errorEl) {
        errorEl.textContent = 'A reason is required.';
        errorEl.classList.remove('hidden');
      }
      return;
    }
    try {
      await onConfirm(reason);
      modal.classList.add('hidden');
    } catch (error) {
      if (errorEl) {
        errorEl.textContent = error.message || 'Action failed.';
        errorEl.classList.remove('hidden');
      }
      showToast(error.message || 'Action failed.', { type: 'error' });
    }
  };
}

export function bindReauthModal() {
  const reauthModal = document.getElementById('reauthModal');
  document.querySelectorAll('[data-open-reauth]').forEach((button) => {
    button.addEventListener('click', () => {
      if (reauthModal) {
        reauthModal.classList.remove('hidden');
      }
    });
  });

  const closeButton = document.querySelector('[data-close-reauth]');
  if (closeButton && reauthModal) {
    closeButton.addEventListener('click', () => reauthModal.classList.add('hidden'));
  }

  const confirmButton = reauthModal ? reauthModal.querySelector('[data-reauth-confirm]') : null;
  if (confirmButton) {
    confirmButton.addEventListener('click', () => {
      if (activeReauthHandler) {
        activeReauthHandler();
      }
    });
  }
}

/**
 * Render one docket/case card matching the markup every dashboard queue
 * (constable, detective, station commander, IPID, active cases) previously
 * duplicated inline as its own template literal.
 */
function resolveOption(value, item, fallback) {
  if (typeof value === 'function') {
    return value(item) ?? fallback;
  }
  return value ?? fallback;
}

export function renderDocketCard(item, { reference, title, linkPrefix, actionLabel = 'Open', status, badges } = {}) {
  const referenceValue = resolveOption(reference, item, item.case_reference ?? item.escalation_id ?? '');
  const titleValue = resolveOption(title, item, item.location ?? item.title ?? 'Details unavailable');
  const statusValue = resolveOption(status, item, item.status ?? 'UNKNOWN');
  const link = linkPrefix ? `${linkPrefix}${referenceValue}` : null;
  // `is_frozen` is only present on payloads that already carry freeze state
  // (e.g. the shared station-commander docket list); anything else (an
  // escalation, a disciplinary case, an SLA-breach row) simply omits it.
  const frozenBadge = item.is_frozen ? '<span class="badge badge-warning">FROZEN</span>' : '';
  // Optional extra badges (e.g. the statutory-mandate marker); each entry is
  // `{ label, className?, title? }`, supplied per item by the caller.
  const extraBadges = (resolveOption(badges, item, []) || [])
    .map((badge) => `<span class="badge ${badge.className || 'badge-statute'}"${badge.title ? ` title="${badge.title}"` : ''}>${badge.label}</span>`)
    .join('');

  return `
    <article class="docket-card">
      <div class="meta-wrap">
        <strong>${referenceValue}</strong>
        <span>${titleValue}</span>
      </div>
      <div class="stack-row">
        <span class="${buildStatusBadge(statusValue)}">${statusValue}</span>
        ${frozenBadge}
        ${extraBadges}
        ${link ? `<button class="secondary-btn small-btn" type="button" data-case-link="${link}">${actionLabel}</button>` : ''}
      </div>
    </article>
  `;
}

/**
 * Render a list of docket cards into a container and wire up navigation,
 * or fall back to an empty-state message.
 */
export function renderDocketCardList(container, items, options = {}) {
  if (!container) {
    return;
  }
  if (!items || !items.length) {
    setEmptyState(container, options.emptyMessage || 'No records are currently available.');
    return;
  }
  container.innerHTML = items.map((item) => renderDocketCard(item, options)).join('');
  bindCaseLinks(container);
}

/**
 * Render every statement recorded on a docket -- the citizen's own plus any
 * added by a detective or IPID reviewer -- as a list, newest first isn't
 * assumed; items render in the order the API returns them. Shared by every
 * role's docket detail view so a statement recorded by one role is visible
 * to every other role handling the case.
 */
export function renderStatementList(container, statements) {
  if (!container) {
    return;
  }
  const items = Array.isArray(statements) ? statements : [];
  if (!items.length) {
    container.innerHTML = '<div class="empty-state">No statements have been recorded yet.</div>';
    return;
  }
  container.innerHTML = items
    .map((statement) => {
      const recordedBy = statement.recorded_by_role ? `${statement.recorded_by_role} (${statement.recorded_by})` : 'Citizen';
      return `
        <article class="mini-case-card">
          <div class="stack-row" style="justify-content:space-between;">
            <strong>${recordedBy}</strong>
            <span>${statement.created_at || ''}</span>
          </div>
          <p>${statement.statement_text}</p>
        </article>
      `;
    })
    .join('');
}

/**
 * Event names treated as milestones in audit trails / timelines. Everything
 * else stays in the DOM but is hidden behind a "Show full trail" toggle.
 */
export const TIMELINE_MILESTONES = new Set([
  'submission_created',
  'submitted',
  'docket_submitted',
  'docket_created',
  'incident_candidate_case_created',
  'docket_registered',
  'interview_completed',
  'investigation_opened',
  'detective_investigation_completed',
  'statutory_ipid_referral',
  'case_frozen',
  'case_unfrozen',
  'withdrawal_requested',
  'correction_logged',
  'escalation_created',
  'ipid_escalation_upheld',
  'ipid_escalation_dismissed',
  'assignment_created',
  'station_commander_force_reassigned_docket',
  'disciplinary_case_created',
  'disciplinary_case_closed',
]);

// Trails this short (or with no recognised milestones) are shown in full.
const TIMELINE_FULL_TRAIL_THRESHOLD = 5;

export function isTimelineMilestone(value) {
  return TIMELINE_MILESTONES.has(String(value || '').trim().toLowerCase());
}

/**
 * Render a chronological event list (audit trail, case timeline) into a
 * `<ul class="timeline-list">` container, matching the structure produced by
 * components/_timeline.html. Longer trails show milestones only by default,
 * with a "Show full trail (N)" toggle; `formatDetail(event)` optionally
 * replaces the plain `detailKey` lookup for the small detail line.
 */
export function renderTimelineList(container, items, { titleKey = 'event_type', detailKey = 'timestamp', fallbackTitle = 'Event', fallbackDetail = 'No timestamp', formatDetail = null, milestonesOnly = true } = {}) {
  if (!container) {
    return;
  }
  const rows = Array.isArray(items) && items.length ? items : [{}];
  const renderRow = (event, className = '') => {
    const detail = formatDetail ? formatDetail(event) : (event[detailKey] || fallbackDetail);
    return `<li${className ? ` class="${className}"` : ''}><span class="timeline-dot"></span><div><strong>${event[titleKey] || fallbackTitle}</strong><small>${detail}</small></div></li>`;
  };
  const milestoneCount = rows.filter((event) => isTimelineMilestone(event[titleKey])).length;
  const showEverything = !milestonesOnly
    || rows.length <= TIMELINE_FULL_TRAIL_THRESHOLD
    || milestoneCount === 0
    || milestoneCount === rows.length;

  if (showEverything) {
    container.innerHTML = rows.map((event) => renderRow(event)).join('');
    return;
  }

  const fullLabel = `Show full trail (${rows.length})`;
  const milestoneLabel = `Show milestones only (${milestoneCount})`;
  container.innerHTML = `${rows
    .map((event) => (isTimelineMilestone(event[titleKey]) ? renderRow(event, 'timeline-milestone') : renderRow(event, 'timeline-minor hidden')))
    .join('')}<li class="timeline-toggle-row"><button type="button" class="link-btn timeline-toggle" aria-expanded="false"${container.id ? ` aria-controls="${container.id}"` : ''}>${fullLabel}</button></li>`;

  const toggle = container.querySelector('.timeline-toggle');
  toggle.addEventListener('click', () => {
    const expanded = toggle.getAttribute('aria-expanded') !== 'true';
    container.querySelectorAll('li.timeline-minor').forEach((row) => row.classList.toggle('hidden', !expanded));
    toggle.setAttribute('aria-expanded', String(expanded));
    toggle.textContent = expanded ? milestoneLabel : fullLabel;
  });
}

const NAV_COLLAPSED_STORAGE_KEY = 'pdasNavCollapsed';

/**
 * Sidebar collapse toggle (base.html #navToggle). The collapsed state is a
 * `nav-collapsed` class on <html>, remembered in localStorage; base.html
 * applies the stored value before first paint.
 */
export function bindNavToggle(button = document.getElementById('navToggle')) {
  if (!button || button.dataset.navToggleBound === 'true') {
    return;
  }
  button.dataset.navToggleBound = 'true';
  const root = document.documentElement;
  try {
    if (localStorage.getItem(NAV_COLLAPSED_STORAGE_KEY) === '1') {
      root.classList.add('nav-collapsed');
    }
  } catch (error) {
    // localStorage unavailable -- the sidebar simply starts expanded.
  }
  const sync = () => {
    const collapsed = root.classList.contains('nav-collapsed');
    const label = collapsed ? 'Expand navigation' : 'Collapse navigation';
    button.setAttribute('aria-expanded', String(!collapsed));
    button.setAttribute('aria-label', label);
    button.title = label;
  };
  sync();
  button.addEventListener('click', () => {
    const collapsed = root.classList.toggle('nav-collapsed');
    try {
      localStorage.setItem(NAV_COLLAPSED_STORAGE_KEY, collapsed ? '1' : '0');
    } catch (error) {
      // Not persisted; the toggle still works for this page view.
    }
    sync();
  });
}

const collapsibleSetters = new WeakMap();
let collapsibleCounter = 0;

function headingText(heading) {
  if (!heading) {
    return 'section';
  }
  const ownText = Array.from(heading.childNodes)
    .filter((node) => node.nodeType === 3)
    .map((node) => node.textContent)
    .join('')
    .trim();
  return ownText || heading.textContent.trim() || 'section';
}

function bindCollapsible(card) {
  if (collapsibleSetters.has(card)) {
    return collapsibleSetters.get(card);
  }
  const children = Array.from(card.children);
  const body = children.find((child) => child.hasAttribute('data-collapsible-body'));
  if (!body) {
    return null;
  }
  let head = children.find((child) => child.hasAttribute('data-collapsible-head'));
  if (!head) {
    const heading = children.find((child) => /^H[2-4]$/.test(child.tagName));
    head = document.createElement('div');
    head.className = 'card-head';
    head.setAttribute('data-collapsible-head', '');
    card.insertBefore(head, heading || body);
    if (heading) {
      head.appendChild(heading);
    }
  }
  const title = card.dataset.collapsibleLabel || headingText(head.querySelector('h2, h3, h4'));
  if (!body.id) {
    collapsibleCounter += 1;
    body.id = `pdasCollapsible${collapsibleCounter}`;
  }

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'collapse-toggle';
  button.setAttribute('aria-controls', body.id);
  head.appendChild(button);

  const setExpanded = (expanded) => {
    body.classList.toggle('hidden', !expanded);
    card.classList.toggle('is-collapsed', !expanded);
    button.setAttribute('aria-expanded', String(expanded));
    button.setAttribute('aria-label', `${expanded ? 'Collapse' : 'Expand'} ${title}`);
    button.innerHTML = `<span class="chevron" aria-hidden="true">▾</span>${expanded ? 'Hide' : 'Show'}`;
  };
  setExpanded(card.dataset.collapsed !== 'true');
  button.addEventListener('click', () => setExpanded(button.getAttribute('aria-expanded') !== 'true'));
  collapsibleSetters.set(card, setExpanded);
  return setExpanded;
}

/**
 * Generic collapsible cards, following the #citizenSubmissionToggle pattern
 * (button, aria-expanded, `.hidden`). Markup:
 *   <div class="panel-card" data-collapsible [data-collapsed="true"]>
 *     <div class="card-head" data-collapsible-head><h3>Title</h3></div>
 *     <div data-collapsible-body> …content that JS may re-render… </div>
 *   </div>
 * Only the outer body wrapper is toggled, so modules that re-render or
 * hide the inner containers keep working. A card without an explicit head
 * gets its first heading wrapped automatically.
 */
export function bindCollapsibles(root = document) {
  if (!root || !root.querySelectorAll) {
    return;
  }
  root.querySelectorAll('[data-collapsible]').forEach((card) => bindCollapsible(card));
}

/**
 * Programmatically expand/collapse one [data-collapsible] card (binding it
 * first if needed), e.g. to collapse cards for a completed investigation.
 */
export function setCollapsibleExpanded(card, expanded) {
  if (!card) {
    return;
  }
  const setExpanded = bindCollapsible(card);
  if (setExpanded) {
    setExpanded(Boolean(expanded));
  }
}

/**
 * Sticky, collapsible in-page section navigation:
 *   <aside class="section-nav" data-section-nav>
 *     <button data-section-nav-toggle>…</button>
 *     <ol data-section-nav-list><li><a href="#cardId">…</a></li>…</ol>
 *   </aside>
 * Links whose target card is hidden (e.g. no interview yet) are hidden too.
 */
export function bindSectionNav(nav) {
  if (!nav || nav.dataset.sectionNavBound === 'true') {
    return;
  }
  nav.dataset.sectionNavBound = 'true';
  const toggle = nav.querySelector('[data-section-nav-toggle]');
  const list = nav.querySelector('[data-section-nav-list]');
  const layout = nav.closest('.with-section-nav');
  const links = Array.from(nav.querySelectorAll('a[href^="#"]'));
  const targets = links.map((link) => document.getElementById(link.getAttribute('href').slice(1)));

  const syncVisibility = () => {
    links.forEach((link, index) => {
      const target = targets[index];
      link.parentElement.classList.toggle('hidden', !target || target.classList.contains('hidden'));
    });
  };
  syncVisibility();
  if (typeof MutationObserver !== 'undefined') {
    const observer = new MutationObserver(syncVisibility);
    targets.filter(Boolean).forEach((target) => observer.observe(target, { attributes: true, attributeFilter: ['class'] }));
  }

  const setExpanded = (expanded) => {
    if (list) {
      list.classList.toggle('hidden', !expanded);
    }
    if (toggle) {
      toggle.setAttribute('aria-expanded', String(expanded));
    }
    if (layout) {
      layout.classList.toggle('section-nav-collapsed', !expanded);
    }
  };
  const startsNarrow = typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 1100px)').matches;
  setExpanded(!startsNarrow);
  toggle?.addEventListener('click', () => setExpanded(toggle.getAttribute('aria-expanded') !== 'true'));

  let frame = null;
  const markActive = () => {
    frame = null;
    let activeIndex = -1;
    targets.forEach((target, index) => {
      if (target && !target.classList.contains('hidden') && target.getBoundingClientRect().top <= 140) {
        activeIndex = index;
      }
    });
    links.forEach((link, index) => link.classList.toggle('is-active', index === activeIndex));
  };
  window.addEventListener('scroll', () => {
    if (frame === null) {
      frame = requestAnimationFrame(markActive);
    }
  }, { passive: true });
  markActive();
}

/**
 * Format one preserved citizen-source value for read-only display.
 */
export function formatProtectedSourceValue(value) {
  if (value === undefined || value === null || value === '') {
    return 'Not provided';
  }
  if (Array.isArray(value)) {
    return value.filter((item) => item !== undefined && item !== null && item !== '').map((item) => String(item)).join(', ') || 'Not provided';
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}

// Display order of the protected-source groups.
const PROTECTED_SOURCE_GROUPS = [
  ['reporter', 'Reporter'],
  ['incident', 'Incident'],
  ['harm', 'Harm & injury'],
  ['people', 'People'],
  ['evidence', 'Evidence & prior reports'],
  ['contact', 'Contact'],
  ['safety', 'Safety'],
  ['other', 'Other'],
];

// Matching order matters (e.g. "contact_*" before the broader incident rules).
const PROTECTED_SOURCE_GROUP_RULES = [
  ['contact', (key) => key === 'can_contact' || key.includes('contact')],
  ['reporter', (key) => /^(legacy_)?reporter_/.test(key)],
  ['safety', (key) => /^current_(safety|risk)/.test(key)],
  ['evidence', (key) => /^(evidence_|previous_report_)/.test(key)],
  ['harm', (key) => /^(was_anyone_|harm_|injury_|injuries|medical_|property_)/.test(key)],
  ['people', (key) => /^(other_people|people_|person|victim|witness)/.test(key)],
  ['incident', (key) => ['title', 'description', 'date_certainty', 'date_unknown_reason'].includes(key) || /^(incident_|approximate_|location|police_|narrative_)/.test(key)],
];

function protectedSourceGroupFor(key) {
  const normalized = String(key).toLowerCase();
  const match = PROTECTED_SOURCE_GROUP_RULES.find(([, test]) => test(normalized));
  return match ? match[0] : 'other';
}

/**
 * Render a preserved (read-only) citizen submission as expandable groups
 * (reporter, incident, harm & injury, people, evidence, contact, safety,
 * other). Every non-empty key/value is kept; groups start collapsed.
 * Shared by the constable review and detective workspace.
 */
export function renderProtectedSourceGroups(container, originalContent, { title = 'Protected citizen source (read-only)', badge = 'immutable', emptyMessage = 'No preserved citizen source details are available for this docket.' } = {}) {
  if (!container) {
    return;
  }
  const content = originalContent && typeof originalContent === 'object' ? originalContent : {};
  const rows = Object.entries(content).filter(([, value]) => value !== undefined && value !== null && value !== '');
  if (!rows.length) {
    container.innerHTML = `<div class="empty-state">${emptyMessage}</div>`;
    return;
  }

  const grouped = new Map(PROTECTED_SOURCE_GROUPS.map(([key]) => [key, []]));
  rows.forEach(([key, value]) => grouped.get(protectedSourceGroupFor(key)).push([key, value]));

  const groupsMarkup = PROTECTED_SOURCE_GROUPS
    .filter(([key]) => grouped.get(key).length)
    .map(([key, label]) => {
      const entries = grouped.get(key);
      const renderedRows = entries
        .map(([entryKey, value]) => `<dt>${String(entryKey).replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())}</dt><dd>${formatProtectedSourceValue(value)}</dd>`)
        .join('');
      return `
        <details class="source-group" data-source-group="${key}">
          <summary>${label}<span class="source-group-count">${entries.length} field${entries.length === 1 ? '' : 's'}</span></summary>
          <dl class="meta-list compact">${renderedRows}</dl>
        </details>
      `;
    })
    .join('');

  container.innerHTML = `
    <article class="mini-case-card">
      <div class="stack-row" style="justify-content:space-between; align-items:center;">
        <strong>${title}</strong>
        <span class="badge badge-muted">${badge}</span>
      </div>
      <div class="source-groups">${groupsMarkup}</div>
    </article>
  `;
}

/**
 * Render evidence rows into a `<tbody>` container, matching the table
 * structure produced by components/_evidence_table.html. SHA-256 hashing is
 * Milestone 6 scope, so the hash column reads a placeholder until then.
 */

/**
 * A small "View" link for one uploaded file (evidence or a recording),
 * given its `storage_reference` (e.g. "recordings/<uuid>_name.wav"). Pair
 * with bindMediaViewButtons() after inserting the returned HTML into the DOM.
 */
export function renderMediaViewButton(storageReference, label = 'View recording') {
  if (!storageReference) {
    return '';
  }
  return `<button type="button" class="link-btn" data-view-media="${storageReference}">${label}</button>`;
}

export function bindMediaViewButtons(container) {
  if (!container) {
    return;
  }
  container.querySelectorAll('[data-view-media]').forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        await openMediaFile(`/api/v1/media/${button.dataset.viewMedia}`);
      } catch (error) {
        showToast(error.message || 'Unable to open file.', { type: 'error' });
      }
    });
  });
}

export function renderEvidenceTable(body, items) {
  if (!body) {
    return;
  }
  if (!Array.isArray(items) || !items.length) {
    body.innerHTML = '<tr><td colspan="6">No evidence has been submitted yet.</td></tr>';
    return;
  }
  body.innerHTML = items
    .map((item, index) => {
      const hasFile = Boolean(item.storage_reference);
      return `
        <tr>
          <td>${item.description || item.filename || 'Evidence record'}</td>
          <td>${item.evidence_type || 'Unspecified'}</td>
          <td>${item.source || item.submitted_by_role || 'Unknown'}</td>
          <td><span class="${buildStatusBadge(item.status)}">${item.status || 'SUBMITTED'}</span></td>
          <td class="hash-cell">${item.sha256_hash ? item.sha256_hash.slice(0, 16) + '…' : 'Not yet computed'}</td>
          <td>${hasFile ? `<button type="button" class="link-btn" data-view-evidence-index="${index}">View</button>` : '—'}</td>
        </tr>
      `;
    })
    .join('');

  body.querySelectorAll('[data-view-evidence-index]').forEach((button) => {
    button.addEventListener('click', async () => {
      const item = items[Number(button.dataset.viewEvidenceIndex)];
      try {
        await openMediaFile(`/api/v1/media/${item.storage_reference}`);
      } catch (error) {
        showToast(error.message || 'Unable to open file.', { type: 'error' });
      }
    });
  });
}

/**
 * Populate a `<select>` with one option per item.
 */
export function populateSelect(select, items, { valueKey = 'test_id', labelKey = 'full_name', placeholder = 'Select an officer…', describeKey } = {}) {
  if (!select) {
    return;
  }
  const options = [`<option value="">${placeholder}</option>`];
  (items || []).forEach((item) => {
    const label = describeKey ? `${item[labelKey]} (${item[describeKey]})` : item[labelKey];
    options.push(`<option value="${item[valueKey]}">${label}</option>`);
  });
  select.innerHTML = options.join('');
}

/**
 * Render a live-updating SLA countdown/progress meter from a deadline
 * timestamp. Returns the interval handle so callers can clear it if the page
 * navigates away, though these pages are single-view and reload on action.
 */
export function renderSlaMeter(container, sla) {
  if (!container || !sla || !sla.sla_due_at) {
    if (container) {
      container.innerHTML = '<div class="field-hint">SLA tracking is unavailable for this docket.</div>';
    }
    return null;
  }

  const isCompleted = String(sla.status || '').toUpperCase().includes('COMPLETED') || Boolean(sla.completed_at);
  if (isCompleted) {
    const completedAt = sla.completed_at ? new Date(sla.completed_at) : null;
    const completedText = completedAt && !Number.isNaN(completedAt.getTime())
      ? completedAt.toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, ' UTC')
      : 'the investigation completion timestamp';
    container.innerHTML = `
      <div class="sla-meter">
        <div class="sla-meter-track"><div class="sla-meter-fill" style="width:100%"></div></div>
        <span class="sla-meter-label">Investigation completed — SLA frozen at ${completedText}</span>
      </div>
    `;
    return null;
  }

  const dueAt = new Date(sla.sla_due_at).getTime();
  const totalWindowHours = (sla.elapsed_hours || 0) + (sla.remaining_hours || 0);

  const paint = () => {
    const now = Date.now();
    const remainingMs = dueAt - now;
    const breached = remainingMs <= 0;
    const remainingHours = Math.max(remainingMs / 3600000, 0);
    const elapsedHours = totalWindowHours > 0 ? totalWindowHours - remainingHours : 0;
    const percentElapsed = totalWindowHours > 0 ? Math.min((elapsedHours / totalWindowHours) * 100, 100) : 100;

    const hours = Math.floor(Math.max(remainingMs, 0) / 3600000);
    const minutes = Math.floor((Math.max(remainingMs, 0) % 3600000) / 60000);
    const label = breached
      ? `72-hour SLA breached ${Math.abs(hours)}h ago`
      : `${hours}h ${minutes}m remaining of the 72-hour SLA (NI 3/2011)`;

    container.innerHTML = `
      <div class="sla-meter">
        <div class="sla-meter-track"><div class="sla-meter-fill ${breached ? 'sla-breached' : percentElapsed > 75 ? 'sla-warning' : ''}" style="width:${percentElapsed}%"></div></div>
        <span class="sla-meter-label">${label}</span>
      </div>
    `;
  };

  paint();
  return setInterval(paint, 60000);
}

/**
 * Show the chosen file's name/size under a file input as it's picked.
 */
export function bindFilePreview(inputId, previewId) {
  const input = document.getElementById(inputId);
  const preview = document.getElementById(previewId);
  if (!input || !preview) {
    return;
  }
  input.addEventListener('change', () => {
    const file = input.files && input.files[0];
    if (!file) {
      preview.classList.add('hidden');
      return;
    }
    const sizeKb = Math.max(1, Math.round(file.size / 1024));
    preview.textContent = `${file.name} (${sizeKb} KB)`;
    preview.classList.remove('hidden');
  });
}
