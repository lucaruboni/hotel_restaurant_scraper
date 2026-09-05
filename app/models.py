"""Modelli del database: utenti, lead, interazioni, note, allegati, job di scraping."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Adesso in UTC, senza tzinfo.

    Il database salva colonne DateTime senza fuso: tenendo tutto naive-UTC
    evitiamo confronti fra datetime aware e naive quando rileggiamo le righe.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LeadStatus(str, Enum):
    """Fasi della pipeline commerciale, in ordine di avanzamento."""

    NUOVO = "nuovo"
    CONTATTATO = "contattato"
    RISPOSTO = "risposto"
    INCONTRO_FISSATO = "incontro_fissato"
    INCONTRO_FATTO = "incontro_fatto"
    IN_TRATTATIVA = "in_trattativa"
    CHIUSO_VINTO = "chiuso_vinto"
    CHIUSO_PERSO = "chiuso_perso"

    @property
    def etichetta(self) -> str:
        return {
            "nuovo": "Nuovo",
            "contattato": "Contattato",
            "risposto": "Ha risposto",
            "incontro_fissato": "Incontro fissato",
            "incontro_fatto": "Incontro fatto",
            "in_trattativa": "In trattativa",
            "chiuso_vinto": "Chiuso — vinto",
            "chiuso_perso": "Chiuso — perso",
        }[self.value]


#: Ordine del funnel commerciale (esclusi gli stati terminali persi)
FUNNEL_ORDER = [
    LeadStatus.NUOVO,
    LeadStatus.CONTATTATO,
    LeadStatus.RISPOSTO,
    LeadStatus.INCONTRO_FISSATO,
    LeadStatus.INCONTRO_FATTO,
    LeadStatus.IN_TRATTATIVA,
    LeadStatus.CHIUSO_VINTO,
]

STATUS_LABELS = {s.value: s.etichetta for s in LeadStatus}


class ContactChannel(str, Enum):
    EMAIL = "email"
    TELEFONO = "telefono"
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    LINKEDIN = "linkedin"
    DI_PERSONA = "di_persona"
    ALTRO = "altro"

    @property
    def etichetta(self) -> str:
        return {
            "email": "Email",
            "telefono": "Telefono",
            "whatsapp": "WhatsApp",
            "instagram": "Instagram",
            "facebook": "Facebook",
            "linkedin": "LinkedIn",
            "di_persona": "Di persona",
            "altro": "Altro",
        }[self.value]


CHANNEL_LABELS = {c.value: c.etichetta for c in ContactChannel}


class InteractionOutcome(str, Enum):
    INVIATO = "inviato"
    NESSUNA_RISPOSTA = "nessuna_risposta"
    RISPOSTA_POSITIVA = "risposta_positiva"
    RISPOSTA_NEGATIVA = "risposta_negativa"
    INCONTRO_FISSATO = "incontro_fissato"
    DA_RICONTATTARE = "da_ricontattare"

    @property
    def etichetta(self) -> str:
        return {
            "inviato": "Inviato / chiamata fatta",
            "nessuna_risposta": "Nessuna risposta",
            "risposta_positiva": "Risposta positiva",
            "risposta_negativa": "Risposta negativa",
            "incontro_fissato": "Incontro fissato",
            "da_ricontattare": "Da ricontattare",
        }[self.value]


OUTCOME_LABELS = {o.value: o.etichetta for o in InteractionOutcome}

#: Esiti che contano come "ha risposto" nelle metriche
OUTCOME_RISPOSTA = {
    InteractionOutcome.RISPOSTA_POSITIVA.value,
    InteractionOutcome.RISPOSTA_NEGATIVA.value,
    InteractionOutcome.INCONTRO_FISSATO.value,
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nickname di accesso: a differenza dell'email non è deducibile da fuori,
    # quindi funziona come un secondo fattore informale oltre alla password.
    # Niente `unique=True` a livello di DB: un database già popolato non
    # potrebbe applicarlo retroattivamente senza valori da assegnare alle
    # righe esistenti (vedi `_aggiungi_colonne_mancanti`); l'unicità è
    # garantita in `app/cli.py` prima dell'inserimento.
    username: Mapped[str] = mapped_column(String(60), index=True, default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    nome: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Lead(Base):
    """Un potenziale cliente (hotel o ristorante)."""

    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("dedup_key", name="uq_lead_dedup_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(500), index=True)

    # Dati dallo scraper
    categoria: Mapped[str] = mapped_column(String(32), index=True)
    nome: Mapped[str] = mapped_column(String(300))
    indirizzo: Mapped[str] = mapped_column(String(500), default="")
    zona: Mapped[str] = mapped_column(String(200), default="", index=True)
    telefono: Mapped[str] = mapped_column(String(60), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    sito_web: Mapped[str] = mapped_column(String(500), default="")
    instagram: Mapped[str] = mapped_column(String(500), default="")
    facebook: Mapped[str] = mapped_column(String(500), default="")
    linkedin: Mapped[str] = mapped_column(String(500), default="")
    stelle: Mapped[str] = mapped_column(String(40), default="")
    fascia_prezzo: Mapped[str] = mapped_column(String(20), default="")
    valutazione: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    numero_recensioni: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    maps_url: Mapped[str] = mapped_column(String(500), default="")
    latitudine: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitudine: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sorgente: Mapped[str] = mapped_column(String(20), default="")

    # Pipeline commerciale
    status: Mapped[str] = mapped_column(String(30), default=LeadStatus.NUOVO.value, index=True)
    valore_stimato: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prossima_azione_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    primo_contatto_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ultimo_contatto_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    risposta_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    incontro_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    chiuso_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    scrape_job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scrape_jobs.id"), nullable=True)

    interazioni: Mapped[list["Interaction"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Interaction.occurred_at.desc()"
    )
    note: Mapped[list["Note"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Note.updated_at.desc()"
    )
    allegati: Mapped[list["Attachment"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Attachment.created_at.desc()"
    )

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def contattabile(self) -> bool:
        return bool(self.email or self.telefono)

    @property
    def is_chiuso(self) -> bool:
        return self.status in (LeadStatus.CHIUSO_VINTO.value, LeadStatus.CHIUSO_PERSO.value)


class Interaction(Base):
    """Un contatto registrato con il potenziale cliente."""

    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    canale: Mapped[str] = mapped_column(String(30))
    esito: Mapped[str] = mapped_column(String(30), default=InteractionOutcome.INVIATO.value)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    testo: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="interazioni")

    @property
    def canale_label(self) -> str:
        return CHANNEL_LABELS.get(self.canale, self.canale)

    @property
    def esito_label(self) -> str:
        return OUTCOME_LABELS.get(self.esito, self.esito)

    @property
    def ha_risposto(self) -> bool:
        return self.esito in OUTCOME_RISPOSTA


class Note(Base):
    """Una nota della scheda cliente."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    titolo: Mapped[str] = mapped_column(String(300), default="")
    corpo: Mapped[str] = mapped_column(Text, default="")
    in_evidenza: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="note")
    allegati: Mapped[list["Attachment"]] = relationship(
        back_populates="nota", order_by="Attachment.created_at.desc()"
    )


