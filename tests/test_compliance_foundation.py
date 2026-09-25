from datetime import UTC, datetime

from app.modules.regulatory_engine import corpus


def login(client, test_id):
    response = client.post("/api/v1/auth/login", json={"test_id": test_id})
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


def test_registry_contains_all_catalogue_rules(app):
    registry = app.extensions["compliance_rule_registry"]
    rules = registry.all()

    assert len(rules) == 18
    assert {rule.code for rule in rules} == {f"R{index:02d}" for index in range(1, 19)}
    assert all(rule.evaluate({}) == [] for rule in rules)
    assert {registry.get(code).verification for code in ("R01", "R02", "R03", "R04", "R16", "R18")} == {"unverified"}
    assert registry.by_trigger("schedule")


def test_active_s28_table_uses_v2011_until_configured(monkeypatch):
    monkeypatch.setattr(corpus, "IPID_S16_COMMENCEMENT_DATE", None)
    assert corpus.active_s28_table() is corpus.IPID_28_V2011

    commencement = datetime(2024, 10, 1, tzinfo=UTC)
    monkeypatch.setattr(corpus, "IPID_S16_COMMENCEMENT_DATE", commencement)
    assert corpus.active_s28_table(datetime(2024, 9, 30, tzinfo=UTC)) is corpus.IPID_28_V2011
    assert corpus.active_s28_table(datetime(2024, 10, 1, tzinfo=UTC)) is corpus.IPID_28_V2024
    assert "IPID.S28.ATTEMPTED_MURDER_FIREARM" in corpus.IPID_28_V2024
    assert "IPID.S28.FIREARM_DISCHARGE" not in corpus.IPID_28_V2024


def test_compliance_flag_round_trip_and_status_transitions(app):
    with app.app_context():
        repository = app.extensions["compliance_flag_repository"]
        flag = repository.create(
            {
                "rule_code": "R01",
                "case_reference": "CAS-FOUNDATION-1",
                "actor_role": "constable",
                "legal_reference_id": "RSA-SAPS-NI-3-2011",
                "provision": "NI 3/2011",
                "corpus_version": 2,
                "verification": "verified",
                "routes_to": "station_commander",
            }
        )
        assert repository.get_by_id(flag["flag_id"])["status"] == "OPEN"
        responded = repository.transition_status(flag["flag_id"], "RESPONDED", response="Acknowledged")
        assert responded["status"] == "RESPONDED"
        dismissed = repository.transition_status(flag["flag_id"], "DISMISSED", actor_id="2200223333116", resolution_note="Reviewed")
        assert dismissed["status"] == "DISMISSED"
        try:
            repository.transition_status(flag["flag_id"], "OPEN")
        except ValueError as error:
            assert "Cannot transition" in str(error)
        else:
            raise AssertionError("A resolved compliance flag must not reopen")

        audit = app.extensions["audit_service"].get_for_case("CAS-FOUNDATION-1")
        assert [entry["action"] for entry in audit] == ["compliance_flag_created", "compliance_flag_status_changed", "compliance_flag_status_changed"]


def test_compliance_api_role_restrictions_and_filters(app_client):
    station_headers = login(app_client, "2200223333116")
    citizen_headers = login(app_client, "2200223333111")

    rules_response = app_client.get("/api/v1/compliance/rules", headers=citizen_headers)
    assert rules_response.status_code == 200
    assert len(rules_response.get_json()) == 18

    with app_client.application.app_context():
        app_client.application.extensions["compliance_flag_repository"].create(
            {
                "rule_code": "R01",
                "case_reference": "CAS-FOUNDATION-2",
                "actor_role": "constable",
                "legal_reference_id": "RSA-SAPS-NI-3-2011",
                "provision": "NI 3/2011",
                "corpus_version": 2,
                "verification": "verified",
                "routes_to": "station_commander",
            }
        )

    assert app_client.get("/api/v1/compliance/flags", headers=citizen_headers).status_code == 403
    response = app_client.get("/api/v1/compliance/flags?rule_code=R01&case_reference=CAS-FOUNDATION-2", headers=station_headers)
    assert response.status_code == 200
    assert len(response.get_json()) == 1
    assert response.get_json()[0]["rule_code"] == "R01"
