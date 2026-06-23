import os
import re
import cv2
import pytesseract
import numpy as np
import base64
import json
import sqlite3
import datetime
import secrets
import hmac
from typing import Optional
from PIL import Image
from io import BytesIO
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, jsonify, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "decodelabs-p4-secret-key")
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "uploads")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=30)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if not app.debug:
    app.config["SESSION_COOKIE_SECURE"] = True
DB_PATH = os.environ.get("DECODELABS_DB", os.path.join(BASE_DIR, "decodelabs.db"))
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp"}
ALLOWED_MIME_PREFIXES = {"image/"}

LANG_MAP = {
    "eng": "English", "ara": "Arabic", "chi_sim": "Chinese (Simplified)",
    "chi_tra": "Chinese (Traditional)", "fra": "French", "deu": "German",
    "hin": "Hindi", "ita": "Italian", "jpn": "Japanese", "kor": "Korean",
    "por": "Portuguese", "rus": "Russian", "spa": "Spanish", "tur": "Turkish"
}

PSM_MAP = {
    "6": "Uniform text block (default)",
    "3": "Fully automatic",
    "4": "Single column",
    "7": "Single text line",
    "8": "Single word",
    "11": "Sparse text",
    "12": "Sparse text with OSD"
}

MOBILENET_CLASSES = [
    "background", "aeroplane", "bicycle", "bird", "boat",
    "bottle", "bus", "car", "cat", "chair",
    "cow", "diningtable", "dog", "horse", "motorbike",
    "person", "pottedplant", "sheep", "sofa", "train", "tvmonitor"
]

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ---------- CSRF ----------

def generate_csrf_token() -> str:
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]

app.jinja_env.globals["csrf_token"] = generate_csrf_token

def validate_csrf() -> bool:
    token = request.form.get("_csrf_token", "")
    if not token:
        json_data = request.get_json(silent=True) or {}
        token = json_data.get("_csrf_token", "")
    session_token = session.get("_csrf_token", "")
    if not token or not session_token:
        return False
    return hmac.compare_digest(session_token, token)

# ---------- SQLite ----------

