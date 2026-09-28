# Lazy_Case_Docket

## Milestone 1: Persistence Layer & SQLAlchemy ORM Connection

Goal: eliminate the in-memory mock repositories and give the app reliable,
transactional storage via SQLAlchemy + SQLite (swappable for Postgres via
`DATABASE_URL`).

### What changed

**Base repository contract** (`app/database/repositories/base_repository.py`)
Rewritten as `BaseSqlAlchemyRepository`: generic `get_by_id`, `list`/`list_all`,
`create`, `update`, `delete`, `paginate`, all backed by `db.session` with
commit-and-rollback-on-failure. Subclasses set `model` and, where the lookup
key isn't the surrogate PK, `id_column`.

**Domain repositories migrated to SQLAlchemy**
All 11 rewritten on top of the base class, against the tables in
`app/models.py`, preserving their exact old method signatures
(`list_for_case`, `get_current_assignment_for_case`, `end_assignment`, etc.)
so nothing in `app/modules/*/services.py` had to change: case, assignment,
freeze, escalation, disciplinary_case, flag, related_case, investigation,
investigation_finding, review_note, review_finding.

**Persistent, immutable audit trail**
New `AuditEventRepository` — append-only, `update()`/`delete()` raise
`ValueError` immediately. `AuditTrailService` takes an optional `repository`;
with one it persists to the DB, without one (default, used by ~10 other
service constructors) it falls back to the original in-memory list.

**Persistent identity service**
New `UserRepository`, keyed by `test_id`, with an idempotent
`seed_if_empty()`. `TestIdentityRegistry` takes an optional
`user_repository`; with one every lookup/mutation hits the DB, without one it
falls back to the original in-memory dicts built from `seed_data/test_citizens.py`.

**Migrations**
Root cause of the empty-migration problem: `app.models` was never imported
anywhere, so Alembic autogenerate saw no tables. Fixed by importing it in
`app/__init__.py`. Deleted the old empty stub migration and regenerated a
real initial migration — 17 tables plus `alembic_version`.

**App wiring** (`app/__init__.py`)
`create_app()` now calls `db.create_all()` and seeds identities inside
`app.app_context()`, and wires `identity_registry`/`audit_service` with real
repositories. Added an optional `database_uri` param for tests that need a
real on-disk SQLite file instead of `:memory:`.

### Tests

`tests/test_persistence.py` (new): CRUD round-trips for `CaseRepository`,
`AssignmentRepository`, and `AuditEventRepository`; audit immutability;
identity-seeding idempotency; and a restart-survival test — write through one
`create_app()` instance pointed at a real SQLite file, dispose its engine,
read the data back through a second instance. All passing, alongside the
full existing suite.

Also verified through a real HTTP test-client cycle (not just direct service
calls): login, the full citizen docket → statement → evidence → submit flow,
constable interview/recording/registration, and station commander
reassignment — re-fetching after each step to confirm it actually persisted.

## Milestone 2: Frontend Monolith Decoupling (`pdas.js` Refactoring)

Goal: break the 719-line `pdas.js` monolith into modular, maintainable ES6
modules with strict separation of concerns, without changing any observable
behavior.

### What changed

**Core modules** (`app/static/js/core/`)
`api.js` — `fetchJson(url, options)` with automatic JWT Bearer header
injection and standardized error surfacing. `auth.js` — `setSession`,
`clearSession`, `getUser`, `getToken`, `isAuthenticated`, `requireRole`,
`routeByRole`, plus dependency-injectable `bindLoginForm`/`bindLogoutButton`.
`ui.js` — `buildStatusBadge`, `setEmptyState`, `bindCaseLinks`,
`refreshUserBadge`, `bindReauthModal`.

**Domain modules** (`app/static/js/modules/`)
`citizen.js`, `constable.js`, `detective.js`, `station_commander.js`,
`ipid.js` — each owns exactly the hydration and event handlers for its
role's dashboard and detail page, ported behavior-for-behavior from the old
monolith. `shared.js` is new: it holds the two cross-role widgets
(`activeCaseList`, `evidenceVaultList`) that render on pages reachable by
more than one role and aren't gated by `data-role`.

