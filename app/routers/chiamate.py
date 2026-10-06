"""Lista chiamate: i lotti di potenziali clienti pronti per il socio, da
chiamare appena ha un momento. Riusa i lead già trovati dallo scraping —
non introduce una fonte di dati separata."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.requests import Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import ContactChannel, InteractionOutcome, Lead, User
from ..services.leads import (
    DIMENSIONE_LOTTO_CHIAMATE,
    aggiungi_lotto_chiamate,
    conta_candidati_lotto_chiamate,
    lista_chiamate_attiva,
    registra_interazione,
)
from ..templating import render

router = APIRouter(prefix="/chiamate")


def _get_lead(db: Session, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Potenziale cliente non trovato")
    return lead


@router.get("")
def elenco(
    request: Request,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    return render(
        request,
        "chiamate.html",
        {
            "pagina": "chiamate",
            "lista": lista_chiamate_attiva(db),
            "disponibili": conta_candidati_lotto_chiamate(db),
            "dimensione_lotto": DIMENSIONE_LOTTO_CHIAMATE,
        },
    )


@router.post("/aggiungi")
def aggiungi(
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    aggiunti = aggiungi_lotto_chiamate(db)
    if aggiunti:
        msg = f"Aggiunti {len(aggiunti)} nuovi contatti alla lista"
    else:
        msg = "Nessun nuovo contatto disponibile al momento"
        return _redirect(msg, tipo="attenzione")
    return _redirect(msg)


@router.post("/{lead_id}/esito")
def registra_esito(
    lead_id: int,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    esito: str = Form(...),
):
    lead = _get_lead(db, lead_id)
    if esito not in {o.value for o in InteractionOutcome}:
        raise HTTPException(status_code=400, detail="Esito non valido")
    registra_interazione(
        db, lead, canale=ContactChannel.TELEFONO.value, esito=esito, user_id=utente.id,
    )
    return _redirect(f"{lead.nome}: contatto registrato")


def _redirect(msg: str, tipo: str = "ok"):
    return RedirectResponse(f"/chiamate?msg={quote(msg)}&tipo={tipo}", status_code=303)
