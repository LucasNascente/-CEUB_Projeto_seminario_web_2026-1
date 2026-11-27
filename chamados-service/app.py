import os
import re
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from io import BytesIO

import click
import requests
from flask import abort, g, jsonify, request, send_file
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from common.web import UPLOAD_LIMIT, app_config, choice, database, field, iso, now, number, payload

app = app_config(__name__)
USERS = os.environ["USERS_URL"].rstrip("/")
SERVICE_KEY = os.environ["SERVICE_KEY"]
if len(SERVICE_KEY) < 32:
    raise RuntimeError("SERVICE_KEY deve ter pelo menos 32 caracteres.")
USERS_READ_TIMEOUT = int(os.getenv("USERS_READ_TIMEOUT", "4"))
SMTP_HOST = os.getenv("SMTP_HOST")
SLA_HOURS = {"baixa": 72, "media": 24, "alta": 8, "critica": 4}
TRANSITIONS = {
    "aberto": ("em_atendimento",),
    "em_atendimento": ("aguardando_usuario", "resolvido"),
    "aguardando_usuario": ("em_atendimento", "resolvido"),
    "resolvido": ("fechado",),
    "fechado": (),
}
STATUS_LABELS = dict(zip(TRANSITIONS, ("Aberto", "Em atendimento", "Aguardando usuário", "Resolvido", "Fechado")))
EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "txt", "log"}


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    normalized: Mapped[str] = mapped_column(String(240), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    def public(self):
        return {"id": self.id, "nome": self.name, "ativa": self.active}


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    priority: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(24), default="aberto", index=True)
    requester_id: Mapped[int] = mapped_column(Integer, index=True)
    technician_id: Mapped[int | None] = mapped_column(Integer, index=True)
    technician_name: Mapped[str | None] = mapped_column(String(120))
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)

    def public(self, category, detailed=False):
        finished = self.resolved is not None
        end = self.resolved or now()
        within = end.replace(tzinfo=end.tzinfo or timezone.utc) <= self.due.replace(
            tzinfo=self.due.tzinfo or timezone.utc)
        sla = ("cumprido" if within else "violado") if finished else ("no_prazo" if within else "atrasado")
        result = {"id": self.id, "titulo": self.title, "categoria": category.name, "categoria_id": category.id,
                  "prioridade": self.priority, "status": self.status, "solicitante_id": self.requester_id,
                  "tecnico_id": self.technician_id, "tecnico": self.technician_name,
                  "criado_em": iso(self.created), "prazo_em": iso(self.due),
                  "resolvido_em": iso(self.resolved), "sla": sla}
        if detailed:
            result.update(descricao=self.description, resolucao=self.resolution)
        return result


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    actor_id: Mapped[int] = mapped_column(Integer)
    actor_name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def public(self):
        return {"id": self.id, "tipo": self.kind, "autor_id": self.actor_id, "autor": self.actor_name,
                "mensagem": self.message, "criado_em": iso(self.created)}


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    size: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)

    def public(self):
        return {"id": self.id, "nome": self.name, "tamanho": self.size}


class Notification(Base):
    __tablename__ = "email_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_id: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sent: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def seed(session):
    for name in ("Acessos", "Equipamentos", "Rede", "Sistemas", "Outros"):
        session.add(Category(name=name, normalized=name.casefold()))


def seed_catalog(session):
    if not session.scalar(select(Category.id).limit(1)):
        seed(session)


Session = database(app, Base.metadata, 6781002, seed_catalog)


@app.teardown_appcontext
def close_session(_error):
    if (session := g.pop("db", None)) is not None:
        session.close()


def get_session():
    if "db" not in g:
        g.db = Session()
    return g.db


