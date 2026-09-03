"""Avvio e monitoraggio dei job di scraping."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from scraper.core import CATEGORIE_VALIDE, SORGENTI_VALIDE, parse_locations

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import ScrapeJob, User
from ..services.scrape_runner import avvia_job, crea_job
from ..templating import render

router = APIRouter(prefix="/scrape")


@router.get("")
def pagina_scrape(
    request: Request,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    job = list(
        db.execute(select(ScrapeJob).order_by(ScrapeJob.created_at.desc()).limit(25)).scalars().all()
    )
    in_corso = any(j.stato in ("in_coda", "in_corso") for j in job)
    return render(
        request,
        "scrape.html",
        {
            "jobs": job,
            "in_corso": in_corso,
            "google_disponibile": bool(settings.google_api_key),
            "max_results_cap": settings.max_results_cap,
            "pagina": "scrape",
        },
    )


@router.post("")
def avvia_scrape(
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    localita: str = Form(...),
    categorie: list[str] = Form(default=["hotel", "ristorante"]),
    sorgente: str = Form("osm"),
    max_results: int = Form(40),
    recensioni: bool = Form(False),
    arricchimento: bool = Form(True),
):
    localita_pulite = parse_locations(localita)
    if not localita_pulite:
        raise HTTPException(status_code=400, detail="Indica almeno una località")

    categorie_pulite = [c for c in categorie if c in CATEGORIE_VALIDE]
    if not categorie_pulite:
        raise HTTPException(status_code=400, detail="Seleziona almeno una categoria")

    if sorgente not in SORGENTI_VALIDE:
        raise HTTPException(status_code=400, detail="Sorgente non valida")
    if sorgente == "google" and not settings.google_api_key:
        raise HTTPException(
            status_code=400,
            detail="Sorgente Google selezionata ma GOOGLE_PLACES_API_KEY non è configurata nel .env",
        )

    max_results = max(1, min(max_results, settings.max_results_cap))

    job = crea_job(
        db,
        localita=", ".join(localita_pulite),
        categorie=categorie_pulite,
        sorgente=sorgente,
        max_results=max_results,
        con_recensioni=recensioni,
        con_arricchimento=arricchimento,
        user_id=utente.id,
    )
    avvia_job(job.id)
    return RedirectResponse("/scrape?msg=Scraping+avviato", status_code=303)


@router.get("/stato", response_class=None)
def stato_jobs(
    request: Request,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    """Frammento HTML per l'aggiornamento live della tabella job (HTMX)."""
    job = list(
        db.execute(select(ScrapeJob).order_by(ScrapeJob.created_at.desc()).limit(25)).scalars().all()
    )
    in_corso = any(j.stato in ("in_coda", "in_corso") for j in job)
    return render(request, "_jobs_table.html", {"jobs": job, "in_corso": in_corso})


@router.get("/{job_id}/csv")
def scarica_csv(
    job_id: int,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    """Scarica il CSV dei soli lead nuovi prodotti dal job."""
    job = db.get(ScrapeJob, job_id)
    if job is None or not job.csv_path:
        raise HTTPException(status_code=404, detail="CSV non disponibile per questo job")

    percorso = Path(job.csv_path)
    if not percorso.exists():
        raise HTTPException(status_code=404, detail="File CSV non più presente su disco")

    return FileResponse(percorso, media_type="text/csv", filename=percorso.name)
