"""API programmatica dello scraper, condivisa tra CLI e dashboard web.

La CLI (`scraper.main`) e il runner della dashboard (`app.services.scrape_runner`)
usano entrambi `scrape()`: la logica di ricerca vive solo qui.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .models import PlaceResult
from .site_enrichment import enrich_from_website

logger = logging.getLogger(__name__)

CATEGORIE_VALIDE = ("hotel", "ristorante")
SORGENTI_VALIDE = ("osm", "google")


@dataclass
class ScrapeParams:
    """Parametri di una sessione di scraping."""

    locations: List[str]
    categories: List[str] = field(default_factory=lambda: ["hotel", "ristorante"])
    source: str = "osm"
    max_results: int = 40
    reviews: bool = False
    max_reviews: int = 3
    website_enrichment: bool = True
    sleep: float = 0.2
    api_key: Optional[str] = None

    def validate(self) -> None:
        if not self.locations:
            raise ValueError("Nessuna località specificata")
        for categoria in self.categories:
            if categoria not in CATEGORIE_VALIDE:
                raise ValueError(f"Categoria non valida: {categoria}")
        if self.source not in SORGENTI_VALIDE:
            raise ValueError(f"Sorgente non valida: {self.source}")


@dataclass
class ScrapeCallbacks:
    """Callback opzionali per seguire l'avanzamento (progress bar, DB, log)."""

    on_task_start: Optional[Callable[[str, str, int], None]] = None
    on_place: Optional[Callable[[PlaceResult], None]] = None
    on_skip: Optional[Callable[[], None]] = None
    on_warning: Optional[Callable[[str], None]] = None

    def task_start(self, location: str, category: str, total: int) -> None:
        if self.on_task_start:
            self.on_task_start(location, category, total)

    def place(self, result: PlaceResult) -> None:
        if self.on_place:
            self.on_place(result)

    def skip(self) -> None:
        if self.on_skip:
            self.on_skip()

    def warning(self, message: str) -> None:
        if self.on_warning:
            self.on_warning(message)


def parse_locations(raw: str) -> List[str]:
    """Trasforma "Riccione, Cattolica" in ["Riccione", "Cattolica"]."""
    return [loc.strip() for loc in raw.split(",") if loc.strip()]


def parse_categories(raw: str) -> List[str]:
    return [c.strip().lower() for c in raw.split(",") if c.strip()]


def _chiave_risultato(result: PlaceResult) -> tuple:
    """Chiave di deduplica interna alla singola sessione di scraping."""
    return (result.category, result.name.lower().strip(), result.address.lower().strip())


def _arricchisci(result: PlaceResult, category: str, abilitato: bool) -> None:
    """Completa email/social/stelle visitando il sito della struttura."""
    if not abilitato or not result.website:
        return
    try:
        dati = enrich_from_website(result.website, is_hotel=(category == "hotel"))
        if not result.email:
            result.email = dati["email"]
        if not result.instagram:
            result.instagram = dati["instagram"]
        if not result.facebook:
            result.facebook = dati["facebook"]
        if not result.linkedin:
            result.linkedin = dati["linkedin"]
        if dati["stars"] and not result.stars:
            result.stars = dati["stars"]
    except Exception as exc:  # il sito della struttura può essere offline o malformato
        logger.debug("Errore arricchimento sito %s: %s", result.website, exc)


def scrape(params: ScrapeParams, callbacks: Optional[ScrapeCallbacks] = None) -> List[PlaceResult]:
    """Esegue lo scraping e restituisce i risultati deduplicati."""
    params.validate()
    cb = callbacks or ScrapeCallbacks()

    if params.source == "google":
        return _scrape_google(params, cb)
    return _scrape_osm(params, cb)


def _scrape_google(params: ScrapeParams, cb: ScrapeCallbacks) -> List[PlaceResult]:
    from .google_places import GooglePlacesClient

    client = GooglePlacesClient(api_key=params.api_key)
    risultati: List[PlaceResult] = []
    visti = set()

    for location in params.locations:
        for category in params.categories:
            cb.task_start(location, category, params.max_results)
            for place in client.search_places(
                location=location, category=category, max_results=params.max_results
            ):
                result = client.parse_place(place, category=category, location=location)
                chiave = _chiave_risultato(result)
                if chiave in visti:
                    cb.skip()
                    continue
                visti.add(chiave)

                place_id = place.get("id")
                if params.reviews and place_id:
                    try:
                        dettagli = client.get_details(place_id)
                        result.reviews = client.parse_reviews(dettagli, max_reviews=params.max_reviews)
                    except Exception as exc:
                        cb.warning(f"Recensioni non disponibili per {result.name}: {exc}")
                    time.sleep(params.sleep)

                _arricchisci(result, category, params.website_enrichment)
                risultati.append(result)
                cb.place(result)
                time.sleep(params.sleep)

    return risultati


def _scrape_osm(params: ScrapeParams, cb: ScrapeCallbacks) -> List[PlaceResult]:
    from .osm_places import OSMPlacesClient

    client = OSMPlacesClient()
    risultati: List[PlaceResult] = []
    visti = set()

    for location in params.locations:
        area = client.geocode_area(location)
        if not area:
            cb.warning(
                f"Zona '{location}' non trovata su OpenStreetMap, la salto. "
                "Prova con un nome più preciso, es. 'Riccione' o 'Provincia di Rimini'."
            )
            continue

        for category in params.categories:
            elementi = list(
                client.search_places(area["area_id"], category, max_results=params.max_results)
            )
            cb.task_start(area["display_name"], category, len(elementi))

            for elemento in elementi:
                result = client.parse_place(elemento, category=category, location=location)
                chiave = _chiave_risultato(result)
                if chiave in visti:
                    cb.skip()
                    continue
                visti.add(chiave)

                _arricchisci(result, category, params.website_enrichment)
                risultati.append(result)
                cb.place(result)
                time.sleep(params.sleep)

    return risultati
