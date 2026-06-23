from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify

from app.models import db_get_user, db_get_dashboard
from app.config import LANG_MAP, PSM_MAP

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/app")
def app_page():
    if "user" not in session:
        flash("Please log in to access the toolkit.", "warning")
        return redirect(url_for("auth.login"))
    user = db_get_user(session["user"])
    safe_settings = {k: v for k, v in user.items() if k != "password_hash"} if user else {}
    return render_template("app.html", user=session["user"], settings=safe_settings, lang_map=LANG_MAP, psm_map=PSM_MAP)


@main_bp.route("/dashboard")
def dashboard():
    if "user" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("auth.login"))
    data = db_get_dashboard(session["user"])
    return render_template("dashboard.html", user=session["user"], data=data)


@main_bp.route("/dashboard_data")
def dashboard_data():
    if "user" not in session:
        return jsonify({})
    return jsonify(db_get_dashboard(session["user"]))
