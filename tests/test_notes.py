"""Test su scheda note, allegati e metriche."""

import io

from app.models import Attachment, LeadStatus, Note
from app.services.leads import aggiorna_status, registra_interazione
from app.services.metrics import calcola_metriche
from tests.conftest import crea_lead


# --- Note -------------------------------------------------------------------

def test_creazione_nota(client_auth, csrf, db):
    lead = crea_lead(db)
    risposta = client_auth.post(
        f"/leads/{lead.id}/note",
        data={"csrf_token": csrf, "titolo": "Prima chiamata", "corpo": "Parlato col direttore."},
        follow_redirects=False,
    )
    assert risposta.status_code == 303
    nota = db.query(Note).one()
    assert nota.titolo == "Prima chiamata"
    assert nota.lead_id == lead.id


def test_nota_senza_titolo_prende_default(client_auth, csrf, db):
    lead = crea_lead(db)
    client_auth.post(f"/leads/{lead.id}/note", data={"csrf_token": csrf, "titolo": "", "corpo": "x"})
    assert db.query(Note).one().titolo == "Nota senza titolo"


def test_pagina_nota_a_schermo_intero(client_auth, csrf, db):
    lead = crea_lead(db)
    client_auth.post(
        f"/leads/{lead.id}/note",
        data={"csrf_token": csrf, "titolo": "Contesto", "corpo": "Contenuto della nota"},
    )
    nota = db.query(Note).one()

    risposta = client_auth.get(f"/leads/{lead.id}/note/{nota.id}")
    assert risposta.status_code == 200
    assert "Contenuto della nota" in risposta.text


def test_modifica_nota(client_auth, csrf, db):
    lead = crea_lead(db)
    nota = Note(lead_id=lead.id, titolo="Vecchio", corpo="vecchio testo")
    db.add(nota)
    db.commit()

    client_auth.post(
        f"/leads/{lead.id}/note/{nota.id}",
        data={"csrf_token": csrf, "titolo": "Nuovo", "corpo": "nuovo testo"},
    )
    db.refresh(nota)
    assert nota.titolo == "Nuovo"
    assert nota.corpo == "nuovo testo"


def test_eliminazione_nota(client_auth, csrf, db):
    lead = crea_lead(db)
    nota = Note(lead_id=lead.id, titolo="Da eliminare")
    db.add(nota)
    db.commit()

    client_auth.post(f"/leads/{lead.id}/note/{nota.id}/elimina", data={"csrf_token": csrf})
    assert db.query(Note).count() == 0


def test_nota_di_un_altro_lead_non_accessibile(client_auth, db):
    """Controllo di appartenenza: la nota si legge solo dal suo lead."""
    lead_a = crea_lead(db, nome="Hotel A", sito_web="https://a.it")
    lead_b = crea_lead(db, nome="Hotel B", sito_web="https://b.it")
    nota = Note(lead_id=lead_a.id, titolo="Riservata")
    db.add(nota)
    db.commit()

    risposta = client_auth.get(f"/leads/{lead_b.id}/note/{nota.id}")
    assert risposta.status_code == 404


# --- Allegati ---------------------------------------------------------------

def test_upload_immagine(client_auth, csrf, db):
    lead = crea_lead(db)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64

    risposta = client_auth.post(
        f"/leads/{lead.id}/allegati",
        data={"csrf_token": csrf, "descrizione": "Screenshot WhatsApp"},
        files={"file": ("chat.png", io.BytesIO(png), "image/png")},
        follow_redirects=False,
    )
    assert risposta.status_code == 303
    allegato = db.query(Attachment).one()
    assert allegato.nome_originale == "chat.png"
    assert allegato.is_immagine
    # Il nome su disco non deve mai derivare dall'input utente
    assert "chat" not in allegato.nome_su_disco
    assert allegato.nome_su_disco.endswith(".png")


