"""Integration tests for the Milestone 1 persistence layer."""

import pytest

from app import create_app
from app.database.repositories.assignment_repository import AssignmentRepository
from app.database.repositories.audit_event_repository import AuditEventRepository
from app.database.repositories.case_repository import CaseRepository
from app.database.repositories.user_repository import UserRepository


@pytest.fixture()
def app():
    return create_app(testing=True)


class TestCaseRepositoryCrud:
    def test_create_and_get_by_id_round_trip(self, app):
        with app.app_context():
            repo = CaseRepository()
            created = repo.create(
                {
                    "id": 1,
                    "case_reference": "CD-TEST-000001",
                    "citizen_id": "2200223333111",
                    "title": "Test docket",
                    "description": "A description long enough to pass validation.",
                    "status": "DRAFT",
                    "statements": [],
                    "evidence": [],
                    "timeline": [],
                }
            )
            assert created["id"] == 1
            assert created["case_reference"] == "CD-TEST-000001"

            fetched = repo.get_by_id(1)
            assert fetched["case_reference"] == "CD-TEST-000001"

            updated = repo.update(1, {**fetched, "status": "REGISTERED"})
            assert updated["status"] == "REGISTERED"

            for_citizen = repo.get_for_citizen("2200223333111", "CD-TEST-000001")
            assert for_citizen["id"] == 1


class TestAssignmentRepositoryCrud:
    def test_create_and_lookup_round_trip(self, app):
        with app.app_context():
            repo = AssignmentRepository()
            created = repo.create(
                {
                    "case_reference": "CD-TEST-000002",
                    "officer_id": "2200223333115",
                    "officer_role": "detective",
                }
            )
            assert created["assignment_id"].startswith("ASG-")
            assert created["status"] == "ACTIVE"

            current = repo.get_current_assignment_for_case("CD-TEST-000002")
            assert current["assignment_id"] == created["assignment_id"]

            ended = repo.end_assignment(created["assignment_id"], ended_by="tester", reason="done")
            assert ended["status"] == "ENDED"
            assert repo.get_current_assignment_for_case("CD-TEST-000002") is None


class TestAuditEventRepositoryCrud:
    def test_create_and_list_for_case(self, app):
        with app.app_context():
            repo = AuditEventRepository()
            created = repo.create(
                {
                    "actor_id": "2200223333111",
                    "actor_role": "citizen",
                    "action": "test_event",
                    "case_reference": "CD-TEST-000003",
                    "metadata": {"foo": "bar"},
                    "details": {"baz": 1},
                }
            )
            assert created["event_id"].startswith("AUDIT-")
            assert created["metadata"] == {"foo": "bar"}
            assert created["details"] == {"baz": 1}

            for_case = repo.list_for_case("CD-TEST-000003")
            assert len(for_case) == 1
            assert for_case[0]["event_id"] == created["event_id"]

    def test_immutability(self, app):
        with app.app_context():
            repo = AuditEventRepository()
            created = repo.create({"actor_id": "x", "action": "test_event", "case_reference": "CD-TEST-000004"})

            with pytest.raises(ValueError):
                repo.update(created["event_id"], {"action": "tampered"})

            with pytest.raises(ValueError):
                repo.delete(created["event_id"])


class TestIdentitySeedingIdempotency:
    def test_seed_if_empty_does_not_duplicate(self, app):
        with app.app_context():
            repo = UserRepository()
            # create_app() already seeded on startup; calling again must be a no-op.
            first_count = len(repo.list())
            assert first_count == 7

            repo.seed_if_empty([{"test_id": "9999999999999", "full_name": "Should Not Insert", "role": "citizen"}])
            assert len(repo.list()) == first_count


class TestRestartSurvival:
    def test_data_survives_a_fresh_app_pointed_at_the_same_file(self, tmp_path):
        db_path = tmp_path / "test.db"
        database_uri = f"sqlite:///{db_path}"

        first_app = create_app(database_uri=database_uri)
        with first_app.app_context():
            repo = CaseRepository()
            repo.create(
                {
                    "id": 1,
                    "case_reference": "CD-RESTART-000001",
                    "citizen_id": "2200223333111",
                    "title": "Survives restart",
                    "description": "A description long enough to pass validation.",
                    "status": "DRAFT",
                    "statements": [],
                    "evidence": [],
                    "timeline": [],
                }
            )
            from app.extensions import db as first_db

            first_db.session.remove()
            first_db.engine.dispose()

        second_app = create_app(database_uri=database_uri)
        with second_app.app_context():
            repo = CaseRepository()
            fetched = repo.get_by_id(1)
            assert fetched is not None
            assert fetched["case_reference"] == "CD-RESTART-000001"

            users = UserRepository().list()
            assert len(users) == 7
