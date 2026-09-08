"""Import deduplicato dei lead, filtri di ricerca ed export CSV."""

import csv
import io
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional
from urllib.parse import urlparse

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from scraper.categories import CATEGORY_LABELS

from ..models import Interaction, Lead, LeadStatus, OUTCOME_RISPOSTA, ScrapeJob, utcnow

# Campi arricchibili: se il lead esiste già e il campo è vuoto, lo completiamo.
CAMPI_ARRICCHIBILI = (
    "indirizzo",
    "telefono",
    "email",
    "sito_web",
    "instagram",
    "facebook",
    "linkedin",
    "stelle",
    "fascia_prezzo",
    "maps_url",
)


def _normalizza(testo: str) -> str:
    """Minuscolo, senza accenti, senza punteggiatura, spazi compressi."""
    if not testo:
        return ""
    testo = unicodedata.normalize("NFKD", testo)
    testo = "".join(c for c in testo if not unicodedata.combining(c))
    testo = testo.lower()
    testo = re.sub(r"[^a-z0-9\s]", " ", testo)
    return re.sub(r"\s+", " ", testo).strip()


def _dominio(url: str) -> str:
    """Estrae il dominio normalizzato da un URL (senza www e senza schema)."""
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    host = (urlparse(url).netloc or "").lower().strip()
    return host[4:] if host.startswith("www.") else host


def calcola_dedup_key(nome: str, indirizzo: str, telefono: str = "", sito_web: str = "") -> str:
    """Chiave di deduplica: dominio > telefono > nome+indirizzo normalizzati.

    L'ordine riflette l'affidabilità: due schede con lo stesso sito o lo stesso
    numero sono la stessa struttura anche se il nome è scritto diversamente.
    """
    dominio = _dominio(sito_web)
    if dominio:
        return f"web:{dominio}"

    cifre = re.sub(r"\D", "", telefono or "")
    if len(cifre) >= 8:
        return f"tel:{cifre[-9:]}"  # ultime 9 cifre: ignora prefisso internazionale

    return f"nome:{_normalizza(nome)}|{_normalizza(indirizzo)}"


def _valore_stelle(stelle: str) -> str:
    return (stelle or "").strip()


def importa_risultati(
    db: Session,
    risultati: Iterable,
    sorgente: str,
    job: Optional[ScrapeJob] = None,
) -> tuple[list[Lead], int]:
    """Importa i PlaceResult dello scraper deduplicando sui lead esistenti.

    Restituisce (lead_nuovi, numero_duplicati). I duplicati non vengono
    reinseriti: i loro campi vuoti vengono arricchiti con i nuovi dati.
    """
    nuovi: list[Lead] = []
    duplicati = 0
    chiavi_batch: dict[str, Lead] = {}

    for r in risultati:
        chiave = calcola_dedup_key(r.name, r.address, r.phone, r.website)

        esistente = chiavi_batch.get(chiave)
        if esistente is None:
            esistente = db.execute(select(Lead).where(Lead.dedup_key == chiave)).scalar_one_or_none()

        if esistente is not None:
            duplicati += 1
            _arricchisci_lead(esistente, r)
            chiavi_batch[chiave] = esistente
            continue

        lead = Lead(
            dedup_key=chiave,
            categoria=r.category,
            nome=r.name,
            indirizzo=r.address,
            zona=r.province_or_region,
            telefono=r.phone,
            email=r.email,
            sito_web=r.website,
            instagram=r.instagram,
            facebook=r.facebook,
            linkedin=r.linkedin,
            stelle=_valore_stelle(r.stars),
            fascia_prezzo=r.price_level or "",
            valutazione=r.rating,
            numero_recensioni=r.user_ratings_total,
            maps_url=r.google_maps_url,
            latitudine=r.latitude,
            longitudine=r.longitude,
            sorgente=sorgente,
            status=LeadStatus.NUOVO.value,
            scrape_job_id=job.id if job else None,
        )
        db.add(lead)
        nuovi.append(lead)
        chiavi_batch[chiave] = lead

    db.commit()
    for lead in nuovi:
        db.refresh(lead)
    return nuovi, duplicati


def _arricchisci_lead(lead: Lead, r) -> None:
    """Completa i campi vuoti di un lead esistente senza sovrascrivere nulla."""
    valori = {
        "indirizzo": r.address,
        "telefono": r.phone,
        "email": r.email,
        "sito_web": r.website,
        "instagram": r.instagram,
        "facebook": r.facebook,
        "linkedin": r.linkedin,
        "stelle": _valore_stelle(r.stars),
        "fascia_prezzo": r.price_level or "",
        "maps_url": r.google_maps_url,
    }
    for campo in CAMPI_ARRICCHIBILI:
        if not getattr(lead, campo, "") and valori.get(campo):
            setattr(lead, campo, valori[campo])
    if lead.valutazione is None and r.rating is not None:
        lead.valutazione = r.rating
    if lead.numero_recensioni is None and r.user_ratings_total is not None:
        lead.numero_recensioni = r.user_ratings_total


#: Segmenti rapidi mostrati nel sotto-menu di "Potenziali clienti": slug ->
#: (etichetta, stati di pipeline compresi — vuoto per i due basati sul contatto).
SEGMENTI_LEAD = {
    "con_contatto": ("Con contatto", ()),
    "senza_contatto": ("Senza contatto", ()),
    "contattati": ("Contattati", (LeadStatus.CONTATTATO.value,)),
    "in_trattativa": (
        "In trattativa",
        (
            LeadStatus.INCONTRO_FISSATO.value,
            LeadStatus.INCONTRO_FATTO.value,
            LeadStatus.IN_TRATTATIVA.value,
        ),
    ),
    "chiusi_persi": ("Chiusi persi", (LeadStatus.CHIUSO_PERSO.value,)),
    "chiusi_vinti": ("Chiusi vinti", (LeadStatus.CHIUSO_VINTO.value,)),
}


def cerca_leads(
    db: Session,
    q: str = "",
    status: str = "",
    categoria: str = "",
    zona: str = "",
    solo_contattabili: bool = False,
    senza_contatto: bool = False,
    ordina: str = "recenti",
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[Lead]:
    """Ricerca filtrata dei lead per la tabella e per l'export.

    `status` accetta anche più fasi separate da virgola (usato dal segmento
    "in trattativa" del sotto-menu, che comprende incontro fissato/fatto).
    """
    stmt = select(Lead)

    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Lead.nome.ilike(pattern),
                Lead.indirizzo.ilike(pattern),
                Lead.email.ilike(pattern),
                Lead.telefono.ilike(pattern),
                Lead.zona.ilike(pattern),
            )
        )
    if status:
        stati = [s.strip() for s in status.split(",") if s.strip()]
        stmt = stmt.where(Lead.status.in_(stati))
    if categoria:
        stmt = stmt.where(Lead.categoria == categoria)
    if zona:
        stmt = stmt.where(Lead.zona == zona)
    if solo_contattabili:
        stmt = stmt.where(or_(Lead.email != "", Lead.telefono != ""))
    elif senza_contatto:
        stmt = stmt.where(Lead.email == "", Lead.telefono == "")

    ordinamenti = {
        "recenti": Lead.created_at.desc(),
        "nome": Lead.nome.asc(),
        "valutazione": Lead.valutazione.desc().nullslast(),
        "aggiornati": Lead.updated_at.desc(),
        "prossima_azione": Lead.prossima_azione_at.asc().nullslast(),
    }
    stmt = stmt.order_by(ordinamenti.get(ordina, Lead.created_at.desc()))

    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)

    return list(db.execute(stmt).scalars().all())


def conta_leads(db: Session, **filtri) -> int:
    return len(cerca_leads(db, **filtri))


def zone_disponibili(db: Session) -> list[str]:
    righe = db.execute(select(Lead.zona).where(Lead.zona != "").distinct().order_by(Lead.zona)).scalars()
    return list(righe)


def href_segmento(slug: str) -> str:
    """URL del sotto-menu lead per un dato segmento (vedi `SEGMENTI_LEAD`)."""
    if slug == "con_contatto":
        return "/leads?contattabili=true"
    if slug == "senza_contatto":
        return "/leads?senza_contatto=true"
    _etichetta, stati = SEGMENTI_LEAD[slug]
    return "/leads?status=" + ",".join(stati)


def segmento_corrente(filtri: dict) -> str:
    """Slug del segmento del sotto-menu che corrisponde esattamente ai filtri
    correnti: 'tutti' se non c'è nessun filtro attivo, '' se è una
    combinazione personalizzata (arrivata dal modulo di ricerca sopra)."""
    extra_attivi = (
        bool(filtri.get("q") or filtri.get("categoria") or filtri.get("zona"))
        or filtri.get("ordina", "recenti") != "recenti"
    )
    if extra_attivi:
        return ""

    status = filtri.get("status", "")
    contattabili = filtri.get("solo_contattabili")
    senza_contatto = filtri.get("senza_contatto")

    if not status and not contattabili and not senza_contatto:
        return "tutti"
    if contattabili and not status:
        return "con_contatto"
    if senza_contatto and not status:
        return "senza_contatto"
    for slug, (_etichetta, stati) in SEGMENTI_LEAD.items():
        if slug in ("con_contatto", "senza_contatto"):
            continue
        if status == ",".join(stati):
            return slug
    return ""


def conta_segmenti(db: Session) -> dict[str, int]:
    """Conteggio per ciascun segmento rapido del sotto-menu lead."""
    conteggi: dict[str, int] = {}
    for slug, (_etichetta, stati) in SEGMENTI_LEAD.items():
        stmt = select(func.count()).select_from(Lead)
        if slug == "con_contatto":
            stmt = stmt.where(or_(Lead.email != "", Lead.telefono != ""))
        elif slug == "senza_contatto":
            stmt = stmt.where(Lead.email == "", Lead.telefono == "")
        else:
            stmt = stmt.where(Lead.status.in_(stati))
        conteggi[slug] = db.execute(stmt).scalar_one()
    return conteggi


def leads_routine_di_oggi(db: Session) -> list[Lead]:
    """I lead rilevanti per la routine di oggi (vedi dashboard): nuovi
    contattabili, da ricontattare, incontri fissati, trattative aperte.
    Un lead può comparire per più motivi ma esce una volta sola, ordinato
    per priorità (prima chi aspetta un'azione, poi i nuovi da contattare)."""
    condizione = (
        ((Lead.status == LeadStatus.NUOVO.value) & ((Lead.email != "") | (Lead.telefono != "")))
        | (Lead.prossima_azione_at.is_not(None) & Lead.status.notin_(
            [LeadStatus.CHIUSO_VINTO.value, LeadStatus.CHIUSO_PERSO.value]
        ))
        | (Lead.status == LeadStatus.INCONTRO_FISSATO.value)
        | (Lead.status == LeadStatus.IN_TRATTATIVA.value)
    )
    ordine_priorita = {
        LeadStatus.INCONTRO_FISSATO.value: 0,
        LeadStatus.IN_TRATTATIVA.value: 1,
    }
    leads = list(db.execute(select(Lead).where(condizione)).scalars().all())
    leads.sort(key=lambda l: (
        0 if l.prossima_azione_at else 1,
        ordine_priorita.get(l.status, 2),
        l.prossima_azione_at or l.created_at,
    ))
    return leads


def leads_incontri_fissati(db: Session) -> list[Lead]:
    """Incontri fissati con data/ora impostata, in ordine cronologico —
    quelli esportabili come eventi di calendario (vedi `leads_a_ics`)."""
    return list(
        db.execute(
            select(Lead)
            .where(Lead.status == LeadStatus.INCONTRO_FISSATO.value)
            .where(Lead.prossima_azione_at.is_not(None))
            .order_by(Lead.prossima_azione_at.asc())
        ).scalars().all()
    )


def routine_pubblica_testo(db: Session) -> str:
    """Riepilogo testuale della routine per l'endpoint pubblico protetto da
    token (vedi `routers/routine_pubblica.py`): SOLO cosa fare e le date/ore
    degli incontri — niente telefoni, email, indirizzi o siti. Pensato per un
    agente esterno che non deve mai vedere i dati di contatto dei clienti."""
    leads = leads_routine_di_oggi(db)
    incontri = leads_incontri_fissati(db)

    righe = ["Routine commerciale — cosa fare oggi:", ""]

    nuovi = [l for l in leads if l.status == LeadStatus.NUOVO.value]
    if nuovi:
        righe.append(f"Nuovi da contattare ({len(nuovi)}):")
        righe += [f"- {l.nome} ({CATEGORY_LABELS.get(l.categoria, l.categoria)})" for l in nuovi[:15]]
        righe.append("")

    da_ricontattare = [l for l in leads if l.prossima_azione_at and l.status != LeadStatus.INCONTRO_FISSATO.value]
    if da_ricontattare:
        righe.append(f"Da ricontattare ({len(da_ricontattare)}):")
        righe += [f"- {l.nome}: entro il {l.prossima_azione_at.strftime('%d/%m alle %H:%M')}" for l in da_ricontattare[:15]]
        righe.append("")

    if incontri:
        righe.append(f"Incontri fissati ({len(incontri)}):")
        righe += [f"- {l.nome}: {l.prossima_azione_at.strftime('%d/%m alle %H:%M')}" for l in incontri[:15]]
        righe.append("")

    in_trattativa = [l for l in leads if l.status == LeadStatus.IN_TRATTATIVA.value]
    if in_trattativa:
        righe.append(f"Trattative aperte ({len(in_trattativa)}):")
        righe += [f"- {l.nome}" for l in in_trattativa[:15]]

    if len(righe) == 2:
        righe.append("Nessuna azione in sospeso al momento.")

    return "\n".join(righe)


def registra_interazione(
    db: Session,
    lead: Lead,
    canale: str,
    esito: str,
    testo: str = "",
    occurred_at: Optional[datetime] = None,
    user_id: Optional[int] = None,
) -> Interaction:
    """Registra un contatto e aggiorna le date sintetiche del lead."""
    quando = occurred_at or utcnow()
    interazione = Interaction(
        lead_id=lead.id,
        user_id=user_id,
        canale=canale,
        esito=esito,
        testo=testo,
        occurred_at=quando,
    )
    db.add(interazione)

    if lead.primo_contatto_at is None or quando < lead.primo_contatto_at:
        lead.primo_contatto_at = quando
    if lead.ultimo_contatto_at is None or quando > lead.ultimo_contatto_at:
        lead.ultimo_contatto_at = quando
    if esito in OUTCOME_RISPOSTA and lead.risposta_at is None:
        lead.risposta_at = quando

    # Avanzamento automatico della pipeline, senza mai farla tornare indietro.
    if lead.status == LeadStatus.NUOVO.value:
        lead.status = LeadStatus.CONTATTATO.value
    if esito in OUTCOME_RISPOSTA and lead.status in (
        LeadStatus.NUOVO.value,
        LeadStatus.CONTATTATO.value,
    ):
        lead.status = LeadStatus.RISPOSTO.value

    db.commit()
    db.refresh(interazione)
    return interazione


def aggiorna_status(db: Session, lead: Lead, nuovo_status: str) -> Lead:
    """Cambia fase della pipeline e mantiene coerenti le date collegate."""
    adesso = utcnow()
    lead.status = nuovo_status

    if nuovo_status in (LeadStatus.INCONTRO_FISSATO.value, LeadStatus.INCONTRO_FATTO.value):
        if lead.incontro_at is None:
            lead.incontro_at = adesso
    if nuovo_status in (LeadStatus.CHIUSO_VINTO.value, LeadStatus.CHIUSO_PERSO.value):
        lead.chiuso_at = adesso
    else:
        lead.chiuso_at = None
    if nuovo_status != LeadStatus.NUOVO.value and lead.primo_contatto_at is None:
        lead.primo_contatto_at = adesso

    db.commit()
    db.refresh(lead)
    return lead


# --- Export CSV -------------------------------------------------------------

COLONNE_CSV = [
    ("nome", "nome"),
    ("categoria", "categoria"),
    ("stelle", "stelle_hotel"),
    ("indirizzo", "indirizzo"),
    ("zona", "zona"),
    ("telefono", "telefono"),
    ("email", "email"),
    ("sito_web", "sito_web"),
    ("instagram", "instagram"),
    ("facebook", "facebook"),
    ("linkedin", "linkedin"),
    ("valutazione", "valutazione"),
    ("numero_recensioni", "numero_recensioni"),
    ("fascia_prezzo", "fascia_prezzo"),
    ("status", "stato_pipeline"),
    ("maps_url", "maps_url"),
]


def leads_to_csv(leads: Iterable[Lead]) -> str:
    """Serializza i lead in CSV (UTF-8 con BOM, compatibile con Excel)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([intestazione for _, intestazione in COLONNE_CSV])
    for lead in leads:
        riga = []
        for campo, _ in COLONNE_CSV:
            valore = getattr(lead, campo, "")
            if campo == "status":
                valore = lead.status_label
            riga.append("" if valore is None else valore)
        writer.writerow(riga)
    return buffer.getvalue()


def _escape_ics(testo: str) -> str:
    """Escape dei caratteri speciali richiesti dal formato iCalendar (RFC 5545)."""
    return (
        testo.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def leads_a_ics(leads: Iterable[Lead], durata_minuti: int = 60) -> str:
    """Genera un calendario iCalendar (.ics) con un evento per ogni lead che
    ha un incontro fissato con data/ora (`prossima_azione_at`). L'orario è
    quello inserito a mano nella scheda cliente: viene esportato come "ora
    locale fluttuante" (senza fuso), così il calendario lo mostra esattamente
    all'ora inserita, senza conversioni di fuso orario a sorpresa."""
    righe = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//HoReCa Leads//IT", "CALSCALE:GREGORIAN"]
    adesso = utcnow().strftime("%Y%m%dT%H%M%SZ")

    for lead in leads:
        if not lead.prossima_azione_at:
            continue
        inizio = lead.prossima_azione_at.strftime("%Y%m%dT%H%M%S")
        fine = (lead.prossima_azione_at + timedelta(minutes=durata_minuti)).strftime("%Y%m%dT%H%M%S")
        descrizione_parti = [p for p in (lead.telefono, lead.email, lead.sito_web) if p]
        righe += [
            "BEGIN:VEVENT",
            f"UID:lead-{lead.id}-incontro@horeca-leads",
            f"DTSTAMP:{adesso}",
            f"DTSTART:{inizio}",
            f"DTEND:{fine}",
            f"SUMMARY:{_escape_ics(f'Incontro — {lead.nome}')}",
        ]
        if lead.indirizzo:
            righe.append(f"LOCATION:{_escape_ics(lead.indirizzo)}")
        if descrizione_parti:
            righe.append(f"DESCRIPTION:{_escape_ics(' · '.join(descrizione_parti))}")
        righe.append("END:VEVENT")

    righe.append("END:VCALENDAR")
    return "\r\n".join(righe) + "\r\n"
