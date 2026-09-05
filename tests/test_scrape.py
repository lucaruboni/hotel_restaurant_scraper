"""Test del runner di scraping: la rete esterna è sempre mockata."""

from scraper.core import ScrapeParams, parse_locations
from scraper.models import PlaceResult

from app.models import Lead, ScrapeJob
from app.services import scrape_runner


def finti_risultati():
    return [
        PlaceResult(
            category="hotel", name="Hotel Mock", address="Via Mock 1, Riccione",
            province_or_region="Riccione", phone="0541 999999",
            email="info@mock.it", website="https://www.hotelmock.it",
        ),
        PlaceResult(
            category="ristorante", name="Trattoria Mock", address="Via Mock 2, Riccione",
            province_or_region="Riccione", website="https://www.trattoriamock.it",
        ),
    ]


def test_parse_locations():
    assert parse_locations("Riccione, Misano Adriatico , Cattolica") == [
        "Riccione", "Misano Adriatico", "Cattolica",
    ]
    assert parse_locations("  ") == []


def test_params_validano_categoria_sbagliata():
    import pytest

    with pytest.raises(ValueError):
        ScrapeParams(locations=["Riccione"], categories=["pizzeria"]).validate()


def test_params_validano_sorgente_sbagliata():
    import pytest

    with pytest.raises(ValueError):
        ScrapeParams(locations=["Riccione"], source="bing").validate()


