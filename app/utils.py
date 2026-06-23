import os
import re
import secrets
import base64
import numpy as np
import cv2
import pytesseract
from PIL import Image
from flask import session
import hmac
from app.config import ALLOWED_EXTENSIONS, ALLOWED_MIME_PREFIXES


def generate_csrf_token() -> str:
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def validate_csrf() -> bool:
    from flask import request
    token = request.form.get("_csrf_token", "")
    if not token:
        json_data = request.get_json(silent=True) or {}
        token = json_data.get("_csrf_token", "")
    session_token = session.get("_csrf_token", "")
    if not token or not session_token:
        return False
    return hmac.compare_digest(session_token, token)


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


def check_tesseract() -> str:
    try:
        pytesseract.get_tesseract_version()
        return None
    except Exception:
        return "Tesseract OCR is not installed or not configured. Install from https://github.com/UB-Mannheim/tesseract/wiki"


def validate_username(username: str) -> str:
    if len(username) < 3:
        return "Username must be at least 3 characters."
    if len(username) > 32:
        return "Username must be at most 32 characters."
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return "Username can only contain letters, numbers, and underscores."
    return None
