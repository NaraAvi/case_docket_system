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

## Open issue fixes

This branch now includes fixes for the three open repository issues:

- **Evidence removal:** citizens can clear a pending file selection and delete
  their own persisted evidence through
  `DELETE /api/v1/citizen/dockets/<case_reference>/evidence/<evidence_id>`.
  Multipart uploads are stored with a SHA-256 hash and are removed only after
  the docket record is updated.
- **Duplicate escalations:** a docket can have at most one unresolved
  escalation (`OPEN` or `UNDER_REVIEW`). A duplicate request returns `409`
  with the existing escalation id; resolved history remains available and a
  new escalation can be opened later. A partial unique database index backs
  the application-level invariant.
- **Refusal-to-register upholds:** IPID can uphold a substantiated
  `REFUSAL_TO_REGISTER` complaint while the docket is awaiting constable
  registration. The docket is placed in a narrow IPID custody freeze, its
  registration status is not changed, and no officer is invented when no
  assignment exists.

## Run locally

```powershell
$env:FLASK_APP = "app:create_app"
python -m flask run
pytest -q
```

The default development database is SQLite. Set `DATABASE_URL` and
`UPLOAD_ROOT` in `.env` to override the database and upload storage locations.
