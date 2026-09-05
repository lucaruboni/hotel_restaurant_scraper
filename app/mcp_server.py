"""Server MCP in sola lettura: espone i dati della dashboard a Claude.

Nessuno strumento qui scrive nulla — servono solo a far leggere a Claude
(tramite un connettore remoto) la routine giornaliera, i segmenti di
potenziali clienti e le metriche, così può usarli per costruire una routine
senza che tu debba incollare dati a mano. Protetto da un token statico
(vedi `settings.mcp_api_key`): senza quello, `/mcp` risponde sempre 401.
"""

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .config import settings
from .database import SessionLocal
from .services.leads import SEGMENTI_LEAD, cerca_leads, conta_segmenti
from .services.metrics import calcola_metriche

mcp_server = MCPServer(
    name="horeca-leads",
    instructions=(
        "Accesso in sola lettura ai dati della dashboard commerciale HoReCa "
        "Leads: routine del giorno, segmenti di potenziali clienti, elenco "
        "lead ed metriche generali. Nessuno strumento qui modifica dati: per "
        "aggiornare stati o registrare contatti si usa la dashboard stessa."
    ),
)


@mcp_server.tool()
def routine_di_oggi() -> dict:
    """Cosa fare oggi sulla pipeline commerciale: nuovi lead contattabili da
    chiamare, lead da ricontattare, incontri fissati da preparare, quante
    trattative sono aperte, quante risposte aspettano un seguito."""
    db = SessionLocal()
    try:
        m = calcola_metriche(db)
        return {
            "nuovi_da_contattare": m.nuovi_da_contattare,
            "da_ricontattare": m.da_ricontattare_totale,
            "incontri_fissati": m.incontri_fissati,
            "in_trattativa": m.in_trattativa,
            "risposte_in_attesa_di_seguito": m.per_status.get("Ha risposto", 0),
        }
    finally:
        db.close()


@mcp_server.tool()
def conteggi_segmenti() -> dict:
    """Quanti potenziali clienti ci sono in ciascun segmento: con contatto,
    senza contatto, contattati, in trattativa, chiusi persi, chiusi vinti."""
    db = SessionLocal()
    try:
        conteggi = conta_segmenti(db)
        return {
            slug: {"etichetta": SEGMENTI_LEAD[slug][0], "conteggio": n}
            for slug, n in conteggi.items()
        }
    finally:
        db.close()


@mcp_server.tool()
def elenco_lead(
    segmento: str = "",
    categoria: str = "",
    zona: str = "",
    ricerca: str = "",
    limite: int = 20,
) -> list[dict]:
    """Elenca i potenziali clienti (sola lettura). `segmento` accetta:
    con_contatto, senza_contatto, contattati, in_trattativa, chiusi_persi,
    chiusi_vinti. `categoria` è uno slug (es. hotel, ristorante, avvocato).
    `ricerca` cerca su nome/indirizzo/email/telefono/zona. `limite` max 100."""
    db = SessionLocal()
    try:
        filtri: dict = {"limit": max(1, min(limite, 100))}
        if categoria:
            filtri["categoria"] = categoria
        if zona:
            filtri["zona"] = zona
        if ricerca:
            filtri["q"] = ricerca
        if segmento == "con_contatto":
            filtri["solo_contattabili"] = True
        elif segmento == "senza_contatto":
            filtri["senza_contatto"] = True
        elif segmento in SEGMENTI_LEAD:
            filtri["status"] = ",".join(SEGMENTI_LEAD[segmento][1])

        leads = cerca_leads(db, **filtri)
        return [
            {
                "id": lead.id,
                "nome": lead.nome,
                "categoria": lead.categoria,
                "zona": lead.zona,
                "indirizzo": lead.indirizzo,
                "telefono": lead.telefono,
                "email": lead.email,
                "sito_web": lead.sito_web,
                "stato_pipeline": lead.status_label,
                "valutazione": lead.valutazione,
                "valore_stimato": lead.valore_stimato,
                "ultimo_contatto": lead.ultimo_contatto_at.isoformat() if lead.ultimo_contatto_at else None,
                "prossima_azione": lead.prossima_azione_at.isoformat() if lead.prossima_azione_at else None,
            }
            for lead in leads
        ]
    finally:
        db.close()


@mcp_server.tool()
def metriche_generali() -> dict:
    """Le metriche principali della dashboard: totale lead, contattabili,
    tassi di risposta/chiusura/conversione, valore della pipeline."""
    db = SessionLocal()
    try:
        m = calcola_metriche(db)
        return {
            "totale_lead": m.totale_lead,
            "contattabili": m.contattabili,
            "tasso_contattabilita": round(m.tasso_contattabilita, 1),
            "tasso_risposta": round(m.tasso_risposta, 1),
            "tasso_chiusura": round(m.tasso_chiusura, 1),
            "conversione_totale": round(m.conversione_totale, 1),
            "valore_pipeline": m.valore_pipeline,
            "valore_vinto": m.valore_vinto,
            "vinti": m.vinti,
            "persi": m.persi,
            "in_trattativa": m.in_trattativa,
        }
    finally:
        db.close()


def crea_mcp_app():
    """Costruisce una nuova sotto-app MCP, con un `session_manager` proprio.

    L'SDK vieta di avviare due volte lo stesso `session_manager` (vedi
    `StreamableHTTPSessionManager.run()`): va bene per un processo che parte
    una volta sola, ma rompe ogni scenario con più avvii sullo stesso
    oggetto — inclusa la suite di test, che apre un `TestClient` per test.
    Per questo se ne crea una istanza nuova a ogni avvio del lifespan
    (vedi `main.py`), invece di tenerne una sola a livello di modulo.

    Nessun rebinding-DNS check: l'endpoint è già dietro Tailscale (rete
    privata) più il token statico sotto. Senza questo, un host come
    "sommelier-1...ts.net" verrebbe rifiutato dalla protezione pensata per
    deployment su localhost.
    """
    return mcp_server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


class RichiedeTokenMCP:
    """Middleware ASGI minimale: senza `Authorization: Bearer <token>`
    corretto, l'endpoint MCP risponde sempre 401. Token vuoto = endpoint
    sempre chiuso (comportamento di default, vedi Settings.mcp_api_key)."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        atteso = f"Bearer {self.token}".encode()
        ricevuto = headers.get(b"authorization", b"")
        if not self.token or ricevuto != atteso:
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({"type": "http.response.body", "body": b"Non autorizzato"})
            return

        await self.app(scope, receive, send)


class MontaggioMCP:
    """Punto di mount stabile in `main.py`: la vera sotto-app (con il suo
    session_manager) viene creata da capo a ogni avvio del lifespan e
    assegnata qui, così la route registrata una volta sola in `create_app()`
    punta sempre alla sotto-app "corrente" senza doverla rimontare."""

    def __init__(self):
        self.mcp_app = None
        self._app_protetto = None

    def imposta(self, mcp_app) -> None:
        self.mcp_app = mcp_app
        self._app_protetto = RichiedeTokenMCP(mcp_app, settings.mcp_api_key)

    async def __call__(self, scope, receive, send):
        if self._app_protetto is None:
            raise RuntimeError("MCP non inizializzato: manca l'avvio del lifespan")
        await self._app_protetto(scope, receive, send)


mcp_mount = MontaggioMCP()
