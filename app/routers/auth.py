"""Login e logout."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User, utcnow
from ..security import (
    create_session_token,
    login_rate_limited,
    register_failed_login,
    reset_login_attempts,
    verify_password,
)
from ..templating import render

router = APIRouter()

MSG_CREDENZIALI = "Nickname o password non corretti."
MSG_BLOCCATO = "Troppi tentativi falliti. Riprova fra qualche minuto."


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "sconosciuto"


@router.get("/login")
def pagina_login(request: Request):
    if request.cookies.get(settings.session_cookie):
        # Sessione già presente: la validità viene comunque verificata dalle pagine protette.
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html", {"errore": ""})


@router.post("/login")
def esegui_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    ip = _client_ip(request)
    username_norm = username.strip().lower()

    if login_rate_limited(ip, username_norm):
        return render(request, "login.html", {"errore": MSG_BLOCCATO}, status_code=429)

    utente = db.execute(select(User).where(User.username == username_norm)).scalar_one_or_none()

    # Messaggio identico per utente inesistente e password errata: nessuna enumerazione.
    if not utente or not utente.is_active or not verify_password(password, utente.password_hash):
        register_failed_login(ip, username_norm)
        return render(request, "login.html", {"errore": MSG_CREDENZIALI}, status_code=401)

    reset_login_attempts(ip, username_norm)
    utente.last_login_at = utcnow()
    db.commit()

    risposta = RedirectResponse("/", status_code=303)
    risposta.set_cookie(
        settings.session_cookie,
        create_session_token(utente.id),
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return risposta


@router.post("/logout")
def logout():
    risposta = RedirectResponse("/login?msg=Sessione+chiusa", status_code=303)
    risposta.delete_cookie(settings.session_cookie, path="/")
    return risposta