def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                default_mode TEXT DEFAULT 'ocr',
                default_grayscale INTEGER DEFAULT 1,
                default_deskew INTEGER DEFAULT 1,
                default_blur_kernel INTEGER DEFAULT 5,
                default_threshold_method TEXT DEFAULT 'otsu',
                default_threshold_block INTEGER DEFAULT 11,
                default_threshold_c INTEGER DEFAULT 2,
                default_lang TEXT DEFAULT 'eng',
                default_brightness INTEGER DEFAULT 0,
                default_contrast INTEGER DEFAULT 0,
                default_psm TEXT DEFAULT '6'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                mode TEXT NOT NULL,
                filename TEXT NOT NULL,
                confidence REAL DEFAULT 0,
                passed INTEGER DEFAULT 0,
                timestamp TEXT NOT NULL,
                text_output TEXT DEFAULT '',
                image_data TEXT DEFAULT ''
            )
        """)
        # Migration: add missing columns for existing databases
        existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        mig = {"default_lang": "TEXT DEFAULT 'eng'", "default_brightness": "INTEGER DEFAULT 0",
               "default_contrast": "INTEGER DEFAULT 0", "default_psm": "TEXT DEFAULT '6'"}
        for col, dtype in mig.items():
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")
        conn.commit()

init_db()

def db_get_user(username: str) -> Optional[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        r = conn.execute(
            "SELECT id, username, email, password_hash, default_mode, default_grayscale, "
            "default_deskew, default_blur_kernel, default_threshold_method, "
            "default_threshold_block, default_threshold_c, default_lang, "
            "default_brightness, default_contrast, default_psm FROM users WHERE username=?",
            (username,)
        ).fetchone()
        if r:
            return {
                "id": r[0], "username": r[1], "email": r[2], "password_hash": r[3],
                "default_mode": r[4], "default_grayscale": bool(r[5]),
                "default_deskew": bool(r[6]), "default_blur_kernel": r[7],
                "default_threshold_method": r[8], "default_threshold_block": r[9],
                "default_threshold_c": r[10], "default_lang": r[11],
                "default_brightness": r[12], "default_contrast": r[13],
                "default_psm": r[14] or "6"
            }
        return None

def db_create_user(username: str, email: str, password: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (username, email, generate_password_hash(password), datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def db_update_settings(username: str, settings: dict) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE users SET default_mode=?, default_grayscale=?, default_deskew=?, "
            "default_blur_kernel=?, default_threshold_method=?, "
            "default_threshold_block=?, default_threshold_c=?, default_lang=?, "
            "default_brightness=?, default_contrast=?, default_psm=? WHERE username=?",
            (
                settings["default_mode"], 1 if settings["grayscale"] else 0,
                1 if settings["deskew"] else 0, settings["blur_kernel"],
                settings["threshold_method"], settings["threshold_block"],
                settings["threshold_c"], settings.get("lang", "eng"),
                settings.get("brightness", 0), settings.get("contrast", 0),
                settings.get("psm", "6"), username
            )
        )
        conn.commit()

def db_update_password(username: str, new_hash: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE users SET password_hash=? WHERE username=?", (new_hash, username))
        conn.commit()

def db_update_email(username: str, new_email: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE users SET email=? WHERE username=?", (new_email, username))
        conn.commit()

def db_delete_user(username: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM history WHERE username=?", (username,))
        conn.execute("DELETE FROM users WHERE username=?", (username,))
        conn.commit()

def db_add_history(username: str, mode: str, filename: str, confidence: float, passed: bool, text_output: str = "", image_data: str = "") -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO history (username, mode, filename, confidence, passed, timestamp, text_output, image_data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (username, mode, filename, confidence, 1 if passed else 0,
             datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text_output, image_data)
        )
        conn.commit()

def db_get_history(username: str, limit: int = 20, offset: int = 0) -> list:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT mode, filename, confidence, passed, timestamp FROM history "
            "WHERE username=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (username, limit, offset)
        ).fetchall()
        return [
            {"mode": r[0], "filename": r[1], "confidence": r[2],
             "passed": bool(r[3]), "timestamp": r[4]}
            for r in rows
        ]

def db_get_history_count(username: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT COUNT(*) FROM history WHERE username=?", (username,)).fetchone()[0]

def db_clear_history(username: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM history WHERE username=?", (username,))
        conn.commit()

def db_export_history(username: str) -> list:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT mode, filename, confidence, passed, timestamp, text_output FROM history "
            "WHERE username=? ORDER BY id DESC", (username,)
        ).fetchall()
        return [
            {"mode": r[0], "filename": r[1], "confidence": r[2],
             "passed": bool(r[3]), "timestamp": r[4], "text": r[5]}
            for r in rows
        ]

def db_get_dashboard(username: str) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        total = conn.execute("SELECT COUNT(*) FROM history WHERE username=?", (username,)).fetchone()[0]
        avg_conf = conn.execute("SELECT AVG(confidence) FROM history WHERE username=?", (username,)).fetchone()[0] or 0
        passed = conn.execute("SELECT COUNT(*) FROM history WHERE username=? AND passed=1", (username,)).fetchone()[0]
        ocr_count = conn.execute("SELECT COUNT(*) FROM history WHERE username=? AND mode='ocr'", (username,)).fetchone()[0]
        det_count = conn.execute("SELECT COUNT(*) FROM history WHERE username=? AND mode='detection'", (username,)).fetchone()[0]
        barcode_count = conn.execute("SELECT COUNT(*) FROM history WHERE username=? AND mode='barcode'", (username,)).fetchone()[0]
        recent = conn.execute(
            "SELECT mode, filename, confidence, passed, timestamp FROM history "
            "WHERE username=? ORDER BY id DESC LIMIT 10", (username,)
        ).fetchall()

        pass_rate = round(passed / total * 100, 1) if total else 0

        return {
            "total_runs": total,
            "avg_confidence": round(avg_conf, 2),
            "pass_rate": pass_rate,
            "passed": passed,
            "failed": total - passed,
            "ocr_count": ocr_count,
            "detection_count": det_count,
            "barcode_count": barcode_count,
            "recent": [
                {"mode": r[0], "filename": r[1], "confidence": r[2],
                 "passed": bool(r[3]), "timestamp": r[4]}
                for r in recent
            ]
        }

# ---------- Helpers ----------

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_mime(content_type: str) -> bool:
    return any(content_type.startswith(p) for p in ALLOWED_MIME_PREFIXES)

def img_to_b64(img: np.ndarray) -> str:
    _, buf = cv2.imencode(".png", img)
    return "data:image/png;base64," + base64.b64encode(buf).decode()

def b64_to_cv2(b64_str: str) -> np.ndarray:
    if "," in b64_str:
        b64_str = b64_str.split(",", 1)[1]
    buf = base64.b64decode(b64_str)
    arr = np.frombuffer(buf, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def trim_image_data(b64_str: str, max_chars: int = 50000) -> str:
    if len(b64_str) > max_chars:
        return ""
    return b64_str

def adjust_brightness_contrast(img: np.ndarray, brightness: int = 0, contrast: int = 0) -> np.ndarray:
    if brightness != 0 or contrast != 0:
        beta = brightness
        alpha = 1.0 + contrast / 100.0
        img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)
    return img

def deskew(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 2:
        gray = image
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray_inv = cv2.bitwise_not(gray)
    coords = np.column_stack(np.where(gray_inv > 0))
    if len(coords) < 5:
        return image
    try:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) < 0.5:
            return image
        h, w = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return rotated
    except cv2.error:
        return image

def rotate_image(img: np.ndarray, rotation: str) -> np.ndarray:
    if rotation == "90":
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == "-90":
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    elif rotation == "180":
        return cv2.rotate(img, cv2.ROTATE_180)
    return img

def check_tesseract() -> Optional[str]:
    try:
        pytesseract.get_tesseract_version()
        return None
    except Exception:
        return "Tesseract OCR is not installed or not configured. Install from https://github.com/UB-Mannheim/tesseract/wiki"

def validate_username(username: str) -> Optional[str]:
    if len(username) < 3:
        return "Username must be at least 3 characters."
    if len(username) > 32:
        return "Username must be at most 32 characters."
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return "Username can only contain letters, numbers, and underscores."
    return None

# ---------- Routes ----------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
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
                return redirect(url_for("app_page"))
            flash("Invalid username or password.", "error")
        else:
            flash("Please fill in all fields.", "error")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
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
            return redirect(url_for("app_page"))
        else:
            flash("Username already taken. Please choose another.", "error")
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/app")
def app_page():
    if "user" not in session:
        flash("Please log in to access the toolkit.", "warning")
        return redirect(url_for("login"))
    user = db_get_user(session["user"])
    safe_settings = {k: v for k, v in user.items() if k != "password_hash"} if user else {}
    return render_template("app.html", user=session["user"], settings=safe_settings, lang_map=LANG_MAP, psm_map=PSM_MAP)

@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    if "user" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        if not validate_csrf():
            flash("Invalid form submission. Please try again.", "error")
            return redirect(url_for("settings_page"))
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
        return redirect(url_for("settings_page"))

    user = db_get_user(session["user"])
    safe_settings = {k: v for k, v in user.items() if k != "password_hash"} if user else {}
    return render_template("settings.html", user=session["user"], settings=safe_settings, lang_map=LANG_MAP, psm_map=PSM_MAP)

@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    if "user" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        if not validate_csrf():
            flash("Invalid form submission. Please try again.", "error")
            return redirect(url_for("change_password"))
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
            return redirect(url_for("settings_page"))

    return render_template("change_password.html", user=session["user"])

@app.route("/update_email", methods=["POST"])
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

@app.route("/delete_account", methods=["POST"])
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

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))
    data = db_get_dashboard(session["user"])
    return render_template("dashboard.html", user=session["user"], data=data)

@app.route("/dashboard_data")
def dashboard_data():
    if "user" not in session:
        return jsonify({})
    return jsonify(db_get_dashboard(session["user"]))

@app.route("/export_history")
def export_history():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    data = db_export_history(session["user"])
    return send_file(
        BytesIO(json.dumps(data, indent=2).encode("utf-8")),
        mimetype="application/json",
        as_attachment=True,
        download_name="decodelabs_history.json"
    )

@app.route("/upload", methods=["POST"])
def upload():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    if not validate_csrf():
        return jsonify({"error": "Invalid CSRF token"}), 400

    mode = request.form.get("mode", "ocr")
    file = request.files.get("file")
    b64_data = request.form.get("image_b64", "")

    filepath = None
    if file and file.filename:
        if not allowed_file(file.filename):
            return jsonify({"error": "File type not allowed. Accepted: PNG, JPG, GIF, BMP, TIFF, WEBP"}), 400
        if not allowed_mime(file.content_type or ""):
            return jsonify({"error": "Invalid file content type."}), 400
        safe_name = secure_filename(file.filename) or "upload"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
        file.save(filepath)
        filename = safe_name
    elif b64_data:
        filename = "clipboard.png"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        img = b64_to_cv2(b64_data)
        cv2.imwrite(filepath, img)
    else:
        return jsonify({"error": "No valid file or image provided."}), 400

    try:
        preprocess_params = {
            "grayscale": request.form.get("grayscale", "true") == "true",
            "blur_kernel": int(request.form.get("blur_kernel", "5")),
            "threshold_method": request.form.get("threshold_method", "otsu"),
            "deskew": request.form.get("deskew", "true") == "true",
            "threshold_block": int(request.form.get("threshold_block", "11")),
            "threshold_c": int(request.form.get("threshold_c", "2")),
            "lang": request.form.get("lang", "eng"),
            "rotation": request.form.get("rotation", ""),
            "brightness": int(request.form.get("brightness", "0")),
            "contrast": int(request.form.get("contrast", "0")),
            "psm": request.form.get("psm", "6")
        }

        if mode == "ocr":
            result = process_ocr(filepath, preprocess_params)
        elif mode == "detection":
            result = process_detection(filepath, preprocess_params)
        elif mode == "barcode":
            result = process_barcode(filepath, preprocess_params)
        else:
            return jsonify({"error": "Invalid mode"}), 400

        if "error" in result:
            return jsonify(result), 500

        result["filename"] = filename
        text_out = result.get("text", "")
        img_data = result.get("processed_image", "")
        img_data = trim_image_data(img_data)
        db_add_history(session["user"], mode, filename,
                       result.get("confidence", 0), result.get("passed", False),
                       text_out[:500], img_data)

        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        return jsonify(result)

    except Exception as e:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"error": str(e)}), 500


@app.route("/upload_batch", methods=["POST"])
def upload_batch():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    if not validate_csrf():
        return jsonify({"error": "Invalid CSRF token"}), 400

    files = request.files.getlist("files")
    mode = request.form.get("mode", "ocr")
    results = []

    # Read preprocessing params from form (same as single upload)
    pp = {
        "grayscale": request.form.get("grayscale", "true") == "true",
        "blur_kernel": int(request.form.get("blur_kernel", "5")),
        "threshold_method": request.form.get("threshold_method", "otsu"),
        "deskew": request.form.get("deskew", "true") == "true",
        "threshold_block": int(request.form.get("threshold_block", "11")),
        "threshold_c": int(request.form.get("threshold_c", "2")),
        "lang": request.form.get("lang", "eng"),
        "rotation": request.form.get("rotation", ""),
        "brightness": int(request.form.get("brightness", "0")),
        "contrast": int(request.form.get("contrast", "0")),
        "psm": request.form.get("psm", "6")
    }

    for file in files:
        if file.filename == "" or not allowed_file(file.filename):
            continue
        safe_name = secure_filename(file.filename) or "upload"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
        file.save(filepath)
        try:
            if mode == "ocr":
                r = process_ocr(filepath, pp)
            elif mode == "detection":
                r = process_detection(filepath, pp)
            elif mode == "barcode":
                r = process_barcode(filepath, pp)
            else:
                r = {"error": "Invalid mode"}
            r["filename"] = file.filename
            if "error" not in r:
                text_out = r.get("text", "")
                img_data = r.get("processed_image", "")
                img_data = trim_image_data(img_data)
                db_add_history(session["user"], mode, file.filename,
                               r.get("confidence", 0), r.get("passed", False),
                               text_out[:500], img_data)
            results.append(r)
        except Exception as e:
            results.append({"filename": file.filename, "error": str(e)})
        if os.path.exists(filepath):
            os.remove(filepath)

    return jsonify({"results": results, "count": len(results)})


@app.route("/history")
def get_history_route():
    if "user" not in session:
        return jsonify([])
    limit = request.args.get("limit", 20, type=int)
    offset = request.args.get("offset", 0, type=int)
    return jsonify(db_get_history(session["user"], limit, offset))


@app.route("/history_count")
def get_history_count():
    if "user" not in session:
        return jsonify(0)
    return jsonify(db_get_history_count(session["user"]))


@app.route("/clear_history", methods=["POST"])
def clear_history_route():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    if not validate_csrf():
        return jsonify({"error": "Invalid CSRF token"}), 400
    db_clear_history(session["user"])
    return jsonify({"ok": True})


@app.route("/download_image", methods=["POST"])
def download_image():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json()
    b64_str = data.get("image", "")
    if "," in b64_str:
        b64_str = b64_str.split(",", 1)[1]
    try:
        buf = base64.b64decode(b64_str)
    except Exception:
        return jsonify({"error": "Invalid image data"}), 400
    if len(buf) < 50:
        return jsonify({"error": "Invalid image data"}), 400
    return send_file(BytesIO(buf), mimetype="image/png", as_attachment=True, download_name="annotated_image.png")


@app.route("/download_report", methods=["POST"])
def download_report():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json()
    text = data.get("text", "")
    confidence = data.get("confidence", 0)
    mode = data.get("mode", "ocr")
    passed = data.get("passed", False)
    import html as html_mod
    safe_text = html_mod.escape(str(text))
    status = "PASSED" if passed else "FAILED"
    mode_label = {"ocr": "OCR (Text Recognition)", "detection": "Object Detection", "barcode": "Barcode / QR Detection"}
    html_content = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>DecodeLabs Report</title>
<style>
body {{ font-family: 'Segoe UI', sans-serif; padding: 40px; color: #1e293b; }}
h1 {{ color: #166534; font-size: 1.6rem; border-bottom: 3px solid #4ade80; padding-bottom: 10px; }}
.badge {{ display:inline-block; padding:6px 16px; border-radius:20px; font-weight:700; }}
.pass {{ background:#d1fae5; color:#166534; }}
.fail {{ background:#fee2e2; color:#f43f5e; }}
pre {{ background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:16px; font-size:0.9rem; }}
.footer {{ margin-top:30px; font-size:0.8rem; color:#64748b; border-top:1px solid #e2e8f0; padding-top:16px; }}
</style></head><body>
<h1>DecodeLabs — Project 4 Report</h1>
<p><strong>Mode:</strong> {mode_label.get(mode, mode.capitalize())}</p>
<p><strong>Confidence:</strong> {confidence}% <span class="badge {"pass" if passed else "fail"}">{status}</span></p>
<h2>Extracted Output</h2>
<pre>{safe_text}</pre>
<div class="footer">Generated by DecodeLabs Toolkit &bull; {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
</body></html>"""
    buf = BytesIO(html_content.encode("utf-8"))
    return send_file(buf, mimetype="text/html", as_attachment=True, download_name="decodelabs_report.html")


