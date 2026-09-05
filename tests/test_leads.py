"""Test su deduplica, import, pipeline commerciale, filtri ed export."""

from scraper.models import PlaceResult

from app.models import Lead, LeadStatus
from app.services.leads import (
    aggiorna_status,
    calcola_dedup_key,
    cerca_leads,
    importa_risultati,
    leads_to_csv,
    registra_interazione,
)
from tests.conftest import crea_lead


def place(**kwargs) -> PlaceResult:
    dati = {
        "category": "hotel",
        "name": "Hotel Aurora",
        "address": "Viale Ceccarini 10, Riccione",
        "province_or_region": "Riccione",
        "phone": "0541 111111",
        "email": "info@aurora.it",
        "website": "https://www.hotelaurora.it",
    }
    dati.update(kwargs)
    return PlaceResult(**dati)


# --- Deduplica --------------------------------------------------------------

def test_dedup_key_usa_il_dominio_quando_disponibile():
    a = calcola_dedup_key("Hotel Aurora", "Via A 1", "0541 1", "https://www.hotelaurora.it/")
    b = calcola_dedup_key("HOTEL AURORA srl", "Via B 2", "0541 2", "http://hotelaurora.it/contatti")
    assert a == b == "web:hotelaurora.it"


def test_dedup_key_usa_il_telefono_senza_sito():
    a = calcola_dedup_key("Trattoria Da Mario", "Via Roma 1", "+39 0541 123456", "")
    b = calcola_dedup_key("Da Mario Trattoria", "Via Roma", "0541 123456", "")
    assert a == b


def test_dedup_key_ricade_su_nome_e_indirizzo():
    a = calcola_dedup_key("Osteria dell'Angolo", "Via Verdi 3, Cattolica", "", "")
    b = calcola_dedup_key("OSTERIA DELL ANGOLO", "via verdi 3, cattolica", "", "")
    assert a == b
    assert a.startswith("nome:")


def test_dedup_key_distingue_strutture_diverse():
    a = calcola_dedup_key("Hotel Mare", "Via A 1", "", "")
    b = calcola_dedup_key("Hotel Monte", "Via A 1", "", "")
    assert a != b


# --- Import -----------------------------------------------------------------

def test_import_crea_lead_nuovi(db):
    nuovi, duplicati = importa_risultati(db, [place(), place(name="Hotel Blu", website="https://blu.it")], "google")
    assert len(nuovi) == 2
    assert duplicati == 0
    assert db.query(Lead).count() == 2


def test_import_non_duplica_lo_stesso_posto(db):
    importa_risultati(db, [place()], "google")
    nuovi, duplicati = importa_risultati(db, [place()], "google")
    assert nuovi == []
    assert duplicati == 1
    assert db.query(Lead).count() == 1


def test_import_deduplica_dentro_lo_stesso_batch(db):
    nuovi, duplicati = importa_risultati(db, [place(), place(name="Hotel Aurora Beach")], "google")
    assert len(nuovi) == 1  # stesso sito web → stessa struttura
    assert duplicati == 1


def test_import_arricchisce_i_campi_vuoti(db):
    """Un secondo passaggio completa i dati mancanti senza sovrascrivere quelli buoni."""
    importa_risultati(db, [place(email="", instagram="")], "osm")
    importa_risultati(db, [place(email="nuova@aurora.it", instagram="https://instagram.com/aurora")], "google")

    lead = db.query(Lead).one()
    assert lead.email == "nuova@aurora.it"
    assert lead.instagram == "https://instagram.com/aurora"


def test_import_non_sovrascrive_dati_esistenti(db):
    importa_risultati(db, [place(email="originale@aurora.it")], "google")
    importa_risultati(db, [place(email="diversa@aurora.it")], "google")
    assert db.query(Lead).one().email == "originale@aurora.it"


def test_import_salva_valutazioni(db):
    nuovi, _ = importa_risultati(db, [place(rating=4.6, user_ratings_total=812)], "google")
    assert nuovi[0].valutazione == 4.6
    assert nuovi[0].numero_recensioni == 812


# --- Pipeline ---------------------------------------------------------------

def test_lead_nasce_nuovo(db):
    lead = crea_lead(db)
    assert lead.status == LeadStatus.NUOVO.value


def test_registrare_un_contatto_avanza_la_pipeline(db):
    lead = crea_lead(db)
    registra_interazione(db, lead, canale="telefono", esito="inviato")
    assert lead.status == LeadStatus.CONTATTATO.value
    assert lead.primo_contatto_at is not None
    assert lead.ultimo_contatto_at is not None


