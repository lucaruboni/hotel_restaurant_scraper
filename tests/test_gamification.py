"""Test su punti, livelli, missioni e personaggio della lista chiamate."""

import io

from app.models import Lead, MissioneCompletata, PuntoEvento
from app.services.gamification import (
    AVATAR_SCELTE,
    MISSIONI,
    assegna_punti,
    livello_di,
    missioni_con_progresso,
    verifica_missioni,
)
from app.services.leads import aggiungi_lotto_chiamate
from tests.conftest import crea_lead


# --- Livelli ------------------------------------------------------------------

def test_livello_di_parte_da_recluta():
    livello = livello_di(0)
    assert livello.nome == "Recluta"
    assert livello.percento_progresso == 0


def test_livello_di_sale_con_i_punti():
    livello = livello_di(200)
    assert livello.nome == "Cacciatore di contatti"
    assert livello.soglia_prossima == 350


def test_livello_massimo_non_ha_soglia_prossima():
    livello = livello_di(5000)
    assert livello.nome == "Leggenda del telefono"
    assert livello.soglia_prossima is None
    assert livello.percento_progresso == 100


# --- Punti ----------------------------------------------------------------

def test_assegna_punti_aggiorna_il_totale_e_registra_evento(db, utente):
    assegna_punti(db, utente, azione="checklist", punti=2, descrizione="test")
    db.refresh(utente)
    assert utente.punti_totali == 2
    assert db.query(PuntoEvento).count() == 1

    assegna_punti(db, utente, azione="checklist", punti=-2, descrizione="annullato")
    db.refresh(utente)
    assert utente.punti_totali == 0


def test_assegna_punti_non_va_mai_sotto_zero(db, utente):
    assegna_punti(db, utente, azione="checklist", punti=-10, descrizione="x")
    db.refresh(utente)
    assert utente.punti_totali == 0


def test_checklist_assegna_punti_via_http(client_auth, csrf, db, utente):
    lead = crea_lead(db, nome="Hotel Punti", telefono="0541 111222")

    client_auth.post(
        f"/chiamate/{lead.id}/checklist", data={"csrf_token": csrf, "voce": "sito"}, follow_redirects=False,
    )
    db.refresh(utente)
    assert utente.punti_totali == 2

    client_auth.post(
        f"/chiamate/{lead.id}/checklist", data={"csrf_token": csrf, "voce": "sito"}, follow_redirects=False,
    )
    db.refresh(utente)
    assert utente.punti_totali == 0


def test_esito_assegna_punti_via_http(client_auth, csrf, db, utente):
    lead = crea_lead(db, nome="Hotel Esito", telefono="0541 333444")

    client_auth.post(
        f"/chiamate/{lead.id}/esito",
        data={"csrf_token": csrf, "esito": "risposta_positiva"},
        follow_redirects=False,
    )
    db.refresh(utente)
    assert utente.punti_totali == 15


# --- Missioni ---------------------------------------------------------------

def test_missione_si_completa_e_assegna_bonus_una_sola_volta(db, utente):
    missione_hotel = next(m for m in MISSIONI if m.slug == "chiamate_hotel")
    for i in range(missione_hotel.target):
        lead = crea_lead(db, nome=f"Hotel {i}", categoria="hotel", telefono=f"0541 00{i}", sito_web=f"https://hotel{i}.it")
        lead.chk_chiamata = True
        lead.chk_email_inviata = True
    db.commit()

    nuove = verifica_missioni(db, utente)
    assert [m.slug for m in nuove] == ["chiamate_hotel"]
    db.refresh(utente)
    assert utente.punti_totali == missione_hotel.punti
    assert db.query(MissioneCompletata).count() == 1

    # Una seconda verifica non assegna di nuovo il bonus.
    assert verifica_missioni(db, utente) == []
    db.refresh(utente)
    assert utente.punti_totali == missione_hotel.punti


def test_missioni_con_progresso_riporta_lo_stato(db, utente):
    missione_hotel = next(m for m in MISSIONI if m.slug == "chiamate_hotel")
    lead = crea_lead(db, nome="Hotel Parziale", categoria="hotel", telefono="0541 555")
    lead.chk_chiamata = True
    lead.chk_email_inviata = True
    db.commit()

    stato = {r["missione"].slug: r for r in missioni_con_progresso(db, utente)}
    assert stato["chiamate_hotel"]["completati"] == 1
    assert stato["chiamate_hotel"]["completata"] is False
    assert 0 < stato["chiamate_hotel"]["percento"] < 100


def test_missione_rispetta_il_filtro_di_categoria(db, utente):
    lead_ristorante = crea_lead(db, nome="Ristorante Uno", categoria="ristorante", telefono="0541 1")
    lead_ristorante.chk_chiamata = True
    lead_ristorante.chk_email_inviata = True
    db.commit()

    missione_hotel = next(m for m in MISSIONI if m.slug == "chiamate_hotel")
    stato = {r["missione"].slug: r for r in missioni_con_progresso(db, utente)}
    assert stato[missione_hotel.slug]["completati"] == 0


