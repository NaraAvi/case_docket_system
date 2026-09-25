from functools import wraps

from flask import Blueprint, redirect, render_template, request, url_for
from flask_jwt_extended import decode_token

ui_bp = Blueprint("ui", __name__, template_folder="../templates", static_folder="../static", url_prefix="")


def get_ui_claims():
    token = request.cookies.get("pdas_session_token")
    if not token:
        return None
    try:
        claims = decode_token(token)
    except Exception:
        return None
    if not claims or claims.get("active") is False:
        return None
    return claims


def require_ui_role(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            claims = get_ui_claims()
            if not claims:
                return redirect(url_for("ui.login"))
            if allowed_roles and claims.get("role") not in allowed_roles:
                return redirect(url_for("ui.login"))
            return view_func(*args, **kwargs)

        return wrapper

    return decorator


@ui_bp.route("/")
def index():
    return redirect(url_for("ui.login"))


@ui_bp.route("/login")
def login():
    claims = get_ui_claims()
    if claims:
        role = claims.get("role")
        if role == "citizen":
            return redirect(url_for("ui.citizen_dashboard"))
        if role == "constable":
            return redirect(url_for("ui.constable_dashboard"))
        if role == "detective":
            return redirect(url_for("ui.detective_dashboard"))
        if role == "station_commander":
            return redirect(url_for("ui.station_commander_dashboard"))
        if role == "ipid":
            return redirect(url_for("ui.ipid_dashboard"))
    return render_template("login.html")


@ui_bp.route("/logout")
def logout():
    response = redirect(url_for("ui.login"))
    response.delete_cookie("pdas_session_token", path="/")
    response.delete_cookie("pdas_user", path="/")
    return response


@ui_bp.route("/citizen")
@require_ui_role("citizen")
def citizen_dashboard():
    return render_template("citizen_dashboard.html", role="citizen", page_title="Citizen Portal")


@ui_bp.route("/citizen/dockets/new")
@require_ui_role("citizen")
def citizen_new_docket():
    return render_template("citizen_docket_form.html", role="citizen", page_title="New Docket")


@ui_bp.route("/citizen/dockets/<case_reference>")
@require_ui_role("citizen")
def citizen_docket_detail(case_reference):
    return render_template("citizen_docket_detail.html", role="citizen", case_reference=case_reference, page_title="Citizen Docket Details")


@ui_bp.route("/constable")
@require_ui_role("constable")
def constable_dashboard():
    return render_template("constable_dashboard.html", role="constable", page_title="Constable Portal")


@ui_bp.route("/constable/dockets/<case_reference>")
@require_ui_role("constable")
def constable_docket_review(case_reference):
    return render_template(
        "constable_docket_review.html",
        role="constable",
        case_reference=case_reference,
        page_title="Constable Docket Review",
    )


@ui_bp.route("/detective")
@require_ui_role("detective")
def detective_dashboard():
    return render_template("detective_dashboard.html", role="detective", page_title="Detective Portal")


@ui_bp.route("/detective/dockets/<case_reference>")
@require_ui_role("detective")
def detective_case_workspace(case_reference):
    return render_template(
        "detective_case_workspace.html",
        role="detective",
        case_reference=case_reference,
        page_title="Detective Case Workspace",
    )


@ui_bp.route("/station-commander")
@require_ui_role("station_commander")
def station_commander_dashboard():
    return render_template("station_commander_dashboard.html", role="station_commander", page_title="Station Commander Portal")


@ui_bp.route("/active-cases")
@require_ui_role("constable", "detective", "station_commander", "ipid")
def active_cases():
    return render_template("active_cases.html", role="station_commander", page_title="Active Cases")


@ui_bp.route("/evidence-vault")
@require_ui_role("constable", "detective", "station_commander", "ipid")
def evidence_vault():
    return render_template("evidence_vault.html", role="station_commander", page_title="Evidence Vault")


@ui_bp.route("/station-commander/dockets/<case_reference>")
@require_ui_role("station_commander")
def station_commander_case_detail(case_reference):
    return render_template(
        "station_commander_docket_detail.html",
        role="station_commander",
        case_reference=case_reference,
        page_title="Station Commander Docket Detail",
    )


@ui_bp.route("/ipid")
@require_ui_role("ipid")
def ipid_dashboard():
    return render_template("ipid_dashboard.html", role="ipid", page_title="IPID Portal")


@ui_bp.route("/ipid/escalations/<escalation_id>")
@require_ui_role("ipid")
def ipid_escalation_detail(escalation_id):
    return render_template(
        "ipid_escalation_detail.html",
        role="ipid",
        escalation_id=escalation_id,
        page_title="IPID Escalation Review",
    )
