"""Elenco lead, scheda lead, pipeline, interazioni ed export CSV."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import ContactChannel, InteractionOutcome, Lead, LeadStatus, User
from ..services.leads import (
    aggiorna_status,
    cerca_leads,
    leads_to_csv,
    registra_interazione,
    zone_disponibili,
)
from ..templating import render

router = APIRouter(prefix="/leads")

PER_PAGINA = 50


def _get_lead(db: Session, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Potenziale cliente non trovato")
    return lead


def _parse_data(valore: str) -> Optional[datetime]:
    """Converte un input datetime-local in datetime naive-UTC (come il DB)."""
    if not valore:
        return None
    for formato in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(valore, formato)
        except ValueError:
            continue
    return None


@router.get("")
def elenco(
    request: Request,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    q: str = Query(""),
    status: str = Query(""),
    categoria: str = Query(""),
    zona: str = Query(""),
    contattabili: bool = Query(False),
    ordina: str = Query("recenti"),
    pagina: int = Query(1, ge=1),
):
    filtri = dict(
        q=q, status=status, categoria=categoria, zona=zona,
        solo_contattabili=contattabili, ordina=ordina,
    )
    tutti = cerca_leads(db, **filtri)
    totale = len(tutti)
    inizio = (pagina - 1) * PER_PAGINA
    risultati = tutti[inizio : inizio + PER_PAGINA]

    return render(
        request,
        "leads.html",
        {
            "leads": risultati,
            "totale": totale,
            "pagina": "leads",
            "pagina_num": pagina,
            "pagine_totali": max(1, (totale + PER_PAGINA - 1) // PER_PAGINA),
            "filtri": {**filtri, "contattabili": contattabili},
            "zone": zone_disponibili(db),
        },
    )


@router.get("/export.csv")
def export_csv(
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    q: str = Query(""),
    status: str = Query(""),
    categoria: str = Query(""),
    zona: str = Query(""),
    contattabili: bool = Query(False),
    ordina: str = Query("recenti"),
):
    """Esporta in CSV esattamente i lead filtrati a schermo (già deduplicati)."""
    leads = cerca_leads(
        db, q=q, status=status, categoria=categoria, zona=zona,
        solo_contattabili=contattabili, ordina=ordina,
    )
    contenuto = leads_to_csv(leads)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return Response(
        content=contenuto.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="leads-{timestamp}.csv"'},
    )


@router.get("/{lead_id}")
def scheda(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    lead = _get_lead(db, lead_id)
    return render(
        request,
        "lead_detail.html",
        {
            "lead": lead,
            "pagina": "leads",
            "canali": list(ContactChannel),
            "esiti": list(InteractionOutcome),
            "stati": list(LeadStatus),
        },
    )


@router.post("/{lead_id}/status")
def cambia_status(
    lead_id: int,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    status: str = Form(...),
):
    lead = _get_lead(db, lead_id)
    if status not in {s.value for s in LeadStatus}:
        raise HTTPException(status_code=400, detail="Stato non valido")
    aggiorna_status(db, lead, status)
    return RedirectResponse(f"/leads/{lead_id}?msg=Stato+aggiornato", status_code=303)


@router.post("/{lead_id}/interazioni")
def aggiungi_interazione(
    lead_id: int,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    canale: str = Form(...),
    esito: str = Form(...),
    testo: str = Form(""),
    quando: str = Form(""),
):
    lead = _get_lead(db, lead_id)
    if canale not in {c.value for c in ContactChannel}:
        raise HTTPException(status_code=400, detail="Canale non valido")
    if esito not in {o.value for o in InteractionOutcome}:
        raise HTTPException(status_code=400, detail="Esito non valido")

    registra_interazione(
        db, lead, canale=canale, esito=esito, testo=testo.strip(),
        occurred_at=_parse_data(quando), user_id=utente.id,
    )
    return RedirectResponse(f"/leads/{lead_id}?msg=Contatto+registrato", status_code=303)


@router.post("/{lead_id}/dettagli")
def aggiorna_dettagli(
    lead_id: int,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    email: str = Form(""),
    telefono: str = Form(""),
    sito_web: str = Form(""),
    instagram: str = Form(""),
    facebook: str = Form(""),
    linkedin: str = Form(""),
    stelle: str = Form(""),
    valore_stimato: str = Form(""),
    prossima_azione: str = Form(""),
):
    """Correzione manuale dei contatti: lo scraper non è infallibile."""
    lead = _get_lead(db, lead_id)
    lead.email = email.strip()
    lead.telefono = telefono.strip()
    lead.sito_web = sito_web.strip()
    lead.instagram = instagram.strip()
    lead.facebook = facebook.strip()
    lead.linkedin = linkedin.strip()
    lead.stelle = stelle.strip()

    try:
        lead.valore_stimato = float(valore_stimato.replace(",", ".")) if valore_stimato.strip() else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Valore stimato non numerico")

    lead.prossima_azione_at = _parse_data(prossima_azione)
    db.commit()
    return RedirectResponse(f"/leads/{lead_id}?msg=Dati+aggiornati", status_code=303)