def test_esito_in_lista_chiamate_puo_sbloccare_una_missione(client_auth, csrf, db, utente):
    """La missione richiede la checklist completa (chiamato + email
    inviata): registrare un esito da solo non basta, ma deve comunque
    innescare il controllo che la assegna appena la checklist la soddisfa."""
    missione_hotel = next(m for m in MISSIONI if m.slug == "chiamate_hotel")
    leads = []
    for i in range(missione_hotel.target):
        lead = crea_lead(
            db, nome=f"Hotel Call {i}", categoria="hotel", telefono=f"0541 77{i}",
            sito_web=f"https://hotelcall{i}.it",
        )
        lead.chk_chiamata = True
        lead.chk_email_inviata = True
        leads.append(lead)
    db.commit()
    aggiungi_lotto_chiamate(db, categoria="hotel", limit=10)

    for lead in leads[:-1]:
        client_auth.post(
            f"/chiamate/{lead.id}/esito", data={"csrf_token": csrf, "esito": "risposta_positiva"},
        )

    risposta = client_auth.post(
        f"/chiamate/{leads[-1].id}/esito",
        data={"csrf_token": csrf, "esito": "risposta_positiva"},
        follow_redirects=False,
    )
    assert risposta.status_code == 303

    db.refresh(utente)
    # Punti delle chiamate (15 x target) + bonus missione
    assert utente.punti_totali == 15 * missione_hotel.target + missione_hotel.punti
    assert db.query(MissioneCompletata).filter_by(user_id=utente.id, slug="chiamate_hotel").count() == 1


# --- Filtro per categoria/gruppo nella lista chiamate ------------------------

def test_filtro_categoria_nella_lista_chiamate(client_auth, db):
    crea_lead(db, nome="Hotel Filtro", categoria="hotel", telefono="0541 1", sito_web="https://h.it")
    crea_lead(db, nome="Ristorante Filtro", categoria="ristorante", telefono="0541 2", sito_web="https://r.it")
    aggiungi_lotto_chiamate(db, categoria="hotel", limit=10)
    aggiungi_lotto_chiamate(db, categoria="ristorante", limit=10)

    risposta = client_auth.get("/chiamate?categoria=hotel")
    assert "Hotel Filtro" in risposta.text
    assert "Ristorante Filtro" not in risposta.text


def test_filtro_gruppo_nella_lista_chiamate(client_auth, db):
    crea_lead(db, nome="Avvocato Filtro", categoria="avvocato", telefono="0541 3", sito_web="https://a.it")
    crea_lead(db, nome="Hotel Gruppo", categoria="hotel", telefono="0541 4", sito_web="https://h2.it")
    aggiungi_lotto_chiamate(db, gruppo="professionisti", limit=10)
    aggiungi_lotto_chiamate(db, gruppo="ricettivo", limit=10)

    risposta = client_auth.get("/chiamate?gruppo=professionisti")
    assert "Avvocato Filtro" in risposta.text
    assert "Hotel Gruppo" not in risposta.text


# --- Personaggio: avatar ed emoji --------------------------------------------

def test_pagina_profilo_si_apre(client_auth):
    risposta = client_auth.get("/chiamate/profilo")
    assert risposta.status_code == 200
    assert "Il tuo personaggio" in risposta.text


def test_salva_personaggio(client_auth, csrf, db, utente):
    emoji = AVATAR_SCELTE[0]
    risposta = client_auth.post(
        "/chiamate/profilo",
        data={"csrf_token": csrf, "avatar_emoji": emoji, "motto": "Chiudo sempre io"},
        follow_redirects=False,
    )
    assert risposta.status_code == 303
    db.refresh(utente)
    assert utente.avatar_emoji == emoji
    assert utente.motto == "Chiudo sempre io"


def test_salva_personaggio_rifiuta_emoji_non_in_lista(client_auth, csrf):
    risposta = client_auth.post(
        "/chiamate/profilo", data={"csrf_token": csrf, "avatar_emoji": "🤑🤑🤑", "motto": ""},
    )
    assert risposta.status_code == 400


def test_carica_avatar_foto(client_auth, csrf, db, utente):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    risposta = client_auth.post(
        "/chiamate/profilo/avatar",
        data={"csrf_token": csrf},
        files={"file": ("io.png", io.BytesIO(png), "image/png")},
        follow_redirects=False,
    )
    assert risposta.status_code == 303
    db.refresh(utente)
    assert utente.avatar_immagine.endswith(".png")
    assert "io" not in utente.avatar_immagine  # nome su disco mai derivato dall'input

    foto = client_auth.get("/chiamate/avatar")
    assert foto.status_code == 200
    assert foto.headers["content-type"] == "image/png"


def test_carica_avatar_rifiuta_tipo_non_immagine(client_auth, csrf):
    risposta = client_auth.post(
        "/chiamate/profilo/avatar",
        data={"csrf_token": csrf},
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert risposta.status_code == 400


def test_rimuovi_avatar(client_auth, csrf, db, utente):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    client_auth.post(
        "/chiamate/profilo/avatar", data={"csrf_token": csrf}, files={"file": ("a.png", io.BytesIO(png), "image/png")},
    )
    db.refresh(utente)
    assert utente.avatar_immagine

    client_auth.post("/chiamate/profilo/avatar/rimuovi", data={"csrf_token": csrf})
    db.refresh(utente)
    assert utente.avatar_immagine == ""
    assert client_auth.get("/chiamate/avatar").status_code == 404


def test_avatar_senza_foto_risponde_404(client_auth):
    assert client_auth.get("/chiamate/avatar").status_code == 404