**Entrypoint** (`app/static/js/pdas_app.js`)
Binds login/logout, dynamically `import()`s only the role module matching
`document.body.dataset.role`, then loads the shared module. `base.html` now
loads `<script type="module" src=".../pdas_app.js">`; the old `pdas.js` and
the dead 0-byte `citizen_dashboard.js` were deleted.

### Tests

**Frontend (Vitest + jsdom, new toolchain — `package.json`,
`vitest.config.js`):** 72 tests across 10 files under
`app/static/js/tests/`:
- *Unit* — `core.api.test.js`, `core.auth.test.js`, `core.ui.test.js` test
  each core module in isolation: token injection, error-message extraction,
  status-badge mapping, cookie/localStorage fallback, malformed-cookie
  handling.
- *Integration* — one file per domain module exercising the real module
  wired to the real `core/api.js` + `core/ui.js` against a jsdom DOM, with
  only `fetch` mocked at the network boundary — dashboard rendering, detail
  hydration, form submission, button wiring, and role/element gating in
  `init()`.
- *System* — `system.pdas_app.test.js` boots the real entrypoint with
  nothing mocked except `fetch`: full login → session → role redirect
  through the real `auth.js`+`api.js`, a full citizen dashboard render with
  the Bearer token verified end-to-end from `localStorage` through the fetch
  call, and the reauth modal / user badge chrome.

**Backend system test** (new — `tests/test_frontend_modularization.py`,
pytest + Flask test client): verifies the real running app — all 10 new
module files are served by Flask's static route with a JS content-type, the
old `pdas.js`/`citizen_dashboard.js` paths now 404, `base.html` emits the
`type="module"` entrypoint tag for the login page and for every one of the 5
role dashboards after a real login, the unauthenticated redirect still
works, and the cross-role Active Cases page still renders for every
non-citizen role.

Full suite still green: **101 tests total** — pytest: 28 passed, 1 skipped
across 2 files; Vitest: 72 passed across 10 files. The Milestone 1
persistence tests were untouched by this refactor.

## Milestone 3: Template Finalization & Interactive UX Completion

Goal: fix broken, mocked, or hardcoded templates and make every button,
input, and modal fully operational.

### What changed

Found and fixed a pre-existing bug first: every child template's
`{% block content %}` was **replacing**, not filling, `base.html`'s block —
so the entire sidebar/topbar/footer shell never rendered, on any page, for
any role, since the UI was first scaffolded. Fixed by moving the shell
markup outside the block. Also fixed `/active-cases` and `/evidence-vault`
hardcoding `role="station_commander"` regardless of who was logged in.

Added four Jinja macros under `app/templates/components/` for the
initial-paint loading skeleton every dashboard/detail page needs (dockets,
timelines, evidence tables, statutory-citation badges) — the actual
per-item rendering stays in JS (`core/ui.js`'s new `renderDocketCard`,
`renderTimelineList`, `renderEvidenceTable`, `populateSelect`,
`renderSlaMeter` helpers) since Milestone 2 made every page fully
client-hydrated with nothing for a macro to loop over server-side.

Wired up every previously-hardcoded control: the high-accountability
modal is now parameter-driven per action instead of a fixed
`CAS-2023-BB1`; constable "Flag Concern" opens a real create/edit modal;
detective "Save Note" and "Add Finding" persist via a **new**
`PATCH /detective/investigations/<id>/notes` endpoint and the existing
findings endpoint; station commander reassignment uses a real officer
picker from a **new** `GET /station-commander/officers` endpoint and shows
a live 72-hour SLA countdown; IPID Dismiss/Uphold collect a mandatory
statutory rationale and hydrate from the richer review-workspace endpoint.

Also untracked 53 stray `__pycache__/*.pyc` files that had been committed
before `.gitignore` existed.

### Tests

