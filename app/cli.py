"""Comandi di amministrazione: creazione utenti, cambio password.

    python -m app.cli create-user --username marco --password '...'
    python -m app.cli set-password --username marco --password '...'
    python -m app.cli set-username --username marco --nuovo-username marco2
    python -m app.cli deactivate-user --username marco
    python -m app.cli activate-user --username marco
    python -m app.cli delete-user --username marco --force
    python -m app.cli list-users
"""

import argparse
import getpass
import re
import sys

from sqlalchemy import select

from .database import SessionLocal, init_db
from .models import User
from .security import hash_password

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,60}$")


def _valida_username(username: str) -> str:
    username = username.strip().lower()
    if not USERNAME_RE.match(username):
        print(
            "Nickname non valido: solo lettere minuscole, cifre, punto, trattino e "
            "underscore, da 3 a 60 caratteri.",
            file=sys.stderr,
        )
        sys.exit(1)
    return username


def _chiedi_password(password: str | None) -> str:
    if password:
        return password
    prima = getpass.getpass("Password (min 10 caratteri): ")
    seconda = getpass.getpass("Conferma password: ")
    if prima != seconda:
        print("Le password non coincidono.", file=sys.stderr)
        sys.exit(1)
    return prima


def _trova_utente(db, username: str) -> User:
    utente = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not utente:
        print(f"Utente '{username}' non trovato.", file=sys.stderr)
        sys.exit(1)
    return utente


def crea_utente(username: str, password: str | None, nome: str) -> None:
    init_db()
    username = _valida_username(username)
    db = SessionLocal()
    try:
        if db.execute(select(User).where(User.username == username)).scalar_one_or_none():
            print(f"Il nickname '{username}' esiste già.", file=sys.stderr)
            sys.exit(1)
        try:
            hash_pw = hash_password(_chiedi_password(password))
        except ValueError as exc:
            print(f"Errore: {exc}", file=sys.stderr)
            sys.exit(1)

        # Placeholder unico e innocuo: sui database creati prima dell'introduzione
        # del nickname la colonna `email` ha ancora il vecchio vincolo UNIQUE (le
        # migrazioni aggiungono colonne mancanti ma non alterano vincoli già
        # presenti). Lasciarla vuota farebbe collidere il secondo utente creato
        # senza email con il primo. L'email non è più usata da nessuna parte
        # dell'app: questo valore esiste solo per soddisfare quel vincolo legacy.
        db.add(User(
            username=username, nome=nome or username, password_hash=hash_pw,
            email=f"{username}@nickname.local",
        ))
        db.commit()
        print(f"✔ Utente '{username}' creato.")
    finally:
        db.close()


def cambia_password(username: str, password: str | None) -> None:
    init_db()
    username = username.strip().lower()
    db = SessionLocal()
    try:
        utente = _trova_utente(db, username)
        try:
            utente.password_hash = hash_password(_chiedi_password(password))
        except ValueError as exc:
            print(f"Errore: {exc}", file=sys.stderr)
            sys.exit(1)
        db.commit()
        print(f"✔ Password aggiornata per '{username}'.")
    finally:
        db.close()


def cambia_username(username: str, nuovo_username: str) -> None:
    init_db()
    username = username.strip().lower()
    nuovo_username = _valida_username(nuovo_username)
    db = SessionLocal()
    try:
        utente = _trova_utente(db, username)
        if db.execute(select(User).where(User.username == nuovo_username)).scalar_one_or_none():
            print(f"Il nickname '{nuovo_username}' esiste già.", file=sys.stderr)
            sys.exit(1)
        utente.username = nuovo_username
        db.commit()
        print(f"✔ Nickname aggiornato: '{username}' -> '{nuovo_username}'.")
    finally:
        db.close()


def imposta_attivo(username: str, attivo: bool) -> None:
    init_db()
    username = username.strip().lower()
    db = SessionLocal()
    try:
        utente = _trova_utente(db, username)
        utente.is_active = attivo
        db.commit()
        stato = "riattivato" if attivo else "disattivato"
        print(f"✔ Utente '{username}' {stato}. Le sue sessioni già aperte scadranno da sole "
              f"(nessuna disconnessione immediata).")
    finally:
        db.close()


def elimina_utente(username: str, force: bool) -> None:
    init_db()
    username = username.strip().lower()
    db = SessionLocal()
    try:
        utente = _trova_utente(db, username)
        if not force:
            risposta = input(
                f"Eliminare definitivamente l'utente '{username}'? "
                "Le interazioni/note già registrate restano ma senza autore associato. "
                "Scrivi 'si' per confermare: "
            )
            if risposta.strip().lower() != "si":
                print("Annullato.")
                return
        db.delete(utente)
        db.commit()
        print(f"✔ Utente '{username}' eliminato.")
    finally:
        db.close()


def elenca_utenti() -> None:
    init_db()
    db = SessionLocal()
    try:
        utenti = db.execute(select(User).order_by(User.created_at)).scalars().all()
        if not utenti:
            print("Nessun utente. Creane uno con: python -m app.cli create-user --username ...")
            return
        for u in utenti:
            stato = "attivo" if u.is_active else "disattivato"
            ultimo = u.last_login_at.strftime("%d/%m/%Y %H:%M") if u.last_login_at else "mai"
            if u.username:
                nickname = u.username
            else:
                riferimento = f", era: {u.email}" if u.email else ""
                nickname = (
                    f"(nessun nickname{riferimento} — esegui: "
                    f'set-username --username "" --nuovo-username <nuovo>)'
                )
            print(f"- {nickname} ({u.nome}) — {stato}, ultimo accesso: {ultimo}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Amministrazione della dashboard HoReCa Leads")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_create = sub.add_parser("create-user", help="Crea un nuovo utente")
    p_create.add_argument("--username", required=True, help="Nickname di accesso (non l'email)")
    p_create.add_argument("--password", default=None, help="Se omessa viene chiesta in modo sicuro")
    p_create.add_argument("--nome", default="")

    p_pw = sub.add_parser("set-password", help="Cambia la password di un utente")
    p_pw.add_argument("--username", required=True)
    p_pw.add_argument("--password", default=None)

    p_username = sub.add_parser("set-username", help="Rinomina il nickname di un utente")
    p_username.add_argument("--username", required=True, help="Nickname attuale")
    p_username.add_argument("--nuovo-username", required=True, dest="nuovo_username")

    p_deact = sub.add_parser("deactivate-user", help="Disattiva un utente (reversibile, non elimina nulla)")
    p_deact.add_argument("--username", required=True)

    p_act = sub.add_parser("activate-user", help="Riattiva un utente disattivato")
    p_act.add_argument("--username", required=True)

    p_del = sub.add_parser("delete-user", help="Elimina definitivamente un utente")
    p_del.add_argument("--username", required=True)
    p_del.add_argument("--force", action="store_true", help="Salta la conferma interattiva")

    sub.add_parser("list-users", help="Elenca gli utenti")

    args = parser.parse_args()
    if args.comando == "create-user":
        crea_utente(args.username, args.password, args.nome)
    elif args.comando == "set-password":
        cambia_password(args.username, args.password)
    elif args.comando == "set-username":
        cambia_username(args.username, args.nuovo_username)
    elif args.comando == "deactivate-user":
        imposta_attivo(args.username, False)
    elif args.comando == "activate-user":
        imposta_attivo(args.username, True)
    elif args.comando == "delete-user":
        elimina_utente(args.username, args.force)
    elif args.comando == "list-users":
        elenca_utenti()


if __name__ == "__main__":
    main()
