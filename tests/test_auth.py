"""Test di autenticazione, protezione delle pagine e CSRF."""

from app.config import settings
from tests.conftest import PASSWORD_TEST


def test_pagina_login_raggiungibile(client):
    risposta = client.get("/login")
    assert risposta.status_code == 200
    assert "Accedi" in risposta.text


def test_dashboard_richiede_login(client):
    risposta = client.get("/", follow_redirects=False)
    assert risposta.status_code == 303
    assert "/login" in risposta.headers["location"]


def test_tutte_le_pagine_protette_richiedono_login(client):
    for percorso in ("/", "/leads", "/scrape", "/leads/1", "/leads/1/scheda", "/leads/export.csv"):
        risposta = client.get(percorso, follow_redirects=False)
        assert risposta.status_code == 303, f"{percorso} non protetto"
        assert "/login" in risposta.headers["location"]


def test_login_con_credenziali_valide(client, utente):
    risposta = client.post(
        "/login",
        data={"email": utente.email, "password": PASSWORD_TEST},
        follow_redirects=False,
    )
    assert risposta.status_code == 303
    assert settings.session_cookie in risposta.cookies


def test_login_password_errata_rifiutato(client, utente):
    risposta = client.post(
        "/login", data={"email": utente.email, "password": "sbagliata-xyz"}, follow_redirects=False
    )
    assert risposta.status_code == 401
    assert settings.session_cookie not in risposta.cookies


def test_login_utente_inesistente_stesso_messaggio(client, utente):
    """Nessuna enumerazione utenti: stesso messaggio per email ignota e password errata."""
    ignoto = client.post("/login", data={"email": "nessuno@esempio.it", "password": "qualcosa123"})
    errata = client.post("/login", data={"email": utente.email, "password": "qualcosa123"})
    assert ignoto.status_code == errata.status_code == 401
    assert "Email o password non corretti" in ignoto.text
    assert "Email o password non corretti" in errata.text


def test_cookie_sessione_httponly(client, utente):
    risposta = client.post(
        "/login",
        data={"email": utente.email, "password": PASSWORD_TEST},
        follow_redirects=False,
    )
    set_cookie = risposta.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie.lower() or "samesite=lax" in set_cookie.lower()


def test_dashboard_accessibile_dopo_login(client_auth):
    risposta = client_auth.get("/")
    assert risposta.status_code == 200
    assert "Dashboard" in risposta.text


def test_logout_cancella_sessione(client_auth, csrf):
    risposta = client_auth.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)
    assert risposta.status_code == 303
    dopo = client_auth.get("/", follow_redirects=False)
    assert dopo.status_code == 303


def test_post_senza_csrf_bloccato(client_auth, db, utente):
    from tests.conftest import crea_lead

    lead = crea_lead(db)
    risposta = client_auth.post(f"/leads/{lead.id}/status", data={"status": "contattato"})
    assert risposta.status_code == 403


def test_post_con_csrf_falso_bloccato(client_auth, db):
    from tests.conftest import crea_lead

    lead = crea_lead(db)
    risposta = client_auth.post(
        f"/leads/{lead.id}/status", data={"status": "contattato", "csrf_token": "token-inventato"}
    )
    assert risposta.status_code == 403


def test_header_di_sicurezza_presenti(client):
    risposta = client.get("/login")
    assert risposta.headers["X-Content-Type-Options"] == "nosniff"
    assert risposta.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in risposta.headers


def test_password_hash_non_reversibile():
    from app.security import hash_password, verify_password

    hash_pw = hash_password("password-lunga-123")
    assert hash_pw != "password-lunga-123"
    assert hash_pw.startswith("$2")
    assert verify_password("password-lunga-123", hash_pw)
    assert not verify_password("password-lunga-124", hash_pw)


def test_password_troppo_corta_rifiutata():
    import pytest

    from app.security import hash_password

    with pytest.raises(ValueError):
        hash_password("corta")


def test_rate_limit_login(client, utente):
    """Dopo troppi tentativi falliti il login viene temporaneamente bloccato."""
    from app.security import _login_attempts

    _login_attempts.clear()
    for _ in range(settings.login_max_attempts):
        client.post("/login", data={"email": utente.email, "password": "sbagliata"})

    risposta = client.post("/login", data={"email": utente.email, "password": PASSWORD_TEST})
    assert risposta.status_code == 429
    _login_attempts.clear()