`tests/test_milestone3.py` (new, 21 tests): the two new endpoints, the
active-cases/evidence-vault role-bug regression, and full-stack renders of
all four reworked detail pages via a real citizen→constable→detective HTTP
lifecycle. Vitest suites for constable/detective/station_commander/ipid
rewritten against the real new markup and endpoints, plus new coverage in
`core.ui.test.js` for every shared render helper.

Full suite green: **133 tests total** — pytest: 49 passed, 1 skipped across
3 files; Vitest: 84 passed across 10 files.

### Post-M3 fixes (commits `95e2280`, `0f6437c`, `a381610`)

Three rounds of manual testing found real bugs the milestone's green tests
didn't catch: the citizen docket lifecycle was a dead end (no
statement/evidence/submit wiring); the interview step had no recording UI
on either side; evidence and recordings were metadata-only text fields
(now real uploads, SHA-256-hashed, viewable); cross-role "Forbidden" on the
detective dashboard and shared Active Cases/Evidence Vault pages; a
reassigned case didn't transfer investigation ownership to the new
detective (fixed for **both** the station-commander and IPID reassignment
paths); a station commander couldn't assign a constable pre-registration;
an escalation vanished from the IPID queue the moment it was opened
(GitHub issue #3); and two dead controls (constable search, detective
flags/related display) found by an id-by-id audit rather than a bug
report. Several of these fixes are invariants other code now depends on —
see the "Post-M3 fixes and load-bearing invariants" section of
`case_docket_system_architecture_and_roadmap.md` before touching
reassignment, file storage, or the citizen/interview lifecycle again.

Full suite green: **212 tests total** — pytest: 105 passed, 1 skipped;
Vitest: 106 passed.

---

# Current System State — Post-Milestone 3

The historical milestone sections above remain the recorded project history.
This section documents the current implementation state of the repository as it
exists now. It is intended as a current authoritative snapshot of the live
system architecture, not a rewrite of the original milestone history.

## Current PDAS Workflow

The current workflow implemented in the repository is:

Citizen Protected Submission
→ Assertions / Claims
→ Incident Candidate
→ Relationship Classification
→ Procedural Case Creation Gate
→ Case Registration / Procedural Record
→ Automatic Detective Assignment
→ Detective Case Access / Presentation
→ Explicit Investigation Start
→ Active Investigation
→ Statements / Evidence
→ Findings
→ Investigative Conclusion
→ Completion Gate
→ Post-Investigation Evaluation
→ Controlled IPID Referral where applicable
→ IPID Review
→ IPID Decision
→ Controlled Disciplinary Workflow where applicable

This is the current architecture now reflected by the codebase, including
backend-controlled case creation, server-side assignment, procedural review,
and explicit, separate IPID and accountability boundaries.

## Protected Citizen Submission Architecture

The live repository implements a protected citizen-submission model rather than
an unrestricted client-created docket system.

The current architecture includes:

- Protected `Submission` records in `app/models.py` with immutable core fields,
  provenance, original content preservation, receipt timestamping, and
  append-only `event_history`.
- Append-only `SubmissionEvent` records for the authoring and workflow history.
- Citizen-authored `Assertion` and extracted `Claim` objects stored separately
  from the original submission text so the citizen's original narrative remains
  available for procedural continuity.
- `CitizenSubmissionService` with provenance metadata, evidence handling, and
  correction/withdrawal patterns where implemented.
- `IncidentCandidateService` that derives provisional incident hypotheses from
  shared claim context and related protected submissions.
- `Relationship` records for duplicate, related, corroborating, and
  contradictory classification states.
- Deterministic relationship analysis and candidate derivation rather than
  client-triggered case creation.
- A controlled conversion gate; the system does not automatically convert every
  protected submission into a case.
- Protected evidence and media with provenance fields, file storage references,
  SHA-256 hashes, and integrity metadata.
- Controlled corrections and withdrawal flows for submission records where the
  repository actually implements them.

