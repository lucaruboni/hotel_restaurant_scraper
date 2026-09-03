"""Esecuzione dei job di scraping in background, con stato persistito su DB.

Il job gira in un thread separato: la richiesta HTTP ritorna subito e la UI
segue l'avanzamento leggendo la riga `ScrapeJob`.
"""

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from scraper.core import ScrapeCallbacks, ScrapeParams, scrape

from ..config import settings
from ..database import SessionLocal
from ..models import ScrapeJob, utcnow
from .leads import importa_risultati, leads_to_csv

logger = logging.getLogger(__name__)


def crea_job(
    db: Session,
    localita: str,
    categorie: list[str],
    sorgente: str,
    max_results: int,
    con_recensioni: bool,
    con_arricchimento: bool,
    user_id: int | None,
) -> ScrapeJob:
    job = ScrapeJob(
        user_id=user_id,
        localita=localita,
        categorie=",".join(categorie),
        sorgente=sorgente,
        max_results=max_results,
        con_recensioni=con_recensioni,
        con_arricchimento=con_arricchimento,
        stato="in_coda",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def avvia_job(job_id: int) -> threading.Thread:
    """Lancia il job in un thread demone e restituisce il thread (utile nei test)."""
    thread = threading.Thread(target=esegui_job, args=(job_id,), daemon=True)
    thread.start()
    return thread


def esegui_job(job_id: int) -> None:
    """Esegue lo scraping, importa i lead deduplicati e salva il CSV dei nuovi."""
    db = SessionLocal()
    try:
        job = db.get(ScrapeJob, job_id)
        if job is None:
            logger.error("Job %s inesistente", job_id)
            return

        job.stato = "in_corso"
        job.started_at = utcnow()
        db.commit()

        params = ScrapeParams(
            locations=[l.strip() for l in job.localita.split(",") if l.strip()],
            categories=[c.strip() for c in job.categorie.split(",") if c.strip()],
            source=job.sorgente,
            max_results=job.max_results,
            reviews=job.con_recensioni,
            website_enrichment=job.con_arricchimento,
            api_key=settings.google_api_key or None,
        )

        trovati = {"n": 0}

        def on_place(_result):
            trovati["n"] += 1
            # Aggiorna il contatore a blocchi per non martellare il DB.
            if trovati["n"] % 5 == 0:
                job.trovati = trovati["n"]
                db.commit()

        risultati = scrape(params, ScrapeCallbacks(on_place=on_place))

        job.trovati = len(risultati)
        db.commit()

        nuovi, duplicati = importa_risultati(db, risultati, sorgente=job.sorgente, job=job)
        job.nuovi = len(nuovi)
        job.duplicati = duplicati

        if nuovi:
            job.csv_path = _salva_csv(job, nuovi)

        job.stato = "completato"
        job.finished_at = utcnow()
        db.commit()
        logger.info("Job %s completato: %s nuovi, %s duplicati", job_id, job.nuovi, duplicati)

    except Exception as exc:
        logger.exception("Job %s fallito", job_id)
        db.rollback()
        job = db.get(ScrapeJob, job_id)
        if job:
            job.stato = "fallito"
            job.errore = str(exc)[:2000]
            job.finished_at = utcnow()
            db.commit()
    finally:
        db.close()


def _salva_csv(job: ScrapeJob, nuovi: list) -> str:
    """Salva il CSV dei soli lead nuovi (già deduplicati) del job."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    nome_file = f"job-{job.id}-{timestamp}.csv"
    percorso = Path(settings.export_dir) / nome_file
    percorso.write_text(leads_to_csv(nuovi), encoding="utf-8-sig")
    return str(percorso)
