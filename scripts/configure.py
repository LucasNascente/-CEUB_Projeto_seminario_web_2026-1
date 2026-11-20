"""Cria um arquivo local de configuração com segredos aleatórios."""
import argparse
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Informe uma porta entre 1 e 65535.")
    values = {
        "PORT": str(args.port),
        "ADMIN_PASSWORD": secrets.token_urlsafe(24),
        "USERS_DB_PASSWORD": secrets.token_hex(24),
        "TICKETS_DB_PASSWORD": secrets.token_hex(24),
        "SERVICE_KEY": secrets.token_hex(32),
    }
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    content = "\n".join(f"{key}={values[key]}" if (key := line.partition("=")[0]) in values else line
                        for line in lines) + "\n"
    old_umask = os.umask(0o077)
    try:
        with (ROOT / ".env").open("x", encoding="utf-8") as environment:
            environment.write(content)
    except FileExistsError:
        parser.exit(1, "O arquivo .env já existe e foi preservado.\n")
    finally:
        os.umask(old_umask)
    print("Arquivo .env criado. Consulte ADMIN_EMAIL e ADMIN_PASSWORD nele para entrar.")


if __name__ == "__main__":
    main()