@app.route("/download_txt", methods=["POST"])
def download_txt():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json()
    text = data.get("text", "")
    buf = BytesIO(str(text).encode("utf-8"))
    return send_file(buf, mimetype="text/plain;charset=utf-8", as_attachment=True, download_name="extracted_text.txt")


@app.route("/check_tesseract")
def check_tesseract_route():
    err = check_tesseract()
    return jsonify({"ok": err is None, "error": err})

@app.route("/check_models")
def check_models_route():
    prototxt = os.path.join(BASE_DIR, "deploy.prototxt")
    caffemodel = os.path.join(BASE_DIR, "mobilenet_ssd.caffemodel")
    ok = os.path.exists(prototxt) and os.path.exists(caffemodel)
    return jsonify({"ok": ok})

# ---------- Processing ----------

def ocr_preprocess(img: np.ndarray, params: dict) -> np.ndarray:
    processed = img.copy()

    if params.get("rotation"):
        processed = rotate_image(processed, params["rotation"])

    if params.get("brightness", 0) != 0 or params.get("contrast", 0) != 0:
        processed = adjust_brightness_contrast(processed, params.get("brightness", 0), params.get("contrast", 0))

    if params["grayscale"]:
        processed = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        if params["deskew"]:
            processed = deskew(processed)
        k = params["blur_kernel"]
        if k % 2 == 0:
            k += 1
        k = max(1, min(31, k))
        processed = cv2.GaussianBlur(processed, (k, k), 0)
        if params["threshold_method"] == "otsu":
            _, processed = cv2.threshold(processed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        elif params["threshold_method"] == "adaptive":
            block = params["threshold_block"]
            if block % 2 == 0:
                block += 1
            block = max(3, min(99, block))
            processed = cv2.adaptiveThreshold(processed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                               cv2.THRESH_BINARY, block, params["threshold_c"])
        else:
            _, processed = cv2.threshold(processed, 128, 255, cv2.THRESH_BINARY)
    else:
        if params["deskew"]:
            processed = deskew(processed)

    return processed


def process_ocr(image_path: str, params: dict) -> dict:
    img = cv2.imread(image_path)
    if img is None:
        pil_img = Image.open(image_path)
        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    original_b64 = img_to_b64(img)

    t_err = check_tesseract()
    if t_err:
        return {"error": t_err, "mode": "ocr",
                "original_image": original_b64, "processed_image": original_b64,
                "confidence": 0, "passed": False, "text": "",
                "confidence_details": [], "histogram": {}, "checks": {}}

    processed = ocr_preprocess(img, params)
    processed_b64 = img_to_b64(processed)

    lang = params.get("lang", "eng")
    psm = params.get("psm", "6")
    ocr_config = f"--psm {psm}"
    if lang != "eng":
        ocr_config = f"--psm {psm} -l {lang}"

    text = pytesseract.image_to_string(processed, config=ocr_config)
    conf_data = pytesseract.image_to_data(processed, config=ocr_config, output_type=pytesseract.Output.DICT)
    char_confidences = []
    for i in range(len(conf_data["text"])):
        txt = conf_data["text"][i].strip()
        if txt and conf_data["conf"][i] != -1:
            char_confidences.append({"text": txt, "conf": int(conf_data["conf"][i])})
    conf_values = [c["conf"] for c in char_confidences]
    avg_confidence = round(sum(conf_values) / len(conf_values), 2) if conf_values else 0
    bins = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "<60": 0}
    for c in conf_values:
        if c >= 90:
            bins["90-100"] += 1
        elif c >= 80:
            bins["80-89"] += 1
        elif c >= 70:
            bins["70-79"] += 1
        elif c >= 60:
            bins["60-69"] += 1
        else:
            bins["<60"] += 1
    checks = {"library_integration": True, "preprocessing": params.get("grayscale", False) or params.get("deskew", False) or params.get("brightness", 0) != 0 or params.get("contrast", 0) != 0,
              "accuracy": avg_confidence >= 80, "visual_confirmation": len(text.strip()) > 0}
    return {"text": text.strip(), "confidence": avg_confidence, "passed": avg_confidence >= 80,
            "mode": "ocr", "original_image": original_b64, "processed_image": processed_b64,
            "confidence_details": char_confidences[:80], "histogram": bins, "checks": checks}


