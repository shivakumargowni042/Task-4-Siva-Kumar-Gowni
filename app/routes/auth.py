import re
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

from app.models import db_get_user, db_create_user, db_update_settings
from app.models import db_update_password, db_update_email, db_delete_user
from app.utils import validate_csrf, validate_username
from app.config import LANG_MAP, PSM_MAP

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username and password:
            user = db_get_user(username)
            if user and check_password_hash(user["password_hash"], password):
                session["user"] = username
                session.permanent = request.form.get("remember") == "on"
                flash(f"Welcome back, {username}!", "success")
                return redirect(url_for("main.app_page"))
            flash("Invalid username or password.", "error")
        else:
            flash("Please fill in all fields.", "error")
    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        err = validate_username(username)
        if err:
            flash(err, "error")
        elif not email:
            flash("Please enter an email address.", "error")
        elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash("Please enter a valid email address.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif re.search(r"(.)\1{3,}", password):
            flash("Password contains too many repeated characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif db_create_user(username, email, password):
            session["user"] = username
            flash(f"Account created! Welcome, {username}!", "success")
            return redirect(url_for("main.app_page"))
        else:
            flash("Username already taken. Please choose another.", "error")
    return render_template("register.html")


@auth_bp.route("/logout")
def logout():
    session.pop("user", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/settings", methods=["GET", "POST"])
def settings_page():
    if "user" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        if not validate_csrf():
            flash("Invalid form submission. Please try again.", "error")
            return redirect(url_for("auth.settings_page"))
        settings = {
            "default_mode": request.form.get("default_mode", "ocr"),
            "grayscale": "grayscale" in request.form,
            "deskew": "deskew" in request.form,
            "blur_kernel": int(request.form.get("blur_kernel", "5")),
            "threshold_method": request.form.get("threshold_method", "otsu"),
            "threshold_block": int(request.form.get("threshold_block", "11")),
            "threshold_c": int(request.form.get("threshold_c", "2")),
            "lang": request.form.get("lang", "eng"),
            "brightness": int(request.form.get("brightness", "0")),
            "contrast": int(request.form.get("contrast", "0")),
            "psm": request.form.get("psm", "6")
        }
        db_update_settings(session["user"], settings)
        flash("Settings saved!", "success")
        return redirect(url_for("auth.settings_page"))

    user = db_get_user(session["user"])
    safe_settings = {k: v for k, v in user.items() if k != "password_hash"} if user else {}
    return render_template("settings.html", user=session["user"], settings=safe_settings, lang_map=LANG_MAP, psm_map=PSM_MAP)


@auth_bp.route("/change_password", methods=["GET", "POST"])
def change_password():
    if "user" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        if not validate_csrf():
            flash("Invalid form submission. Please try again.", "error")
            return redirect(url_for("auth.change_password"))
        current = request.form.get("current_password", "")
        new_pass = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        user = db_get_user(session["user"])
        if not user:
            flash("Account not found.", "error")
        elif not check_password_hash(user["password_hash"], current):
            flash("Current password is incorrect.", "error")
        elif len(new_pass) < 8:
            flash("New password must be at least 8 characters.", "error")
        elif re.search(r"(.)\1{3,}", new_pass):
            flash("Password contains too many repeated characters.", "error")
        elif new_pass != confirm:
            flash("Passwords do not match.", "error")
        else:
            db_update_password(session["user"], generate_password_hash(new_pass))
            flash("Password changed successfully!", "success")
            return redirect(url_for("auth.settings_page"))

    return render_template("change_password.html", user=session["user"])


@auth_bp.route("/update_email", methods=["POST"])
def update_email():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    if not validate_csrf():
        return jsonify({"error": "Invalid CSRF token"}), 400
    data = request.get_json()
    new_email = (data.get("email") or "").strip()
    if not re.match(r"[^@]+@[^@]+\.[^@]+", new_email):
        return jsonify({"error": "Invalid email address"}), 400
    db_update_email(session["user"], new_email)
    return jsonify({"ok": True})


@auth_bp.route("/delete_account", methods=["POST"])
def delete_account():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    if not validate_csrf():
        return jsonify({"error": "Invalid CSRF token"}), 400
    data = request.get_json()
    password = data.get("password", "")
    user = db_get_user(session["user"])
    if not user:
        return jsonify({"error": "Account not found"}), 400
    if not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Password is incorrect"}), 400
    db_delete_user(session["user"])
    session.pop("user", None)
    return jsonify({"ok": True})
