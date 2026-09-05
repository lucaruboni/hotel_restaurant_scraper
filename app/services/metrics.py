"""Calcolo delle metriche commerciali mostrate in dashboard.

Le metriche rispondono a domande di business precise:
- quanti potenziali clienti ho e quanti sono davvero contattabili?
- dove si blocca il funnel?
- quale canale di contatto ottiene più risposte?
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scraper.categories import CATEGORY_LABELS

from ..models import (
    utcnow,
    CHANNEL_LABELS,
    FUNNEL_ORDER,
    Interaction,
    Lead,
    LeadStatus,
    OUTCOME_RISPOSTA,
    STATUS_LABELS,
)


@dataclass
class FaseFunnel:
    chiave: str
    etichetta: str
    conteggio: int
    percentuale: float


@dataclass
class CanaleStat:
    canale: str
    etichetta: str
    tentativi: int
    risposte: int

    @property
    def tasso_risposta(self) -> float:
        return (self.risposte / self.tentativi * 100) if self.tentativi else 0.0


@dataclass
class Metriche:
    totale_lead: int = 0
    contattabili: int = 0
    con_email: int = 0
    con_telefono: int = 0
    con_social: int = 0
    contattati: int = 0
    risposte: int = 0
    incontri: int = 0
    in_trattativa: int = 0
    vinti: int = 0
    persi: int = 0
    valore_pipeline: float = 0.0
    valore_vinto: float = 0.0
    nuovi_7g: int = 0
    contatti_7g: int = 0
    funnel: list[FaseFunnel] = field(default_factory=list)
    per_status: dict[str, int] = field(default_factory=dict)
    per_zona: list[tuple[str, int]] = field(default_factory=list)
    per_categoria: list[tuple[str, str, int]] = field(default_factory=list)
    canali: list[CanaleStat] = field(default_factory=list)
    da_ricontattare: list[Lead] = field(default_factory=list)

    @property
    def top_categorie_hint(self) -> str:
        """Le due categorie più numerose, per il KPI in cima alla dashboard."""
        return " · ".join(f"{n} {label.lower()}" for _, label, n in self.per_categoria[:2])

    @property
    def tasso_contattabilita(self) -> float:
        return (self.contattabili / self.totale_lead * 100) if self.totale_lead else 0.0

    @property
    def tasso_risposta(self) -> float:
        return (self.risposte / self.contattati * 100) if self.contattati else 0.0

    @property
    def tasso_incontro(self) -> float:
        return (self.incontri / self.risposte * 100) if self.risposte else 0.0

    @property
    def tasso_chiusura(self) -> float:
        chiusi = self.vinti + self.persi
        return (self.vinti / chiusi * 100) if chiusi else 0.0

    @property
    def conversione_totale(self) -> float:
        return (self.vinti / self.totale_lead * 100) if self.totale_lead else 0.0


def _conta(db: Session, condizione) -> int:
    return db.execute(select(func.count()).select_from(Lead).where(condizione)).scalar_one()


def calcola_metriche(db: Session) -> Metriche:
    m = Metriche()

    m.totale_lead = db.execute(select(func.count()).select_from(Lead)).scalar_one()
    if m.totale_lead == 0:
        return m

    m.per_categoria = [
        (categoria, CATEGORY_LABELS.get(categoria, categoria), n)
        for categoria, n in db.execute(
            select(Lead.categoria, func.count())
            .group_by(Lead.categoria)
            .order_by(func.count().desc())
        ).all()
    ]
    m.con_email = _conta(db, Lead.email != "")
    m.con_telefono = _conta(db, Lead.telefono != "")
    m.contattabili = _conta(db, (Lead.email != "") | (Lead.telefono != ""))
    m.con_social = _conta(db, (Lead.instagram != "") | (Lead.facebook != "") | (Lead.linkedin != ""))

    # Conteggi per fase della pipeline
    righe = db.execute(select(Lead.status, func.count()).group_by(Lead.status)).all()
    m.per_status = {STATUS_LABELS.get(s, s): n for s, n in righe}
    conteggi = {s: n for s, n in righe}

    stati_contattati = [
        LeadStatus.CONTATTATO.value,
        LeadStatus.RISPOSTO.value,
        LeadStatus.INCONTRO_FISSATO.value,
        LeadStatus.INCONTRO_FATTO.value,
        LeadStatus.IN_TRATTATIVA.value,
        LeadStatus.CHIUSO_VINTO.value,
        LeadStatus.CHIUSO_PERSO.value,
    ]
    m.contattati = sum(conteggi.get(s, 0) for s in stati_contattati)
    stati_risposta = stati_contattati[1:]
    m.risposte = sum(conteggi.get(s, 0) for s in stati_risposta)
    stati_incontro = [
        LeadStatus.INCONTRO_FISSATO.value,
        LeadStatus.INCONTRO_FATTO.value,
        LeadStatus.IN_TRATTATIVA.value,
        LeadStatus.CHIUSO_VINTO.value,
    ]
    m.incontri = sum(conteggi.get(s, 0) for s in stati_incontro)
    m.in_trattativa = conteggi.get(LeadStatus.IN_TRATTATIVA.value, 0)
    m.vinti = conteggi.get(LeadStatus.CHIUSO_VINTO.value, 0)
    m.persi = conteggi.get(LeadStatus.CHIUSO_PERSO.value, 0)

    # Funnel: ogni fase conta i lead che l'hanno raggiunta o superata
    cumulativi = {
        LeadStatus.NUOVO: m.totale_lead,
        LeadStatus.CONTATTATO: m.contattati,
        LeadStatus.RISPOSTO: m.risposte,
        LeadStatus.INCONTRO_FISSATO: m.incontri,
        LeadStatus.INCONTRO_FATTO: sum(
            conteggi.get(s, 0)
            for s in (
                LeadStatus.INCONTRO_FATTO.value,
                LeadStatus.IN_TRATTATIVA.value,
                LeadStatus.CHIUSO_VINTO.value,
            )
        ),
        LeadStatus.IN_TRATTATIVA: m.in_trattativa + m.vinti,
        LeadStatus.CHIUSO_VINTO: m.vinti,
    }
    for fase in FUNNEL_ORDER:
        n = cumulativi.get(fase, 0)
        m.funnel.append(
            FaseFunnel(
                chiave=fase.value,
                etichetta=fase.etichetta,
                conteggio=n,
                percentuale=(n / m.totale_lead * 100) if m.totale_lead else 0.0,
            )
        )

    # Valore economico
    m.valore_pipeline = db.execute(
        select(func.coalesce(func.sum(Lead.valore_stimato), 0.0)).where(
            Lead.status.notin_([LeadStatus.CHIUSO_VINTO.value, LeadStatus.CHIUSO_PERSO.value])
        )
    ).scalar_one()
    m.valore_vinto = db.execute(
        select(func.coalesce(func.sum(Lead.valore_stimato), 0.0)).where(
            Lead.status == LeadStatus.CHIUSO_VINTO.value
        )
    ).scalar_one()

    # Attività recente
    sette_giorni_fa = utcnow() - timedelta(days=7)
    m.nuovi_7g = _conta(db, Lead.created_at >= sette_giorni_fa)
    m.contatti_7g = db.execute(
        select(func.count()).select_from(Interaction).where(Interaction.occurred_at >= sette_giorni_fa)
    ).scalar_one()

    # Zone più presidiate
    m.per_zona = [
        (zona, n)
        for zona, n in db.execute(
            select(Lead.zona, func.count())
            .where(Lead.zona != "")
            .group_by(Lead.zona)
            .order_by(func.count().desc())
            .limit(8)
        ).all()
    ]

    # Efficacia per canale di contatto
    per_canale = db.execute(
        select(Interaction.canale, func.count()).group_by(Interaction.canale)
    ).all()
    risposte_canale = dict(
        db.execute(
            select(Interaction.canale, func.count())
            .where(Interaction.esito.in_(list(OUTCOME_RISPOSTA)))
            .group_by(Interaction.canale)
        ).all()
    )
    m.canali = sorted(
        (
            CanaleStat(
                canale=canale,
                etichetta=CHANNEL_LABELS.get(canale, canale),
                tentativi=n,
                risposte=risposte_canale.get(canale, 0),
            )
            for canale, n in per_canale
        ),
        key=lambda c: c.tentativi,
        reverse=True,
    )

    # Lead con un'azione pianificata scaduta o imminente
    m.da_ricontattare = list(
        db.execute(
            select(Lead)
            .where(Lead.prossima_azione_at.is_not(None))
            .where(Lead.status.notin_([LeadStatus.CHIUSO_VINTO.value, LeadStatus.CHIUSO_PERSO.value]))
            .order_by(Lead.prossima_azione_at.asc())
            .limit(8)
        ).scalars().all()
    )

    return m