class Attachment(Base):
    """File allegato a un lead (foto, screenshot, PDF, documento)."""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    note_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("notes.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    nome_originale: Mapped[str] = mapped_column(String(300))
    nome_su_disco: Mapped[str] = mapped_column(String(120), unique=True)
    content_type: Mapped[str] = mapped_column(String(120))
    dimensione: Mapped[int] = mapped_column(Integer, default=0)
    descrizione: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="allegati")
    nota: Mapped[Optional[Note]] = relationship(back_populates="allegati")

    @property
    def is_immagine(self) -> bool:
        return self.content_type.startswith("image/")

    @property
    def dimensione_leggibile(self) -> str:
        size = float(self.dimensione)
        for unita in ("B", "KB", "MB", "GB"):
            if size < 1024 or unita == "GB":
                return f"{size:.0f} {unita}" if unita == "B" else f"{size:.1f} {unita}"
            size /= 1024
        return f"{size:.1f} GB"


class ScrapeJob(Base):
    """Una esecuzione dello scraper lanciata dalla dashboard."""

    __tablename__ = "scrape_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    localita: Mapped[str] = mapped_column(String(500))
    categorie: Mapped[str] = mapped_column(String(100))
    sorgente: Mapped[str] = mapped_column(String(20))
    max_results: Mapped[int] = mapped_column(Integer, default=40)
    con_recensioni: Mapped[bool] = mapped_column(Boolean, default=False)
    con_arricchimento: Mapped[bool] = mapped_column(Boolean, default=True)

    stato: Mapped[str] = mapped_column(String(20), default="in_coda", index=True)
    trovati: Mapped[int] = mapped_column(Integer, default=0)
    nuovi: Mapped[int] = mapped_column(Integer, default=0)
    duplicati: Mapped[int] = mapped_column(Integer, default=0)
    errore: Mapped[str] = mapped_column(Text, default="")
    csv_path: Mapped[str] = mapped_column(String(500), default="")
    annullamento_richiesto: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    @property
    def stato_label(self) -> str:
        return {
            "in_coda": "In coda",
            "in_corso": "In corso",
            "completato": "Completato",
            "fallito": "Fallito",
            "annullato": "Annullato",
        }.get(self.stato, self.stato)

    @property
    def durata_secondi(self) -> Optional[float]:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None
