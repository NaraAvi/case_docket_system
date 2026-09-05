document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.getElementById('loginForm');
  const loginError = document.getElementById('loginError');
  const logoutButton = document.getElementById('logoutButton');
  const role = document.body.dataset.role || '';

  const setSession = (token, user) => {
    localStorage.setItem('pdasToken', token);
    localStorage.setItem('pdasUser', JSON.stringify(user));
    document.cookie = `pdas_session_token=${encodeURIComponent(token)}; path=/; max-age=43200; SameSite=Lax`;
    document.cookie = `pdas_user=${encodeURIComponent(JSON.stringify(user))}; path=/; max-age=43200; SameSite=Lax`;
  };

  const clearSession = () => {
    localStorage.removeItem('pdasToken');
    localStorage.removeItem('pdasUser');
    document.cookie = 'pdas_session_token=; path=/; max-age=0; SameSite=Lax';
    document.cookie = 'pdas_user=; path=/; max-age=0; SameSite=Lax';
  };

  const getStoredToken = () => {
    const token = localStorage.getItem('pdasToken');
    if (token) {
      return token;
    }
    const match = document.cookie.match(/(?:^|; )pdas_session_token=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : null;
  };

  const getUser = () => {
    const raw = localStorage.getItem('pdasUser');
    if (raw) {
      try {
        return JSON.parse(raw);
      } catch (error) {
        return null;
      }
    }

    const match = document.cookie.match(/(?:^|; )pdas_user=([^;]*)/);
    if (!match) {
      return null;
    }

    try {
      return JSON.parse(decodeURIComponent(match[1]));
    } catch (error) {
      return null;
    }
  };

  const routeByRole = (targetRole) => {
    const map = {
      citizen: '/citizen',
      constable: '/constable',
      detective: '/detective',
      station_commander: '/station-commander',
      ipid: '/ipid',
    };
    const destination = map[targetRole] || '/login';
    window.location.href = destination;
  };

  const refreshUserBadge = () => {
    const user = getUser();
    const badge = document.getElementById('userBadge');
    if (badge && user) {
      badge.textContent = `${user.full_name || user.role || 'User'} • ${user.role}`;
    }
  };

  const fetchJson = async (url, options = {}) => {
    const headers = { ...(options.headers || {}) };
    const token = getStoredToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    if (options.body && typeof options.body !== 'string') {
      headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }

    const response = await fetch(url, {
      credentials: 'same-origin',
      ...options,
      headers,
      body: options.body && typeof options.body !== 'string' ? JSON.stringify(options.body) : options.body,
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || 'Request failed.');
    }
    return payload;
  };

  const buildStatusBadge = (status) => {
    const value = (status || 'UNKNOWN').toString().toUpperCase();
    if (value.includes('REGISTERED') || value.includes('VERIFIED') || value.includes('ACTIVE')) {
      return 'badge badge-verified';
    }
    if (value.includes('FROZEN') || value.includes('AWAITING') || value.includes('PENDING') || value.includes('REVIEW')) {
      return 'badge badge-warning';
    }
    return 'badge badge-muted';
  };

  const setEmptyState = (container, message) => {
    if (!container) {
      return;
    }
    container.innerHTML = `<div class="empty-state">${message}</div>`;
  };

  const hydrateCitizenDashboard = async () => {
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

      container.querySelectorAll('[data-case-link]').forEach((button) => {
        button.addEventListener('click', () => {
          window.location.href = button.dataset.caseLink;
        });
      });
    } catch (error) {
      setEmptyState(container, error.message || 'Unable to load dockets.');
    }
  };

  const getCitizenCaseReference = () => {
    const match = window.location.pathname.match(/^\/citizen\/dockets\/(?!new(?:\/)?$)([^/]+)/);
    return match ? match[1] : null;
  };

  const hydrateCitizenDetail = async () => {
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
  };

  const hydrateCitizenForm = () => {
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
  };

  const hydrateConstableDashboard = async () => {
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

      container.querySelectorAll('[data-case-link]').forEach((button) => {
        button.addEventListener('click', () => {
          window.location.href = button.dataset.caseLink;
        });
      });
    } catch (error) {
      setEmptyState(container, error.message || 'Unable to load constable queue.');
    }
  };

  const hydrateConstableReview = async () => {
    const caseMatch = window.location.pathname.match(/\/constable\/dockets\/([^/]+)/);
    if (!caseMatch) {
      return;
    }
    const caseReference = caseMatch[1];

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
          const interview = await fetchJson(`/api/v1/constable/dockets/${caseReference}/interview`, { method: 'POST' });
          window.location.href = `/constable/dockets/${caseReference}`;
        });
      }
    } catch (error) {
      const meta = document.getElementById('constableCaseMeta');
      if (meta) {
        meta.innerHTML = `<dt>Status</dt><dd>Unavailable</dd><dt>Message</dt><dd>${error.message}</dd>`;
      }
    }
  };

  const hydrateDetectiveDashboard = async () => {
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

      container.querySelectorAll('[data-case-link]').forEach((button) => {
        button.addEventListener('click', () => {
          window.location.href = button.dataset.caseLink;
        });
      });
    } catch (error) {
      setEmptyState(container, error.message || 'Unable to load detective queue.');
    }
  };

  const hydrateDetectiveCase = async () => {
    const caseMatch = window.location.pathname.match(/\/detective\/dockets\/([^/]+)/);
    if (!caseMatch) {
      return;
    }
    const caseReference = caseMatch[1];
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
          const investigation = await fetchJson(`/api/v1/detective/dockets/${caseReference}/investigation`, {
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
  };

  const hydrateStationCommanderDashboard = async () => {
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

      container.querySelectorAll('[data-case-link]').forEach((button) => {
        button.addEventListener('click', () => {
          window.location.href = button.dataset.caseLink;
        });
      });
    } catch (error) {
      setEmptyState(container, error.message || 'Unable to load station commander queue.');
    }
  };

  const hydrateStationCommanderDetail = async () => {
    const caseMatch = window.location.pathname.match(/\/station-commander\/dockets\/([^/]+)/);
    if (!caseMatch) {
      return;
    }
    const caseReference = caseMatch[1];
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
  };

  const hydrateIpidDashboard = async () => {
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

      container.querySelectorAll('[data-case-link]').forEach((button) => {
        button.addEventListener('click', () => {
          window.location.href = button.dataset.caseLink;
        });
      });
    } catch (error) {
      setEmptyState(container, error.message || 'Unable to load IPID review queue.');
    }
  };

  const hydrateIpidDetail = async () => {
    const match = window.location.pathname.match(/\/ipid\/escalations\/([^/]+)/);
    if (!match) {
      return;
    }
    const escalationId = match[1];
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
  };

  const hydrateActiveCases = async () => {
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
  };

  const hydrateEvidenceVault = async () => {
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
  };

  if (loginForm) {
    if (loginForm) {
      loginForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const idInput = document.getElementById('testId');
        const testId = idInput.value.trim();
        loginError?.classList.add('hidden');

        try {
          const payload = await fetchJson('/api/v1/auth/login', {
            method: 'POST',
            body: { test_id: testId },
          });

          setSession(payload.access_token, {
            full_name: payload.full_name,
            role: payload.role,
            test_id: payload.test_id,
          });

          routeByRole(payload.role);
        } catch (error) {
          loginError.textContent = error.message || 'Unable to sign in.';
          loginError.classList.remove('hidden');
        }
      });
    }
  }

  if (logoutButton) {
    logoutButton.addEventListener('click', () => {
      clearSession();
      window.location.href = '/login';
    });
  }

  if (document.body.dataset.role === 'citizen' && document.getElementById('citizenDockets')) {
    hydrateCitizenDashboard();
  }
  if (document.body.dataset.role === 'citizen' && getCitizenCaseReference()) {
    hydrateCitizenDetail();
  }
  if (document.body.dataset.role === 'citizen' && document.getElementById('submitCitizenDocket')) {
    hydrateCitizenForm();
  }

  if (document.body.dataset.role === 'constable' && document.getElementById('constableQueueState')) {
    hydrateConstableDashboard();
  }
  if (window.location.pathname.startsWith('/constable/dockets/')) {
    hydrateConstableReview();
  }

  if (document.body.dataset.role === 'detective' && document.getElementById('detectiveInvestigationList')) {
    hydrateDetectiveDashboard();
  }
  if (window.location.pathname.startsWith('/detective/dockets/')) {
    hydrateDetectiveCase();
  }

  if (document.body.dataset.role === 'station_commander' && document.getElementById('stationCommanderCaseList')) {
    hydrateStationCommanderDashboard();
  }
  if (window.location.pathname.startsWith('/station-commander/dockets/')) {
    hydrateStationCommanderDetail();
  }

  if (document.body.dataset.role === 'ipid' && document.getElementById('ipidQueueList')) {
    hydrateIpidDashboard();
  }
  if (window.location.pathname.startsWith('/ipid/escalations/')) {
    hydrateIpidDetail();
  }

  if (document.getElementById('activeCaseList')) {
    hydrateActiveCases();
  }
  if (document.getElementById('evidenceVaultList')) {
    hydrateEvidenceVault();
  }

  refreshUserBadge();

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

  const citizenNewDocketBtn = document.getElementById('newCitizenDocketBtn');
  if (citizenNewDocketBtn) {
    citizenNewDocketBtn.addEventListener('click', () => {
      window.location.href = '/citizen/dockets/new';
    });
  }

  const backToCitizenDashboard = document.getElementById('backToCitizenDashboard');
  if (backToCitizenDashboard) {
    backToCitizenDashboard.addEventListener('click', () => {
      window.location.href = '/citizen';
    });
  }
  if (window.location.pathname === '/login' && getStoredToken()) {
    const user = getUser();
    if (user && user.role) {
      routeByRole(user.role);
    }
  }
});
