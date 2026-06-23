import os
import json
import base64
import datetime
import html as html_mod
from io import BytesIO
from flask import (
    Blueprint, request, session, jsonify, send_file, current_app
)
from werkzeug.utils import secure_filename

from app.utils import (
    validate_csrf, allowed_file, allowed_mime,
    b64_to_cv2, trim_image_data, check_tesseract
)
from app.models import (
    db_add_history, db_get_history, db_get_history_count,
    db_clear_history, db_export_history
)
from app.processing import process_ocr, process_detection, process_barcode
from app.config import MODELS_DIR

api_bp = Blueprint("api", __name__)


@api_bp.route("/upload", methods=["POST"])
def upload():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    if not validate_csrf():
        return jsonify({"error": "Invalid CSRF token"}), 400

    mode = request.form.get("mode", "ocr")
    file = request.files.get("file")
    b64_data = request.form.get("image_b64", "")

    filepath = None
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    if file and file.filename:
        if not allowed_file(file.filename):
            return jsonify({"error": "File type not allowed. Accepted: PNG, JPG, GIF, BMP, TIFF, WEBP"}), 400
        if not allowed_mime(file.content_type or ""):
            return jsonify({"error": "Invalid file content type."}), 400
        safe_name = secure_filename(file.filename) or "upload"
        filepath = os.path.join(upload_dir, safe_name)
        file.save(filepath)
        filename = safe_name
    elif b64_data:
        filename = "clipboard.png"
        filepath = os.path.join(upload_dir, filename)
        img = b64_to_cv2(b64_data)
        cv2.imwrite(filepath, img)
        import cv2
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


@api_bp.route("/upload_batch", methods=["POST"])
def upload_batch():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    if not validate_csrf():
        return jsonify({"error": "Invalid CSRF token"}), 400

    files = request.files.getlist("files")
    mode = request.form.get("mode", "ocr")
    results = []
    upload_dir = current_app.config["UPLOAD_FOLDER"]

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
        filepath = os.path.join(upload_dir, safe_name)
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


@api_bp.route("/history")
def get_history_route():
    if "user" not in session:
        return jsonify([])
    limit = request.args.get("limit", 20, type=int)
    offset = request.args.get("offset", 0, type=int)
    return jsonify(db_get_history(session["user"], limit, offset))


@api_bp.route("/history_count")
def get_history_count():
    if "user" not in session:
        return jsonify(0)
    return jsonify(db_get_history_count(session["user"]))


@api_bp.route("/clear_history", methods=["POST"])
def clear_history_route():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    if not validate_csrf():
        return jsonify({"error": "Invalid CSRF token"}), 400
    db_clear_history(session["user"])
    return jsonify({"ok": True})


@api_bp.route("/export_history")
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


@api_bp.route("/download_image", methods=["POST"])
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


@api_bp.route("/download_report", methods=["POST"])
def download_report():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json()
    text = data.get("text", "")
    confidence = data.get("confidence", 0)
    mode = data.get("mode", "ocr")
    passed = data.get("passed", False)
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


@api_bp.route("/download_txt", methods=["POST"])
def download_txt():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json()
    text = data.get("text", "")
    buf = BytesIO(str(text).encode("utf-8"))
    return send_file(buf, mimetype="text/plain;charset=utf-8", as_attachment=True, download_name="extracted_text.txt")


@api_bp.route("/check_tesseract")
def check_tesseract_route():
    err = check_tesseract()
    return jsonify({"ok": err is None, "error": err})


@api_bp.route("/check_models")
def check_models_route():
    prototxt = os.path.join(MODELS_DIR, "deploy.prototxt")
    caffemodel = os.path.join(MODELS_DIR, "mobilenet_ssd.caffemodel")
    ok = os.path.exists(prototxt) and os.path.exists(caffemodel)
    return jsonify({"ok": ok})
