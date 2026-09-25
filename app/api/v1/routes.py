from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, jwt_required

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

# Roles with broad, cross-case operational visibility (as opposed to citizens,
# who are scoped to their own dockets). Used by endpoints -- like the docket
# list backing the shared Active Cases / Evidence Vault pages, and the
# detective dashboard's registered-case queue -- that every operational role
# needs to read, not just station commanders.
OPERATIONAL_ROLES = {"constable", "detective", "station_commander", "ipid"}


def get_identity_registry():
    return current_app.extensions["identity_registry"]


def get_media_manager():
    return current_app.extensions["media_manager"]


def get_case_service():
    return current_app.extensions["case_service"]


def _recording_payload_from_request():
    """Build a submit_recording() payload from either a real multipart file
    upload or a JSON body, raising ValueError on a bad upload."""
    uploaded_file = request.files.get("file")
    if uploaded_file is not None:
        media = get_media_manager().save_upload(uploaded_file, subdir="recordings")
        return {
            "recording_type": request.form.get("recording_type"),
            "filename": media["filename"],
            "storage_reference": media["storage_reference"],
            "content_type": media["content_type"],
            "size_bytes": media["size_bytes"],
            "sha256_hash": media["sha256_hash"],
        }
    return request.get_json(silent=True) or {}


def get_citizen_auth_service():
    return current_app.extensions["citizen_auth_service"]


def get_citizen_docket_service():
    return current_app.extensions["citizen_docket_service"]


def get_constable_registration_service():
    return current_app.extensions["constable_registration_service"]


def get_investigation_service():
    return current_app.extensions["investigation_service"]


def get_station_commander_service():
    return current_app.extensions["station_commander_service"]


def get_escalation_service():
    return current_app.extensions["escalation_service"]


def get_ipid_service():
    return current_app.extensions["ipid_service"]


def get_decision_engine():
    return current_app.extensions["decision_engine"]


def get_conflict_service():
    return current_app.extensions["conflict_service"]


def get_regulatory_rule_service():
    return current_app.extensions["regulatory_rule_service"]


def get_legal_reference_service():
    return current_app.extensions["legal_reference_service"]


def get_compliance_rule_registry():
    return current_app.extensions["compliance_rule_registry"]


def get_compliance_flag_repository():
    return current_app.extensions["compliance_flag_repository"]


def _error_status(exc):
    return 404 if "not found" in str(exc).lower() else 400


@api_v1_bp.get("/status")
def api_status():
    return jsonify({"status": "ok", "version": "v1"})


@api_v1_bp.get("/compliance/rules")
@jwt_required()
def list_compliance_rules():
    return jsonify([rule.to_dict() for rule in get_compliance_rule_registry().all()])


@api_v1_bp.get("/compliance/flags")
@jwt_required()
def list_compliance_flags():
    if get_jwt().get("role") not in {"station_commander", "ipid"}:
        return jsonify({"error": "Forbidden."}), 403
    status = request.args.get("status")
    rule_code = request.args.get("rule_code")
    case_reference = request.args.get("case_reference")
    return jsonify(get_compliance_flag_repository().list_filtered(status, rule_code, case_reference))


@api_v1_bp.post("/auth/login")
def citizen_login():
    payload = request.get_json(silent=True) or {}
    test_id = payload.get("test_id")

    if test_id is None:
        return jsonify({"error": "Test ID must be a 13-digit number."}), 400

    value = str(test_id).strip()
    if not value.isdigit() or len(value) != 13:
        return jsonify({"error": "Test ID must be a 13-digit number."}), 400

    citizen = get_citizen_auth_service().authenticate(value)
    if citizen is None:
        return jsonify({"error": "Invalid or unknown test identity."}), 401

    token = create_access_token(
        identity=citizen["test_id"],
        additional_claims={
            "role": citizen["role"],
            "full_name": citizen["full_name"],
            "active": citizen["active"],
        },
    )

    return jsonify(
        {
            "access_token": token,
            "token_type": "bearer",
            "test_id": citizen["test_id"],
            "full_name": citizen["full_name"],
            "role": citizen["role"],
            "active": citizen["active"],
        }
    )


@api_v1_bp.get("/citizen/me")
@jwt_required()
def citizen_me():
    current_identity = get_jwt_identity()
    identity = get_identity_registry().get_identity(current_identity)
    if identity is None:
        return jsonify({"error": "Citizen identity not found."}), 404

    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    return jsonify(
        {
            "test_id": identity["test_id"],
            "full_name": identity["full_name"],
            "role": identity["role"],
            "active": identity["active"],
        }
    )


