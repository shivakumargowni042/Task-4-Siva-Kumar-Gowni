import os
import secrets
import hmac
import datetime
from flask import Flask, session
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, "templates"),
        static_folder=os.path.join(BASE_DIR, "static"),
    )
    app.secret_key = os.environ.get("SECRET_KEY", "decodelabs-p4-secret-key")
    app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "uploads")
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
    app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=30)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if not app.debug:
        app.config["SESSION_COOKIE_SECURE"] = True

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    from app.config import DB_PATH
    from app.models import init_db
    init_db()

    from app.utils import generate_csrf_token
    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.api import api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)

    for f in os.listdir(app.config["UPLOAD_FOLDER"]):
        fp = os.path.join(app.config["UPLOAD_FOLDER"], f)
        if os.path.isfile(fp):
            try:
                os.remove(fp)
            except OSError:
                pass

    return app
