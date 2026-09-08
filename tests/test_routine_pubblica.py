"""Test dell'endpoint pubblico della routine: protetto da token, e — punto
critico di sicurezza — non deve MAI restituire contatti dei lead."""

import pytest

from tests.conftest import crea_lead


@pytest.fixture
def token(monkeypatch):
    from app.config import settings

    valore = "token-pubblico-di-test-molto-lungo"
    monkeypatch.setattr(settings, "routine_public_token", valore)
    return valore


def test_endpoint_chiuso_di_default(client):
    """Senza ROUTINE_PUBLIC_TOKEN configurata, l'endpoint non esiste (404)."""
    risposta = client.get("/pubblico/routine?token=qualsiasi")
    assert risposta.status_code == 404


def test_token_sbagliato_rifiutato(token, client):
    risposta = client.get("/pubblico/routine?token=sbagliato")
    assert risposta.status_code == 404


def test_senza_token_rifiutato(token, client):
    risposta = client.get("/pubblico/routine")
    assert risposta.status_code == 404


def test_token_corretto_restituisce_la_routine(token, client, db):
    crea_lead(db, nome="Nuovo Contattabile", sito_web="https://a.it")
    risposta = client.get(f"/pubblico/routine?token={token}")
    assert risposta.status_code == 200
    assert "Nuovo Contattabile" in risposta.text


def test_nessun_dato_di_contatto_nella_routine_pubblica(token, client, db):
    """Il punto critico: telefono/email/indirizzo/sito NON devono comparire
    mai, nemmeno per un lead con incontro fissato (che ha più dati esposti
    nelle altre funzionalità come l'ICS)."""
    from app.models import LeadStatus
    from datetime import datetime

    lead = crea_lead(
        db, nome="Lead Con Contatti Sensibili",
        telefono="0541 999888", email="segreto@privato.it",
        indirizzo="Via Riservata 42", sito_web="https://privatissimo.it",
    )
    lead.status = LeadStatus.INCONTRO_FISSATO.value
    lead.prossima_azione_at = datetime(2026, 12, 1, 10, 0)
    db.commit()

    risposta = client.get(f"/pubblico/routine?token={token}")
    testo = risposta.text
    assert "Lead Con Contatti Sensibili" in testo  # il nome sì
    assert "0541 999888" not in testo
    assert "segreto@privato.it" not in testo
    assert "Via Riservata 42" not in testo
    assert "privatissimo.it" not in testo
    assert "01/12 alle 10:00" in testo  # data/ora dell'incontro sì


def test_routine_pubblica_non_richiede_login(token, client):
    """A differenza di ogni altra pagina, questa non deve reindirizzare al
    login: deve funzionare per un agente esterno senza sessione."""
    risposta = client.get(f"/pubblico/routine?token={token}", follow_redirects=False)
    assert risposta.status_code == 200