def test_risposta_positiva_porta_a_risposto(db):
    lead = crea_lead(db)
    registra_interazione(db, lead, canale="email", esito="risposta_positiva")
    assert lead.status == LeadStatus.RISPOSTO.value
    assert lead.risposta_at is not None


def test_la_pipeline_non_torna_indietro_da_sola(db):
    lead = crea_lead(db)
    aggiorna_status(db, lead, LeadStatus.IN_TRATTATIVA.value)
    registra_interazione(db, lead, canale="telefono", esito="inviato")
    assert lead.status == LeadStatus.IN_TRATTATIVA.value


def test_chiusura_registra_la_data(db):
    lead = crea_lead(db)
    aggiorna_status(db, lead, LeadStatus.CHIUSO_VINTO.value)
    assert lead.chiuso_at is not None


def test_riapertura_azzera_la_data_di_chiusura(db):
    lead = crea_lead(db)
    aggiorna_status(db, lead, LeadStatus.CHIUSO_PERSO.value)
    aggiorna_status(db, lead, LeadStatus.IN_TRATTATIVA.value)
    assert lead.chiuso_at is None


# --- Filtri ed export -------------------------------------------------------

def test_filtro_per_categoria(db):
    crea_lead(db, nome="Hotel Uno", sito_web="https://uno.it")
    crea_lead(db, nome="Da Gino", categoria="ristorante", sito_web="https://gino.it")
    assert len(cerca_leads(db, categoria="hotel")) == 1
    assert len(cerca_leads(db, categoria="ristorante")) == 1


def test_filtro_solo_contattabili(db):
    crea_lead(db, nome="Con contatti", sito_web="https://con.it")
    crea_lead(db, nome="Senza contatti", sito_web="https://senza.it", email="", telefono="")
    assert len(cerca_leads(db, solo_contattabili=True)) == 1


def test_filtro_senza_contatto(db):
    crea_lead(db, nome="Con contatti", sito_web="https://con.it")
    crea_lead(db, nome="Senza contatti", sito_web="https://senza.it", email="", telefono="")
    risultati = cerca_leads(db, senza_contatto=True)
    assert [r.nome for r in risultati] == ["Senza contatti"]


def test_filtro_status_multiplo(db):
    from app.models import LeadStatus

    a = crea_lead(db, nome="A", sito_web="https://a.it")
    b = crea_lead(db, nome="B", sito_web="https://b.it")
    c = crea_lead(db, nome="C", sito_web="https://c.it")
    a.status = LeadStatus.INCONTRO_FISSATO.value
    b.status = LeadStatus.IN_TRATTATIVA.value
    c.status = LeadStatus.CHIUSO_VINTO.value
    db.commit()

    risultati = cerca_leads(db, status="incontro_fissato,incontro_fatto,in_trattativa")
    assert {r.nome for r in risultati} == {"A", "B"}


def test_conta_segmenti(db):
    from app.models import LeadStatus
    from app.services.leads import conta_segmenti

    con = crea_lead(db, nome="Con contatti", sito_web="https://con.it")
    senza = crea_lead(db, nome="Senza contatti", sito_web="https://senza.it", email="", telefono="")
    senza.status = LeadStatus.CHIUSO_PERSO.value
    db.commit()

    conteggi = conta_segmenti(db)
    assert conteggi["con_contatto"] == 1
    assert conteggi["senza_contatto"] == 1
    assert conteggi["chiusi_persi"] == 1
    assert conteggi["chiusi_vinti"] == 0


def test_segmento_corrente(db):
    from app.services.leads import segmento_corrente

    assert segmento_corrente({"q": "", "status": "", "categoria": "", "zona": "",
                               "solo_contattabili": False, "senza_contatto": False,
                               "ordina": "recenti"}) == "tutti"
    assert segmento_corrente({"q": "", "status": "", "categoria": "", "zona": "",
                               "solo_contattabili": True, "senza_contatto": False,
                               "ordina": "recenti"}) == "con_contatto"
    assert segmento_corrente({"q": "", "status": "chiuso_vinto", "categoria": "", "zona": "",
                               "solo_contattabili": False, "senza_contatto": False,
                               "ordina": "recenti"}) == "chiusi_vinti"
    assert segmento_corrente({"q": "hotel", "status": "", "categoria": "", "zona": "",
                               "solo_contattabili": True, "senza_contatto": False,
                               "ordina": "recenti"}) == ""  # combinazione personalizzata


