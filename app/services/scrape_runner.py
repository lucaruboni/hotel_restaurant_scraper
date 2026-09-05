"""Esecuzione dei job di scraping in background, con stato persistito su DB.

Il job gira in un thread separato: la richiesta HTTP ritorna subito e la UI
segue l'avanzamento leggendo la riga `ScrapeJob`.
"""

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
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


def recupera_job_interrotti() -> int:
    """Da chiamare all'avvio del processo: un job 'in_coda' o 'in_corso'
    trovato a questo punto non può essere reale, perché il thread che lo
    eseguiva viveva nel processo precedente (riavvio, crash, deploy) ed è
    morto con lui. Senza questo passo il job resterebbe bloccato per sempre
    con un badge che nessuno aggiornerà più, e il pulsante "Ferma" non
    avrebbe nessun thread ad ascoltarlo. Restituisce quanti job ha corretto.
    """
    db = SessionLocal()
    try:
        pendenti = list(
            db.execute(
                select(ScrapeJob).where(ScrapeJob.stato.in_(("in_coda", "in_corso")))
            ).scalars()
        )
        for job in pendenti:
            job.stato = "fallito"
            job.errore = (
                "Interrotto da un riavvio del server prima del completamento. "
                "I risultati raccolti fino a quel momento non sono stati importati: rilancia la ricerca."
            )
            job.finished_at = utcnow()
        if pendenti:
            db.commit()
            logger.warning("%s job risultavano ancora in corso all'avvio: segnati come falliti", len(pendenti))
        return len(pendenti)
    finally:
        db.close()


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
        avvisi: list[str] = []
        fermato = {"si": False}

        def on_place(_result):
            trovati["n"] += 1
            # Aggiorna il contatore a blocchi per non martellare il DB.
            if trovati["n"] % 5 == 0:
                job.trovati = trovati["n"]
                db.commit()

        def on_warning(messaggio: str):
            avvisi.append(messaggio)
            logger.warning("Job %s: %s", job_id, messaggio)

        def dovrebbe_fermarsi() -> bool:
            # Legge la richiesta di stop da un'altra sessione (la richiesta
            # HTTP che ha premuto "Ferma"): una semplice SELECT, non passa
            # dall'identity map, quindi vede sempre il valore committato.
            if fermato["si"]:
                return True
            richiesto = db.execute(
                select(ScrapeJob.annullamento_richiesto).where(ScrapeJob.id == job_id)
            ).scalar_one_or_none()
            if richiesto:
                fermato["si"] = True
            return bool(richiesto)

        risultati = scrape(
            params,
            ScrapeCallbacks(on_place=on_place, on_warning=on_warning, on_should_stop=dovrebbe_fermarsi),
        )

        job.trovati = len(risultati)
        db.commit()

        nuovi, duplicati = importa_risultati(db, risultati, sorgente=job.sorgente, job=job)
        job.nuovi = len(nuovi)
        job.duplicati = duplicati

        if nuovi:
            job.csv_path = _salva_csv(job, nuovi)

        job.stato = "annullato" if fermato["si"] else "completato"
        # Una categoria o una zona rifiutata durante il job non lo fa fallire
        # (le altre potrebbero essere andate a buon fine): l'avviso resta
        # comunque visibile, riusando lo stesso campo mostrato sui job falliti.
        if avvisi:
            job.errore = "\n".join(avvisi)[:2000]
        job.finished_at = utcnow()
        db.commit()
        logger.info(
            "Job %s %s: %s nuovi, %s duplicati", job_id, job.stato, job.nuovi, duplicati
        )

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