The important principle is that the citizen-submission record remains a
preserved source layer. The procedural case is a separate, consequential state
that is created only via an explicit backend gate and not by ad hoc client
side mutation.

## Procedural Case Creation Gate

Candidate-to-case conversion is controlled by a backend procedural gate and is
not simply a UI action.

The implemented pattern is:

- `candidate ≠ case`
- `submission ≠ case`
- case creation is a consequential backend-controlled transition
- the client cannot simply create authoritative case state
- the conversion decision is deterministic and gate-checked

The repository implements `CaseCreationGate` in `app/modules/control_gate.py`.
It prevents conversion when:

- the candidate is missing or incomplete
- the source submission is missing
- the candidate is already tied to a procedural case
- the candidate is blocked or duplicated/uncertain and requires review
- the candidate does not meet the controlled conversion prerequisites

This means a protected submission may remain as a protected submission even when
it has an incident candidate, and the system may intentionally keep it in a
provisional or review-required state instead of creating a docket automatically.

## Current Constable Workflow

The current constable flow is focused on controlled docket intake and
registration rather than ad hoc case creation.

The supported flow in the repository includes:

- unregistered docket queue (`list_unregistered_dockets`)
- opening a docket for procedural review
- interview lifecycle handling
- citizen recording capture
- constable recording capture
- recording completion and continuity handling
- registration decision and procedural case record creation
- flags and related-case association
- protected-source continuity between the original citizen submission and the
  procedural case
- procedural assessment and continuity checks where implemented
- evidence continuity throughout the registration and review flow

This workflow is implemented in the constable engine and associated gate checks.
The repository does include a transcription/comparison engine for recordings,
but the current implementation is not a full AI-generated transcript pipeline
that fabricates content. `WhisperXProvider` explicitly reports blocked or
unavailable results when the runtime dependency stack is missing; it does not
pretend to have successfully transcribed a recording when it has not.

In other words, recording transcription and comparison are present as a
technical boundary, but their real-world execution remains contingent on the
runtime environment and provider availability.

## Automatic Detective Assignment

The system automatically assigns the initial detective.

Station Commander does not perform the initial detective assignment manually in
this workflow. The repository's assignment engine handles automatic assignment
for registered dockets.

The current assignment behavior is deterministic and based on active eligibility,
workload, and stable tie-break ordering. The implemented logic in
`app/modules/assignment_engine/services.py` selects an eligible detective using:

- active detective identity and role validity
- conflict clearance / eligibility checks
- lower active assignment count
- lower total assignment count
- stable `test_id` ordering as the final deterministic tie-break

The persisted assignment metadata includes:

- `assignment_method` = `AUTOMATIC`
- `selection_rule`
- `selection_rule_version`
- `selection_basis`

The assignment is logged as an audit event and the repository preserves the
assignment metadata for traceability. Station Commander reassignment is
supported as a controlled, later-stage action where permitted; this is not the
initial assignment mechanism.

## Detective Workflow

The current detective workflow is the active investigation and case-completion
path for a registered docket after automatic assignment.

The implemented sequence is:

- registered case arrives with assignment
- automatic detective assignment is active
- detective can access the case workspace and review the procedural context
- detective case presentation includes evidence and procedural context
- explicit investigation start is required
- investigation lifecycle proceeds with notes, evidence review, and case
  actions
- statements, preserved evidence, findings, and investigative reasoning are
  recorded in the investigation record
- investigative conclusion is produced as a finding or outcome, not as a
  criminal adjudication
- completion gate is enforced for formal case completion
- completed case remains read-only or restricted as appropriate for later review
- the post-investigation engine evaluates whether a next procedural action is
  permitted
- controlled next action is allowed only when the code path supports it

The repository is explicit that:

- Investigation ≠ adjudication.
- Investigative conclusion ≠ criminal conviction.
- The system must not treat `VALID`, `INVALID`, or `REVIEW_REQUIRED` as a
  judicial finding of guilt or innocence.

This is enforced in the investigation and decision engine logic, which uses
investigative outcome states as procedural terms rather than criminal
judgments.

