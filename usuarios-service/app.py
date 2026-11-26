import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta

from flask import abort, g, jsonify, request
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from werkzeug.security import check_password_hash, generate_password_hash

from common.web import ROLES, app_config, choice, database, field, now, payload

COOKIE = "helpdesk_session"
EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
SESSION_SECONDS = 8 * 3600
DUMMY_HASH = generate_password_hash(secrets.token_hex())
SERVICE_KEY = os.environ["SERVICE_KEY"]
if len(SERVICE_KEY) < 32:
    raise RuntimeError("SERVICE_KEY deve ter pelo menos 32 caracteres.")

app = app_config(__name__)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), unique=True)
    role: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    bootstrap: Mapped[bool] = mapped_column(Boolean, default=False)

    def public(self):
        return {"id": self.id, "nome": self.name, "email": self.email,
                "perfil": self.role, "ativo": self.active, "principal": self.bootstrap}


class Login(Base):
    __tablename__ = "sessions"

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def valid_email(value):
    value = value.strip().lower()
    if len(value) > 180 or not EMAIL.fullmatch(value):
        abort(400, "Informe um e-mail válido.")
    return value


def seed(session):
    if session.scalar(select(User.id).where(User.bootstrap)):
        return
    email = valid_email(os.environ["ADMIN_EMAIL"])
    password = field({"senha": os.environ["ADMIN_PASSWORD"]}, "senha", 128, 10, strip=False)
    session.add(User(name="Administrador", email=email, role="administrador",
                     password_hash=generate_password_hash(password), bootstrap=True))


Session = database(app, Base.metadata, 6781001, seed)


def get_session():
    if "db" not in g:
        g.db = Session()
    return g.db


@app.teardown_appcontext
def close_session(_error):
    if (session := g.pop("db", None)) is not None:
        session.close()


def token_digest():
    token = request.cookies.get(COOKIE, "")
    if token and len(token) <= 100:
        return hashlib.sha256(token.encode()).hexdigest()
    return None


def current_user(admin=False):
    digest = token_digest()
    if not digest:
        abort(401, "Entre para continuar.")
    user = get_session().scalar(select(User).join(Login).where(
        Login.digest == digest, Login.expires > now(), User.active))
    if not user:
        abort(401, "Sessão inválida ou expirada.")
    if admin and user.role != "administrador":
        abort(403, "Acesso restrito a administradores.")
    return user


def commit(session):
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        abort(409, "Já existe um usuário com este e-mail.")


@app.post("/api/users/login")
def login():
    data = payload()
    email = valid_email(field(data, "email", 180))
    password = field(data, "senha", 128, strip=False)
    session = get_session()
    user = session.scalar(select(User).where(User.email == email))
    if not check_password_hash(user.password_hash if user else DUMMY_HASH, password) or not user or not user.active:
        abort(401, "E-mail ou senha inválidos.")
    token = secrets.token_urlsafe(32)
    session.execute(delete(Login).where(Login.expires <= now()))
    if digest := token_digest():
        session.execute(delete(Login).where(Login.digest == digest))
    session.add(Login(digest=hashlib.sha256(token.encode()).hexdigest(),
                      user_id=user.id, expires=now() + timedelta(seconds=SESSION_SECONDS)))
    session.commit()

    response = jsonify(user.public())
    response.set_cookie(COOKIE, token, httponly=True, samesite="Strict",
                        secure=os.getenv("COOKIE_SECURE") == "1", max_age=SESSION_SECONDS)
    return response


@app.post("/api/users/logout")
def logout():
    if digest := token_digest():
        session = get_session()
        session.execute(delete(Login).where(Login.digest == digest))
        session.commit()
    response = jsonify(ok=True)
    response.delete_cookie(COOKIE, httponly=True, samesite="Strict",
                           secure=os.getenv("COOKIE_SECURE") == "1")
    return response


@app.get("/api/users/me")
def me():
    return current_user().public()


@app.get("/api/users")
def list_users():
    current_user(admin=True)
    session = get_session()
    return jsonify([user.public() for user in session.scalars(select(User).order_by(User.name, User.id))])


@app.post("/api/users")
def create_user():
    current_user(admin=True)
    data = payload()
    user = User(
        name=field(data, "nome", 120),
        email=valid_email(field(data, "email", 180)),
        role=choice(data, "perfil", ROLES),
        password_hash=generate_password_hash(field(data, "senha", 128, 10, strip=False)),
    )
    session = get_session()
    session.add(user)
    commit(session)
    return user.public(), 201


@app.patch("/api/users/<int:user_id>")
def update_user(user_id):
    actor = current_user(admin=True)
    data = payload()
    session = get_session()
    user = session.get(User, user_id, with_for_update=True)
    if not user:
        abort(404, "Usuário não encontrado.")
    if user.bootstrap and actor.id != user.id:
        abort(403, "Somente a conta inicial pode editar seu cadastro.")
    if "nome" in data:
        user.name = field(data, "nome", 120)
    if "email" in data:
        user.email = valid_email(field(data, "email", 180))
    role = choice(data, "perfil", ROLES) if "perfil" in data else user.role
    active = data.get("ativo", user.active)
    if type(active) is not bool:
        abort(400, "O campo ativo deve ser verdadeiro ou falso.")
    if (user.bootstrap or actor.id == user.id) and (not active or role != "administrador"):
        abort(409, "Esta conta deve permanecer ativa como administradora.")
    revoke = user.role != role or user.active != active or "senha" in data
    user.role, user.active = role, active
    if "senha" in data:
        user.password_hash = generate_password_hash(field(data, "senha", 128, 10, strip=False))
    if revoke:
        session.execute(delete(Login).where(Login.user_id == user.id))
    commit(session)
    return user.public()


@app.get("/internal/users/<int:user_id>")
def internal_user(user_id):
    key = request.headers.get("X-Service-Key", "").encode()
    if not hmac.compare_digest(key, SERVICE_KEY.encode()):
        abort(403)
    user = get_session().get(User, user_id)
    if not user:
        abort(404, "Usuário não encontrado.")
    return user.public()
