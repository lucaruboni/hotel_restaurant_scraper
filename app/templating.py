"""Configurazione Jinja2 e helper di rendering."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .models import CHANNEL_LABELS, OUTCOME_LABELS, STATUS_LABELS, LeadStatus

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def formatta_data(valore: Optional[datetime], con_ora: bool = True) -> str:
    if not valore:
        return "—"
    formato = "%d/%m/%Y %H:%M" if con_ora else "%d/%m/%Y"
    return valore.strftime(formato)


def da_quanto(valore: Optional[datetime]) -> str:
    """Distanza temporale leggibile: '3 giorni fa', 'fra 2 ore'."""
    if not valore:
        return "—"
    adesso = datetime.now(timezone.utc)
    if valore.tzinfo is None:
        valore = valore.replace(tzinfo=timezone.utc)
    delta = adesso - valore
    secondi = delta.total_seconds()
    futuro = secondi < 0
    secondi = abs(secondi)

    if secondi < 60:
        testo = "pochi secondi"
    elif secondi < 3600:
        testo = f"{int(secondi // 60)} min"
    elif secondi < 86400:
        ore = int(secondi // 3600)
        testo = f"{ore} or{'a' if ore == 1 else 'e'}"
    else:
        giorni = int(secondi // 86400)
        testo = f"{giorni} giorn{'o' if giorni == 1 else 'i'}"
    return f"fra {testo}" if futuro else f"{testo} fa"


def euro(valore: Optional[float]) -> str:
    if not valore:
        return "—"
    return f"€ {valore:,.0f}".replace(",", ".")


templates.env.filters["data"] = formatta_data
templates.env.filters["da_quanto"] = da_quanto
templates.env.filters["euro"] = euro
templates.env.globals["STATUS_LABELS"] = STATUS_LABELS
templates.env.globals["CHANNEL_LABELS"] = CHANNEL_LABELS
templates.env.globals["OUTCOME_LABELS"] = OUTCOME_LABELS
templates.env.globals["LeadStatus"] = LeadStatus


def render(request: Request, template: str, contesto: dict | None = None, **kwargs):
    """Renderizza un template iniettando utente corrente, CSRF e messaggi flash."""
    dati = {
        "request": request,
        "utente": getattr(request.state, "utente", None),
        "csrf_token": getattr(request.state, "csrf_token", ""),
        "flash": request.query_params.get("msg", ""),
        "flash_tipo": request.query_params.get("tipo", "ok"),
    }
    if contesto:
        dati.update(contesto)
    return templates.TemplateResponse(request, template, dati, **kwargs)
