"""Dashboard: metriche commerciali e stato generale."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Interaction, Lead, ScrapeJob, User
from ..services.metrics import calcola_metriche
from ..templating import render

router = APIRouter()


@router.get("/")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    metriche = calcola_metriche(db)

    ultime_interazioni = list(
        db.execute(
            select(Interaction).order_by(Interaction.occurred_at.desc()).limit(8)
        ).scalars().all()
    )
    ultimi_job = list(
        db.execute(select(ScrapeJob).order_by(ScrapeJob.created_at.desc()).limit(5)).scalars().all()
    )
    ultimi_lead = list(
        db.execute(select(Lead).order_by(Lead.created_at.desc()).limit(6)).scalars().all()
    )

    return render(
        request,
        "dashboard.html",
        {
            "m": metriche,
            "ultime_interazioni": ultime_interazioni,
            "ultimi_job": ultimi_job,
            "ultimi_lead": ultimi_lead,
            "pagina": "dashboard",
        },
    )
