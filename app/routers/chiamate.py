"""Lista chiamate: i lotti di potenziali clienti pronti per il socio, da
chiamare appena ha un momento. Riusa i lead già trovati dallo scraping —
non introduce una fonte di dati separata. Gamificata (vedi
services/gamification.py): punti, livello, missioni, personaggio."""

import uuid
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.requests import Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import CHECKLIST_CHIAMATE_SLUG, ContactChannel, InteractionOutcome, Lead, PuntoEvento, User
from ..services.gamification import (
    AVATAR_SCELTE,
    PUNTI_CHECKLIST_VOCE,
    PUNTI_ESITO,
    assegna_punti,
    categorie_filtro,
    livello_di,
    missioni_con_progresso,
    verifica_missioni,
)
from ..services.leads import (
    DIMENSIONE_LOTTO_CHIAMATE,
    aggiungi_lotto_chiamate,
    conta_candidati_lotto_chiamate,
    inverti_voce_checklist,
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


def _query_filtro(categoria: str = "", gruppo: str = "") -> dict:
    if categoria:
        return {"categoria": categoria}
    if gruppo:
        return {"gruppo": gruppo}
    return {}


def _redirect(msg: str = "", categoria: str = "", gruppo: str = "", tipo: str = "ok", ancora: str = ""):
    parametri = {**({"msg": msg, "tipo": tipo} if msg else {}), **_query_filtro(categoria, gruppo)}
    frammento = f"#{ancora}" if ancora else ""
    query = f"?{urlencode(parametri)}" if parametri else ""
    return RedirectResponse(f"/chiamate{query}{frammento}", status_code=303)


@router.get("")
def elenco(
    request: Request,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    categoria: str = "",
    gruppo: str = "",
):
    return render(
        request,
        "chiamate.html",
        {
            "pagina": "chiamate",
            "lista": lista_chiamate_attiva(db, categoria=categoria, gruppo=gruppo),
            "disponibili": conta_candidati_lotto_chiamate(db, categoria=categoria, gruppo=gruppo),
            "dimensione_lotto": DIMENSIONE_LOTTO_CHIAMATE,
            "categoria_attiva": categoria,
            "gruppo_attivo": gruppo,
            "gruppi_categorie": categorie_filtro(),
            "livello": livello_di(utente.punti_totali),
            "missioni": missioni_con_progresso(db, utente),
        },
    )


@router.get("/profilo")
def profilo(
    request: Request,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    ultimi_punti = list(
        db.execute(
            select(PuntoEvento)
            .where(PuntoEvento.user_id == utente.id)
            .order_by(PuntoEvento.creato_at.desc())
            .limit(15)
        ).scalars().all()
    )
    return render(
        request,
        "chiamate_profilo.html",
        {
            "pagina": "chiamate",
            "livello": livello_di(utente.punti_totali),
            "avatar_scelte": AVATAR_SCELTE,
            "ultimi_punti": ultimi_punti,
        },
    )


@router.post("/profilo")
def salva_profilo(
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    avatar_emoji: str = Form(...),
    motto: str = Form(""),
):
    if avatar_emoji not in AVATAR_SCELTE:
        raise HTTPException(status_code=400, detail="Avatar non valido")
    utente.avatar_emoji = avatar_emoji
    utente.motto = motto.strip()[:200]
    db.commit()
    return RedirectResponse("/chiamate/profilo?msg=Personaggio+salvato", status_code=303)


@router.post("/profilo/avatar")
async def carica_avatar(
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    file: UploadFile = File(...),
):
    """Carica una foto come avatar, al posto dell'emoji — da telefono o PC.
    Stesse regole di sicurezza degli allegati: tipo in allowlist, dimensione
    limitata, nome su disco casuale (mai il nome del file caricato)."""
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    estensione = settings.allowed_avatar_types.get(content_type)
    if not estensione:
        raise HTTPException(status_code=400, detail="Formato non supportato: usa JPG, PNG o WEBP")

    contenuto = await file.read()
    if not contenuto:
        raise HTTPException(status_code=400, detail="File vuoto")
    if len(contenuto) > settings.max_avatar_bytes:
        raise HTTPException(
            status_code=413, detail=f"Immagine troppo grande (max {settings.max_avatar_bytes // (1024*1024)} MB)",
        )

    nome_su_disco = f"{uuid.uuid4().hex}{estensione}"
    (Path(settings.avatar_dir) / nome_su_disco).write_bytes(contenuto)

    vecchio = utente.avatar_immagine
    utente.avatar_immagine = nome_su_disco
    db.commit()
    if vecchio:
        (Path(settings.avatar_dir) / vecchio).unlink(missing_ok=True)

    return RedirectResponse("/chiamate/profilo?msg=Foto+caricata", status_code=303)


@router.post("/profilo/avatar/rimuovi")
def rimuovi_avatar(
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    if utente.avatar_immagine:
        (Path(settings.avatar_dir) / utente.avatar_immagine).unlink(missing_ok=True)
        utente.avatar_immagine = ""
        db.commit()
    return RedirectResponse("/chiamate/profilo?msg=Foto+rimossa", status_code=303)


@router.get("/avatar")
def avatar_foto(
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    """Serve sempre e solo la foto dell'utente della sessione corrente —
    mai da una directory statica pubblica, mai quella di un altro utente."""
    if not utente.avatar_immagine:
        raise HTTPException(status_code=404)
    percorso = Path(settings.avatar_dir) / utente.avatar_immagine
    if not percorso.exists():
        raise HTTPException(status_code=404)
    content_type = next(
        (ct for ct, ext in settings.allowed_avatar_types.items() if ext == percorso.suffix.lower()),
        "application/octet-stream",
    )
    return FileResponse(percorso, media_type=content_type)


@router.post("/aggiungi")
def aggiungi(
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    categoria: str = Form(""),
    gruppo: str = Form(""),
):
    aggiunti = aggiungi_lotto_chiamate(db, categoria=categoria, gruppo=gruppo)
    if aggiunti:
        return _redirect(f"Aggiunti {len(aggiunti)} nuovi contatti alla lista", categoria=categoria, gruppo=gruppo)
    return _redirect(
        "Nessun nuovo contatto disponibile al momento", categoria=categoria, gruppo=gruppo, tipo="attenzione",
    )


@router.post("/{lead_id}/esito")
def registra_esito(
    lead_id: int,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    esito: str = Form(...),
    categoria: str = Form(""),
    gruppo: str = Form(""),
):
    lead = _get_lead(db, lead_id)
    if esito not in {o.value for o in InteractionOutcome}:
        raise HTTPException(status_code=400, detail="Esito non valido")
    registra_interazione(
        db, lead, canale=ContactChannel.TELEFONO.value, esito=esito, user_id=utente.id,
    )
    punti = PUNTI_ESITO.get(esito, 0)
    if punti:
        assegna_punti(
            db, utente, azione="esito_chiamata", punti=punti, lead=lead, descrizione=f"Chiamata a {lead.nome}",
        )
    nuove_missioni = verifica_missioni(db, utente)

    msg = f"{lead.nome}: contatto registrato (+{punti} punti)" if punti else f"{lead.nome}: contatto registrato"
    if nuove_missioni:
        msg += " · 🎉 missione completata: " + ", ".join(m.titolo for m in nuove_missioni)
    return _redirect(msg, categoria=categoria, gruppo=gruppo)


@router.post("/{lead_id}/checklist")
def checklist(
    lead_id: int,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    voce: str = Form(...),
    categoria: str = Form(""),
    gruppo: str = Form(""),
):
    lead = _get_lead(db, lead_id)
    if voce not in CHECKLIST_CHIAMATE_SLUG:
        raise HTTPException(status_code=400, detail="Voce di checklist non valida")
    nuovo_valore = inverti_voce_checklist(db, lead, voce)
    assegna_punti(
        db, utente, azione="checklist",
        punti=PUNTI_CHECKLIST_VOCE if nuovo_valore else -PUNTI_CHECKLIST_VOCE,
        lead=lead, descrizione=f"Checklist «{voce}» su {lead.nome}",
    )
    if nuovo_valore:
        verifica_missioni(db, utente)
    return _redirect("", categoria=categoria, gruppo=gruppo, ancora=f"lead-{lead_id}")
