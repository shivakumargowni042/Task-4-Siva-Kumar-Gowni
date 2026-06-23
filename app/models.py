import sqlite3
import datetime
from typing import Optional
from werkzeug.security import generate_password_hash
from app.config import DB_PATH


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
        existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        mig = {"default_lang": "TEXT DEFAULT 'eng'", "default_brightness": "INTEGER DEFAULT 0",
               "default_contrast": "INTEGER DEFAULT 0", "default_psm": "TEXT DEFAULT '6'"}
        for col, dtype in mig.items():
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")
        conn.commit()


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
