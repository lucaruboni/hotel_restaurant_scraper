"""Tassonomia delle categorie di potenziali clienti.

Unica fonte di verità condivisa da CLI, dashboard e client delle sorgenti dati
(OSM/Google): aggiungere una categoria richiede di toccare solo questo file
più il filtro OSM (`osm_places.CATEGORY_OSM_FILTER`) e/o il template di
ricerca Google (`google_places.CATEGORY_QUERY_TEMPLATES`), a seconda di quali
sorgenti la supportano.

Tre profili di ricerca pensati per tre segmenti commerciali diversi:
- **ricettivo**: hotel, ristoranti, bar e strutture ricettive (campeggi,
  glamping, villaggi turistici) — buona copertura su OpenStreetMap.
- **professionisti**: studi e liberi professionisti che vendono servizi B2B
  (fotografi, social media manager, avvocati, commercialisti, architetti,
  geometri) — su OSM sono quasi sempre assenti, servono Google Places.
- **ecommerce**: produttori e botteghe artigiane che vendono un prodotto
  fisico e sono naturali candidati a un e-commerce ma spesso non ce l'hanno
  ancora (frantoi, aziende agricole, pasticcerie, torrefazioni, birrifici,
  vivai, botteghe artigiane) — buona copertura su OpenStreetMap.
"""

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class CategoryMeta:
    label: str
    gruppo: str
    sorgenti: Tuple[str, ...]


GRUPPI: Dict[str, str] = {
    "ricettivo": "Hotel, ristoranti e strutture ricettive",
    "professionisti": "Professionisti",
    "ecommerce": "Potenziali clienti e-commerce",
}

CATEGORIES: Dict[str, CategoryMeta] = {
    # --- Ricettivo / ristorazione (OSM, come oggi) --------------------------
    "hotel": CategoryMeta("Hotel", "ricettivo", ("osm", "google")),
    "ristorante": CategoryMeta("Ristoranti", "ricettivo", ("osm", "google")),
    "bar": CategoryMeta("Bar", "ricettivo", ("osm",)),
    "campeggio": CategoryMeta("Campeggi e glamping", "ricettivo", ("osm",)),
    "villaggio_turistico": CategoryMeta("Villaggi turistici", "ricettivo", ("osm",)),
    # --- Professionisti (Google: su OSM sono quasi sempre assenti) ----------
    "fotografo": CategoryMeta("Fotografi", "professionisti", ("google",)),
    "social_media_manager": CategoryMeta("Social media manager", "professionisti", ("google",)),
    "avvocato": CategoryMeta("Studi legali", "professionisti", ("google",)),
    "commercialista": CategoryMeta("Studi di commercialisti", "professionisti", ("google",)),
    "architetto": CategoryMeta("Studi di architettura", "professionisti", ("google",)),
    "geometra": CategoryMeta("Studi di geometri", "professionisti", ("google",)),
    # --- Candidati e-commerce (OSM: produttori e botteghe artigiane) --------
    "frantoio": CategoryMeta("Frantoi", "ecommerce", ("osm",)),
    "azienda_agricola": CategoryMeta("Aziende agricole con vendita diretta", "ecommerce", ("osm",)),
    "pasticceria": CategoryMeta("Pasticcerie artigianali", "ecommerce", ("osm",)),
    "torrefazione": CategoryMeta("Torrefazioni di caffè", "ecommerce", ("osm",)),
    "birrificio": CategoryMeta("Birrifici artigianali", "ecommerce", ("osm",)),
    "vivaio": CategoryMeta("Vivai e floricoltori", "ecommerce", ("osm",)),
    "bottega_artigiana": CategoryMeta("Botteghe artigiane (ceramica, pelletteria, ...)", "ecommerce", ("osm",)),
}

CATEGORIE_VALIDE: Tuple[str, ...] = tuple(CATEGORIES)

#: slug -> etichetta leggibile, per template e CSV
CATEGORY_LABELS: Dict[str, str] = {slug: meta.label for slug, meta in CATEGORIES.items()}

#: slug -> gruppo di appartenenza, usato per colorare i badge in dashboard
CATEGORY_GROUP: Dict[str, str] = {slug: meta.gruppo for slug, meta in CATEGORIES.items()}


def categorie_per_sorgente(sorgente: str) -> Tuple[str, ...]:
    """Categorie selezionabili con una data sorgente."""
    return tuple(slug for slug, meta in CATEGORIES.items() if sorgente in meta.sorgenti)


def categorie_raggruppate() -> list[dict]:
    """Struttura pronta per il form di ricerca: un blocco per gruppo, con le
    sorgenti compatibili di ciascuna categoria (serve alla UI per abilitare
    solo le caselle coerenti con la sorgente scelta)."""
    blocchi = []
    for gruppo, titolo in GRUPPI.items():
        categorie = [
            {"slug": slug, "label": meta.label, "sorgenti": meta.sorgenti}
            for slug, meta in CATEGORIES.items()
            if meta.gruppo == gruppo
        ]
        blocchi.append({"gruppo": gruppo, "titolo": titolo, "categorie": categorie})
    return blocchi
