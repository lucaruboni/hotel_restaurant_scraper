"""Comandi di amministrazione: creazione utenti, cambio password.

    python -m app.cli create-user --email tu@esempio.it --password '...'
    python -m app.cli set-password --email tu@esempio.it --password '...'
    python -m app.cli list-users
"""

import argparse
import getpass
import sys

from sqlalchemy import select

from .database import SessionLocal, init_db
from .models import User
from .security import hash_password


def _chiedi_password(password: str | None) -> str:
    if password:
        return password
    prima = getpass.getpass("Password (min 10 caratteri): ")
    seconda = getpass.getpass("Conferma password: ")
    if prima != seconda:
        print("Le password non coincidono.", file=sys.stderr)
        sys.exit(1)
    return prima


def crea_utente(email: str, password: str | None, nome: str) -> None:
    init_db()
    db = SessionLocal()
    try:
        email = email.strip().lower()
        if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
            print(f"L'utente {email} esiste già.", file=sys.stderr)
            sys.exit(1)
        try:
            hash_pw = hash_password(_chiedi_password(password))
        except ValueError as exc:
            print(f"Errore: {exc}", file=sys.stderr)
            sys.exit(1)

        db.add(User(email=email, nome=nome or email.split("@")[0], password_hash=hash_pw))
        db.commit()
        print(f"✔ Utente {email} creato.")
    finally:
        db.close()


def cambia_password(email: str, password: str | None) -> None:
    init_db()
    db = SessionLocal()
    try:
        utente = db.execute(select(User).where(User.email == email.strip().lower())).scalar_one_or_none()
        if not utente:
            print(f"Utente {email} non trovato.", file=sys.stderr)
            sys.exit(1)
        try:
            utente.password_hash = hash_password(_chiedi_password(password))
        except ValueError as exc:
            print(f"Errore: {exc}", file=sys.stderr)
            sys.exit(1)
        db.commit()
        print(f"✔ Password aggiornata per {email}.")
    finally:
        db.close()


def elenca_utenti() -> None:
    init_db()
    db = SessionLocal()
    try:
        utenti = db.execute(select(User).order_by(User.created_at)).scalars().all()
        if not utenti:
            print("Nessun utente. Creane uno con: python -m app.cli create-user --email ...")
            return
        for u in utenti:
            stato = "attivo" if u.is_active else "disattivato"
            ultimo = u.last_login_at.strftime("%d/%m/%Y %H:%M") if u.last_login_at else "mai"
            print(f"- {u.email} ({u.nome}) — {stato}, ultimo accesso: {ultimo}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Amministrazione della dashboard HoReCa Leads")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_create = sub.add_parser("create-user", help="Crea un nuovo utente")
    p_create.add_argument("--email", required=True)
    p_create.add_argument("--password", default=None, help="Se omessa viene chiesta in modo sicuro")
    p_create.add_argument("--nome", default="")

    p_pw = sub.add_parser("set-password", help="Cambia la password di un utente")
    p_pw.add_argument("--email", required=True)
    p_pw.add_argument("--password", default=None)

    sub.add_parser("list-users", help="Elenca gli utenti")

    args = parser.parse_args()
    if args.comando == "create-user":
        crea_utente(args.email, args.password, args.nome)
    elif args.comando == "set-password":
        cambia_password(args.email, args.password)
    elif args.comando == "list-users":
        elenca_utenti()


if __name__ == "__main__":
    main()
