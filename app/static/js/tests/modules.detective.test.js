import fs from 'node:fs';
import path from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../core/auth.js', () => ({
  getToken: vi.fn().mockReturnValue(null),
  getUser: vi.fn(),
}));

import { getDetectiveCaseReference, hydrateDetectiveCase, hydrateDetectiveDashboard, init } from '../modules/detective.js';

function setLocation(pathname) {
  delete window.location;
  window.location = { pathname, href: '', reload: vi.fn() };
}

describe('modules/detective.js (integration)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.body.dataset.role = 'detective';
  });

  it('getDetectiveCaseReference extracts the reference', () => {
    setLocation('/detective/dockets/CD-2');
    expect(getDetectiveCaseReference()).toBe('CD-2');
  });

  it('builds a review-only detective workspace before investigation starts', () => {
    const templatePath = path.join(process.cwd(), 'app', 'templates', 'detective_case_workspace.html');
    const html = fs.readFileSync(templatePath, 'utf8');

    expect(html).toContain('Detective Case Review');
    expect(html).toContain('Case / Docket Details');
    expect(html).toContain('Original Protected Citizen Submission');
    expect(html).toContain('Investigation has not started.');
    expect(html).toContain('Start Investigation');
    expect(html).toContain('id="openFindingModal" hidden');
    expect(html).toContain('id="openCompleteInvestigationModal" hidden');
    expect(html).not.toContain('Add Victim Statement');
  });

  it('exposes the six required investigative actions in the required display order with no generic dropdown', () => {
    const templatePath = path.join(process.cwd(), 'app', 'templates', 'detective_case_workspace.html');
    const html = fs.readFileSync(templatePath, 'utf8');

    expect(html).toContain('Investigation Order');
    expect(html).toContain('Required Investigative Actions');
    expect(html).toContain('Witness Contact');
    expect(html).toContain('Interview');
    expect(html).toContain('Evidence Review');
    expect(html).toContain('Evidence Collection');
    expect(html).toContain('Record Request');
    expect(html).toContain('Scene Review');
    expect(html).toContain('Complete Witness Contact');
    expect(html).toContain('Complete Interview');
    expect(html).toContain('Complete Evidence Review');
    expect(html).toContain('Complete Evidence Collection');
    expect(html).toContain('Complete Record Request');
    expect(html).toContain('Complete Scene Review');
    expect(html).not.toContain('id="investigativeActionType"');
    expect(html).not.toContain('Complete next required action');
  });

  it('exposes the final detective workflow controls for findings, final reasoning, and completion', () => {
    const templatePath = path.join(process.cwd(), 'app', 'templates', 'detective_case_workspace.html');
    const html = fs.readFileSync(templatePath, 'utf8');

    expect(html).toContain('id="detectiveFindingsList"');
    expect(html).toContain('id="detectiveNoteEntriesList"');
    expect(html).toContain('id="openFindingModal"');
    expect(html).toContain('id="findingModal"');
    expect(html).toContain('id="submitFindingModal"');
    expect(html).toContain('id="openCompleteInvestigationModal"');
    expect(html).toContain('id="completeInvestigationModal"');
    expect(html).toContain('id="submitCompleteInvestigationModal"');
    expect(html).toContain('Final Reasoning');
    expect(html).toContain('Complete Investigation');
  });

  it('requires selected investigation records and findings as checkbox references in the modal flow', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');

    const fetchMock = vi.fn((url, options = {}) => {
      if (url.endsWith('/actions')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([
            { action_id: 'ACT-000001', action_type: 'WITNESS_CONTACT', record_data: { witness_name: 'Jordan Smith' } },
            { action_id: 'ACT-000002', action_type: 'INTERVIEW', record_data: { person_name: 'Witness' } },
            { action_id: 'ACT-000003', action_type: 'EVIDENCE_REVIEW', record_data: { observation: 'Photo review shows broken lock.' } },
            { action_id: 'ACT-000004', action_type: 'EVIDENCE_COLLECTION', record_data: { description: 'Recovered lock fragment.' } },
            { action_id: 'ACT-000005', action_type: 'RECORD_REQUEST', record_data: { request_reference: 'REQ-17' } },
            { action_id: 'ACT-000006', action_type: 'SCENE_REVIEW', record_data: { location: 'Main St' } },
          ]),
        });
      }
      if (url.endsWith('/findings') && options.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ finding_id: 'FND-000001', action_ids: ['ACT-000001', 'ACT-000002'] }) });
      }
      if (url.endsWith('/findings')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([
            { finding_id: 'FND-000001', notes: 'Witness account corroborates the scene.', action_ids: ['ACT-000001', 'ACT-000002'] },
            { finding_id: 'FND-000002', notes: 'Conflicting claim not borne out.', action_ids: ['ACT-000003'] },
          ]),
        });
      }
      if (url.endsWith('/complete') && options.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'COMPLETED' }) });
      }
      if (url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          status: 'REGISTERED',
          timeline: [],
          evidence: [],
          statements: [],
          investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: '' },
        }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    document.getElementById('openFindingModal').click();
    const recordCheckboxes = Array.from(document.querySelectorAll('#findingActionReferences input[type="checkbox"]'));
    expect(recordCheckboxes.length).toBeGreaterThan(0);
    expect(document.getElementById('findingType')).toBeNull();
    const witnessCheckbox = recordCheckboxes.find((checkbox) => checkbox.value === 'ACT-000001');
    expect(witnessCheckbox).toBeTruthy();
    witnessCheckbox.checked = true;
    document.getElementById('findingNotes').value = 'Witness account corroborates the scene.';
    document.getElementById('submitFindingModal').click();

    await vi.waitFor(() => {
      const findingsCall = fetchMock.mock.calls.find(([url, options = {}]) => url.endsWith('/findings') && options.method === 'POST');
      expect(findingsCall).toBeTruthy();
      expect(JSON.parse(findingsCall[1].body)).toMatchObject({
        notes: 'Witness account corroborates the scene.',
        action_ids: ['ACT-000001'],
      });
      expect(JSON.parse(findingsCall[1].body)).not.toHaveProperty('finding_type');
    });

    document.getElementById('openCompleteInvestigationModal').click();
    const finalFindingCheckboxes = Array.from(document.querySelectorAll('#completeInvestigationFindingReferences input[type="checkbox"]'));
    expect(finalFindingCheckboxes.length).toBeGreaterThan(0);
    const findingCheckbox = finalFindingCheckboxes.find((checkbox) => checkbox.value === 'FND-000001');
    expect(findingCheckbox).toBeTruthy();
    findingCheckbox.checked = true;
    document.getElementById('completeInvestigationOutcome').value = 'VALID';
    document.getElementById('completeInvestigationNotes').value = 'The evidence remains consistent across the case.';
    document.getElementById('submitCompleteInvestigationModal').click();

    await vi.waitFor(() => {
      const completionCall = fetchMock.mock.calls.find(([url, options = {}]) => url.endsWith('/complete') && options.method === 'POST');
      expect(completionCall).toBeTruthy();
      expect(JSON.parse(completionCall[1].body)).toMatchObject({
        outcome: 'VALID',
        final_notes: 'The evidence remains consistent across the case.',
        finding_ids: ['FND-000001'],
      });
    });
  });

  it('renders the required investigative actions before findings and final reasoning in the detective workflow', () => {
    const templatePath = path.join(process.cwd(), 'app', 'templates', 'detective_case_workspace.html');
    const html = fs.readFileSync(templatePath, 'utf8');

    const actionIndex = html.indexOf('id="detectiveInvestigationActions"');
    const findingsIndex = html.indexOf('id="detectiveFindingsList"');
    const finalReasoningIndex = html.indexOf('Final Reasoning and Completion');

    expect(actionIndex).toBeGreaterThan(-1);
    expect(findingsIndex).toBeGreaterThan(-1);
    expect(finalReasoningIndex).toBeGreaterThan(-1);
    expect(actionIndex).toBeLessThan(findingsIndex);
    expect(findingsIndex).toBeLessThan(finalReasoningIndex);
  });

  it('renders the required interview, evidence review, collection and scene review fields in the browser-specific action form', () => {
    document.body.innerHTML = '<div id="actionModalFields"></div>';
    const container = document.getElementById('actionModalFields');
    const actionType = 'INTERVIEW';
    container.innerHTML = `
      <div class="action-form-header">Interview 1</div>
      <input type="file" data-action-field="recordings" multiple />
      <select data-action-field="role"></select>
      <textarea data-action-field="information_obtained"></textarea>
    `;

    expect(container.textContent).toContain('Interview 1');
    expect(container.querySelector('input[type="file"][data-action-field="recordings"]')).not.toBeNull();
    expect(container.querySelector('[data-action-field="role"]')).not.toBeNull();
    expect(container.querySelector('[data-action-field="information_obtained"]')).not.toBeNull();
  });

  it('uses a standard single-select for evidence review so a real evidence item can be chosen from the popup', async () => {
    document.body.innerHTML = `
      <div id="detectiveProcedureBoard"></div>
      <div id="detectiveWorkflowRail"></div>
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <div id="detectiveDeposition"></div>
      <div id="detectiveCaseEvidence"></div>
      <div id="detectiveStatementsList"></div>
      <ul id="detectiveCaseTimeline"></ul>
      <div id="detectiveFindingsList"></div>
      <div id="detectiveFlagsList"></div>
      <div id="detectiveRelatedCases"></div>
      <div id="detectiveNoteEntriesList"></div>
      <p id="detectiveInvestigationStateText"></p>
      <div id="detectiveInvestigationActions"></div>
      <div id="detectiveInvestigationOrder"></div>
      <button id="startInvestigation"></button>
      <div id="actionModal" class="reauth-modal hidden">
        <div id="actionModalContext"></div>
        <div id="actionModalFields"></div>
        <p id="actionModalError" class="inline-error hidden"></p>
        <button id="closeActionModal"></button>
        <button id="submitActionModal"></button>
      </div>
    `;
    setLocation('/detective/dockets/CD-1');

    const fetchMock = vi.fn((url, options) => {
      if (url.endsWith('/procedure-state')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            current_stage: 'INVESTIGATION_OPEN',
            next_permitted_action: 'Continue investigation',
            allowed: true,
            procedure_status: 'ACTIVE',
            requirements: [{ rule_code: 'PROCEDURE.INVESTIGATION_ACTIVE', satisfied: true, title: 'Investigation active', description: 'Investigation remains active.', required_action: 'continue_investigation' }],
            blocking_requirements: [],
          }),
        });
      }
      if (url.endsWith('/actions') && options && options.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ action_id: 'ACT-000001', action_type: 'EVIDENCE_REVIEW' }) });
      }
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (url.endsWith('/actions')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([]),
        });
      }

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          case_reference: 'CD-1',
          status: 'REGISTERED',
          location: 'Main St',
          timeline: [],
          evidence: [{ evidence_id: 'EVD-1', description: 'Witness photo', evidence_type: 'PHOTO' }],
          statements: [],
          investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: 'Active.' },
        }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();
    document.querySelector('[data-required-action-type="EVIDENCE_REVIEW"]').click();

    const evidenceSelect = document.querySelector('#actionModalFields [data-action-field="selected_evidence_ids"]');
    expect(evidenceSelect).not.toBeNull();
    expect(evidenceSelect.multiple).toBe(false);
    expect(Array.from(evidenceSelect.options).some((option) => option.value === 'EVD-1')).toBe(true);

    evidenceSelect.value = 'EVD-1';
    evidenceSelect.dispatchEvent(new Event('change', { bubbles: true }));
    expect(evidenceSelect.value).toBe('EVD-1');
  });

  it('uses numbered interview headers and real file inputs for evidence and scene action forms', async () => {
    document.body.innerHTML = `
      <div id="detectiveProcedureBoard"></div>
      <div id="detectiveWorkflowRail"></div>
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <div id="detectiveDeposition"></div>
      <div id="detectiveCaseEvidence"></div>
      <div id="detectiveStatementsList"></div>
      <ul id="detectiveCaseTimeline"></ul>
      <div id="detectiveFindingsList"></div>
      <div id="detectiveFlagsList"></div>
      <div id="detectiveRelatedCases"></div>
      <div id="detectiveNoteEntriesList"></div>
      <p id="detectiveInvestigationStateText"></p>
      <div id="detectiveInvestigationActions"></div>
      <div id="detectiveInvestigationOrder"></div>
      <button id="startInvestigation"></button>
      <div id="actionModal" class="reauth-modal hidden">
        <div id="actionModalContext"></div>
        <div id="actionModalFields"></div>
        <p id="actionModalError" class="inline-error hidden"></p>
        <button id="closeActionModal"></button>
        <button id="submitActionModal"></button>
      </div>
    `;
    setLocation('/detective/dockets/CD-1');

    const fetchMock = vi.fn((url, options) => {
      if (url.endsWith('/procedure-state')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            current_stage: 'INVESTIGATION_OPEN',
            next_permitted_action: 'Continue investigation',
            allowed: true,
            procedure_status: 'ACTIVE',
            requirements: [{ rule_code: 'PROCEDURE.INVESTIGATION_ACTIVE', satisfied: true, title: 'Investigation active', description: 'Investigation remains active.', required_action: 'continue_investigation' }],
            blocking_requirements: [],
          }),
        });
      }
      if (url.endsWith('/actions') && options && options.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ action_id: 'ACT-000001', action_type: 'INTERVIEW' }) });
      }
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (url.endsWith('/actions')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([
            { action_type: 'INTERVIEW', action_id: 'ACT-000001', record_data: { interview_number: 1 } },
          ]),
        });
      }

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          case_reference: 'CD-1',
          status: 'REGISTERED',
          location: 'Main St',
          description: 'Incident description',
          timeline: [],
          evidence: [{ evidence_id: 'EVD-1', description: 'Witness photo', evidence_type: 'PHOTO' }],
          statements: [],
          investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: 'Active.' },
        }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    const interviewButton = document.querySelector('[data-required-action-type="INTERVIEW"]');
    expect(interviewButton).not.toBeNull();
    interviewButton.click();

    const interviewFields = document.getElementById('actionModalFields');
    expect(interviewFields.textContent).toContain('Interview 2');
    expect(interviewFields.querySelector('input[type="file"][data-action-field="recordings"][multiple]')).not.toBeNull();

    const evidenceButton = document.querySelector('[data-required-action-type="EVIDENCE_REVIEW"]');
    expect(evidenceButton).not.toBeNull();
    evidenceButton.click();

    const evidenceSelect = document.querySelector('#actionModalFields [data-action-field="selected_evidence_ids"]');
    expect(evidenceSelect).not.toBeNull();
    expect(Array.from(evidenceSelect.options).some((option) => option.value === 'EVD-1')).toBe(true);

    const sceneButton = document.querySelector('[data-required-action-type="SCENE_REVIEW"]');
    expect(sceneButton).not.toBeNull();
    sceneButton.click();

    const sceneMaterialInput = document.querySelector('#actionModalFields [data-action-field="scene_material"]');
    expect(sceneMaterialInput).not.toBeNull();
    expect(sceneMaterialInput.type).toBe('file');
    expect(sceneMaterialInput.multiple).toBe(true);

    const evidenceCollectionButton = document.querySelector('[data-required-action-type="EVIDENCE_COLLECTION"]');
    expect(evidenceCollectionButton).not.toBeNull();
    evidenceCollectionButton.click();

    const evidenceTypeSelect = document.querySelector('#actionModalFields [data-action-field="evidence_type"]');
    expect(evidenceTypeSelect).not.toBeNull();
    expect(evidenceTypeSelect.tagName).toBe('SELECT');
    expect(Array.from(evidenceTypeSelect.options).map((option) => option.value)).toContain('PHOTO');
    expect(Array.from(evidenceTypeSelect.options).map((option) => option.value)).toContain('VIDEO');
    expect(Array.from(evidenceTypeSelect.options).map((option) => option.value)).toContain('DOCUMENT');
    expect(Array.from(evidenceTypeSelect.options).map((option) => option.value)).toContain('AUDIO');
    expect(Array.from(evidenceTypeSelect.options).map((option) => option.value)).toContain('WITNESS_STATEMENT');
    expect(Array.from(evidenceTypeSelect.options).map((option) => option.value)).toContain('OTHER');
  });

  it('allows adding multiple evidence collection items from the detective action modal', async () => {
    document.body.innerHTML = `
      <div id="detectiveProcedureBoard"></div>
      <div id="detectiveWorkflowRail"></div>
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <div id="detectiveDeposition"></div>
      <div id="detectiveCaseEvidence"></div>
      <div id="detectiveStatementsList"></div>
      <ul id="detectiveCaseTimeline"></ul>
      <div id="detectiveFindingsList"></div>
      <div id="detectiveFlagsList"></div>
      <div id="detectiveRelatedCases"></div>
      <div id="detectiveNoteEntriesList"></div>
      <p id="detectiveInvestigationStateText"></p>
      <div id="detectiveInvestigationActions"></div>
      <div id="detectiveInvestigationOrder"></div>
      <button id="startInvestigation"></button>
      <div id="actionModal" class="reauth-modal hidden">
        <div id="actionModalContext"></div>
        <div id="actionModalFields"></div>
        <p id="actionModalError" class="inline-error hidden"></p>
        <button id="closeActionModal"></button>
        <button id="submitActionModal"></button>
      </div>
    `;
    setLocation('/detective/dockets/CD-1');

    const fetchMock = vi.fn((url, options) => {
      if (url.endsWith('/procedure-state')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            current_stage: 'INVESTIGATION_OPEN',
            next_permitted_action: 'Continue investigation',
            allowed: true,
            procedure_status: 'ACTIVE',
            requirements: [{ rule_code: 'PROCEDURE.INVESTIGATION_ACTIVE', satisfied: true, title: 'Investigation active', description: 'Investigation remains active.', required_action: 'continue_investigation' }],
            blocking_requirements: [],
          }),
        });
      }
      if (url.endsWith('/actions') && options && options.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ action_id: 'ACT-000001', action_type: 'EVIDENCE_COLLECTION' }) });
      }
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (url.endsWith('/actions')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([]),
        });
      }

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          case_reference: 'CD-1',
          status: 'REGISTERED',
          location: 'Main St',
          timeline: [],
          evidence: [{ evidence_id: 'EVD-1', description: 'Witness photo', evidence_type: 'PHOTO' }],
          statements: [],
          investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: 'Active.' },
        }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    const evidenceCollectionButton = document.querySelector('[data-required-action-type="EVIDENCE_COLLECTION"]');
    expect(evidenceCollectionButton).not.toBeNull();
    evidenceCollectionButton.click();

    const addButton = document.querySelector('[data-add-evidence-collection-item]');
    expect(addButton).not.toBeNull();

    expect(document.querySelectorAll('[data-evidence-collection-item]').length).toBe(1);
    addButton.click();
    expect(document.querySelectorAll('[data-evidence-collection-item]').length).toBe(2);
  });

  it('allows repeat evidence review and collection records without locking the modal into read-only mode', async () => {
    document.body.innerHTML = `
      <div id="detectiveProcedureBoard"></div>
      <div id="detectiveWorkflowRail"></div>
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <div id="detectiveDeposition"></div>
      <div id="detectiveCaseEvidence"></div>
      <div id="detectiveStatementsList"></div>
      <ul id="detectiveCaseTimeline"></ul>
      <div id="detectiveFindingsList"></div>
      <div id="detectiveFlagsList"></div>
      <div id="detectiveRelatedCases"></div>
      <div id="detectiveNoteEntriesList"></div>
      <p id="detectiveInvestigationStateText"></p>
      <div id="detectiveInvestigationActions"></div>
      <div id="detectiveInvestigationOrder"></div>
      <button id="startInvestigation"></button>
      <div id="actionModal" class="reauth-modal hidden">
        <div id="actionModalContext"></div>
        <div id="actionModalFields"></div>
        <p id="actionModalError" class="inline-error hidden"></p>
        <button id="closeActionModal"></button>
        <button id="submitActionModal"></button>
      </div>
    `;
    setLocation('/detective/dockets/CD-1');

    const fetchMock = vi.fn((url, options) => {
      if (url.endsWith('/procedure-state')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            current_stage: 'INVESTIGATION_OPEN',
            next_permitted_action: 'Continue investigation',
            allowed: true,
            procedure_status: 'ACTIVE',
            requirements: [{ rule_code: 'PROCEDURE.INVESTIGATION_ACTIVE', satisfied: true, title: 'Investigation active', description: 'Investigation remains active.', required_action: 'continue_investigation' }],
            blocking_requirements: [],
          }),
        });
      }
      if (url.endsWith('/actions') && options && options.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ action_id: 'ACT-000003', action_type: 'EVIDENCE_REVIEW' }) });
      }
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (url.endsWith('/actions')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([
            { action_id: 'ACT-000001', action_type: 'EVIDENCE_REVIEW', record_data: { selected_evidence_ids: ['EVD-1'], observation: 'Seen', interpretation: 'Useful', unknown_limitation: 'None', consistency: 'SUPPORTS_EXISTING_INFORMATION' } },
            { action_id: 'ACT-000002', action_type: 'EVIDENCE_COLLECTION', record_data: { evidence_type: 'PHOTO', description: 'Scene still', source: 'Witness', date_time_obtained: '2026-09-26T12:00:00Z', provider: 'Witness', collection_method: 'PHOTOGRAPH_VIDEO', result: 'OBTAINED' } },
          ]),
        });
      }

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          case_reference: 'CD-1',
          status: 'REGISTERED',
          location: 'Main St',
          timeline: [],
          evidence: [{ evidence_id: 'EVD-1', description: 'Witness photo', evidence_type: 'PHOTO' }],
          statements: [],
          investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: 'Active.' },
        }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    const reviewButton = document.querySelector('[data-required-action-type="EVIDENCE_REVIEW"]');
    expect(reviewButton).not.toBeNull();
    reviewButton.click();
    expect(document.getElementById('submitActionModal').hidden).toBe(false);
    expect(document.getElementById('actionModalFields').textContent).not.toContain('Related evidence');

    const collectionButton = document.querySelector('[data-required-action-type="EVIDENCE_COLLECTION"]');
    expect(collectionButton).not.toBeNull();
    collectionButton.click();
    expect(document.getElementById('submitActionModal').hidden).toBe(false);
  });

  it('opens and submits the required action modal from the detective action card for an active investigation', async () => {
    document.body.innerHTML = `
      <div id="detectiveProcedureBoard"></div>
      <div id="detectiveWorkflowRail"></div>
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <div id="detectiveDeposition"></div>
      <div id="detectiveCaseEvidence"></div>
      <div id="detectiveStatementsList"></div>
      <ul id="detectiveCaseTimeline"></ul>
      <div id="detectiveFindingsList"></div>
      <div id="detectiveFlagsList"></div>
      <div id="detectiveRelatedCases"></div>
      <div id="detectiveNoteEntriesList"></div>
      <p id="detectiveInvestigationStateText"></p>
      <div id="detectiveInvestigationActions"></div>
      <div id="detectiveInvestigationOrder"></div>
      <button id="startInvestigation"></button>
      <div id="actionModal" class="reauth-modal hidden">
        <div id="actionModalContext"></div>
        <div id="actionModalFields"></div>
        <p id="actionModalError" class="inline-error hidden"></p>
        <button id="closeActionModal"></button>
        <button id="submitActionModal"></button>
      </div>
    `;
    setLocation('/detective/dockets/CD-1');

    const fetchMock = vi.fn((url, options) => {
      if (url.endsWith('/procedure-state')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            current_stage: 'INVESTIGATION_OPEN',
            next_permitted_action: 'Complete investigation',
            allowed: true,
            procedure_status: 'ACTIVE',
            requirements: [{ rule_code: 'PROCEDURE.INVESTIGATION_ACTIVE', satisfied: true, title: 'Investigation active', description: 'Investigation remains active.', required_action: 'complete_investigation' }],
            blocking_requirements: [],
          }),
        });
      }
      if (url.endsWith('/actions') && options && options.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ action_id: 'ACT-000001', action_type: 'INTERVIEW' }),
        });
      }
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (url.endsWith('/actions')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([]),
        });
      }

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          case_reference: 'CD-1',
          status: 'REGISTERED',
          location: 'Main St',
          timeline: [],
          evidence: [{ evidence_id: 'EVD-1', description: 'Witness photo' }],
          statements: [],
          investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: 'Active.' },
        }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();
    const interviewActionCard = document.querySelector('[data-required-action-type="INTERVIEW"]');
    expect(interviewActionCard).not.toBeNull();
    interviewActionCard.click();
    expect(document.getElementById('actionModal').classList.contains('hidden')).toBe(false);

    document.querySelector('[data-action-field="person_name"]').value = 'Jane Doe';
    document.querySelector('[data-action-field="role"]').value = 'WITNESS';
    document.querySelector('[data-action-field="interview_date"]').value = '2026-09-27';
    document.querySelector('[data-action-field="interview_time"]').value = '10:15';
    document.querySelector('[data-action-field="location_method"]').value = 'Interview at the witness residence';
    document.querySelector('[data-action-field="interview_type"]').value = 'FOLLOW_UP';
    const interviewRecordingInput = document.querySelector('[data-action-field="recordings"]');
    Object.defineProperty(interviewRecordingInput, 'files', {
      value: [new File(['audio'], 'rec-001.mp3', { type: 'audio/mpeg' })],
      configurable: true,
    });
    document.querySelector('[data-action-field="information_obtained"]').value = 'Witness confirmed the vehicle seen leaving the alley.';
    document.querySelector('[data-action-field="contradictions"]').value = 'NONE_IDENTIFIED';
    document.querySelector('[data-action-field="follow_up_lead"]').value = 'false';
    document.querySelector('[data-action-field="outcome"]').value = 'INFORMATION_OBTAINED';

    document.getElementById('submitActionModal').click();

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/detective/investigations/INV-1/actions',
        expect.objectContaining({ method: 'POST' })
      );
    });
  });

  it('hydrateDetectiveDashboard filters to REGISTERED cases only', async () => {
    document.body.innerHTML = '<div id="detectiveInvestigationList"></div>';
    setLocation('/detective');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve([
            { case_reference: 'CD-1', status: 'REGISTERED', location: 'Main St' },
            { case_reference: 'CD-2', status: 'DRAFT', location: 'Elm St' },
          ]),
      })
    );

    await hydrateDetectiveDashboard();

    const container = document.getElementById('detectiveInvestigationList');
    expect(container.textContent).toContain('CD-1');
    expect(container.textContent).not.toContain('CD-2');
  });

  it('excludes completed investigations from the detective active queue', async () => {
    document.body.innerHTML = '<div id="detectiveInvestigationList"></div>';
    setLocation('/detective');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve([
            { case_reference: 'CD-1', status: 'REGISTERED', investigation_status: 'COMPLETED', location: 'Main St' },
            { case_reference: 'CD-2', status: 'REGISTERED', investigation_status: 'IN_PROGRESS', location: 'Elm St' },
            { case_reference: 'CD-3', status: 'DRAFT', location: 'Oak St' },
          ]),
      })
    );

    await hydrateDetectiveDashboard();

    const container = document.getElementById('detectiveInvestigationList');
    expect(container.textContent).toContain('CD-2');
    expect(container.textContent).not.toContain('CD-1');
    expect(container.textContent).not.toContain('CD-3');
  });

  it('renders a state-derived workflow rail for the detective stages and distinguishes findings from final reasoning', async () => {
    document.body.innerHTML = `
      <div id="detectiveWorkflowRail"></div>
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <div id="detectiveDeposition"></div>
      <div id="detectiveStatementBox"></div>
      <ul id="detectiveCaseTimeline"></ul>
      <ul id="detectiveCaseEvidence"></ul>
      <textarea id="investigationNotes"></textarea>
      <button id="saveInvestigationNote"></button>
      <p id="investigationNotesError" class="hidden"></p>
      <div id="detectiveFindingsList"></div>
      <div id="detectiveFlagsList"></div>
      <div id="detectiveRelatedCases"></div>
      <button id="openFindingModal"></button>
      <button id="startInvestigation"></button>
    `;
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ finding_type: 'VALID', notes: 'Consistent with evidence.' }]) });
      }
      if (url.endsWith('/flags') || url.endsWith('/related')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            location: 'Main St',
            status: 'REGISTERED',
            timeline: [],
            evidence: [{ description: 'Photo of the scene' }],
            statements: [{ statement_text: 'Victim statement.' }],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: 'Initial notes.' },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    const rail = document.getElementById('detectiveWorkflowRail');
    expect(rail.textContent).toContain('Case Review');
    expect(rail.textContent).toContain('Statements & Evidence');
    expect(rail.textContent).toContain('Investigation');
    expect(rail.textContent).toContain('Findings');
    expect(rail.textContent).toContain('Final Reasoning');
    expect(rail.textContent).toContain('Completion');
    expect(rail.textContent).toContain('Investigation Finding');
    expect(rail.querySelectorAll('.workflow-step.current').length).toBeGreaterThan(0);
  });

  it('hydrateDetectiveCase renders evidence from the citizen_evidence payload returned by the docket API', async () => {
    document.body.innerHTML = `
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <div id="detectiveDeposition"></div>
      <div id="detectiveStatementBox"></div>
      <table><tbody id="detectiveCaseEvidence"></tbody></table>
      <textarea id="investigationNotes"></textarea>
      <button id="saveInvestigationNote"></button>
      <p id="investigationNotesError" class="hidden"></p>
      <div id="detectiveFindingsList"></div>
      <div id="detectiveFlagsList"></div>
      <div id="detectiveRelatedCases"></div>
      <div id="detectiveNoteEntriesList"></div>
      <button id="openFindingModal"></button>
      <button id="startInvestigation"></button>
    `;
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            location: 'Main St',
            status: 'REGISTERED',
            timeline: [],
            citizen_evidence: [{ description: 'Witness photo', evidence_type: 'PHOTO', source: 'citizen_submission', status: 'SUBMITTED' }],
            statements: [],
            investigation: null,
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    expect(document.getElementById('detectiveCaseEvidence').textContent).toContain('Witness photo');
    expect(document.getElementById('detectiveCaseEvidence').textContent).not.toContain('No evidence has been submitted yet.');
  });

  it('hydrateDetectiveCase renders detail and wires Start Investigation when no investigation exists yet', async () => {
    document.body.innerHTML = `
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <div id="detectiveDeposition"></div>
      <div id="detectiveStatementBox"></div>
      <ul id="detectiveCaseTimeline"></ul>
      <ul id="detectiveCaseEvidence"></ul>
      <textarea id="investigationNotes"></textarea>
      <button id="saveInvestigationNote"></button>
      <p id="investigationNotesError" class="hidden"></p>
      <div id="detectiveFindingsList"></div>
      <button id="openFindingModal"></button>
      <button id="startInvestigation"></button>
    `;
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/procedure-state')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            case_reference: 'CD-1',
            current_stage: 'INVESTIGATION_OPEN',
            next_permitted_action: 'Start investigation',
            allowed: true,
            procedure_status: 'ACTIVE',
            requirements: [],
            blocking_requirements: [],
          }),
        });
      }
      if (url.endsWith('/investigation')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ investigation_id: 'INV-1' }) });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ location: 'Main St', status: 'REGISTERED', timeline: [], evidence: [], statements: [], investigation: null }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();
    expect(document.getElementById('detectiveCaseMeta').textContent).toContain('Main St');
    expect(document.getElementById('detectiveCaseMeta').textContent).toContain('Not yet assigned');
    expect(document.getElementById('openFindingModal').disabled).toBe(true);
    expect(document.getElementById('startInvestigation').hidden).toBe(false);

    document.getElementById('startInvestigation').click();
    await vi.waitFor(() => expect(window.location.href).toBe('/detective/dockets/CD-1'));
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/detective/dockets/CD-1/investigation',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('hydrateDetectiveCase disables Start Investigation and loads findings when an investigation already exists', async () => {
    document.body.innerHTML = `
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <div id="detectiveDeposition"></div>
      <div id="detectiveStatementBox"></div>
      <ul id="detectiveCaseTimeline"></ul>
      <ul id="detectiveCaseEvidence"></ul>
      <textarea id="investigationNotes"></textarea>
      <button id="saveInvestigationNote"></button>
      <p id="investigationNotesError" class="hidden"></p>
      <div id="detectiveFindingsList"></div>
      <div id="detectiveFlagsList"></div>
      <div id="detectiveRelatedCases"></div>
      <button id="openFindingModal"></button>
      <button id="startInvestigation"></button>
    `;
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ finding_type: 'VALID', notes: 'Consistent with evidence.' }]) });
      }
      if (url.endsWith('/flags')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ category: 'INSUFFICIENT_INFORMATION', status: 'OPEN', notes: 'Missing detail from constable.' }]),
        });
      }
      if (url.endsWith('/related')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ relationship_type: 'RELATED_CASE', source_case_reference: 'CD-1', related_case_reference: 'CD-2' }]),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            location: 'Main St',
            status: 'REGISTERED',
            timeline: [],
            evidence: [],
            statements: [],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'OPEN', notes: 'Initial notes.' },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    expect(document.getElementById('detectiveCaseMeta').textContent).toContain('DET-1');
    expect(document.getElementById('investigationNotes').value).toBe('Initial notes.');
    expect(document.getElementById('startInvestigation').disabled).toBe(true);
    expect(document.getElementById('openFindingModal').disabled).toBe(true);
    expect(document.getElementById('detectiveFindingsList').textContent).toContain('Consistent with evidence.');
    await vi.waitFor(() => expect(document.getElementById('detectiveFlagsList').textContent).toContain('Missing detail from constable.'));
    expect(document.getElementById('detectiveRelatedCases').textContent).toContain('CD-2');
  });

  it('shows placeholder copy for flags/related when no investigation has started yet, without fetching them', async () => {
    document.body.innerHTML = `
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <div id="detectiveDeposition"></div>
      <div id="detectiveStatementBox"></div>
      <ul id="detectiveCaseTimeline"></ul>
      <ul id="detectiveCaseEvidence"></ul>
      <textarea id="investigationNotes"></textarea>
      <button id="saveInvestigationNote"></button>
      <p id="investigationNotesError" class="hidden"></p>
      <div id="detectiveFindingsList"></div>
      <div id="detectiveFlagsList">Start the investigation to review constable-raised flags.</div>
      <div id="detectiveRelatedCases">Start the investigation to review related case links.</div>
      <button id="openFindingModal"></button>
      <button id="startInvestigation"></button>
    `;
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.includes('/flags') || url.includes('/related')) {
        throw new Error(`unexpected pre-investigation fetch to ${url}`);
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ location: 'Main St', status: 'REGISTERED', timeline: [], evidence: [], statements: [], investigation: null }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    expect(document.getElementById('detectiveFlagsList').textContent).toContain('Start the investigation');
    expect(document.getElementById('detectiveRelatedCases').textContent).toContain('Start the investigation');
  });

  function activeInvestigationMarkup() {
    return `
      <span id="detectiveStatusBadge"></span>
      <span id="detectiveFreezeBadge" class="hidden"></span>
      <div id="detectiveFrozenNotice" class="hidden"><p id="detectiveFrozenReason"></p></div>
      <div id="detectiveDocketContent">
        <dl id="detectiveCaseMeta"></dl>
        <div id="detectiveDeposition"></div>
        <div id="detectiveStatementsList"></div>
        <button id="openStatementModal"></button>
        <ul id="detectiveCaseTimeline"></ul>
        <table><tbody id="detectiveCaseEvidence"></tbody></table>
        <textarea id="investigationNotes"></textarea>
        <button id="saveInvestigationNote"></button>
        <p id="investigationNotesError" class="hidden"></p>
        <div id="detectiveFindingsList"></div>
        <div id="detectiveFlagsList"></div>
        <div id="detectiveRelatedCases"></div>
        <div id="detectiveNoteEntriesList"></div>
        <button id="openFindingModal"></button>
        <button id="openCompleteInvestigationModal"></button>
        <button id="openNoteEntryModal"></button>
        <button id="startInvestigation"></button>
      </div>
      <div id="toastContainer"></div>
      <div class="reauth-modal hidden" id="statementModal">
        <textarea id="statementText"></textarea>
        <p id="statementModalError" class="hidden"></p>
        <button id="closeStatementModal"></button>
        <button id="submitStatementModal"></button>
      </div>
      <div class="reauth-modal hidden" id="findingModal">
        <div id="findingActionReferences"></div>
        <textarea id="findingNotes"></textarea>
        <p id="findingModalError" class="hidden"></p>
        <button id="closeFindingModal"></button>
        <button id="submitFindingModal"></button>
      </div>
      <div class="reauth-modal hidden" id="completeInvestigationModal">
        <select id="completeInvestigationOutcome">
          <option value="VALID">Valid</option>
          <option value="INVALID">Invalid</option>
          <option value="REVIEW_REQUIRED">Review Required</option>
        </select>
        <div id="completeInvestigationFindingReferences"></div>
        <textarea id="completeInvestigationNotes"></textarea>
        <p id="completeInvestigationModalError" class="hidden"></p>
        <button id="closeCompleteInvestigationModal"></button>
        <button id="submitCompleteInvestigationModal"></button>
      </div>
      <div class="reauth-modal hidden" id="noteEntryModal">
        <select id="noteEntryEvidence"></select>
        <textarea id="noteEntryText"></textarea>
        <p id="noteEntryModalError" class="hidden"></p>
        <button id="closeNoteEntryModal"></button>
        <button id="submitNoteEntryModal"></button>
      </div>
    `;
  }

  it('the Complete Investigation modal posts outcome + final notes and reloads', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/actions')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([
            { action_type: 'WITNESS_CONTACT' },
            { action_type: 'INTERVIEW' },
            { action_type: 'EVIDENCE_REVIEW' },
            { action_type: 'EVIDENCE_COLLECTION' },
            { action_type: 'RECORD_REQUEST' },
            { action_type: 'SCENE_REVIEW' },
          ]),
        });
      }
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ finding_type: 'VALID', notes: 'Evidence supports the case.' }]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            location: 'Main St',
            status: 'REGISTERED',
            timeline: [],
            evidence: [],
            statements: [],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: 'Working notes.' },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();
    expect(document.getElementById('openCompleteInvestigationModal').disabled).toBe(false);

    document.getElementById('openCompleteInvestigationModal').click();
    expect(document.getElementById('completeInvestigationModal').classList.contains('hidden')).toBe(false);

    const findingSelect = document.getElementById('completeInvestigationFindingReferences');
    const findingOption = document.createElement('option');
    findingOption.value = 'FND-000001';
    findingOption.textContent = 'VALID';
    findingOption.selected = true;
    findingSelect.appendChild(findingOption);

    document.getElementById('completeInvestigationOutcome').value = 'VALID';
    document.getElementById('completeInvestigationNotes').value = 'Evidence and testimony are conclusive.';
    document.getElementById('submitCompleteInvestigationModal').click();

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/detective/investigations/INV-1/complete',
        expect.objectContaining({ method: 'POST' })
      )
    );
    const [, options] = fetchMock.mock.calls.find(([url]) => url.endsWith('/complete'));
    expect(JSON.parse(options.body)).toEqual({ outcome: 'VALID', final_notes: 'Evidence and testimony are conclusive.', finding_ids: ['FND-000001'] });
    await vi.waitFor(() => expect(sessionStorage.getItem('pdasFlashMessage')).toContain('Investigation completed'));
  });

  it('the Complete Investigation modal requires final reasoning before submitting', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'REGISTERED',
            timeline: [],
            evidence: [],
            statements: [],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: '' },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();
    const findingSelect = document.getElementById('completeInvestigationFindingReferences');
    const pendingFindingOption = document.createElement('option');
    pendingFindingOption.value = 'FND-000001';
    pendingFindingOption.textContent = 'VALID';
    pendingFindingOption.selected = true;
    findingSelect.appendChild(pendingFindingOption);

    document.getElementById('openCompleteInvestigationModal').click();
    document.getElementById('submitCompleteInvestigationModal').click();

    expect(document.getElementById('completeInvestigationModalError').classList.contains('hidden')).toBe(false);
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining('/complete'), expect.anything());
  });

  it('adds a note entry optionally linked to an evidence item, and lists it grouped by evidence', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    let noteAdded = false;
    const fetchMock = vi.fn((url, options = {}) => {
      if (url.endsWith('/note-entries') && options.method === 'POST') {
        noteAdded = true;
        expect(JSON.parse(options.body)).toEqual({ note_text: 'Zoomed crop shows forced entry.', evidence_reference: '1' });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ note_id: 'NOTE-1' }) });
      }
      if (url.endsWith('/note-entries')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve(
              noteAdded ? [{ note_id: 'NOTE-1', evidence_reference: '1', note_text: 'Zoomed crop shows forced entry.', created_at: '2026-01-01' }] : []
            ),
        });
      }
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'REGISTERED',
            timeline: [],
            evidence: [{ evidence_id: 1, description: 'Broken window photo' }],
            statements: [],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: '' },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();
    expect(document.getElementById('detectiveNoteEntriesList').textContent).toContain('No notes have been recorded');

    document.getElementById('openNoteEntryModal').click();
    expect(document.getElementById('noteEntryEvidence').options.length).toBeGreaterThan(1);
    document.getElementById('noteEntryEvidence').value = '1';
    document.getElementById('noteEntryText').value = 'Zoomed crop shows forced entry.';
    document.getElementById('submitNoteEntryModal').click();

    await vi.waitFor(() => expect(document.getElementById('detectiveNoteEntriesList').textContent).toContain('Broken window photo'));
    expect(document.getElementById('toastContainer').textContent).toContain('Note recorded');
  });

  it('shows the freeze badge with a reason when the docket is frozen, and hides it otherwise', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'REGISTERED',
            timeline: [],
            evidence: [],
            statements: [],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: '' },
            is_frozen: true,
            freeze_reason: 'IPID took custody of the docket while reviewing escalation ESC-1',
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    const badge = document.getElementById('detectiveFreezeBadge');
    expect(badge.classList.contains('hidden')).toBe(false);
    expect(badge.textContent).toContain('IPID took custody');
  });

  it('marks a completed investigation as complete in the workflow and renders the persisted final reasoning summary', async () => {
    document.body.innerHTML = `
      <div id="detectiveWorkflowRail"></div>
      <div id="detectiveProcedureBoard"></div>
      <dl id="detectiveCaseMeta"></dl>
      <span id="detectiveStatusBadge"></span>
      <span id="detectiveFreezeBadge" class="hidden"></span>
      <div id="detectiveFrozenNotice" class="hidden"><p id="detectiveFrozenReason"></p></div>
      <div id="detectiveDocketContent">
        <div id="detectiveDeposition"></div>
        <div id="detectiveStatementsList"></div>
        <ul id="detectiveCaseTimeline"></ul>
        <table><tbody id="detectiveCaseEvidence"></tbody></table>
        <textarea id="investigationNotes"></textarea>
        <button id="saveInvestigationNote"></button>
        <div id="detectiveFindingsList"></div>
        <div id="detectiveFlagsList"></div>
        <div id="detectiveRelatedCases"></div>
        <div id="detectiveNoteEntriesList"></div>
        <button id="openFindingModal"></button>
        <button id="openCompleteInvestigationModal"></button>
        <button id="openNoteEntryModal"></button>
        <button id="startInvestigation"></button>
        <p id="detectiveInvestigationStateText"></p>
        <div id="detectiveInvestigationActions"></div>
      </div>
      <div id="toastContainer"></div>
    `;
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url, options = {}) => {
      if (url.endsWith('/procedure-state')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ current_stage: 'INVESTIGATION_COMPLETE', procedure_status: 'COMPLETED', allowed: true, next_permitted_action: 'Investigation completed', requirements: [], blocking_requirements: [] }) });
      }
      if (url.endsWith('/findings')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ finding_id: 'FND-000001', notes: 'Consistent with evidence.', action_ids: [] }]) });
      }
      if (url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (url.endsWith('/flags') || url.endsWith('/related')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'REGISTERED',
            timeline: [],
            evidence: [],
            statements: [],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'COMPLETED', notes: 'Working notes.', outcome: 'VALID', final_notes: 'The evidence remains consistent across the case.', completed_at: '2026-01-02T12:00:00Z', referenced_finding_ids: ['FND-000001'] },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    const workflowSteps = Array.from(document.getElementById('detectiveWorkflowRail').querySelectorAll('.workflow-step'));
    expect(workflowSteps[6].classList.contains('complete')).toBe(true);
    expect(workflowSteps[6].textContent).toContain('Completion');
    expect(document.getElementById('detectiveInvestigationStateText').textContent).toContain('complete');
    expect(document.getElementById('detectiveNoteEntriesList').textContent).toContain('The evidence remains consistent across the case.');
    expect(document.getElementById('openCompleteInvestigationModal').disabled).toBe(true);
  });

  it('shows a completed investigation read-only: findings/notes still load, but the write controls stay disabled', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ finding_type: 'VALID', notes: 'Consistent with evidence.' }]) });
      }
      if (url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ note_id: 'NOTE-1', evidence_reference: null, note_text: 'Witness confirmed.', created_at: '2026-01-01' }]) });
      }
      if (url.endsWith('/flags') || url.endsWith('/related')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'REGISTERED',
            timeline: [],
            evidence: [],
            statements: [],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'COMPLETED', notes: 'Working notes.', outcome: 'VALID' },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    expect(document.getElementById('detectiveFindingsList').textContent).toContain('Consistent with evidence.');
    expect(document.getElementById('detectiveNoteEntriesList').textContent).toContain('Witness confirmed.');
    expect(document.getElementById('startInvestigation').textContent).toContain('COMPLETED');
    expect(document.getElementById('openFindingModal').disabled).toBe(true);
    expect(document.getElementById('openCompleteInvestigationModal').disabled).toBe(true);
    expect(document.getElementById('openNoteEntryModal').disabled).toBe(true);
    expect(document.getElementById('saveInvestigationNote').disabled).toBe(true);
  });

  it('adds a victim statement and shows it alongside the existing ones', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    let statementAdded = false;
    const fetchMock = vi.fn((url, options = {}) => {
      if (url.endsWith('/statements') && options.method === 'POST') {
        statementAdded = true;
        expect(JSON.parse(options.body)).toEqual({ statement_text: 'Witness confirms seeing the suspect flee northbound.' });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ statement_id: 2, recorded_by_role: 'detective' }) });
      }
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'REGISTERED',
            timeline: [],
            evidence: [],
            statements: statementAdded
              ? [
                  { statement_text: 'Someone broke my window.', created_at: '2026-01-01' },
                  { statement_text: 'Witness confirms seeing the suspect flee northbound.', recorded_by: 'DET-1', recorded_by_role: 'detective' },
                ]
              : [{ statement_text: 'Someone broke my window.', created_at: '2026-01-01' }],
            investigation: { investigation_id: 'INV-1', detective_id: 'DET-1', status: 'IN_PROGRESS', notes: '' },
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();
    expect(document.getElementById('detectiveStatementsList').textContent).toContain('Someone broke my window.');

    document.getElementById('openStatementModal').click();
    document.getElementById('statementText').value = 'Witness confirms seeing the suspect flee northbound.';
    document.getElementById('submitStatementModal').click();

    await vi.waitFor(() => expect(document.getElementById('detectiveStatementsList').textContent).toContain('Witness confirms seeing the suspect flee northbound.'));
    expect(document.getElementById('detectiveStatementsList').textContent).toContain('detective');
    expect(document.getElementById('toastContainer').textContent).toContain('Statement recorded');
  });

  it('shows the "Case Frozen" notice and withholds case content while the docket is frozen', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/findings') || url.endsWith('/flags') || url.endsWith('/related') || url.endsWith('/note-entries')) {
        throw new Error(`unexpected fetch to ${url} for a frozen docket`);
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            case_reference: 'CD-1',
            status: 'REGISTERED',
            is_frozen: true,
            freeze_status: 'FROZEN',
            freeze_reason: 'IPID uphold decision for escalation ESC-1',
          }),
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    expect(document.getElementById('detectiveFrozenNotice').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('detectiveFrozenReason').textContent).toContain('IPID uphold decision');
    expect(document.getElementById('detectiveDocketContent').classList.contains('hidden')).toBe(true);
    expect(document.getElementById('detectiveCaseMeta').textContent).toBe('');
    expect(document.getElementById('detectiveFreezeBadge').classList.contains('hidden')).toBe(false);
  });

  it('shows a restricted-access state and halts dependent loading when the detective has no active assignment', async () => {
    document.body.innerHTML = activeInvestigationMarkup();
    setLocation('/detective/dockets/CD-1');
    const fetchMock = vi.fn((url) => {
      if (url.endsWith('/dockets/CD-1')) {
        return Promise.resolve({
          ok: false,
          json: () => Promise.resolve({ error: 'Detective access requires an active assignment to this docket.' }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
    });
    vi.stubGlobal('fetch', fetchMock);

    await hydrateDetectiveCase();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(document.getElementById('detectiveDocketContent').textContent).toContain('Detective access requires an active assignment to this docket.');
    expect(document.getElementById('detectiveStatementsList').textContent).toContain('Detective access requires an active assignment to this docket.');
    expect(document.getElementById('detectiveCaseEvidence').textContent).toContain('Detective access requires an active assignment to this docket.');
    expect(document.getElementById('detectiveCaseTimeline').textContent).toContain('Detective access requires an active assignment to this docket.');
    expect(document.getElementById('detectiveRelatedCases').textContent).toContain('Detective access requires an active assignment to this docket.');
    expect(document.getElementById('detectiveNoteEntriesList').textContent).toContain('Detective access requires an active assignment to this docket.');
    expect(document.getElementById('detectiveFindingsList').textContent).toContain('Detective access requires an active assignment to this docket.');
  });

  it('init does nothing on a page with no detective containers or matching path', () => {
    document.body.innerHTML = '<div id="somethingElse"></div>';
    setLocation('/citizen');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    init();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