def process_detection(image_path: str, params: dict) -> dict:
    img = cv2.imread(image_path)
    if img is None:
        pil_img = Image.open(image_path)
        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    original_b64 = img_to_b64(img)
    h, w = img.shape[:2]
    prototxt = os.path.join(BASE_DIR, "deploy.prototxt")
    caffemodel = os.path.join(BASE_DIR, "mobilenet_ssd.caffemodel")
    if not (os.path.exists(prototxt) and os.path.exists(caffemodel)):
        return {"error": "Model files not found. Run download_models.py", "mode": "detection",
                "original_image": original_b64, "processed_image": original_b64,
                "confidence": 0, "passed": False, "count": 0, "objects": [], "checks": {}}

    processed = img.copy()
    preproc_applied = params.get("brightness", 0) != 0 or params.get("contrast", 0) != 0
    if preproc_applied:
        processed = adjust_brightness_contrast(processed, params.get("brightness", 0), params.get("contrast", 0))

    net = cv2.dnn.readNetFromCaffe(prototxt, caffemodel)
    blob = cv2.dnn.blobFromImage(cv2.resize(processed, (300, 300)), 0.007843, (300, 300), 127.5)
    net.setInput(blob)
    detections = net.forward()
    annotated = processed.copy()
    results = []
    for i in range(detections.shape[2]):
        conf = float(detections[0, 0, i, 2])
        if conf > 0.5:
            class_id = int(detections[0, 0, i, 1])
            label = MOBILENET_CLASSES[class_id] if 0 <= class_id < len(MOBILENET_CLASSES) else f"class_{class_id}"
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            (x1, y1, x2, y2) = box.astype("int")
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (74, 222, 128), 3)
            display_label = f"{label}: {conf:.0%}"
            (tw, th), _ = cv2.getTextSize(display_label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(annotated, (x1, y1 - th - 8), (x1 + tw + 8, y1), (74, 222, 128), -1)
            cv2.putText(annotated, display_label, (x1 + 4, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (22, 101, 52), 2)
            results.append({"class": label, "confidence": round(conf * 100, 2),
                            "bbox": [int(x1), int(y1), int(x2), int(y2)]})
    avg_conf = round(sum(r["confidence"] for r in results) / len(results), 2) if results else 0
    processed_b64 = img_to_b64(annotated)
    checks = {"library_integration": True, "preprocessing": preproc_applied,
              "accuracy": avg_conf >= 80 if results else False, "visual_confirmation": len(results) > 0}
    return {"objects": results, "count": len(results), "confidence": avg_conf,
            "passed": avg_conf >= 80 if results else False, "mode": "detection",
            "original_image": original_b64, "processed_image": processed_b64, "checks": checks}


def process_barcode(image_path: str, params: dict) -> dict:
    img = cv2.imread(image_path)
    if img is None:
        pil_img = Image.open(image_path)
        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    original_b64 = img_to_b64(img)

    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
    except ImportError:
        return {"error": "pyzbar not installed. Run: pip install pyzbar", "mode": "barcode",
                "original_image": original_b64, "processed_image": original_b64,
                "confidence": 0, "passed": False, "count": 0, "barcodes": [], "checks": {}}

    processed = img.copy()
    if params.get("brightness", 0) != 0 or params.get("contrast", 0) != 0:
        processed = adjust_brightness_contrast(processed, params.get("brightness", 0), params.get("contrast", 0))
    processed_gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)

    barcodes = pyzbar_decode(processed_gray)
    annotated = img.copy()
    results = []
    for bc in barcodes:
        (x, y, w, h) = bc.rect
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (74, 222, 128), 3)
        data = bc.data.decode("utf-8", errors="replace")
        bc_type = bc.type
        label = f"{bc_type}: {data[:30]}"
        cv2.putText(annotated, label, (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (22, 101, 52), 2)
        results.append({"type": bc_type, "data": data, "bbox": [x, y, x + w, y + h]})

    confidence = 100 if results else 0
    processed_b64 = img_to_b64(annotated)
    text_output = "\n".join([f"[{r['type']}] {r['data']}" for r in results])
    checks = {"library_integration": True, "preprocessing": True,
              "accuracy": len(results) > 0, "visual_confirmation": len(results) > 0}
    return {"barcodes": results, "count": len(results), "confidence": confidence,
            "passed": len(results) > 0, "mode": "barcode", "text": text_output,
            "original_image": original_b64, "processed_image": processed_b64, "checks": checks}


# ---------- Error Handlers ----------

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message="Something went wrong on our end"), 500


# Clean up stale uploads on startup
for f in os.listdir(app.config["UPLOAD_FOLDER"]):
    fp = os.path.join(app.config["UPLOAD_FOLDER"], f)
    if os.path.isfile(fp):
        try:
            os.remove(fp)
        except OSError:
            pass

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_ENV") == "development")
