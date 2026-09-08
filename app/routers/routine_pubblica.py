"""Endpoint pubblico, sola lettura, protetto da token — SOLO per l'agente
Claude schedulato che legge la routine da fuori la rete privata Tailscale.

Regole non negoziabili di questo file:
- Nessun dato di contatto (telefono, email, indirizzo, sito): solo nomi,
  categorie e date/ore degli incontri. Se un domani serve di più, va
  ridiscusso esplicitamente — non ampliare qui "per comodità".
- Nessuna sessione, nessun cookie: un token statico in query string,
  confrontato a tempo costante. Vuoto in `.env` = endpoint sempre 404.
- Sola lettura: nessuna route qui deve poter scrivere sul database.
"""

import hmac

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..services.leads import routine_pubblica_testo

router = APIRouter(prefix="/pubblico")


def _richiede_token(token: str = Query("")) -> None:
    if not settings.routine_public_token or not hmac.compare_digest(token, settings.routine_public_token):
        # 404, non 401/403: verso un token indovinato non conviene nemmeno
        # confermare che l'endpoint esiste.
        raise HTTPException(status_code=404)


@router.get("/routine", response_class=PlainTextResponse)
def routine_pubblica(
    db: Session = Depends(get_db),
    _verificato: None = Depends(_richiede_token),
):
    return routine_pubblica_testo(db)
