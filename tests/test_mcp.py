"""Test dell'endpoint MCP: sola lettura, protetto da token statico.

Le chiamate reali (initialize, tools/call) sono già state verificate a mano
contro il server vero durante lo sviluppo; qui si copre l'autenticazione e
che gli strumenti restituiscano dati coerenti con il database di test.
"""

import pytest

HEADERS_BASE = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def _rpc(client, token, metodo, params=None, id_=1):
    headers = {**HEADERS_BASE}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    corpo = {"jsonrpc": "2.0", "id": id_, "method": metodo}
    if params is not None:
        corpo["params"] = params
    return client.post("/mcp/", json=corpo, headers=headers)


@pytest.fixture
def token(monkeypatch):
    from app.config import settings

    valore = "token-di-test-mcp"
    monkeypatch.setattr(settings, "mcp_api_key", valore)
    return valore


def test_mcp_senza_token_rifiutato(token, client):
    risposta = _rpc(client, None, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    assert risposta.status_code == 401


def test_mcp_token_sbagliato_rifiutato(token, client):
    risposta = client.post(
        "/mcp/",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        headers={**HEADERS_BASE, "Authorization": "Bearer token-sbagliato"},
    )
    assert risposta.status_code == 401


def test_mcp_chiuso_di_default_senza_chiave_configurata(client, monkeypatch):
    """Se MCP_API_KEY non è impostata (default), l'endpoint resta chiuso
    anche passando una stringa vuota come token."""
    from app.config import settings

    monkeypatch.setattr(settings, "mcp_api_key", "")
    risposta = client.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}, headers=HEADERS_BASE)
    assert risposta.status_code == 401


def test_mcp_initialize_con_token_corretto(token, client):
    risposta = _rpc(client, token, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    assert risposta.status_code == 200
    corpo = risposta.json()
    assert corpo["result"]["serverInfo"]["name"] == "horeca-leads"


def _sessione(client, token):
    risposta = _rpc(client, token, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    return risposta.headers["mcp-session-id"]


def test_mcp_elenca_gli_strumenti(token, client):
    session = _sessione(client, token)
    risposta = client.post(
        "/mcp/", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers={**HEADERS_BASE, "Authorization": f"Bearer {token}", "Mcp-Session-Id": session},
    )
    nomi = {t["name"] for t in risposta.json()["result"]["tools"]}
    assert nomi == {"routine_di_oggi", "conteggi_segmenti", "elenco_lead", "metriche_generali"}


def test_mcp_routine_di_oggi_riflette_il_database(token, client, db):
    from datetime import timedelta

    from app.models import LeadStatus, utcnow
    from tests.conftest import crea_lead

    incontro = crea_lead(db, nome="Incontro", sito_web="https://incontro.it")
    incontro.status = LeadStatus.INCONTRO_FISSATO.value
    db.commit()

    session = _sessione(client, token)
    risposta = client.post(
        "/mcp/",
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "routine_di_oggi", "arguments": {}}},
        headers={**HEADERS_BASE, "Authorization": f"Bearer {token}", "Mcp-Session-Id": session},
    )
    import json as json_mod
    testo = risposta.json()["result"]["content"][0]["text"]
    dati = json_mod.loads(testo)
    assert dati["incontri_fissati"] == 1


def test_mcp_elenco_lead_filtra_per_segmento(token, client, db):
    from tests.conftest import crea_lead

    crea_lead(db, nome="Con contatti", sito_web="https://con.it")
    crea_lead(db, nome="Senza contatti", sito_web="https://senza.it", email="", telefono="")

    session = _sessione(client, token)
    risposta = client.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "elenco_lead", "arguments": {"segmento": "senza_contatto"}},
        },
        headers={**HEADERS_BASE, "Authorization": f"Bearer {token}", "Mcp-Session-Id": session},
    )
    risultato = risposta.json()["result"]["structuredContent"]["result"]
    assert [r["nome"] for r in risultato] == ["Senza contatti"]


def test_mcp_non_ha_strumenti_che_scrivono(token, client):
    """Verifica esplicita dell'intento 'sola lettura': nessuno strumento MCP
    deve poter aggiornare stati o registrare interazioni."""
    session = _sessione(client, token)
    risposta = client.post(
        "/mcp/", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers={**HEADERS_BASE, "Authorization": f"Bearer {token}", "Mcp-Session-Id": session},
    )
    for tool in risposta.json()["result"]["tools"]:
        assert not any(p in tool["name"] for p in ("scrivi", "aggiorna", "registra", "elimina", "crea"))
