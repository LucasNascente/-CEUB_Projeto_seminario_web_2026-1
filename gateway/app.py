import os

import requests
from flask import abort, request

from common.web import app_config

app = app_config(__name__)
USERS = os.environ["USERS_URL"].rstrip("/")
TICKETS = os.environ["TICKETS_URL"].rstrip("/")
REQUEST_HEADERS = {"content-type", "cookie", "x-helpdesk-request"}
RESPONSE_HEADERS = {"content-type", "content-disposition", "set-cookie"}


@app.get("/health")
def health():
    for upstream in (USERS, TICKETS):
        try:
            requests.get(f"{upstream}/health", timeout=(2, 3)).raise_for_status()
        except requests.RequestException:
            abort(503, "Serviço interno indisponível.")
    return {"status": "ok"}


@app.route("/api/<section>", defaults={"path": ""}, methods=["GET", "POST", "PATCH"])
@app.route("/api/<section>/<path:path>", methods=["GET", "POST", "PATCH"])
def proxy(section, path):
    if section == "users":
        upstream = USERS
    elif section in {"tickets", "categories", "reports"}:
        upstream = TICKETS
    else:
        abort(404, "Rota desconhecida.")
    if any(part in {".", ".."} for part in path.split("/")) or any(c in path for c in "\\?#%"):
        abort(404, "Rota desconhecida.")

    suffix = f"/{path}" if path else ""
    target = f"{upstream}/api/{section}{suffix}"
    headers = {key: value for key, value in request.headers if key.lower() in REQUEST_HEADERS}
    try:
        response = requests.request(
            request.method, target, params=request.args.items(multi=True),
            headers=headers, data=request.get_data(), timeout=(2, 12), allow_redirects=False,
        )
    except requests.Timeout:
        abort(504, "O serviço demorou a responder.")
    except requests.RequestException:
        abort(502, "Serviço interno indisponível.")
    if 300 <= response.status_code < 400:
        abort(502, "Resposta inesperada do serviço interno.")
    forwarded = [(key, value) for key, value in response.headers.items() if key.lower() in RESPONSE_HEADERS]
    return response.content, response.status_code, forwarded