def users_get(path, headers):
    try:
        response = requests.get(f"{USERS}{path}", headers={**headers, "X-Service-Key": SERVICE_KEY}, timeout=(3, USERS_READ_TIMEOUT),
                                allow_redirects=False)
        if response.ok and response.status_code == 200:
            return response.json()
    except (requests.RequestException, ValueError):
        abort(503, "Serviço de usuários indisponível.")
    if response.status_code == 401:
        abort(401, "Sessão inválida ou expirada.")
    if response.status_code == 404:
        return None
    abort(503, "Serviço de usuários indisponível.")


def actor(*roles):
    token = request.cookies.get("helpdesk_session", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        abort(401, "Entre para continuar.")
    user = users_get("/api/users/me", {"Cookie": f"helpdesk_session={token}"})
    if not user or (roles and user["perfil"] not in roles):
        abort(403, "Seu perfil não tem permissão para esta operação.")
    return user


def user_record(user_id):
    return users_get(f"/internal/users/{user_id}", {"X-Service-Key": SERVICE_KEY})


def scoped(user):
    query = select(Ticket, Category).join(Category)
    if user["perfil"] == "solicitante":
        query = query.where(Ticket.requester_id == user["id"])
    elif user["perfil"] == "tecnico":
        query = query.where(Ticket.technician_id == user["id"])
    return query


def ticket_for(user, ticket_id, lock=False):
    query = scoped(user).where(Ticket.id == ticket_id)
    row = get_session().execute(query.with_for_update(of=Ticket) if lock else query).one_or_none()
    if row is None:
        abort(404, "Chamado não encontrado.")
    return row


def event(ticket, user, kind, message):
    get_session().add(Event(ticket_id=ticket.id, actor_id=user["id"], actor_name=user["nome"],
                            kind=kind, message=message, created=now()))


def notify(ticket, recipient_id, message):
    if SMTP_HOST:
        get_session().add(Notification(recipient_id=recipient_id, subject=f"HelpDesk | Chamado #{ticket.id}",
                                       body=message, next_attempt=now()))


@app.get("/api/categories")
def categories():
    user = actor()
    query = select(Category).order_by(Category.name)
    if user["perfil"] != "administrador":
        query = query.where(Category.active)
    return jsonify([category.public() for category in get_session().scalars(query)])


@app.post("/api/categories")
@app.patch("/api/categories/<int:category_id>")
def save_category(category_id=None):
    actor("administrador")
    data = payload()
    session = get_session()
    category = session.get(Category, category_id, with_for_update=True) if category_id else Category(active=True)
    if category is None:
        abort(404, "Categoria não encontrada.")
    if "nome" in data or category_id is None:
        category.name = field(data, "nome", 80)
        category.normalized = category.name.casefold()
    if "ativa" in data:
        if type(data["ativa"]) is not bool:
            abort(400, "O campo ativa deve ser verdadeiro ou falso.")
        category.active = data["ativa"]
    session.add(category)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        abort(409, "Esse nome já existe no catálogo.")
    return category.public(), 200 if category_id else 201


@app.get("/api/tickets")
def tickets():
    user = actor()
    query = scoped(user).order_by(Ticket.created.desc(), Ticket.id.desc())
    return jsonify([ticket.public(category) for ticket, category in get_session().execute(query)])


@app.post("/api/tickets")
def create_ticket():
    user = actor("solicitante", "administrador")
    data = payload()
    session = get_session()
    category = session.get(Category, number(data, "categoria_id"), with_for_update=True)
    if not category or not category.active:
        abort(400, "Selecione uma categoria ativa.")
    priority = choice(data, "prioridade", tuple(SLA_HOURS))
    created = now()
    ticket = Ticket(title=field(data, "titulo", 150), description=field(data, "descricao", 6000),
                    category_id=category.id, priority=priority, requester_id=user["id"], created=created,
                    due=created + timedelta(hours=SLA_HOURS[priority]))
    session.add(ticket)
    session.flush()
    event(ticket, user, "abertura", "Chamado aberto.")
    notify(ticket, user["id"], f"O chamado #{ticket.id} foi aberto com sucesso.")
    session.commit()
    return ticket.public(category, detailed=True), 201


@app.get("/api/tickets/<int:ticket_id>")
def detail(ticket_id):
    user = actor()
    ticket, category = ticket_for(user, ticket_id)
    session = get_session()
    result = ticket.public(category, detailed=True)
    result["historico"] = [entry.public() for entry in session.scalars(
        select(Event).where(Event.ticket_id == ticket_id).order_by(Event.id))]
    result["anexos"] = [entry.public() for entry in session.scalars(
        select(Attachment).where(Attachment.ticket_id == ticket_id).order_by(Attachment.id))]
    result["transicoes"] = list(TRANSITIONS[ticket.status]) if user["perfil"] != "solicitante" else []
    if not ticket.technician_id:
        result["transicoes"] = []
    return result


@app.patch("/api/tickets/<int:ticket_id>/assignment")
def assign(ticket_id):
    user = actor("administrador")
    technician_id = number(payload(), "tecnico_id")
    technician = user_record(technician_id)
    if not technician or technician["perfil"] != "tecnico" or not technician["ativo"]:
        abort(400, "Selecione um técnico ativo.")
    ticket, category = ticket_for(user, ticket_id, lock=True)
    if ticket.status in {"resolvido", "fechado"}:
        abort(409, "Chamados concluídos não podem ser reatribuídos.")
    if ticket.technician_id != technician_id:
        ticket.technician_id, ticket.technician_name = technician_id, technician["nome"]
        event(ticket, user, "atribuicao", f"Chamado atribuído a {technician['nome']}.")
        notify(ticket, technician_id, f"O chamado #{ticket.id} foi atribuído a você.")
        get_session().commit()
    return ticket.public(category)


@app.patch("/api/tickets/<int:ticket_id>/status")
def update_status(ticket_id):
    user = actor("tecnico", "administrador")
    data = payload()
    status = choice(data, "status", tuple(TRANSITIONS))
    ticket, category = ticket_for(user, ticket_id, lock=True)
    if status not in TRANSITIONS[ticket.status] or not ticket.technician_id:
        abort(409, "A transição exige um chamado atribuído e um próximo estado válido.")
    previous = ticket.status
    ticket.status = status
    if status == "resolvido":
        ticket.resolution = field(data, "resolucao", 6000)
        ticket.resolved = now()
    event(ticket, user, "status", f"{STATUS_LABELS[previous]} → {STATUS_LABELS[status]}.")
    if status == "resolvido":
        event(ticket, user, "resolucao", ticket.resolution)
    notify(ticket, ticket.requester_id, f"O chamado #{ticket.id} agora está com status {STATUS_LABELS[status]}.")
    get_session().commit()
    return ticket.public(category, detailed=True)


@app.post("/api/tickets/<int:ticket_id>/comments")
def comment(ticket_id):
    user = actor()
    message = field(payload(), "mensagem", 3000)
    ticket, _ = ticket_for(user, ticket_id, lock=True)
    if ticket.status == "fechado":
        abort(409, "Chamado fechado. Os comentários ficam disponíveis para consulta.")
    event(ticket, user, "comentario", message)
    get_session().commit()
    return {"ok": True}, 201


@app.post("/api/tickets/<int:ticket_id>/attachments")
def upload(ticket_id):
    user = actor()
    ticket, _ = ticket_for(user, ticket_id, lock=True)
    if ticket.status == "fechado":
        abort(409, "Chamado fechado. Os anexos ficam disponíveis para consulta.")
    item = request.files.get("arquivo")
    if not item or not item.filename:
        abort(400, "Selecione um arquivo.")
    filename = secure_filename(item.filename)
    if len(filename) > 180 or "." not in filename or filename.rsplit(".", 1)[-1].lower() not in EXTENSIONS:
        abort(400, "Use arquivos PDF, PNG, JPEG, TXT ou LOG.")
    content = item.stream.read(UPLOAD_LIMIT + 1)
    if not content or len(content) > UPLOAD_LIMIT:
        abort(400, "O arquivo deve ter entre 1 byte e 5 MiB.")
    session = get_session()
    count = session.scalar(select(func.count()).select_from(Attachment).where(Attachment.ticket_id == ticket.id))
    if count >= 5:
        abort(409, "O chamado atingiu o limite de cinco anexos.")
    attachment = Attachment(ticket_id=ticket.id, name=filename, size=len(content), content=content)
    session.add(attachment)
    event(ticket, user, "anexo", f"Anexo adicionado: {filename}.")
    session.commit()
    return attachment.public(), 201


@app.get("/api/tickets/<int:ticket_id>/attachments/<int:attachment_id>")
def download(ticket_id, attachment_id):
    user = actor()
    ticket_for(user, ticket_id)
    attachment = get_session().get(Attachment, attachment_id)
    if not attachment or attachment.ticket_id != ticket_id:
        abort(404, "Anexo não encontrado.")
    return send_file(BytesIO(attachment.content), as_attachment=True,
                     download_name=attachment.name, mimetype="application/octet-stream")


@app.get("/api/reports")
def reports():
    actor("administrador")
    session = get_session()
    by_status = dict.fromkeys(TRANSITIONS, 0)
    by_status.update({status: total for status, total in session.execute(
        select(Ticket.status, func.count()).group_by(Ticket.status))})
    times = [(resolved - created).total_seconds() / 3600 for created, resolved in session.execute(
        select(Ticket.created, Ticket.resolved).where(Ticket.resolved.is_not(None)))]
    by_technician = [{"id": user_id, "nome": name, "total": total} for user_id, name, total in session.execute(
        select(Ticket.technician_id, func.max(Ticket.technician_name), func.count()).where(
            Ticket.technician_id.is_not(None)).group_by(Ticket.technician_id).order_by(func.count().desc()))]
    return {"total": sum(by_status.values()), "por_status": by_status,
            "media_resolucao_horas": round(sum(times) / len(times), 2) if times else None,
            "resolvidos": len(times), "por_tecnico": by_technician}


def send_notification(item):
    recipient = user_record(item.recipient_id)
    if not recipient or not recipient["ativo"]:
        return
    message = EmailMessage()
    message["From"] = os.environ["SMTP_FROM"]
    message["To"] = recipient["email"]
    message["Subject"] = item.subject
    message.set_content(item.body)
    with smtplib.SMTP(SMTP_HOST, int(os.getenv("SMTP_PORT", "587")), timeout=10) as smtp:
        if os.getenv("SMTP_STARTTLS", "1") == "1":
            smtp.starttls()
        if username := os.getenv("SMTP_USERNAME"):
            smtp.login(username, os.environ["SMTP_PASSWORD"])
        smtp.send_message(message)


@app.cli.command("send-emails")
@click.option("--once", is_flag=True, help="Processa a próxima notificação disponível e encerra.")
def send_emails(once):
    if not SMTP_HOST or not os.getenv("SMTP_FROM"):
        raise click.ClickException("Configure SMTP_HOST e SMTP_FROM.")
    while True:
        with Session.begin() as session:
            item = session.scalar(select(Notification).where(
                Notification.sent.is_(None), Notification.next_attempt <= now()).order_by(
                Notification.next_attempt, Notification.id).limit(1).with_for_update(skip_locked=True))
            if item:
                try:
                    send_notification(item)
                except (OSError, smtplib.SMTPException, HTTPException) as error:
                    item.attempts += 1
                    item.next_attempt = now() + timedelta(seconds=min(3600, 30 * 2 ** min(item.attempts, 7)))
                    app.logger.warning("Falha no envio do item %s (%s)", item.id, type(error).__name__)
                else:
                    item.sent = now()
        if once:
            return
        if not item:
            time.sleep(3)
