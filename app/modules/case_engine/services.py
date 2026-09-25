"""Case engine service layer for the citizen docket foundation."""

from app.services.case_service import CaseService


class DocketManagementService:
    """Handles docket lifecycle orchestration for citizen case creation."""

    def __init__(self, case_service=None, app=None):
        self.app = app
        self.case_service = case_service or CaseService(app=app)

    def create_docket(self, citizen_id, payload):
        return self.case_service.create_case(citizen_id, payload)

    def update_docket(self, case_data):
        return self.case_service.update_case(case_data)

    def list_dockets_for_citizen(self, citizen_id):
        return self.case_service.list_cases_for_citizen(citizen_id)

    def get_docket_for_citizen(self, citizen_id, case_reference):
        return self.case_service.get_case_for_citizen(citizen_id, case_reference)

    def register_docket(self, docket):
        return docket
