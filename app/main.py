"""Applicazione FastAPI: dashboard privata per la pipeline commerciale HoReCa."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import SessionLocal, init_db
from .deps import RedirectToLogin, get_session_data
from .middleware import CSRFMiddleware
from .models import User
from .routers import auth, dashboard, leads, notes, scrape
from .templating import render

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Percorsi che non richiedono un token CSRF (nessuna sessione ancora attiva).
CSRF_EXEMPT = {"/login"}

CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database pronto (%s)", settings.database_url)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Dashboard privata: scraping, pipeline commerciale e schede clienti.",
        docs_url=None,      # nessuna documentazione API pubblica su un'app privata
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.middleware("http")
    async def contesto_e_header(request: Request, call_next):
        """Popola utente/CSRF per i template e aggiunge gli header di sicurezza."""
        # Rende utente e token CSRF disponibili ai template senza riaprire il DB.
        dati = get_session_data(request)
        request.state.csrf_token = dati.get("csrf", "") if dati else ""
        request.state.utente = None
        if dati:
            db = SessionLocal()
            try:
                utente = db.get(User, dati.get("uid"))
                request.state.utente = utente if utente and utente.is_active else None
            finally:
                db.close()

        risposta = await call_next(request)
        risposta.headers["X-Content-Type-Options"] = "nosniff"
        risposta.headers["X-Frame-Options"] = "DENY"
        risposta.headers["Referrer-Policy"] = "same-origin"
        risposta.headers["Content-Security-Policy"] = CSP
        risposta.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        if settings.cookie_secure:
            risposta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return risposta

    @app.exception_handler(RedirectToLogin)
    async def _login_richiesto(request: Request, exc: RedirectToLogin):
        return RedirectResponse(f"/login?next={exc.next_url}", status_code=303)

    @app.exception_handler(HTTPException)
    async def _errore_http(request: Request, exc: HTTPException):
        if request.headers.get("accept", "").startswith("application/json"):
            raise exc
        return render(
            request,
            "errore.html",
            {"codice": exc.status_code, "messaggio": exc.detail},
            status_code=exc.status_code,
        )

    # CSRF fail-closed su ogni scrittura, prima di ogni altro middleware.
    app.add_middleware(CSRFMiddleware, esenti=CSRF_EXEMPT)

    app.include_router(auth.router, tags=["auth"])
    app.include_router(dashboard.router, tags=["dashboard"])
    app.include_router(leads.router, tags=["leads"])
    app.include_router(notes.router, tags=["note"])
    app.include_router(scrape.router, tags=["scrape"])

    return app


app = create_app()
