"""Test dei comandi di amministrazione utenti (app/cli.py)."""

import pytest
from sqlalchemy import select

from app import cli
from app.models import User


def test_crea_utente_con_username(db):
    cli.crea_utente("Marco.Rossi", "password-lunga-123", "Marco")
    utente = db.execute(select(User).where(User.username == "marco.rossi")).scalar_one()
    assert utente.nome == "Marco"
    assert utente.is_active is True


def test_crea_utente_rifiuta_username_non_valido(db):
    with pytest.raises(SystemExit):
        cli.crea_utente("ma", "password-lunga-123", "")  # troppo corto
    with pytest.raises(SystemExit):
        cli.crea_utente("nome con spazi", "password-lunga-123", "")


def test_crea_utente_rifiuta_username_duplicato(db):
    cli.crea_utente("socio", "password-lunga-123", "")
    with pytest.raises(SystemExit):
        cli.crea_utente("socio", "altra-password-123", "")


def test_due_utenti_senza_email_non_collidono(db):
    """Riproduce il bug reale: su un DB legacy `email` ha ancora un vincolo
    UNIQUE (le migrazioni additive non lo rimuovono). Due utenti creati senza
    email non devono collidere sulla stessa stringa vuota."""
    cli.crea_utente("primo", "password-lunga-123", "")
    cli.crea_utente("secondo", "password-lunga-123", "")  # non deve sollevare

    utenti = {u.username: u.email for u in db.execute(select(User)).scalars()}
    assert utenti["primo"] != utenti["secondo"]
    assert utenti["primo"] and utenti["secondo"]  # nessuno dei due è vuoto


def test_cambia_password(db):
    from app.security import verify_password

    cli.crea_utente("socio", "password-vecchia-1", "")
    cli.cambia_password("socio", "password-nuova-12")

    utente = db.execute(select(User).where(User.username == "socio")).scalar_one()
    assert verify_password("password-nuova-12", utente.password_hash)


def test_cambia_username(db):
    cli.crea_utente("vecchio", "password-lunga-123", "")
    cli.cambia_username("vecchio", "nuovo")

    assert db.execute(select(User).where(User.username == "vecchio")).scalar_one_or_none() is None
    assert db.execute(select(User).where(User.username == "nuovo")).scalar_one_or_none() is not None


def test_disattiva_e_riattiva_utente(db):
    cli.crea_utente("socio", "password-lunga-123", "")

    cli.imposta_attivo("socio", False)
    assert db.execute(select(User).where(User.username == "socio")).scalar_one().is_active is False

    cli.imposta_attivo("socio", True)
    db.expire_all()
    assert db.execute(select(User).where(User.username == "socio")).scalar_one().is_active is True


def test_utente_disattivato_non_puo_fare_login(client, db):
    from tests.conftest import PASSWORD_TEST

    cli.crea_utente("socio", PASSWORD_TEST, "")
    cli.imposta_attivo("socio", False)

    risposta = client.post("/login", data={"username": "socio", "password": PASSWORD_TEST})
    assert risposta.status_code == 401


def test_elimina_utente_con_force(db):
    cli.crea_utente("socio", "password-lunga-123", "")
    cli.elimina_utente("socio", force=True)
    assert db.execute(select(User).where(User.username == "socio")).scalar_one_or_none() is None


def test_elimina_utente_senza_force_chiede_conferma(db, monkeypatch):
    cli.crea_utente("socio", "password-lunga-123", "")
    monkeypatch.setattr("builtins.input", lambda _msg: "no")
    cli.elimina_utente("socio", force=False)
    # rifiutato: l'utente resta
    assert db.execute(select(User).where(User.username == "socio")).scalar_one_or_none() is not None
