"""Fixture condivise: app isolata su database temporaneo, client autenticato.

Ogni test gira su un DB SQLite usa-e-getta e su directory dati temporanee:
il database reale e gli upload dell'utente non vengono mai toccati.
"""

import os
import tempfile
from pathlib import Path

import pytest

# Le variabili d'ambiente vanno impostate PRIMA di importare app.config.
_TMP = tempfile.mkdtemp(prefix="horeca-test-")
os.environ["SECRET_KEY"] = "chiave-di-test-non-usare-in-produzione"
os.environ["DATA_DIR"] = _TMP
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP) / 'test.db'}"
os.environ["APP_ENV"] = "test"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402

PASSWORD_TEST = "password-di-test-1"


@pytest.fixture(autouse=True)
def db_pulito():
    """Ricrea lo schema prima di ogni test: nessuno stato condiviso."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    sessione = SessionLocal()
    try:
        yield sessione
    finally:
        sessione.close()


@pytest.fixture
def utente(db) -> User:
    u = User(
        email="venditore@esempio.it",
        nome="Venditore",
        password_hash=hash_password(PASSWORD_TEST),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def client():
    """Client HTTP non autenticato."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_auth(client, utente):
    """Client con sessione aperta."""
    risposta = client.post(
        "/login",
        data={"email": utente.email, "password": PASSWORD_TEST},
        follow_redirects=False,
    )
    assert risposta.status_code == 303, "login fallito nella fixture"
    return client


@pytest.fixture
def csrf(client_auth) -> str:
    """Estrae un token CSRF valido da una pagina protetta."""
    html = client_auth.get("/scrape").text
    marcatore = 'name="csrf_token" value="'
    inizio = html.index(marcatore) + len(marcatore)
    return html[inizio : html.index('"', inizio)]


def crea_lead(db, **kwargs):
    """Helper: crea un lead con valori sensati di default."""
    from app.models import Lead
    from app.services.leads import calcola_dedup_key

    dati = {
        "categoria": "hotel",
        "nome": "Hotel Test",
        "indirizzo": "Via Roma 1, Riccione",
        "zona": "Riccione",
        "telefono": "0541 000000",
        "email": "info@hoteltest.it",
        "sito_web": "https://www.hoteltest.it",
    }
    dati.update(kwargs)
    lead = Lead(
        dedup_key=calcola_dedup_key(
            dati["nome"], dati["indirizzo"], dati.get("telefono", ""), dati.get("sito_web", "")
        ),
        **dati,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead
