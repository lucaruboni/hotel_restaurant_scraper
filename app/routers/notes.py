"""Scheda note a pagina intera: note, allegati (foto, screenshot, file)."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Attachment, Lead, Note, User
from ..templating import render

router = APIRouter(prefix="/leads/{lead_id}")


def _get_lead(db: Session, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Potenziale cliente non trovato")
    return lead


def _get_nota(db: Session, lead_id: int, note_id: int) -> Note:
    nota = db.get(Note, note_id)
    # Verifica di appartenenza: una nota si legge solo dal lead a cui appartiene.
    if nota is None or nota.lead_id != lead_id:
        raise HTTPException(status_code=404, detail="Nota non trovata")
    return nota


@router.get("/scheda")
def scheda_note(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    """Pagina intera con tutte le note e la galleria allegati del cliente."""
    lead = _get_lead(db, lead_id)
    return render(
        request,
        "scheda_note.html",
        {
            "lead": lead,
            "note": lead.note,
            "allegati": lead.allegati,
            "pagina": "leads",
        },
    )


@router.get("/note/{note_id}")
def pagina_nota(
    lead_id: int,
    note_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    modifica: bool = False,
):
    """Singola nota a pagina intera, in lettura o in modifica."""
    lead = _get_lead(db, lead_id)
    nota = _get_nota(db, lead_id, note_id)
    return render(
        request,
        "nota.html",
        {"lead": lead, "nota": nota, "modifica": modifica, "pagina": "leads"},
    )


@router.post("/note")
def crea_nota(
    lead_id: int,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    titolo: str = Form(""),
    corpo: str = Form(""),
):
    lead = _get_lead(db, lead_id)
    nota = Note(
        lead_id=lead.id,
        user_id=utente.id,
        titolo=titolo.strip() or "Nota senza titolo",
        corpo=corpo.strip(),
    )
    db.add(nota)
    db.commit()
    db.refresh(nota)
    return RedirectResponse(f"/leads/{lead_id}/note/{nota.id}", status_code=303)


@router.post("/note/{note_id}")
def modifica_nota(
    lead_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    titolo: str = Form(""),
    corpo: str = Form(""),
    in_evidenza: bool = Form(False),
):
    nota = _get_nota(db, lead_id, note_id)
    nota.titolo = titolo.strip() or "Nota senza titolo"
    nota.corpo = corpo.strip()
    nota.in_evidenza = in_evidenza
    db.commit()
    return RedirectResponse(f"/leads/{lead_id}/note/{note_id}?msg=Nota+salvata", status_code=303)


@router.post("/note/{note_id}/elimina")
def elimina_nota(
    lead_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    nota = _get_nota(db, lead_id, note_id)
    db.delete(nota)
    db.commit()
    return RedirectResponse(f"/leads/{lead_id}/scheda?msg=Nota+eliminata", status_code=303)


@router.post("/allegati")
async def carica_allegato(
    lead_id: int,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
    file: UploadFile = File(...),
    descrizione: str = Form(""),
    note_id: str = Form(""),
):
    """Upload validato: tipo in allowlist, dimensione limitata, nome su disco casuale."""
    lead = _get_lead(db, lead_id)

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    estensione = settings.allowed_upload_types.get(content_type)
    if not estensione:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo di file non consentito ({content_type or 'sconosciuto'}). "
            "Ammessi: immagini, PDF, testo, CSV, DOCX, XLSX.",
        )

    contenuto = await file.read()
    if len(contenuto) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File troppo grande (max {settings.max_upload_bytes // (1024*1024)} MB)",
        )
    if not contenuto:
        raise HTTPException(status_code=400, detail="File vuoto")

    # Il nome su disco non deriva mai dall'input utente: niente path traversal.
    nome_su_disco = f"{uuid.uuid4().hex}{estensione}"
    percorso = Path(settings.upload_dir) / nome_su_disco
    percorso.write_bytes(contenuto)

    allegato = Attachment(
        lead_id=lead.id,
        note_id=int(note_id) if note_id.strip().isdigit() else None,
        user_id=utente.id,
        nome_originale=Path(file.filename or "file").name[:300],
        nome_su_disco=nome_su_disco,
        content_type=content_type,
        dimensione=len(contenuto),
        descrizione=descrizione.strip()[:500],
    )
    db.add(allegato)
    db.commit()

    destinazione = (
        f"/leads/{lead_id}/note/{allegato.note_id}" if allegato.note_id else f"/leads/{lead_id}/scheda"
    )
    return RedirectResponse(f"{destinazione}?msg=Allegato+caricato", status_code=303)


@router.get("/allegati/{attachment_id}")
def scarica_allegato(
    lead_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    """Serve il file solo a utenti autenticati (mai da directory statica pubblica)."""
    allegato = db.get(Attachment, attachment_id)
    if allegato is None or allegato.lead_id != lead_id:
        raise HTTPException(status_code=404, detail="Allegato non trovato")

    percorso = Path(settings.upload_dir) / allegato.nome_su_disco
    if not percorso.exists():
        raise HTTPException(status_code=404, detail="File non più presente su disco")

    return FileResponse(
        percorso,
        media_type=allegato.content_type,
        filename=allegato.nome_originale,
        content_disposition_type="inline" if allegato.is_immagine else "attachment",
    )


@router.post("/allegati/{attachment_id}/elimina")
def elimina_allegato(
    lead_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    utente: User = Depends(get_current_user),
):
    allegato = db.get(Attachment, attachment_id)
    if allegato is None or allegato.lead_id != lead_id:
        raise HTTPException(status_code=404, detail="Allegato non trovato")

    percorso = Path(settings.upload_dir) / allegato.nome_su_disco
    percorso.unlink(missing_ok=True)
    db.delete(allegato)
    db.commit()
    return RedirectResponse(f"/leads/{lead_id}/scheda?msg=Allegato+eliminato", status_code=303)
