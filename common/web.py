import hmac
import os
from datetime import datetime, timezone

from flask import Flask, abort, jsonify, request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from werkzeug.exceptions import HTTPException

UPLOAD_LIMIT = 5 * 1024 * 1024
ROLES = ("solicitante", "tecnico", "administrador")


def now():
    return datetime.now(timezone.utc)


def iso(value):
    if value is None:
        return None
    return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()


def app_config(name):
    app = Flask(name)
    app.config["MAX_CONTENT_LENGTH"] = UPLOAD_LIMIT + 64 * 1024

    if os.getenv("REQUIRE_SERVICE_KEY") == "1":
        service_key = os.environ.get("SERVICE_KEY", "").encode()
        if len(service_key) < 32:
            raise RuntimeError("SERVICE_KEY deve ter pelo menos 32 caracteres.")

        @app.before_request
        def protect_service():
            if request.path != "/ready" and not hmac.compare_digest(
                request.headers.get("X-Service-Key", "").encode(), service_key,
            ):
                abort(403, "Acesso permitido somente pelo gateway.")

    @app.get("/ready")
    def ready():
        return {"status": "ok"}

    @app.before_request
    def protect_writes():
        if request.path.startswith("/api/") and request.method in {"POST", "PATCH", "DELETE"}:
            if request.headers.get("X-HelpDesk-Request") != "1":
                abort(403, "Cabeçalho de segurança ausente.")

    @app.after_request
    def response_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    return app


def database(app, metadata, lock_id, seed):
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)

    @app.cli.command("init-db")
    def init_db():
        with engine.begin() as connection:
            if engine.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": lock_id})
            metadata.create_all(connection)
            with sessions(bind=connection) as session:
                seed(session)
                session.commit()

    @app.get("/health")
    def health():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    return sessions


def payload():
    value = request.get_json()
    if not isinstance(value, dict):
        abort(400, "Envie um objeto JSON.")
    return value


def field(data, name, maximum, minimum=1, strip=True):
    value = data.get(name)
    if isinstance(value, str):
        value = value.strip() if strip else value
        if minimum <= len(value) <= maximum and "\x00" not in value:
            return value
    abort(400, f"O campo {name} deve ter entre {minimum} e {maximum} caracteres.")


def choice(data, name, options):
    value = data.get(name)
    if value not in options:
        abort(400, f"Valor inválido para {name}.")
    return value


def number(data, name):
    value = data.get(name)
    if type(value) is not int or not 0 < value <= 2147483647:
        abort(400, f"Valor inválido para {name}.")
    return value
