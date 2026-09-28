"""Repositories for protected source continuity and detective procedure state."""

from app.database.repositories.base_repository import BaseSqlAlchemyRepository
from app.models import (
    CaseProcedureState,
    ProcedureProfile,
    ProcedureRequirement,
    ProcedureRule,
    SourceRegister,
)


class SourceRegisterRepository(BaseSqlAlchemyRepository):
    model = SourceRegister
    id_column = "source_id"

    def list_for_case(self, case_reference):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(case_reference=case_reference).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def get_latest_for_case(self, case_reference):
        with self._app_context():
            instance = self.session.query(self.model).filter_by(case_reference=case_reference).order_by(self.model.id.desc()).first()
        return self._serialize(instance)


class ProcedureRuleRepository(BaseSqlAlchemyRepository):
    model = ProcedureRule
    id_column = "rule_id"

    def list_for_code(self, rule_code):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(rule_code=rule_code).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def get_by_code_version(self, rule_code, version):
        with self._app_context():
            instance = self.session.query(self.model).filter_by(rule_code=rule_code, version=version).first()
        return self._serialize(instance)

    def list_active(self):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(active=True).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def versions_for_code(self, rule_code):
        return {item.get("version") for item in self.list_for_code(rule_code) if item.get("version")}


class ProcedureProfileRepository(BaseSqlAlchemyRepository):
    model = ProcedureProfile
    id_column = "profile_id"

    def list_for_case_type(self, case_type):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(case_type=case_type, active=True).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]


class CaseProcedureStateRepository(BaseSqlAlchemyRepository):
    model = CaseProcedureState
    id_column = "state_id"

    def list_for_case(self, case_reference):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(case_reference=case_reference).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def get_latest_for_case(self, case_reference):
        with self._app_context():
            instance = self.session.query(self.model).filter_by(case_reference=case_reference).order_by(self.model.id.desc()).first()
        return self._serialize(instance)


class ProcedureRequirementRepository(BaseSqlAlchemyRepository):
    model = ProcedureRequirement
    id_column = "requirement_id"

    def list_for_case(self, case_reference):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(case_reference=case_reference).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]

    def list_for_state(self, state_id):
        with self._app_context():
            instances = self.session.query(self.model).filter_by(state_id=state_id).order_by(self.model.id.asc()).all()
        return [self._serialize(instance) for instance in instances]