## Detective Completion Gate

The completion gate is implemented in the investigation and procedure engines.
It is not a free-form finalisation step and it includes only those conditions
actually present in the repository.

The real implementation includes:

- active, authorized investigative assignment
- detective authorization for completion
- active investigation state and procedural readiness
- freeze and conflict control checks
- final notes and conclusion payload
- final finding linkage where required
- final outcome finding recorded in the investigation result
- `completed_at` persistence where the record is finalized
- protected post-completion state after completion
- SLA/time-to-completion persistence in the operational workflow

The code explicitly blocks unsupported completion patterns and requires the
investigation to satisfy the needed procedural path before a final completion
state is allowed. It does not represent a criminal verdict, and it does not
convert an investigative outcome into a conviction state.

## IPID / Statutory Referral Architecture

The repository implements a separate IPID referral and review architecture.

The current architecture is:

- the post-investigation decision engine evaluates whether a controlled next
  action is permitted
- incomplete investigations cannot proceed as though completed
- statutory-triggered matters can enter controlled IPID referral
- referral is not a finding of guilt
- IPID review is a separate authority boundary
- IPID uphold/dismiss is distinct from criminal conviction

This is implemented through the decision engine, escalation service, review
workspace, and IPID review flows. The system is careful to distinguish a
statutory referral or oversight action from the actual criminal/legal outcome
of a case. The repository includes legal reference and statutory triage logic,
but the final legal mapping remains a later, separate phase of verification and
codification rather than a claim that every rule has already been conclusively
settled in production code.

## Accountability System

The accountability foundation now exists and is implemented as a server-controlled
recording layer rather than a client-driven discipline model.

The implemented accountability model includes:

- an `AccountabilityProfile` per subject identity
- append-only `AccountabilityEvent` records
- total demerit accumulation and threshold tracking
- accountability status and access-state transitions
- threshold review machinery and review-required state
- access restriction architecture for restricted officers
- accountability UI for the role dashboards
- server-controlled accountability events only
- no client-controlled demerit creation
- review queue architecture for accountability-triggered cases
- automatic IPID accountability review foundation where the service creates a
  review/escalation item after threshold crossing

The repository uses terms such as `Accountability Record`, `Accountability /
Demerit Record`, and `accountability review` rather than mislabeling the record
as a criminal record. The implementation keeps the following distinct:

- ACCOUNTABILITY FLAG
- MISCONDUCT FINDING
- CRIMINAL CONVICTION

These are conceptually different outcomes and the system does not collapse them
into one another.

## Accountability Implementation Status

The accountability foundation is implemented, but not every real-world trigger
has been fully wired in the repository.

Implemented foundation:

- accountability profile storage
- append-only demerit history
- threshold review state
- access-state integration with user identity records
- automatic escalation creation when the review threshold is reached
- administrative / IPID accountability review foundation

Remaining trigger work:

- citizen repeated / spam behaviour
- constable malpractice
- constable registration delay
- detective malpractice
- detective investigation delay
- improper or unsupported investigative conclusion
- station commander malpractice / intervention
- station commander delay
- automatic IPID accountability investigation / review

The existence of the accountability service does not mean every trigger is fully
wired. The repository currently implements the core foundation, while some
operational triggers still require explicit completion and integration.

## Audit / Security Architecture

The repository implements a backend-authoritative security posture.

Current security principles in the code include:

- backend authoritative state transitions
- server-controlled identity and role assignment
- server-controlled timestamps and provenance metadata
- append-only operational audit trail
- failed attempts recorded in audit/history
- role authorization checks and role-scoped access control
- protected evidence and media integrity handling
- SHA-256 integrity metadata for file-backed evidence
- frozen-case restrictions for procedural integrity
- no client-controlled consequential state
- direct API attempts cannot legitimately bypass backend gates

The code is intentionally designed around `service` and `gate` boundaries so
that state-changing operations are not left to client trust.

## Freeze / Procedural Control

