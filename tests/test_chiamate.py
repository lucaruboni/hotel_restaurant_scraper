"""Test sulla lista chiamate: selezione del lotto e registrazione degli esiti."""

from app.models import Lead, LeadStatus
from app.services.leads import (
    aggiungi_lotto_chiamate,
    conta_candidati_lotto_chiamate,
    lista_chiamate_attiva,
)
from tests.conftest import crea_lead


def test_aggiungi_lotto_prende_solo_nuovi_con_telefono(db):
    con_telefono = crea_lead(db, nome="Hotel Con Telefono", telefono="0541 111111", email="")
    crea_lead(db, nome="Hotel Senza Telefono", telefono="", sito_web="https://senzatel.it")
    gia_contattato = crea_lead(db, nome="Hotel Gia Contattato", telefono="0541 222222", sito_web="https://gia.it")
    gia_contattato.status = LeadStatus.CONTATTATO.value
    db.commit()

    lotto = aggiungi_lotto_chiamate(db, limit=10)

    assert [l.id for l in lotto] == [con_telefono.id]
    assert con_telefono.in_coda_chiamate is True
    assert con_telefono.coda_chiamate_at is not None


def test_aggiungi_lotto_non_ripropone_chi_e_gia_in_coda(db):
    crea_lead(db, nome="Hotel Uno", telefono="0541 111111", sito_web="https://uno.it")

    primo_lotto = aggiungi_lotto_chiamate(db, limit=10)
    secondo_lotto = aggiungi_lotto_chiamate(db, limit=10)

    assert len(primo_lotto) == 1
    assert secondo_lotto == []
    assert conta_candidati_lotto_chiamate(db) == 0


def test_rispetta_il_limite_del_lotto(db):
    for i in range(15):
        crea_lead(db, nome=f"Hotel {i}", telefono=f"0541 00000{i}", sito_web=f"https://hotel{i}.it")

    lotto = aggiungi_lotto_chiamate(db, limit=10)

    assert len(lotto) == 10
    assert conta_candidati_lotto_chiamate(db) == 5


def test_lead_esce_dalla_lista_dopo_un_esito(client_auth, csrf, db):
    lead = crea_lead(db, nome="Hotel Da Chiamare", telefono="0541 999999", sito_web="https://dachiamare.it")
    aggiungi_lotto_chiamate(db, limit=10)
    assert len(lista_chiamate_attiva(db)) == 1

    risposta = client_auth.post(
        f"/chiamate/{lead.id}/esito",
        data={"csrf_token": csrf, "esito": "nessuna_risposta"},
        follow_redirects=False,
    )

    assert risposta.status_code == 303
    assert lista_chiamate_attiva(db) == []
    db.refresh(lead)
    assert lead.status == LeadStatus.CONTATTATO.value
    assert len(lead.interazioni) == 1
    assert lead.interazioni[0].canale == "telefono"


def test_pagina_chiamate_richiede_login(client):
    risposta = client.get("/chiamate", follow_redirects=False)
    assert risposta.status_code == 303
    assert risposta.headers["location"].startswith("/login")


def test_checklist_si_puo_spuntare_e_despuntare(client_auth, csrf, db):
    lead = crea_lead(db, nome="Hotel Checklist", telefono="0541 444444", sito_web="https://checklist.it")

    risposta = client_auth.post(
        f"/chiamate/{lead.id}/checklist",
        data={"csrf_token": csrf, "voce": "sito"},
        follow_redirects=False,
    )
    assert risposta.status_code == 303
    assert risposta.headers["location"] == f"/chiamate#lead-{lead.id}"
    db.refresh(lead)
    assert lead.chk_sito is True
    assert lead.chk_social is False

    client_auth.post(f"/chiamate/{lead.id}/checklist", data={"csrf_token": csrf, "voce": "sito"})
    db.refresh(lead)
    assert lead.chk_sito is False


def test_checklist_rifiuta_voce_non_valida(client_auth, csrf, db):
    lead = crea_lead(db, nome="Hotel Voce Invalida", telefono="0541 555555", sito_web="https://invalida.it")

    risposta = client_auth.post(
        f"/chiamate/{lead.id}/checklist",
        data={"csrf_token": csrf, "voce": "non_esiste"},
    )
    assert risposta.status_code == 400


def test_aggiungi_lotto_via_http(client_auth, csrf, db):
    crea_lead(db, nome="Hotel Http", telefono="0541 333333", sito_web="https://http.it")

    risposta = client_auth.post(
        "/chiamate/aggiungi", data={"csrf_token": csrf}, follow_redirects=False,
    )

    assert risposta.status_code == 303
    assert len(lista_chiamate_attiva(db)) == 1