def test_job_completato_importa_i_lead(db, monkeypatch, utente):
    monkeypatch.setattr(scrape_runner, "scrape", lambda params, callbacks=None: finti_risultati())

    job = scrape_runner.crea_job(
        db, localita="Riccione", categorie=["hotel", "ristorante"], sorgente="osm",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    scrape_runner.esegui_job(job.id)

    db.expire_all()
    job = db.get(ScrapeJob, job.id)
    assert job.stato == "completato"
    assert job.trovati == 2
    assert job.nuovi == 2
    assert job.duplicati == 0
    assert db.query(Lead).count() == 2


def test_secondo_job_identico_non_duplica(db, monkeypatch, utente):
    monkeypatch.setattr(scrape_runner, "scrape", lambda params, callbacks=None: finti_risultati())

    for _ in range(2):
        job = scrape_runner.crea_job(
            db, localita="Riccione", categorie=["hotel"], sorgente="osm",
            max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
        )
        scrape_runner.esegui_job(job.id)

    db.expire_all()
    assert db.query(Lead).count() == 2  # non 4
    ultimo = db.query(ScrapeJob).order_by(ScrapeJob.id.desc()).first()
    assert ultimo.nuovi == 0
    assert ultimo.duplicati == 2


def test_job_salva_csv_dei_soli_nuovi(db, monkeypatch, utente):
    from pathlib import Path

    monkeypatch.setattr(scrape_runner, "scrape", lambda params, callbacks=None: finti_risultati())

    job = scrape_runner.crea_job(
        db, localita="Riccione", categorie=["hotel"], sorgente="osm",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    scrape_runner.esegui_job(job.id)

    db.expire_all()
    job = db.get(ScrapeJob, job.id)
    contenuto = Path(job.csv_path).read_text(encoding="utf-8-sig")
    assert "Hotel Mock" in contenuto
    assert "Trattoria Mock" in contenuto


def test_job_fallito_registra_errore(db, monkeypatch, utente):
    def esplode(params, callbacks=None):
        raise RuntimeError("API non raggiungibile")

    monkeypatch.setattr(scrape_runner, "scrape", esplode)

    job = scrape_runner.crea_job(
        db, localita="Riccione", categorie=["hotel"], sorgente="google",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    scrape_runner.esegui_job(job.id)

    db.expire_all()
    job = db.get(ScrapeJob, job.id)
    assert job.stato == "fallito"
    assert "API non raggiungibile" in job.errore


def test_avvio_scrape_da_web(client_auth, csrf, db, monkeypatch):
    """Il POST crea il job e ritorna subito: l'esecuzione è in background."""
    # Va sostituito il riferimento importato nel router, non quello nel servizio.
    monkeypatch.setattr("app.routers.scrape.avvia_job", lambda job_id: None)

    risposta = client_auth.post(
        "/scrape",
        data={
            "csrf_token": csrf, "localita": "Riccione, Cattolica",
            "categorie": ["hotel", "ristorante"], "sorgente": "osm", "max_results": "20",
        },
        follow_redirects=False,
    )
    assert risposta.status_code == 303
    job = db.query(ScrapeJob).one()
    assert job.localita == "Riccione, Cattolica"
    assert job.stato == "in_coda"


def test_scrape_senza_localita_rifiutato(client_auth, csrf):
    risposta = client_auth.post(
        "/scrape", data={"csrf_token": csrf, "localita": "  ", "categorie": ["hotel"], "sorgente": "osm"}
    )
    assert risposta.status_code == 400


def test_scrape_google_senza_chiave_rifiutato(client_auth, csrf, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "google_api_key", "")
    risposta = client_auth.post(
        "/scrape",
        data={"csrf_token": csrf, "localita": "Riccione", "categorie": ["hotel"], "sorgente": "google"},
    )
    assert risposta.status_code == 400
    assert "GOOGLE_PLACES_API_KEY" in risposta.text


def test_scrape_categoria_incompatibile_con_sorgente_rifiutata(client_auth, csrf):
    """'avvocato' richiede Google: selezionarlo con osm deve fallire con un
    errore esplicito, non con una ricerca silenziosamente vuota."""
    risposta = client_auth.post(
        "/scrape",
        data={
            "csrf_token": csrf, "localita": "Riccione",
            "categorie": ["hotel", "avvocato"], "sorgente": "osm",
        },
    )
    assert risposta.status_code == 400
    assert "avvocato" in risposta.text.lower() or "Studi legali" in risposta.text


def test_scrape_professionisti_con_google_accettato(client_auth, csrf, db, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "google_api_key", "chiave-di-test")
    monkeypatch.setattr("app.routers.scrape.avvia_job", lambda job_id: None)

    risposta = client_auth.post(
        "/scrape",
        data={
            "csrf_token": csrf, "localita": "Riccione",
            "categorie": ["avvocato", "commercialista"], "sorgente": "google",
        },
        follow_redirects=False,
    )
    assert risposta.status_code == 303
    job = db.query(ScrapeJob).one()
    assert set(job.categorie.split(",")) == {"avvocato", "commercialista"}


def test_pagina_scrape_mostra_i_tre_gruppi_di_categorie(client_auth):
    risposta = client_auth.get("/scrape")
    assert risposta.status_code == 200
    html = risposta.text
    for etichetta in ("Professionisti", "Potenziali clienti e-commerce"):
        assert etichetta in html
    # una categoria per gruppo, come prova che tutti e tre sono renderizzati
    for slug in ("bar", "avvocato", "frantoio"):
        assert f'value="{slug}"' in html
    # le categorie Google-only dichiarano la sorgente per il toggle JS
    assert 'data-sorgenti="google"' in html


def test_categoria_google_fallita_non_perde_le_altre(monkeypatch):
    """Riproduce il bug reale: 'architect' non è un includedType valido e Google
    risponde 400 sulla singola categoria. Le altre categorie/località dello
    stesso job non devono andare perse."""
    from scraper import core

    class ClientFinto:
        def __init__(self, api_key=None):
            pass

        def search_places(self, location, category, max_results):
            if category == "architetto":
                raise Exception("400 Client Error: Bad Request")
            yield {"id": f"{category}-1", "displayName": {"text": f"Studio {category}"}}

        def parse_place(self, place, category, location):
            return PlaceResult(
                category=category, name=place["displayName"]["text"],
                address="", province_or_region=location,
            )

    monkeypatch.setattr("scraper.google_places.GooglePlacesClient", ClientFinto)

    params = core.ScrapeParams(
        locations=["Riccione"], categories=["commercialista", "architetto", "geometra"],
        source="google", website_enrichment=False,
    )
    avvisi = []
    risultati = core.scrape(params, core.ScrapeCallbacks(on_warning=avvisi.append))

    nomi = {r.name for r in risultati}
    assert nomi == {"Studio commercialista", "Studio geometra"}
    assert any("architetto" in a for a in avvisi)


def test_categoria_osm_fallita_non_perde_le_altre(monkeypatch):
    from scraper import core, osm_places

    class ClientFinto:
        def geocode_area(self, location):
            return {"area_id": 1, "display_name": location}

        def search_places(self, area_id, category, max_results):
            if category == "bar":
                raise osm_places.OverpassNonDisponibile("Overpass sovraccarico")
            return iter([{"type": "node", "id": 1, "tags": {"name": f"{category.title()} Mock"}}])

        def parse_place(self, elemento, category, location):
            return PlaceResult(
                category=category, name=elemento["tags"]["name"],
                address="", province_or_region=location,
            )

    monkeypatch.setattr("scraper.osm_places.OSMPlacesClient", ClientFinto)

    params = core.ScrapeParams(
        locations=["Riccione"], categories=["hotel", "bar"], source="osm", website_enrichment=False,
    )
    avvisi = []
    risultati = core.scrape(params, core.ScrapeCallbacks(on_warning=avvisi.append))

    assert [r.name for r in risultati] == ["Hotel Mock"]
    assert any("bar" in a for a in avvisi)


def test_job_con_avviso_resta_completato_ma_lo_segnala(db, monkeypatch, utente):
    def scrape_con_avviso(params, callbacks=None):
        callbacks.warning("Categoria 'architetto' a Riccione non recuperata: 400 Bad Request")
        return [finti_risultati()[0]]

    monkeypatch.setattr(scrape_runner, "scrape", scrape_con_avviso)

    job = scrape_runner.crea_job(
        db, localita="Riccione", categorie=["hotel", "architetto"], sorgente="google",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    scrape_runner.esegui_job(job.id)

    db.expire_all()
    job = db.get(ScrapeJob, job.id)
    assert job.stato == "completato"
    assert "architetto" in job.errore
    assert job.nuovi == 1


def test_architetto_non_ha_included_type_google():
    """Regressione: 'architect' non è un tipo valido nell'API Google (verificato
    dal vivo, risponde 400 INVALID_ARGUMENT). Non deve essere reintrodotto senza
    aver prima controllato la tabella ufficiale dei tipi supportati."""
    from scraper.google_places import CATEGORY_INCLUDED_TYPE

    assert "architetto" not in CATEGORY_INCLUDED_TYPE


def test_should_stop_ferma_subito_la_ricerca_osm(monkeypatch):
    """cb.should_stop() deve interrompere il ciclo appena viene richiesto,
    senza perdere i risultati già raccolti nelle categorie precedenti."""
    from scraper import core

    class ClientFinto:
        def geocode_area(self, location):
            return {"area_id": 1, "display_name": location}

        def search_places(self, area_id, category, max_results):
            return iter([{"type": "node", "id": 1, "tags": {"name": f"{category.title()} Mock"}}])

        def parse_place(self, elemento, category, location):
            return PlaceResult(category=category, name=elemento["tags"]["name"], address="", province_or_region=location)

    monkeypatch.setattr("scraper.osm_places.OSMPlacesClient", ClientFinto)

    risultati_raccolti = {"n": 0}

    def should_stop():
        # Diventa vero solo DOPO che il primo risultato (categoria 'hotel') è
        # stato aggiunto: verifica che lo stop non tronchi la categoria in
        # corso, ma impedisca a quella successiva ('ristorante') di partire.
        return risultati_raccolti["n"] >= 1

    params = core.ScrapeParams(
        locations=["Riccione"], categories=["hotel", "ristorante", "bar"],
        source="osm", website_enrichment=False,
    )
    risultati = core.scrape(
        params,
        core.ScrapeCallbacks(
            on_place=lambda _r: risultati_raccolti.__setitem__("n", risultati_raccolti["n"] + 1),
            on_should_stop=should_stop,
        ),
    )

    assert [r.name for r in risultati] == ["Hotel Mock"]


def test_job_fermato_dall_utente_diventa_annullato(db, monkeypatch, utente):
    """Riproduce il flusso reale: l'utente preme 'Ferma' mentre il job gira,
    scrivendo annullamento_richiesto=True da un'altra sessione DB."""

    def scrape_che_controlla_stop(params, callbacks=None):
        risultati = [finti_risultati()[0]]
        # Simula il ciclo di scraping: dopo il primo risultato, il runner
        # deve accorgersi della richiesta di stop scritta nel frattempo.
        assert callbacks.should_stop() is True
        return risultati

    monkeypatch.setattr(scrape_runner, "scrape", scrape_che_controlla_stop)

    job = scrape_runner.crea_job(
        db, localita="Riccione", categorie=["hotel"], sorgente="osm",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    job.annullamento_richiesto = True
    db.commit()

    scrape_runner.esegui_job(job.id)

    db.expire_all()
    job = db.get(ScrapeJob, job.id)
    assert job.stato == "annullato"
    assert job.nuovi == 1  # il risultato raccolto prima dello stop resta salvato


def test_annulla_job_in_coda(client_auth, csrf, db, utente):
    job = scrape_runner.crea_job(
        db, localita="Riccione", categorie=["hotel"], sorgente="osm",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    assert job.stato == "in_coda"

    risposta = client_auth.post(
        f"/scrape/{job.id}/annulla", data={"csrf_token": csrf}, follow_redirects=False
    )
    assert risposta.status_code == 303

    db.expire_all()
    job = db.get(ScrapeJob, job.id)
    assert job.annullamento_richiesto is True


def test_annulla_job_gia_completato_non_ha_effetto(client_auth, csrf, db, utente):
    job = scrape_runner.crea_job(
        db, localita="Riccione", categorie=["hotel"], sorgente="osm",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    job.stato = "completato"
    db.commit()

    risposta = client_auth.post(
        f"/scrape/{job.id}/annulla", data={"csrf_token": csrf}, follow_redirects=False
    )
    assert risposta.status_code == 303

    db.expire_all()
    job = db.get(ScrapeJob, job.id)
    assert job.annullamento_richiesto is False


def test_annulla_job_inesistente_404(client_auth, csrf):
    risposta = client_auth.post("/scrape/999999/annulla", data={"csrf_token": csrf})
    assert risposta.status_code == 404


def test_recupera_job_interrotti_dal_riavvio(db, utente):
    """All'avvio del processo un job 'in_corso' non può essere reale: il
    thread che lo eseguiva è morto con il processo precedente."""
    in_corso = scrape_runner.crea_job(
        db, localita="Riccione", categorie=["hotel"], sorgente="osm",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    in_corso.stato = "in_corso"
    in_coda = scrape_runner.crea_job(
        db, localita="Cattolica", categorie=["hotel"], sorgente="osm",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    completato = scrape_runner.crea_job(
        db, localita="Rimini", categorie=["hotel"], sorgente="osm",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    completato.stato = "completato"
    db.commit()

    n = scrape_runner.recupera_job_interrotti()
    assert n == 2  # in_corso e in_coda, non il completato

    db.expire_all()
    assert db.get(ScrapeJob, in_corso.id).stato == "fallito"
    assert db.get(ScrapeJob, in_coda.id).stato == "fallito"
    assert db.get(ScrapeJob, completato.id).stato == "completato"
    assert "riavvio" in db.get(ScrapeJob, in_corso.id).errore.lower()


def test_recupera_job_interrotti_nessun_effetto_se_tutto_fermo(db):
    assert scrape_runner.recupera_job_interrotti() == 0


def test_riprova_job_fallito_ricrea_con_gli_stessi_parametri(client_auth, csrf, db, utente, monkeypatch):
    monkeypatch.setattr("app.routers.scrape.avvia_job", lambda job_id: None)

    vecchio = scrape_runner.crea_job(
        db, localita="Riccione, Cattolica", categorie=["hotel", "ristorante"], sorgente="osm",
        max_results=25, con_recensioni=False, con_arricchimento=True, user_id=utente.id,
    )
    vecchio.stato = "fallito"
    vecchio.errore = "Overpass sovraccarico"
    db.commit()

    risposta = client_auth.post(
        f"/scrape/{vecchio.id}/riprova", data={"csrf_token": csrf}, follow_redirects=False
    )
    assert risposta.status_code == 303

    nuovo = db.query(ScrapeJob).order_by(ScrapeJob.id.desc()).first()
    assert nuovo.id != vecchio.id
    assert nuovo.localita == "Riccione, Cattolica"
    assert set(nuovo.categorie.split(",")) == {"hotel", "ristorante"}
    assert nuovo.sorgente == "osm"
    assert nuovo.max_results == 25
    assert nuovo.con_arricchimento is True
    assert nuovo.stato == "in_coda"


def test_riprova_job_annullato_accettato(client_auth, csrf, db, utente, monkeypatch):
    monkeypatch.setattr("app.routers.scrape.avvia_job", lambda job_id: None)

    vecchio = scrape_runner.crea_job(
        db, localita="Rimini", categorie=["bar"], sorgente="osm",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    vecchio.stato = "annullato"
    db.commit()

    risposta = client_auth.post(
        f"/scrape/{vecchio.id}/riprova", data={"csrf_token": csrf}, follow_redirects=False
    )
    assert risposta.status_code == 303


def test_riprova_job_completato_rifiutata(client_auth, csrf, db, utente):
    job = scrape_runner.crea_job(
        db, localita="Rimini", categorie=["hotel"], sorgente="osm",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    job.stato = "completato"
    db.commit()

    risposta = client_auth.post(f"/scrape/{job.id}/riprova", data={"csrf_token": csrf})
    assert risposta.status_code == 400


def test_riprova_job_google_senza_chiave_rifiutata(client_auth, csrf, db, utente, monkeypatch):
    from app.config import settings

    job = scrape_runner.crea_job(
        db, localita="Rimini", categorie=["avvocato"], sorgente="google",
        max_results=10, con_recensioni=False, con_arricchimento=False, user_id=utente.id,
    )
    job.stato = "fallito"
    db.commit()

    monkeypatch.setattr(settings, "google_api_key", "")
    risposta = client_auth.post(f"/scrape/{job.id}/riprova", data={"csrf_token": csrf})
    assert risposta.status_code == 400


def test_riprova_job_inesistente_404(client_auth, csrf):
    risposta = client_auth.post("/scrape/999999/riprova", data={"csrf_token": csrf})
    assert risposta.status_code == 404
