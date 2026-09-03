"""Dipendenze FastAPI condivise: utente corrente, protezione CSRF."""

from typing import Optional

from fastapi import Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User
from .security import CSRF_FIELD, read_session_token, verify_csrf


class RedirectToLogin(Exception):
    """Sollevata quando una pagina HTML richiede il login."""

    def __init__(self, next_url: str = "/"):
        self.next_url = next_url


def get_session_data(request: Request) -> Optional[dict]:
    token = request.cookies.get(settings.session_cookie)
    if not token:
        return None
    return read_session_token(token)


def get_current_user_optional(
    request: Request, db: Session = Depends(get_db)
) -> Optional[User]:
    dati = get_session_data(request)
    if not dati:
        return None
    utente = db.get(User, dati.get("uid"))
    if not utente or not utente.is_active:
        return None
    request.state.csrf_token = dati.get("csrf", "")
    return utente


def get_current_user(
    request: Request, utente: Optional[User] = Depends(get_current_user_optional)
) -> User:
    """Richiede un utente autenticato: sulle pagine HTML redirige al login."""
    if utente is None:
        raise RedirectToLogin(next_url=str(request.url.path))
    return utente


async def require_csrf(request: Request) -> None:
    """Valida il token CSRF dei form POST."""
    dati = get_session_data(request)
    form = await request.form()
    token = form.get(CSRF_FIELD)
    if not verify_csrf(dati, token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF mancante o non valido: ricarica la pagina e riprova.",
        )
