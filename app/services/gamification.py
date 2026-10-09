"""Gamification della lista chiamate: punti, livelli, missioni, personaggio.

Tutto qui è derivato da dati che esistono già (checklist, interazioni, lead)
più due tabelle minime (`PuntoEvento`, `MissioneCompletata`) che servono solo
a non riassegnare gli stessi punti due volte — niente stato duplicato che
possa disallinearsi dalla pipeline commerciale vera.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scraper.categories import CATEGORY_LABELS, GRUPPI, categorie_raggruppate
from scraper.categories import CATEGORIES as SCRAPER_CATEGORIES

from ..models import Lead, MissioneCompletata, PuntoEvento, User, utcnow

#: Scelte fisse per l'avatar del personaggio: niente upload di immagini (meno
#: superficie d'attacco, meno complessità), solo un set curato di emoji.
AVATAR_SCELTE = ["🦊", "🐺", "🦁", "🐯", "🦅", "🐉", "🥷", "🕵️", "🧑‍💼", "🧑‍🚀", "🏆", "⚡"]
AVATAR_DEFAULT = AVATAR_SCELTE[8]

#: Punti per ogni voce di checklist spuntata (vedi models.CHECKLIST_CHIAMATE).
PUNTI_CHECKLIST_VOCE = 2

#: Punti per esito di chiamata registrato (vedi models.InteractionOutcome).
PUNTI_ESITO = {
    "risposta_positiva": 15,
    "incontro_fissato": 15,
    "da_ricontattare": 8,
    "nessuna_risposta": 3,
    "risposta_negativa": 3,
}

#: Soglie di livello, in ordine crescente: (punti_minimi, nome, descrizione).
LIVELLI = [
    (0, "Recluta", "Il primo giorno è sempre il più lento."),
    (50, "Procacciatore", "Hai preso il ritmo delle chiamate."),
    (150, "Cacciatore di contatti", "I no non ti fermano più."),
    (350, "Chiusore", "Sai quando spingere e quando lasciare andare."),
    (700, "Venditore d'assalto", "La lista chiamate ti teme."),
    (1500, "Leggenda del telefono", "Raccontano di te nelle altre aziende."),
]


@dataclass(frozen=True)
class LivelloInfo:
    nome: str
    descrizione: str
    punti: int
    soglia_attuale: int
    soglia_prossima: Optional[int]
    percento_progresso: int


def livello_di(punti: int) -> LivelloInfo:
    """Il livello corrispondente a un totale punti, con il progresso verso
    il prossimo (100% e nessuna soglia prossima se è il livello massimo)."""
    corrente = LIVELLI[0]
    prossima_soglia = None
    for i, (soglia, nome, descrizione) in enumerate(LIVELLI):
        if punti >= soglia:
            corrente = (soglia, nome, descrizione)
            prossima_soglia = LIVELLI[i + 1][0] if i + 1 < len(LIVELLI) else None
        else:
            break

    soglia_attuale, nome, descrizione = corrente
    if prossima_soglia is None:
        percento = 100
    else:
        campo = prossima_soglia - soglia_attuale
        percento = int(min(100, max(0, (punti - soglia_attuale) / campo * 100))) if campo else 100

    return LivelloInfo(
        nome=nome, descrizione=descrizione, punti=punti,
        soglia_attuale=soglia_attuale, soglia_prossima=prossima_soglia,
        percento_progresso=percento,
    )


def assegna_punti(
    db: Session, utente: User, azione: str, punti: int, lead: Optional[Lead] = None, descrizione: str = "",
) -> PuntoEvento:
    """Registra un evento punti e aggiorna il totale cache sull'utente."""
    evento = PuntoEvento(
        user_id=utente.id,
        lead_id=lead.id if lead else None,
        azione=azione,
        descrizione=descrizione,
        punti=punti,
        creato_at=utcnow(),
    )
    db.add(evento)
    utente.punti_totali = max(0, utente.punti_totali + punti)
    db.commit()
    return evento


# --- Missioni ----------------------------------------------------------------

@dataclass(frozen=True)
class Missione:
    slug: str
    titolo: str
    descrizione: str
    icona: str
    filtro_tipo: str  # "categoria" o "gruppo"
    filtro_valore: str
    target: int
    punti: int

    @property
    def href(self) -> str:
        return f"/chiamate?{self.filtro_tipo}={self.filtro_valore}"


def _missioni_categorie_principali() -> list[Missione]:
    """Una missione per le due categorie che aprono più spesso la lista
    chiamate (hotel, ristoranti): le altre sono coperte dalle missioni per
    gruppo, altrimenti sarebbero troppe da leggere tutte insieme."""
    extra = []
    for slug, icona, target in (("hotel", "🏨", 3), ("ristorante", "🍝", 3)):
        extra.append(
            Missione(
                slug=f"chiamate_{slug}",
                titolo=f"Missione {CATEGORY_LABELS[slug]}",
                descrizione=(
                    f"Chiama 3 contatti della categoria «{CATEGORY_LABELS[slug]}» "
                    "e manda a ciascuno l'email di follow-up."
                ),
                icona=icona,
                filtro_tipo="categoria",
                filtro_valore=slug,
                target=target,
                punti=30,
            )
        )
    return extra


