"""Testes HTTP pela interface pública. Use exclusivamente uma instância de teste."""
import argparse
import json
import secrets
import time
import unittest
from collections import Counter
from pathlib import Path
from uuid import uuid4

import requests

BASE = ""
ADMIN_EMAIL = ""
ADMIN_PASSWORD = ""
FIXTURE = None
MARKER = "integração <b>texto literal</b>"
HEADER = {"X-HelpDesk-Request": "1"}


class Integration(unittest.TestCase):
    def setUp(self):
        self.sessions = []
        self.admin = self.client()
        self.login(self.admin, ADMIN_EMAIL, ADMIN_PASSWORD)
        self.password = secrets.token_urlsafe(16)
        self.run_id = uuid4().hex[:12]

    def tearDown(self):
        for client in self.sessions:
            client.close()

    def client(self):
        client = requests.Session()
        self.sessions.append(client)
        return client

    def call(self, client, method, path, expected, *, data=None, files=None, headers=HEADER):
        response = client.request(method, BASE + path, json=data, files=files, headers=headers, timeout=15)
        self.assertEqual(response.status_code, expected, f"{method} {path}: {response.text[:300]}")
        return response

    def login(self, client, email, password, expected=200):
        for attempt in range(4):
            response = client.post(BASE + "/api/users/login", headers=HEADER, timeout=15,
                                   json={"email": email, "senha": password})
            if response.status_code != 429 or attempt == 3:
                self.assertEqual(response.status_code, expected, response.text[:300])
                return response
            time.sleep(6.2)  # Nginx accepts one attempt every six seconds after the initial burst.

    def account(self, role):
        email = f"{role}-{uuid4().hex[:10]}@example.test"
        record = self.call(self.admin, "POST", "/api/users", 201,
                           data={"nome": role.title(), "email": email, "perfil": role, "senha": self.password}).json()
        client = self.client()
        self.login(client, email, self.password)
        return client, record

    def sample_ticket(self, client, category):
        return self.call(client, "POST", "/api/tickets", 201, data={
            "titulo": f"Erro de rede {self.run_id}", "descricao": "O acesso à rede está intermitente.",
            "categoria_id": category, "prioridade": "alta",
        }).json()

    def test_authentication_and_roles(self):
        anonymous = self.client()
        for path in ("/api/tickets", "/api/categories", "/api/reports", "/api/users", "/api/users/me"):
            self.call(anonymous, "GET", path, 401)
        known = self.login(anonymous, ADMIN_EMAIL, "senha-incorreta", 401)
        unknown = self.login(anonymous, "inexistente@example.test", "senha-incorreta", 401)
        self.assertEqual(known.json(), unknown.json())
        for profile in ("tecnico", "solicitante"):
            client, account = self.account(profile)
            self.call(client, "GET", "/api/users", 403)
            self.call(client, "POST", "/api/users", 403, data={})
            self.call(client, "GET", "/api/reports", 403)
            self.call(client, "POST", "/api/categories", 403, data={"nome": "Teste"})
            self.call(client, "POST", "/api/tickets", 403, data={}, headers={})
            if profile == "tecnico":
                self.call(client, "POST", "/api/tickets", 403, data={})
                self.call(self.admin, "PATCH", f"/api/users/{account['id']}", 200, data={"ativo": False})
                self.call(client, "GET", "/api/users/me", 401)
                self.login(client, account["email"], self.password, 401)
            else:
                cookie = client.cookies.get("helpdesk_session")
                self.call(client, "POST", "/api/users/logout", 200)
                old = self.client()
                old.cookies.set("helpdesk_session", cookie)
                self.call(old, "GET", "/api/users/me", 401)

    def test_health_and_origin(self):
        response = self.call(self.admin, "GET", "/", 200)
        self.assertIn("Entre na sua conta", response.text)
        self.assertIn("swagger-ui-bundle.js", self.call(self.admin, "GET", "/api-docs/", 200).text)
        spec = self.call(self.admin, "GET", "/api-docs/openapi.json", 200).json()
        self.assertTrue(spec["openapi"].startswith("3."))
        self.assertIn("post", spec["paths"]["/api/tickets"])
        bundle = self.call(self.admin, "GET", "/api-docs/vendor/swagger-ui-bundle.js", 200)
        self.assertGreater(len(bundle.content), 100_000)
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(self.call(self.admin, "GET", "/health", 200).json(), {"status": "ok"})
        self.assertIn("HttpOnly", self.login(self.admin, ADMIN_EMAIL, ADMIN_PASSWORD).headers["Set-Cookie"])
        self.call(self.client(), "POST", "/api/users/login", 403, headers={}, data={})

    def test_ticket_lifecycle(self):
        requester, requester_record = self.account("solicitante")
        outsider, _ = self.account("solicitante")
        technician, record = self.account("tecnico")
        category = self.call(self.admin, "POST", "/api/categories", 201,
                             data={"nome": "Rede " + self.run_id}).json()
        self.call(self.admin, "POST", "/api/categories", 409, data={"nome": category["nome"].upper()})
        ticket = self.sample_ticket(requester, category["id"])
        path = f"/api/tickets/{ticket['id']}"
        self.assertEqual(ticket["status"], "aberto")
        self.assertEqual(ticket["sla"], "no_prazo")
        self.assertEqual(ticket["solicitante_id"], requester_record["id"])
        self.call(self.admin, "PATCH", f"/api/categories/{category['id']}", 200, data={"ativa": False})
        self.assertNotIn(category["id"], [c["id"] for c in self.call(requester, "GET", "/api/categories", 200).json()])
        self.call(requester, "POST", "/api/tickets", 400, data={
            "titulo": "Inválido", "descricao": "Categoria arquivada", "prioridade": "alta", "categoria_id": category["id"]})
        self.call(outsider, "GET", path, 404)
        self.call(outsider, "POST", path + "/comments", 404, data={"mensagem": "Indevido"})
        self.assertNotIn(ticket["id"], [t["id"] for t in self.call(outsider, "GET", "/api/tickets", 200).json()])
        self.call(technician, "GET", path, 404)
        self.call(requester, "PATCH", path + "/assignment", 403, data={"tecnico_id": record["id"]})
        self.call(self.admin, "PATCH", path + "/assignment", 400, data={"tecnico_id": requester_record["id"]})
        self.call(self.admin, "PATCH", path + "/assignment", 200, data={"tecnico_id": record["id"]})
        self.assertIn(ticket["id"], [t["id"] for t in self.call(technician, "GET", "/api/tickets", 200).json()])
        self.call(technician, "PATCH", path + "/status", 409, data={"status": "fechado"})
        for stage in ("em_atendimento", "aguardando_usuario"):
            self.call(technician, "PATCH", path + "/status", 200, data={"status": stage})
        self.call(requester, "POST", path + "/comments", 201, data={"mensagem": MARKER})
        self.call(technician, "POST", path + "/comments", 201, data={"mensagem": "Diagnóstico concluído."})
        attachment = self.call(requester, "POST", path + "/attachments", 201,
                               files={"arquivo": ("evidencia.txt", b"trace local", "text/plain")}).json()
        download_path = path + f"/attachments/{attachment['id']}"
        self.call(outsider, "GET", download_path, 404)
        download = self.call(requester, "GET", download_path, 200)
        self.assertEqual(download.content, b"trace local")
        self.assertIn("attachment;", download.headers["Content-Disposition"])
        self.call(technician, "PATCH", path + "/status", 400, data={"status": "resolvido"})
        self.call(technician, "PATCH", path + "/status", 200,
                  data={"status": "resolvido", "resolucao": "Rede restabelecida."})
        self.call(technician, "PATCH", path + "/status", 200, data={"status": "fechado"})
        self.call(requester, "POST", path + "/comments", 409, data={"mensagem": "Encerrado"})
        result = self.call(requester, "GET", path, 200).json()
        self.assertEqual(result["status"], "fechado")
        self.assertEqual(result["sla"], "cumprido")
        self.assertEqual(result["resolucao"], "Rede restabelecida.")
        self.assertEqual(Counter(entry["tipo"] for entry in result["historico"]),
                         {"abertura": 1, "atribuicao": 1, "status": 4, "comentario": 2, "anexo": 1, "resolucao": 1})
        self.assertIn(MARKER, [entry["mensagem"] for entry in result["historico"]])
        self.assertEqual(result["historico"][-1]["autor_id"], record["id"])
        report = self.call(self.admin, "GET", "/api/reports", 200).json()
        self.assertGreaterEqual(report["por_status"]["fechado"], 1)
        self.assertGreaterEqual(report["media_resolucao_horas"], 0)
        self.assertIn({"id": record["id"], "nome": record["nome"], "total": 1}, report["por_tecnico"])
        FIXTURE.write_text(json.dumps({"path": path, "file": download_path, "title": ticket["titulo"],
                                       "user_id": requester_record["id"]}), encoding="utf-8")

    def test_data_after_restart(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        ticket = self.call(self.admin, "GET", fixture["path"], 200).json()
        self.assertEqual(ticket["titulo"], fixture["title"])
        self.assertEqual(ticket["status"], "fechado")
        self.assertTrue(any(entry["mensagem"] == MARKER for entry in ticket["historico"]))
        self.assertEqual(self.call(self.admin, "GET", fixture["file"], 200).content, b"trace local")
        self.assertIn(fixture["user_id"], [user["id"] for user in self.call(self.admin, "GET", "/api/users", 200).json()])


def main():
    global BASE, ADMIN_EMAIL, ADMIN_PASSWORD, FIXTURE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["flow", "persistence"])
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    settings = dict(line.split("=", 1) for line in args.env.read_text(encoding="utf-8").splitlines()
                    if "=" in line and not line.startswith("#"))
    BASE, ADMIN_EMAIL, ADMIN_PASSWORD, FIXTURE = args.url.rstrip("/"), settings["ADMIN_EMAIL"], settings["ADMIN_PASSWORD"], args.fixture
    names = ["test_health_and_origin", "test_authentication_and_roles", "test_ticket_lifecycle"] if args.phase == "flow" else ["test_data_after_restart"]
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Integration(name) for name in names))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
