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
