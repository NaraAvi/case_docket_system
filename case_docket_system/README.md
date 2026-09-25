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