@api_v1_bp.post("/citizen/dockets")
@jwt_required()
def create_citizen_docket():
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Only citizens can create dockets."}), 403

    payload = request.get_json(silent=True) or {}
    citizen_id = get_jwt_identity()
    try:
        docket = get_citizen_docket_service().create_docket(citizen_id, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(docket), 201


@api_v1_bp.get("/citizen/dockets")
@jwt_required()
def list_citizen_dockets():
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    dockets = get_citizen_docket_service().list_dockets(citizen_id)
    return jsonify(dockets)


@api_v1_bp.get("/citizen/dockets/<case_reference>")
@jwt_required()
def get_citizen_docket(case_reference):
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    docket = get_citizen_docket_service().get_docket_with_freeze_status(citizen_id, case_reference)
    if docket is None:
        return jsonify({"error": "Docket not found."}), 404
    return jsonify(docket)


@api_v1_bp.get("/citizen/dockets/<case_reference>/statements")
@jwt_required()
def list_docket_statements(case_reference):
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    try:
        statements = get_citizen_docket_service().list_statements(citizen_id, case_reference)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404 if "not found" in str(exc).lower() else 400
    return jsonify(statements)


@api_v1_bp.post("/citizen/dockets/<case_reference>/statements")
@jwt_required()
def add_docket_statement(case_reference):
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        statement = get_citizen_docket_service().add_statement(citizen_id, case_reference, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400 if "draft" not in str(exc).lower() and "not found" not in str(exc).lower() else 404
    return jsonify(statement), 201


@api_v1_bp.put("/citizen/dockets/<case_reference>/statements")
@jwt_required()
def update_docket_statement(case_reference):
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        statement = get_citizen_docket_service().update_statement(citizen_id, case_reference, None, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(statement)


@api_v1_bp.put("/citizen/dockets/<case_reference>/statements/<statement_id>")
@jwt_required()
def update_docket_statement_by_id(case_reference, statement_id):
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        statement = get_citizen_docket_service().update_statement(citizen_id, case_reference, statement_id, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(statement)


@api_v1_bp.get("/citizen/dockets/<case_reference>/evidence")
@jwt_required()
def list_docket_evidence(case_reference):
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    try:
        evidence = get_citizen_docket_service().list_evidence(citizen_id, case_reference)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404 if "not found" in str(exc).lower() else 400
    return jsonify(evidence)


@api_v1_bp.post("/citizen/dockets/<case_reference>/evidence")
@jwt_required()
def add_docket_evidence(case_reference):
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    uploaded_file = request.files.get("file")
    if uploaded_file is not None:
        try:
            media = get_media_manager().save_upload(uploaded_file, subdir="evidence")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        payload = {
            "evidence_type": request.form.get("evidence_type", ""),
            "description": request.form.get("description", ""),
            "filename": media["filename"],
            "storage_reference": media["storage_reference"],
            "content_type": media["content_type"],
            "size_bytes": media["size_bytes"],
            "sha256_hash": media["sha256_hash"],
        }
    else:
        payload = request.get_json(silent=True) or {}

    try:
        evidence = get_citizen_docket_service().add_evidence(citizen_id, case_reference, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400 if "not found" not in str(exc).lower() else 404
    return jsonify(evidence), 201


@api_v1_bp.post("/citizen/dockets/<case_reference>/submit")
@jwt_required()
def submit_citizen_docket(case_reference):
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    try:
        docket = get_citizen_docket_service().submit_docket(citizen_id, case_reference)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(docket)


@api_v1_bp.get("/citizen/dockets/<case_reference>/timeline")
@jwt_required()
def get_docket_timeline(case_reference):
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    try:
        timeline = get_citizen_docket_service().list_timeline(citizen_id, case_reference)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404 if "not found" in str(exc).lower() else 400
    return jsonify(timeline)


@api_v1_bp.post("/citizen/dockets/<case_reference>/escalations")
@jwt_required()
def create_citizen_escalation(case_reference):
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        escalation = get_citizen_docket_service().create_escalation(citizen_id, case_reference, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(escalation), 201


@api_v1_bp.get("/citizen/dockets/<case_reference>/escalations")
@jwt_required()
def list_citizen_escalations(case_reference):
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    try:
        escalations = get_citizen_docket_service().list_escalations(citizen_id, case_reference)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404 if "not found" in str(exc).lower() else 400
    return jsonify(escalations)


@api_v1_bp.get("/ipid/escalations")
@jwt_required()
def list_ipid_escalations():
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    status = request.args.get("status")
    try:
        escalations = get_ipid_service().list_queue(status=status)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(escalations)


@api_v1_bp.get("/ipid/custody-cases")
@jwt_required()
def list_ipid_custody_cases():
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    return jsonify(get_ipid_service().list_custody_cases())


@api_v1_bp.get("/ipid/escalations/<escalation_id>")
@jwt_required()
def get_ipid_escalation_detail(escalation_id):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    try:
        escalation = get_ipid_service().get_escalation_detail(escalation_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404 if "not found" in str(exc).lower() else 400
    return jsonify(escalation)


@api_v1_bp.post("/ipid/escalations/<escalation_id>/review")
@jwt_required()
def review_ipid_escalation(escalation_id):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    actor_id = get_jwt_identity()
    try:
        review = get_ipid_service().start_review(escalation_id, actor_id, "ipid")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400 if "status" in str(exc).lower() or "already" in str(exc).lower() else 404
    return jsonify(review)


@api_v1_bp.post("/ipid/escalations/<escalation_id>/take-custody")
@jwt_required()
def take_custody_ipid_escalation(escalation_id):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    actor_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        freeze = get_ipid_service().take_custody(escalation_id, actor_id, "ipid", reason=payload.get("reason"))
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(freeze)


@api_v1_bp.post("/ipid/escalations/<escalation_id>/dismiss")
@jwt_required()
def dismiss_ipid_escalation(escalation_id):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    actor_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        decision = get_ipid_service().dismiss_escalation(escalation_id, actor_id, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404 if "not found" in str(exc).lower() else 400
    return jsonify(decision)


@api_v1_bp.post("/ipid/escalations/<escalation_id>/uphold")
@jwt_required()
def uphold_ipid_escalation(escalation_id):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    actor_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        decision = get_ipid_service().uphold_escalation(escalation_id, actor_id, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404 if "not found" in str(exc).lower() else 400
    return jsonify(decision)


@api_v1_bp.post("/ipid/dockets/<case_reference>/reassign")
@jwt_required()
def reassign_ipid_case_officer(case_reference):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    officer_id = payload.get("officer_id")
    if not officer_id:
        return jsonify({"error": "officer_id is required."}), 400

    actor_id = get_jwt_identity()
    try:
        assignment = get_ipid_service().reassign_case_officer(case_reference, str(officer_id), actor_id, reason=payload.get("reason"))
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(assignment)


@api_v1_bp.post("/ipid/dockets/<case_reference>/statements")
@jwt_required()
def create_ipid_statement(case_reference):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    actor_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        statement = get_ipid_service().add_case_statement(case_reference, actor_id, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(statement), 201


@api_v1_bp.get("/ipid/disciplinary-cases")
@jwt_required()
def list_ipid_disciplinary_cases():
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    return jsonify(get_ipid_service().list_disciplinary_cases())


@api_v1_bp.get("/ipid/disciplinary-cases/<disciplinary_case_id>")
@jwt_required()
def get_ipid_disciplinary_case(disciplinary_case_id):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    try:
        case = get_ipid_service().get_disciplinary_case(disciplinary_case_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(case)


@api_v1_bp.post("/ipid/disciplinary-cases/<disciplinary_case_id>/close")
@jwt_required()
def close_ipid_disciplinary_case(disciplinary_case_id):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    payload = request.get_json(silent=True) or {}
    try:
        case = get_ipid_service().close_disciplinary_case(disciplinary_case_id, get_jwt_identity(), payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), _error_status(exc)
    return jsonify(case)


@api_v1_bp.get("/ipid/escalations/<escalation_id>/review-workspace")
@jwt_required()
def get_ipid_review_workspace(escalation_id):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    try:
        workspace = get_ipid_service().get_review_workspace(escalation_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404 if "not found" in str(exc).lower() else 400
    return jsonify(workspace)


@api_v1_bp.get("/ipid/escalations/<escalation_id>/review-notes")
@jwt_required()
def list_ipid_review_notes(escalation_id):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    notes = get_ipid_service().list_review_notes(escalation_id)
    return jsonify(notes)


@api_v1_bp.post("/ipid/escalations/<escalation_id>/review-notes")
@jwt_required()
def create_ipid_review_note(escalation_id):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    actor_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        note = get_ipid_service().add_review_note(escalation_id, actor_id, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404 if "not found" in str(exc).lower() else 400
    return jsonify(note), 201


@api_v1_bp.get("/ipid/escalations/<escalation_id>/review-findings")
@jwt_required()
def list_ipid_review_findings(escalation_id):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    findings = get_ipid_service().list_review_findings(escalation_id)
    return jsonify(findings)


@api_v1_bp.post("/ipid/escalations/<escalation_id>/review-findings")
@jwt_required()
def create_ipid_review_finding(escalation_id):
    claims = get_jwt()
    if claims.get("role") != "ipid":
        return jsonify({"error": "Forbidden."}), 403

    actor_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        finding = get_ipid_service().add_review_finding(escalation_id, actor_id, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404 if "not found" in str(exc).lower() else 400
    return jsonify(finding), 201


@api_v1_bp.get("/station-commander/me")
@jwt_required()
def station_commander_me():
    current_identity = get_jwt_identity()
    identity = get_identity_registry().get_identity(current_identity)
    if identity is None:
        return jsonify({"error": "Station commander identity not found."}), 404

    claims = get_jwt()
    if claims.get("role") != "station_commander":
        return jsonify({"error": "Forbidden."}), 403

    return jsonify(
        {
            "test_id": identity["test_id"],
            "full_name": identity["full_name"],
            "role": identity["role"],
            "active": identity["active"],
        }
    )


@api_v1_bp.get("/station-commander/dockets")
@jwt_required()
def list_station_commander_dockets():
    claims = get_jwt()
    if claims.get("role") not in OPERATIONAL_ROLES:
        return jsonify({"error": "Forbidden."}), 403

    dockets = get_station_commander_service().list_dockets()
    return jsonify(dockets)


@api_v1_bp.get("/station-commander/dockets/<case_reference>")
@jwt_required()
def get_station_commander_docket(case_reference):
    claims = get_jwt()
    if claims.get("role") != "station_commander":
        return jsonify({"error": "Forbidden."}), 403

    docket = get_station_commander_service().get_docket_detail(case_reference)
    if docket is None:
        return jsonify({"error": "Docket not found."}), 404
    return jsonify(docket)


@api_v1_bp.get("/station-commander/dockets/<case_reference>/assignments")
@jwt_required()
def get_station_commander_assignments(case_reference):
    claims = get_jwt()
    if claims.get("role") != "station_commander":
        return jsonify({"error": "Forbidden."}), 403

    case = get_station_commander_service().get_docket(case_reference)
    if case is None:
        return jsonify({"error": "Docket not found."}), 404

    return jsonify(get_station_commander_service().get_assignment_summary(case_reference))


@api_v1_bp.post("/station-commander/dockets/<case_reference>/reassign")
@jwt_required()
def station_commander_force_reassign_docket(case_reference):
    claims = get_jwt()
    if claims.get("role") != "station_commander":
        return jsonify({"error": "Forbidden."}), 403

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    forbidden_keys = {"assigned_by", "assigned_by_role", "actor_id", "officer_role"}
    if any(key in payload for key in forbidden_keys):
        return jsonify({"error": "assigned_by, assigned_by_role, officer_role, and actor identity are server-controlled only."}), 400

    officer_id = payload.get("officer_id")
    if not officer_id:
        return jsonify({"error": "officer_id is required."}), 400

    actor_id = get_jwt_identity()
    reason = payload.get("reason")
    try:
        assignment = get_station_commander_service().force_reassign_docket(
            case_reference,
            str(officer_id),
            actor_id,
            reason=reason,
        )
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(assignment)


@api_v1_bp.get("/station-commander/dockets/<case_reference>/audit")
@jwt_required()
def get_station_commander_docket_audit(case_reference):
    claims = get_jwt()
    if claims.get("role") != "station_commander":
        return jsonify({"error": "Forbidden."}), 403

    case = get_station_commander_service().get_docket(case_reference)
    if case is None:
        return jsonify({"error": "Docket not found."}), 404

    audit_entries = get_station_commander_service().get_case_audit(case_reference)
    return jsonify(audit_entries)


@api_v1_bp.get("/station-commander/officers/<officer_id>/audit")
@jwt_required()
def get_station_commander_officer_audit(officer_id):
    claims = get_jwt()
    if claims.get("role") != "station_commander":
        return jsonify({"error": "Forbidden."}), 403

    actor_id = get_jwt_identity()
    try:
        audit_entries = get_station_commander_service().get_officer_audit(officer_id, actor_id=actor_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(audit_entries)


@api_v1_bp.get("/station-commander/officers")
@jwt_required()
def list_station_commander_officers():
    claims = get_jwt()
    if claims.get("role") != "station_commander":
        return jsonify({"error": "Forbidden."}), 403

    role = request.args.get("role")
    try:
        officers = get_station_commander_service().list_officers(role=role)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(officers)


@api_v1_bp.get("/station-commander/sla/breaches")
@jwt_required()
def get_station_commander_sla_breaches():
    claims = get_jwt()
    if claims.get("role") != "station_commander":
        return jsonify({"error": "Forbidden."}), 403

    breaches = get_station_commander_service().get_sla_breaches()
    return jsonify(breaches)


@api_v1_bp.post("/station-commander/dockets/<case_reference>/evidence")
@jwt_required()
def station_commander_upload_frozen_docket_evidence(case_reference):
    claims = get_jwt()
    if claims.get("role") != "station_commander":
        return jsonify({"error": "Forbidden."}), 403

    actor_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        evidence = get_station_commander_service().upload_frozen_docket_evidence(case_reference, actor_id, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(evidence)


@api_v1_bp.get("/constable/dockets/unregistered")
@jwt_required()
def list_unregistered_dockets():
    claims = get_jwt()
    if claims.get("role") != "constable":
        return jsonify({"error": "Forbidden."}), 403

    queue = get_constable_registration_service().list_unregistered_dockets()
    return jsonify(queue)


@api_v1_bp.get("/constable/dockets/search")
@jwt_required()
def search_constable_dockets():
    claims = get_jwt()
    if claims.get("role") != "constable":
        return jsonify({"error": "Forbidden."}), 403

    query = request.args.get("q", "")
    results = get_constable_registration_service().search_dockets(query)
    return jsonify(results)


@api_v1_bp.post("/constable/dockets/<case_reference>/flags")
@jwt_required()
def create_constable_flag(case_reference):
    claims = get_jwt()
    if claims.get("role") != "constable":
        return jsonify({"error": "Forbidden."}), 403

    constable_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        flag = get_constable_registration_service().create_flag(case_reference, constable_id, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(flag), 201


@api_v1_bp.get("/constable/dockets/<case_reference>/flags")
@jwt_required()
def list_constable_flags(case_reference):
    claims = get_jwt()
    if claims.get("role") != "constable":
        return jsonify({"error": "Forbidden."}), 403

    flags = get_constable_registration_service().list_flags_for_case(case_reference)
    return jsonify(flags)


@api_v1_bp.patch("/constable/flags/<flag_id>")
@jwt_required()
def update_constable_flag(flag_id):
    claims = get_jwt()
    if claims.get("role") != "constable":
        return jsonify({"error": "Forbidden."}), 403

    constable_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        flag = get_constable_registration_service().update_flag(flag_id, constable_id, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(flag)


@api_v1_bp.post("/constable/dockets/<case_reference>/related")
@jwt_required()
def create_related_case(case_reference):
    claims = get_jwt()
    if claims.get("role") != "constable":
        return jsonify({"error": "Forbidden."}), 403

    constable_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        relationship = get_constable_registration_service().create_related_case_link(case_reference, constable_id, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(relationship), 201


@api_v1_bp.get("/constable/dockets/<case_reference>/related")
@jwt_required()
def list_related_cases(case_reference):
    claims = get_jwt()
    if claims.get("role") != "constable":
        return jsonify({"error": "Forbidden."}), 403

    relationships = get_constable_registration_service().list_related_cases(case_reference)
    return jsonify(relationships)


@api_v1_bp.get("/constable/dockets/<case_reference>")
@jwt_required()
def get_constable_docket(case_reference):
    claims = get_jwt()
    if claims.get("role") != "constable":
        return jsonify({"error": "Forbidden."}), 403

    constable_id = get_jwt_identity()
    try:
        docket = get_constable_registration_service().open_docket(case_reference, constable_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404 if "not found" in str(exc).lower() else 400
    if docket is None:
        return jsonify({"error": "Docket not found."}), 404
    return jsonify(docket)


@api_v1_bp.post("/constable/dockets/<case_reference>/interview")
@jwt_required()
def start_constable_interview(case_reference):
    claims = get_jwt()
    if claims.get("role") != "constable":
        return jsonify({"error": "Forbidden."}), 403

    constable_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        interview = get_constable_registration_service().start_interview(case_reference, constable_id, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400 if "not awaiting" not in str(exc).lower() and "not found" not in str(exc).lower() else 404
    return jsonify(interview), 201


@api_v1_bp.get("/constable/interviews/<interview_id>")
@jwt_required()
def get_constable_interview(interview_id):
    claims = get_jwt()
    if claims.get("role") != "constable":
        return jsonify({"error": "Forbidden."}), 403

    constable_id = get_jwt_identity()
    interview = get_constable_registration_service().get_interview_for_constable(constable_id, interview_id)
    if interview is None:
        return jsonify({"error": "Interview not found."}), 404
    return jsonify(interview)


@api_v1_bp.post("/constable/interviews/<interview_id>/recording")
@jwt_required()
def submit_constable_recording(interview_id):
    claims = get_jwt()
    if claims.get("role") != "constable":
        return jsonify({"error": "Forbidden."}), 403

    constable_id = get_jwt_identity()
    try:
        payload = _recording_payload_from_request()
        recording = get_constable_registration_service().submit_recording(constable_id, "constable", interview_id, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400 if "not found" not in str(exc).lower() else 404
    return jsonify(recording), 201


@api_v1_bp.post("/constable/interviews/<interview_id>/register")
@jwt_required()
def register_docket_from_interview(interview_id):
    claims = get_jwt()
    if claims.get("role") != "constable":
        return jsonify({"error": "Forbidden."}), 403

    constable_id = get_jwt_identity()
    try:
        docket = get_constable_registration_service().register_docket(interview_id, constable_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400 if "not found" not in str(exc).lower() else 404
    return jsonify(docket)


@api_v1_bp.get("/citizen/interviews/<interview_id>")
@jwt_required()
def get_citizen_interview(interview_id):
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    interview = get_constable_registration_service().get_interview_for_citizen(citizen_id, interview_id)
    if interview is None:
        return jsonify({"error": "Interview not found."}), 404
    return jsonify(interview)


@api_v1_bp.get("/detective/dockets/<case_reference>")
@jwt_required()
def get_detective_docket(case_reference):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    try:
        docket = get_investigation_service().get_docket_for_detective(case_reference)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(docket)


@api_v1_bp.post("/detective/dockets/<case_reference>/statements")
@jwt_required()
def create_detective_statement(case_reference):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        statement = get_investigation_service().add_statement(case_reference, detective_id, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(statement), 201


@api_v1_bp.post("/detective/dockets/<case_reference>/investigation")
@jwt_required()
def create_detective_investigation(case_reference):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        investigation = get_investigation_service().create_investigation(case_reference, detective_id, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(investigation), 201


@api_v1_bp.get("/detective/investigations/<investigation_id>")
@jwt_required()
def get_detective_investigation(investigation_id):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    try:
        investigation = get_investigation_service().get_investigation(investigation_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    if investigation.get("detective_id") != detective_id:
        return jsonify({"error": "Detective is not authorized for this investigation."}), 403
    return jsonify(investigation)


@api_v1_bp.get("/detective/investigations/<investigation_id>/case")
@jwt_required()
def get_detective_investigation_case(investigation_id):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    try:
        case_view = get_investigation_service().get_case_view_for_detective(investigation_id, detective_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(case_view)


@api_v1_bp.get("/detective/investigations/<investigation_id>/statements")
@jwt_required()
def get_detective_investigation_statements(investigation_id):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    try:
        statements = get_investigation_service().get_case_statements_for_detective(investigation_id, detective_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(statements)


@api_v1_bp.get("/detective/investigations/<investigation_id>/evidence")
@jwt_required()
def get_detective_investigation_evidence(investigation_id):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    try:
        evidence = get_investigation_service().get_case_evidence_for_detective(investigation_id, detective_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(evidence)


@api_v1_bp.get("/detective/investigations/<investigation_id>/flags")
@jwt_required()
def get_detective_investigation_flags(investigation_id):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    try:
        flags = get_investigation_service().get_case_flags_for_detective(investigation_id, detective_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(flags)


@api_v1_bp.get("/detective/investigations/<investigation_id>/related")
@jwt_required()
def get_detective_investigation_related(investigation_id):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    try:
        related = get_investigation_service().get_case_related_for_detective(investigation_id, detective_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(related)


@api_v1_bp.post("/detective/investigations/<investigation_id>/findings")
@jwt_required()
def create_detective_finding(investigation_id):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        finding = get_investigation_service().create_finding(investigation_id, detective_id, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(finding), 201


@api_v1_bp.get("/detective/investigations/<investigation_id>/findings")
@jwt_required()
def list_detective_findings(investigation_id):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    try:
        findings = get_investigation_service().list_findings_for_investigation(investigation_id, detective_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(findings)


@api_v1_bp.post("/detective/investigations/<investigation_id>/note-entries")
@jwt_required()
def create_detective_note_entry(investigation_id):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        note = get_investigation_service().add_note(investigation_id, detective_id, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(note), 201


@api_v1_bp.get("/detective/investigations/<investigation_id>/note-entries")
@jwt_required()
def list_detective_note_entries(investigation_id):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    try:
        notes = get_investigation_service().list_notes(investigation_id, detective_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(notes)


@api_v1_bp.post("/detective/investigations/<investigation_id>/complete")
@jwt_required()
def complete_detective_investigation(investigation_id):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        completed = get_investigation_service().complete_investigation(investigation_id, detective_id, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(completed)


@api_v1_bp.patch("/detective/investigations/<investigation_id>/notes")
@jwt_required()
def update_detective_investigation_notes(investigation_id):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        investigation = get_investigation_service().update_notes(investigation_id, detective_id, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(investigation)


@api_v1_bp.patch("/detective/investigations/<investigation_id>/status")
@jwt_required()
def update_detective_investigation_status(investigation_id):
    claims = get_jwt()
    if claims.get("role") != "detective":
        return jsonify({"error": "Forbidden."}), 403

    detective_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}
    try:
        investigation = get_investigation_service().update_status(investigation_id, detective_id, payload)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        return jsonify({"error": str(exc)}), status
    return jsonify(investigation)


@api_v1_bp.post("/citizen/interviews/<interview_id>/recording")
@jwt_required()
def submit_citizen_recording(interview_id):
    claims = get_jwt()
    if claims.get("role") != "citizen":
        return jsonify({"error": "Forbidden."}), 403

    citizen_id = get_jwt_identity()
    try:
        payload = _recording_payload_from_request()
        recording = get_constable_registration_service().submit_recording(citizen_id, "citizen", interview_id, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400 if "not found" not in str(exc).lower() else 404
    return jsonify(recording), 201


def _find_evidence_by_storage_reference(storage_reference):
    for case in get_case_service().get_all_cases():
        for item in case.get("evidence", []):
            if item.get("storage_reference") == storage_reference:
                return case.get("citizen_id"), item
    return None, None


@api_v1_bp.get("/media/evidence/<path:stored_filename>")
@jwt_required()
def get_evidence_file(stored_filename):
    claims = get_jwt()
    storage_reference = f"evidence/{stored_filename}"
    owning_citizen_id, evidence = _find_evidence_by_storage_reference(storage_reference)
    if evidence is None:
        return jsonify({"error": "File not found."}), 404
    if claims.get("role") == "citizen" and str(owning_citizen_id) != str(get_jwt_identity()):
        return jsonify({"error": "Forbidden."}), 403

    path = get_media_manager().resolve_path(storage_reference)
    if path is None:
        return jsonify({"error": "File not found."}), 404
    return send_file(
        path,
        mimetype=evidence.get("content_type") or "application/octet-stream",
        download_name=evidence.get("filename") or stored_filename,
        as_attachment=False,
    )


@api_v1_bp.get("/media/recordings/<path:stored_filename>")
@jwt_required()
def get_recording_file(stored_filename):
    claims = get_jwt()
    storage_reference = f"recordings/{stored_filename}"
    recording = get_constable_registration_service().find_recording_by_storage_reference(storage_reference)
    if recording is None:
        return jsonify({"error": "File not found."}), 404
    if claims.get("role") == "citizen":
        interview = get_constable_registration_service().get_interview_by_id(recording.get("interview_id"))
        if interview is None or str(interview.get("citizen_id")) != str(get_jwt_identity()):
            return jsonify({"error": "Forbidden."}), 403

    path = get_media_manager().resolve_path(storage_reference)
    if path is None:
        return jsonify({"error": "File not found."}), 404
    return send_file(
        path,
        mimetype=recording.get("content_type") or "application/octet-stream",
        download_name=recording.get("filename") or stored_filename,
        as_attachment=False,
    )


# ---------------------------------------------------------------------------
# Milestone 4: regulatory corpus, decision engine and conflict of interest.
# ---------------------------------------------------------------------------


@api_v1_bp.get("/regulatory/rules")
@jwt_required()
def list_regulatory_rules():
    return jsonify(get_regulatory_rule_service().list_rules(rule_family=request.args.get("family")))


@api_v1_bp.get("/regulatory/rules/<rule_code>")
@jwt_required()
def get_regulatory_rule(rule_code):
    rule = get_regulatory_rule_service().get_rule(rule_code)
    if rule is None:
        return jsonify({"error": "Rule not found."}), 404
    rule["version_history"] = get_regulatory_rule_service().get_version_history(rule_code)
    return jsonify(rule)


@api_v1_bp.get("/regulatory/legal-references")
@jwt_required()
def list_legal_references():
    return jsonify(get_legal_reference_service().list_references())


@api_v1_bp.get("/regulatory/sanction-matrix")
@jwt_required()
def get_sanction_matrix():
    return jsonify(get_regulatory_rule_service().get_sanction_matrix())


@api_v1_bp.get("/regulatory/misconduct-schedule")
@jwt_required()
def get_misconduct_schedule():
    return jsonify(get_regulatory_rule_service().get_misconduct_schedule())


@api_v1_bp.get("/regulatory/statutory-categories")
@jwt_required()
def get_statutory_categories():
    return jsonify(get_regulatory_rule_service().get_statutory_categories())


@api_v1_bp.get("/regulatory/sla-thresholds")
@jwt_required()
def get_sla_thresholds():
    return jsonify(get_regulatory_rule_service().get_sla_thresholds())


@api_v1_bp.post("/decision/triage")
@jwt_required()
def preview_statutory_triage():
    """Side-effect free preview of the statutory triage for a piece of text
    or a docket-shaped payload. Nothing is referred, frozen or stored."""
    claims = get_jwt()
    if claims.get("role") not in OPERATIONAL_ROLES:
        return jsonify({"error": "Forbidden."}), 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    extra = [("text", payload.get("text"))] if payload.get("text") else None
    return jsonify(get_decision_engine().evaluate_statutory_triage(payload, extra))


@api_v1_bp.get("/decision/dockets/<case_reference>/sla")
@jwt_required()
def evaluate_docket_sla(case_reference):
    claims = get_jwt()
    if claims.get("role") not in OPERATIONAL_ROLES:
        return jsonify({"error": "Forbidden."}), 403

    try:
        return jsonify(get_decision_engine().evaluate_sla_compliance(case_reference))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), _error_status(exc)


@api_v1_bp.post("/decision/misconduct-tier")
@jwt_required()
def calculate_misconduct_tier():
    claims = get_jwt()
    if claims.get("role") not in {"ipid", "station_commander"}:
        return jsonify({"error": "Forbidden."}), 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    context = payload.get("evidence_context")
    if context is not None and not isinstance(context, dict):
        return jsonify({"error": "evidence_context must be a JSON object."}), 400
    try:
        result = get_decision_engine().calculate_misconduct_tier(
            payload.get("officer_id"), payload.get("infraction_type"), context
        )
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@api_v1_bp.get("/decision/officers/<officer_id>/sanction")
@jwt_required()
def determine_mandatory_sanction(officer_id):
    claims = get_jwt()
    if claims.get("role") not in {"ipid", "station_commander"}:
        return jsonify({"error": "Forbidden."}), 403

    try:
        return jsonify(get_decision_engine().determine_mandatory_sanction(officer_id, request.args.get("tier")))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@api_v1_bp.post("/conflicts/declarations")
@jwt_required()
def declare_conflict_of_interest():
    claims = get_jwt()
    role = claims.get("role")
    if role not in {"constable", "detective", "station_commander", "ipid"}:
        return jsonify({"error": "Forbidden."}), 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400
    actor_id = get_jwt_identity()
    officer_id = payload.get("officer_id") or actor_id
    try:
        record = get_conflict_service().declare_conflict(officer_id, payload, actor_id, role)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else (403 if "Only the officer" in str(exc) else 400)
        return jsonify({"error": str(exc)}), status
    return jsonify(record), 201


@api_v1_bp.get("/conflicts/declarations")
@jwt_required()
def list_conflict_declarations():
    claims = get_jwt()
    role = claims.get("role")
    if role not in {"constable", "detective", "station_commander", "ipid"}:
        return jsonify({"error": "Forbidden."}), 403

    actor_id = get_jwt_identity()
    officer_id = request.args.get("officer_id")
    if role in {"constable", "detective"}:
        # Officers see only their own declarations.
        officer_id = actor_id
    return jsonify(get_conflict_service().list_declarations(officer_id=officer_id, case_reference=request.args.get("case_reference")))


@api_v1_bp.get("/conflicts/check")
@jwt_required()
def check_conflict_of_interest():
    claims = get_jwt()
    if claims.get("role") not in {"station_commander", "ipid"}:
        return jsonify({"error": "Forbidden."}), 403

    case_reference = request.args.get("case_reference")
    officer_id = request.args.get("officer_id")
    if not case_reference or not officer_id:
        return jsonify({"error": "case_reference and officer_id are required."}), 400
    try:
        result = get_conflict_service().evaluate(case_reference, officer_id, request.args.get("operation") or "assignment")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), _error_status(exc)
    return jsonify(result)