def test_upload_tipo_non_consentito_rifiutato(client_auth, csrf, db):
    lead = crea_lead(db)
    risposta = client_auth.post(
        f"/leads/{lead.id}/allegati",
        data={"csrf_token": csrf},
        files={"file": ("malware.exe", io.BytesIO(b"MZ..."), "application/x-msdownload")},
    )
    assert risposta.status_code == 400
    assert db.query(Attachment).count() == 0


def test_download_allegato_richiede_login(client_auth, csrf, db):
    from fastapi.testclient import TestClient

    from app.main import app

    lead = crea_lead(db)
    client_auth.post(
        f"/leads/{lead.id}/allegati",
        data={"csrf_token": csrf},
        files={"file": ("nota.txt", io.BytesIO(b"contenuto"), "text/plain")},
    )
    allegato = db.query(Attachment).one()

    # Client separato, senza cookie di sessione.
    with TestClient(app) as anonimo:
        risposta = anonimo.get(f"/leads/{lead.id}/allegati/{allegato.id}", follow_redirects=False)
    assert risposta.status_code == 303  # redirect al login, mai il file


def test_allegato_di_un_altro_lead_non_accessibile(client_auth, csrf, db):
    lead_a = crea_lead(db, nome="Hotel A", sito_web="https://a.it")
    lead_b = crea_lead(db, nome="Hotel B", sito_web="https://b.it")
    client_auth.post(
        f"/leads/{lead_a.id}/allegati",
        data={"csrf_token": csrf},
        files={"file": ("privato.txt", io.BytesIO(b"segreto"), "text/plain")},
    )
    allegato = db.query(Attachment).one()

    risposta = client_auth.get(f"/leads/{lead_b.id}/allegati/{allegato.id}")
    assert risposta.status_code == 404


# --- Metriche ---------------------------------------------------------------

def test_metriche_archivio_vuoto(db):
    m = calcola_metriche(db)
    assert m.totale_lead == 0
    assert m.tasso_risposta == 0


def test_metriche_conteggi_base(db):
    crea_lead(db, nome="Hotel Uno", sito_web="https://uno.it")
    crea_lead(db, nome="Da Gino", categoria="ristorante", sito_web="https://gino.it")
    crea_lead(db, nome="Senza contatti", sito_web="https://senza.it", email="", telefono="")

    m = calcola_metriche(db)
    assert m.totale_lead == 3
    conteggi = {slug: n for slug, _, n in m.per_categoria}
    assert conteggi["hotel"] == 2
    assert conteggi["ristorante"] == 1
    assert m.contattabili == 2


def test_metriche_funnel_e_tassi(db):
    contattato = crea_lead(db, nome="A", sito_web="https://a.it")
    risposto = crea_lead(db, nome="B", sito_web="https://b.it")
    vinto = crea_lead(db, nome="C", sito_web="https://c.it")
    crea_lead(db, nome="D", sito_web="https://d.it")  # resta nuovo

    aggiorna_status(db, contattato, LeadStatus.CONTATTATO.value)
    aggiorna_status(db, risposto, LeadStatus.RISPOSTO.value)
    aggiorna_status(db, vinto, LeadStatus.CHIUSO_VINTO.value)

    m = calcola_metriche(db)
    assert m.contattati == 3
    assert m.risposte == 2
    assert m.vinti == 1
    assert m.tasso_risposta == 2 / 3 * 100
    assert m.conversione_totale == 25.0
    assert m.funnel[0].conteggio == 4  # tutti passano da "nuovo"


def test_metriche_efficacia_canali(db):
    lead1 = crea_lead(db, nome="A", sito_web="https://a.it")
    lead2 = crea_lead(db, nome="B", sito_web="https://b.it")
    registra_interazione(db, lead1, canale="email", esito="nessuna_risposta")
    registra_interazione(db, lead2, canale="email", esito="risposta_positiva")
    registra_interazione(db, lead1, canale="telefono", esito="risposta_positiva")

    m = calcola_metriche(db)
    per_canale = {c.canale: c for c in m.canali}
    assert per_canale["email"].tentativi == 2
    assert per_canale["email"].risposte == 1
    assert per_canale["email"].tasso_risposta == 50.0
    assert per_canale["telefono"].tasso_risposta == 100.0
