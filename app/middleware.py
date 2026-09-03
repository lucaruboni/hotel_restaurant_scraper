"""Middleware ASGI per la protezione CSRF.

È scritto come middleware ASGI puro (non BaseHTTPMiddleware) perché deve
leggere il corpo della richiesta per estrarre il token: il corpo viene poi
riprodotto per l'applicazione a valle, che altrimenti lo troverebbe già
consumato.
"""

from typing import Iterable

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import HTMLResponse

from .security import verify_csrf

METODI_NON_SICURI = {"POST", "PUT", "PATCH", "DELETE"}

RISPOSTA_403 = (
    "<!doctype html><html lang='it'><head><meta charset='utf-8'>"
    "<title>Sessione scaduta</title></head><body style='font-family: system-ui; padding: 40px;'>"
    "<h1>403 — Sessione scaduta o richiesta non valida</h1>"
    "<p>Ricarica la pagina e riprova.</p>"
    "<p><a href='/login'>Vai al login</a></p></body></html>"
)


def _replay(body: bytes):
    """Crea un `receive` che restituisce una sola volta il corpo memorizzato."""
    inviato = False

    async def receive():
        nonlocal inviato
        if inviato:
            return {"type": "http.disconnect"}
        inviato = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


class CSRFMiddleware:
    def __init__(self, app, esenti: Iterable[str] = ()):
        self.app = app
        self.esenti = set(esenti)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        metodo = scope.get("method", "GET")
        percorso = scope.get("path", "")
        if metodo not in METODI_NON_SICURI or percorso in self.esenti:
            return await self.app(scope, receive, send)

        # Legge il corpo per intero una sola volta.
        corpo = b""
        while True:
            messaggio = await receive()
            if messaggio["type"] == "http.disconnect":
                return
            corpo += messaggio.get("body", b"")
            if not messaggio.get("more_body", False):
                break

        richiesta = Request(scope, _replay(corpo))
        try:
            form = await richiesta.form()
            token = form.get("csrf_token")
        except Exception:
            token = None

        from .deps import get_session_data  # import locale: evita cicli

        if not verify_csrf(get_session_data(richiesta), token):
            risposta = HTMLResponse(RISPOSTA_403, status_code=403)
            return await risposta(scope, _replay(b""), send)

        # Il corpo viene riproposto intatto all'applicazione.
        await self.app(scope, _replay(corpo), send)