The repository includes a freeze architecture that restricts ordinary mutations
and preserves procedural continuity for sensitive cases.

The freeze service enforces active freeze state for case mutation, and frozen
cases are treated as exceptional control states rather than criminal or
disciplinary findings. The freeze is a procedural control to preserve integrity,
not a legal guilt determination or a disciplinary finding.

## Legal / Procedural Authority Model

The project design now distinguishes among authority categories that are
important for governance and compliance. The current codebase uses explicit
classifications and provenance metadata, even though the final legal reference
mapping remains a separate final phase.

The intended authority categories are:

- `VERIFIED_LEGAL`: a source that is directly established as legal authority
- `VERIFIED_SAPS_INSTRUCTION`: a source that is established as a SAPS instruction
- `VERIFIED_IPID_REQUIREMENT`: a source that is established as an IPID requirement
- `VERIFIED_POLICY`: an internal verified policy source
- `SYSTEM_CONTROL`: system-enforced operational control logic
- `PROJECT_ASSUMPTION`: a project assumption that tool or workflow logic is
  relying on but which has not yet been independently verified as law or policy
- `NOT_CODIFIED`: a rule or authority boundary that is not yet codified in the
  project reference set

The implementation does not yet appear to enforce a single runtime enum for
all of these across every module, but the repository clearly separates legal
reference data, regulatory rule metadata, and system-control logic. The current
final legislation/reference mapping remains a separate verification phase and
must not be treated as complete merely because the code includes legal reference
records and rule catalogues.

## 72-Hour SLA

The current implementation contains a 72-hour operational SLA boundary that is
used in the case workflow, the decision engine, and the automation layer.

The repo currently implements:

- `SlaService.SLA_HOURS = 72`
- time measured from the assignment/attendance start or the case registration
  boundary depending on the case state
- breach detection and overdue calculation in the SLA evaluation modules
- auto-escalation creation for `SLA_BREACH` cases
- automatic freeze behaviour when the SLA breach path is triggered

The actual code treats this as a system/operational control rather than as a
fully proven legal statement of a statutory right or duty in the way a final
legislative opinion would phrase it. The legal reference metadata in the
regulatory catalog flags the instruction as `PROTOTYPE_CODIFICATION` and notes
that the instruction text should be confirmed before production use. The system
uses the 72-hour window as a deterministic internal operational control, not as
an unverified claim that “South African law says detectives have 72 hours”
without a live, verified source in the repository.

## Citizen Completion / Outcome

The current citizen-side behaviour distinguishes active or in-review cases from
completed cases.

The repository implements:

- current active/in-review case presentation for citizens
- completed-case display where the investigation is finished
- outcome visibility in the citizen-facing workflow as part of the case record
- final reasoning / notes linked to the investigation or case record
- completion timestamp handling in the case/investigation lifecycle
- escalation visibility or read-only access for matters that require review or
  oversight

This is a procedural reporting layer, not a criminal conviction layer. The
system presents the case outcome as investigation status and final narrative,
not as a judicial or criminal outcome.

## Current Verification Status

The repository is currently not fully green; the current verification status is:

- Backend `pytest`: 16 failed, 425 passed, 1 skipped in 34.04s.
- Frontend `Vitest`: 1 failed, 170 passed (171) in 1.81s.
- The failures are present in the current repository state and are not historical
  milestone results.

This section reflects the current live test state in the repository at the time
of this documentation update.

## Known Limitations / Next Phase

The current project still has a small number of genuinely outstanding items,
including:

1. final accountability trigger wiring for the remaining real-world scenarios
2. final South African legislation and reference mapping
3. currentness verification of SAPS instructions and operational legal sources
4. remaining UI and workflow bug fixes
5. recording transcription/comparison completion if the real provider stack is
   still unavailable in some deployment contexts
6. final security and regression audit before broad operational sign-off

These are the currently identified gaps, not a rewrite of the original milestone
history.

---

The earlier milestone sections remain historical project documentation. This
section is the current system state as implemented in the repository now.