def _missioni_per_gruppo() -> list[Missione]:
    icone = {"ricettivo": "🏨", "professionisti": "💼", "ecommerce": "🫙"}
    target = {"ricettivo": 4, "professionisti": 3, "ecommerce": 2}
    punti = {"ricettivo": 35, "professionisti": 30, "ecommerce": 25}
    missioni = []
    for gruppo, titolo in GRUPPI.items():
        missioni.append(
            Missione(
                slug=f"gruppo_{gruppo}",
                titolo=f"Missione {titolo}",
                descrizione=(
                    f"Chiama {target[gruppo]} contatti del gruppo «{titolo}» "
                    "e manda a ciascuno l'email di follow-up."
                ),
                icona=icone.get(gruppo, "🎯"),
                filtro_tipo="gruppo",
                filtro_valore=gruppo,
                target=target[gruppo],
                punti=punti[gruppo],
            )
        )
    return missioni


MISSIONE_CHECKLIST_PERFETTA = Missione(
    slug="checklist_perfetta",
    titolo="Missione checklist perfetta",
    descrizione="Completa tutte e 5 le voci della checklist su 5 contatti diversi, di qualunque categoria.",
    icona="🏆",
    filtro_tipo="",
    filtro_valore="",
    target=5,
    punti=50,
)

MISSIONI: list[Missione] = [
    MISSIONE_CHECKLIST_PERFETTA,
    *_missioni_categorie_principali(),
    *_missioni_per_gruppo(),
]


def _categorie_del_gruppo(gruppo: str) -> list[str]:
    return [slug for slug, meta in SCRAPER_CATEGORIES.items() if meta.gruppo == gruppo]


def _progresso_missione(db: Session, missione: Missione) -> int:
    if missione.slug == MISSIONE_CHECKLIST_PERFETTA.slug:
        stmt = (
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.chk_sito.is_(True), Lead.chk_social.is_(True), Lead.chk_email_preparata.is_(True),
                Lead.chk_chiamata.is_(True), Lead.chk_email_inviata.is_(True),
            )
        )
        return db.execute(stmt).scalar_one()

    stmt = (
        select(func.count())
        .select_from(Lead)
        .where(Lead.chk_chiamata.is_(True), Lead.chk_email_inviata.is_(True))
    )
    if missione.filtro_tipo == "categoria":
        stmt = stmt.where(Lead.categoria == missione.filtro_valore)
    elif missione.filtro_tipo == "gruppo":
        stmt = stmt.where(Lead.categoria.in_(_categorie_del_gruppo(missione.filtro_valore)))
    return db.execute(stmt).scalar_one()


def missioni_con_progresso(db: Session, utente: User) -> list[dict]:
    """Tutte le missioni con lo stato di avanzamento per questo utente,
    pronte per il template."""
    completate = set(
        db.execute(
            select(MissioneCompletata.slug).where(MissioneCompletata.user_id == utente.id)
        ).scalars().all()
    )
    risultato = []
    for missione in MISSIONI:
        completati = missione.target if missione.slug in completate else _progresso_missione(db, missione)
        risultato.append({
            "missione": missione,
            "completati": min(completati, missione.target),
            "percento": int(min(100, completati / missione.target * 100)) if missione.target else 0,
            "completata": missione.slug in completate,
        })
    return risultato


def verifica_missioni(db: Session, utente: User) -> list[Missione]:
    """Da chiamare dopo ogni azione che potrebbe aver completato una
    missione (checklist, esito): assegna il bonus la prima volta che il
    traguardo viene raggiunto, restituisce le missioni appena completate."""
    già_completate = set(
        db.execute(
            select(MissioneCompletata.slug).where(MissioneCompletata.user_id == utente.id)
        ).scalars().all()
    )
    nuove = []
    for missione in MISSIONI:
        if missione.slug in già_completate:
            continue
        if _progresso_missione(db, missione) >= missione.target:
            db.add(MissioneCompletata(user_id=utente.id, slug=missione.slug, completata_at=utcnow()))
            assegna_punti(
                db, utente, azione="missione", punti=missione.punti,
                descrizione=f"Missione completata: {missione.titolo}",
            )
            nuove.append(missione)
    return nuove


def categorie_filtro() -> list[dict]:
    """Struttura per i pulsanti di filtro categoria/gruppo nella lista
    chiamate: riusa la tassonomia dello scraper, un solo posto da cambiare
    se le categorie cambiano."""
    return categorie_raggruppate()