def test_pagina_leads_mostra_il_sottomenu_segmenti(client_auth, db):
    from app.models import LeadStatus

    crea_lead(db, nome="Vinto").status = LeadStatus.CHIUSO_VINTO.value
    db.commit()

    risposta = client_auth.get("/leads")
    for etichetta in ("Con contatto", "Senza contatto", "Contattati", "In trattativa", "Chiusi persi", "Chiusi vinti"):
        assert etichetta in risposta.text

    solo_vinti = client_auth.get("/leads?status=chiuso_vinto")
    assert "Vinto" in solo_vinti.text
    assert 'class="nav-link active"' in solo_vinti.text or "nav-link active" in solo_vinti.text


def test_ricerca_testuale(db):
    crea_lead(db, nome="Hotel Splendido", sito_web="https://splendido.it")
    crea_lead(db, nome="Trattoria Rossa", sito_web="https://rossa.it")
    risultati = cerca_leads(db, q="splendido")
    assert len(risultati) == 1
    assert risultati[0].nome == "Hotel Splendido"


def test_export_csv_contiene_intestazioni_e_dati(db):
    crea_lead(db, nome="Hotel CSV")
    csv_testo = leads_to_csv(cerca_leads(db))
    assert "nome" in csv_testo.splitlines()[0]
    assert "Hotel CSV" in csv_testo


def test_export_csv_riporta_lo_stato_leggibile(db):
    lead = crea_lead(db)
    aggiorna_status(db, lead, LeadStatus.IN_TRATTATIVA.value)
    assert "In trattativa" in leads_to_csv([lead])


def test_pagina_successiva_con_contattabili_vuoto_non_va_in_errore(client_auth):
    """Il link 'pagina successiva' generato dal template passa contattabili=""
    quando il filtro non è attivo: prima della correzione FastAPI rispondeva
    422 (bool_parsing) invece di mostrare la pagina."""
    risposta = client_auth.get("/leads?pagina=2&contattabili=")
    assert risposta.status_code == 200


def test_contattabili_accetta_anche_valori_alternativi(client_auth):
    for valore in ("true", "1", "on", "si", "TRUE"):
        risposta = client_auth.get(f"/leads?contattabili={valore}")
        assert risposta.status_code == 200, valore


def test_pagina_leads_elenca_tutte_le_categorie_nel_filtro(client_auth):
    risposta = client_auth.get("/leads")
    assert risposta.status_code == 200
    html = risposta.text
    for etichetta in ("Fotografi", "Frantoi", "Studi legali"):
        assert etichetta in html


def test_badge_categoria_usa_il_gruppo_e_l_etichetta(client_auth, db):
    from tests.conftest import crea_lead

    crea_lead(db, nome="Studio Rossi", categoria="avvocato")
    risposta = client_auth.get("/leads")
    assert "badge-professionisti" in risposta.text
    assert "Studi legali" in risposta.text


def test_testo_lead_per_claude_include_i_dati_di_contatto(db):
    from app.templating import testo_lead_per_claude
    from tests.conftest import crea_lead

    lead = crea_lead(db, nome="Hotel Prova", telefono="0541 123456", email="info@prova.it")
    testo = testo_lead_per_claude(lead, includi_interazioni=False)

    assert "Hotel Prova" in testo
    assert "0541 123456" in testo
    assert "info@prova.it" in testo
    assert "Stato pipeline" in testo


def test_pulsante_copia_per_claude_presente_su_elenco_e_scheda(client_auth, db):
    from tests.conftest import crea_lead

    lead = crea_lead(db, nome="Hotel Copiabile")

    elenco = client_auth.get("/leads")
    assert "data-copy-text=" in elenco.text
    assert "Hotel Copiabile" in elenco.text

    scheda = client_auth.get(f"/leads/{lead.id}")
    assert "data-copy-text=" in scheda.text


def test_pulsante_copia_per_claude_su_job_con_csv(client_auth, csrf, db, monkeypatch, utente):
    from app.services import scrape_runner

    def finti_risultati():
        from scraper.models import PlaceResult
        return [PlaceResult(category="hotel", name="Hotel Mock", address="", province_or_region="Riccione")]

    monkeypatch.setattr(scrape_runner, "scrape", lambda params, callbacks=None: finti_risultati())
    job = scrape_runner.crea_job(
        db, localita="Riccione", categorie=["hotel"], sorgente="osm",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    scrape_runner.esegui_job(job.id)

    risposta = client_auth.get("/scrape")
    assert f'data-copy-url="/scrape/{job.id}/csv"' in risposta.text
