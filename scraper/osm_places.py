"""Sorgente dati gratuita basata su OpenStreetMap (Nominatim + Overpass API).

Non richiede alcuna API key: utile come opzione predefinita quando non si
dispone di una chiave Google Places. I dati sono contribuiti dalla comunità
OSM e possono essere meno completi rispetto a Google (in particolare non
sono disponibili le recensioni).
"""

import logging
import time
from typing import Iterator, Optional

import requests

from . import config
from .models import PlaceResult

logger = logging.getLogger(__name__)


class OverpassNonDisponibile(RuntimeError):
    """Overpass ha rifiutato la richiesta su tutti gli endpoint disponibili."""


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Codici con cui le istanze Overpass pubbliche segnalano sovraccarico o rifiuto
# temporaneo: vanno ritentati, non trattati come errore definitivo.
STATUS_RITENTABILI = {406, 429, 502, 503, 504}

CATEGORY_OSM_FILTER = {
    # Ricettivo / ristorazione
    "hotel": '["tourism"="hotel"]',
    "ristorante": '["amenity"="restaurant"]',
    "bar": '["amenity"="bar"]',
    "campeggio": '["tourism"="camp_site"]',
    "villaggio_turistico": '["tourism"="resort"]',
    # Candidati e-commerce: produttori e botteghe artigiane
    "frantoio": '["craft"="oil_mill"]',
    "azienda_agricola": '["shop"="farm"]',
    "pasticceria": '["shop"="pastry"]',
    "torrefazione": '["craft"="coffee_roaster"]',
    "birrificio": '["craft"="brewery"]',
    "vivaio": '["shop"="garden_centre"]',
    "bottega_artigiana": '["shop"="craft"]',
}


class OSMPlacesClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.OSM_USER_AGENT})

    def geocode_area(self, location: str) -> Optional[dict]:
        """Risolve il nome di una provincia/regione italiana in un'area OSM."""
        params = {
            "q": f"{location}, Italia",
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 0,
            "extratags": 0,
        }
        resp = self.session.get(params=params, url=NOMINATIM_URL, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        item = results[0]
        osm_type = item.get("osm_type")
        osm_id = item.get("osm_id")
        if osm_type != "relation":
            return None
        area_id = 3600000000 + int(osm_id)
        return {"area_id": area_id, "display_name": item.get("display_name", location)}

    def _interroga_overpass(self, query: str) -> dict:
        """Esegue una query Overpass ritentando su rifiuti temporanei.

        Le istanze pubbliche rispondono 429 (rate limit) o 406/504 quando sono
        sotto carico, anche a query perfettamente valide. Si ritenta con attesa
        crescente sullo stesso endpoint e, esauriti i tentativi, si passa al
        mirror successivo.
        """
        ultimo_errore = ""
        for url in config.OVERPASS_URLS:
            for tentativo in range(1, config.OVERPASS_TENTATIVI + 1):
                try:
                    resp = self.session.post(url, data={"data": query}, timeout=90)
                except requests.RequestException as exc:
                    ultimo_errore = f"{url}: {type(exc).__name__}"
                    logger.warning("Overpass %s non raggiungibile (%s)", url, type(exc).__name__)
                    break  # endpoint irraggiungibile: inutile insistere, passo al mirror

                if resp.status_code == 200:
                    return resp.json()

                ultimo_errore = f"{url}: HTTP {resp.status_code}"
                if resp.status_code not in STATUS_RITENTABILI:
                    logger.error("Errore Overpass (%s): %s", resp.status_code, resp.text[:500])
                    resp.raise_for_status()

                if tentativo < config.OVERPASS_TENTATIVI:
                    attesa = self._attesa(resp, tentativo)
                    logger.warning(
                        "Overpass %s ha risposto %s (server occupato): riprovo fra %.0fs "
                        "(tentativo %s/%s)",
                        url, resp.status_code, attesa, tentativo, config.OVERPASS_TENTATIVI,
                    )
                    time.sleep(attesa)

        raise OverpassNonDisponibile(
            "Il servizio OpenStreetMap (Overpass) sta rifiutando le richieste perché "
            "sovraccarico. Non è un errore della ricerca: riprova fra qualche minuto, "
            f"oppure usa la sorgente Google. Ultimo esito — {ultimo_errore}."
        )

    @staticmethod
    def _attesa(resp: requests.Response, tentativo: int) -> float:
        """Attesa prima del ritentativo: rispetta Retry-After, altrimenti backoff."""
        retry_after = resp.headers.get("Retry-After", "")
        if retry_after.strip().isdigit():
            return min(float(retry_after), 60.0)
        return config.OVERPASS_ATTESA_BASE * (2 ** (tentativo - 1))

    def search_places(self, area_id: int, category: str, max_results: int = 60) -> Iterator[dict]:
        osm_filter = CATEGORY_OSM_FILTER[category]
        query = f"""
        [out:json][timeout:60];
        area({area_id})->.searchArea;
        (
          node{osm_filter}(area.searchArea);
          way{osm_filter}(area.searchArea);
          relation{osm_filter}(area.searchArea);
        );
        out center tags {max_results * 2};
        """
        data = self._interroga_overpass(query)
        elements = data.get("elements", [])
        count = 0
        for el in elements:
            tags = el.get("tags", {})
            if not tags.get("name"):
                continue
            yield el
            count += 1
            if count >= max_results:
                break

    @staticmethod
    def parse_place(element: dict, category: str, location: str) -> PlaceResult:
        tags = element.get("tags", {})

        address_parts = []
        street = tags.get("addr:street", "")
        housenumber = tags.get("addr:housenumber", "")
        if street:
            address_parts.append(f"{street} {housenumber}".strip())
        postcode = tags.get("addr:postcode", "")
        city = tags.get("addr:city", "")
        if postcode or city:
            address_parts.append(f"{postcode} {city}".strip())
        address = ", ".join(p for p in address_parts if p)

        website = tags.get("website") or tags.get("contact:website", "")
        phone = tags.get("phone") or tags.get("contact:phone", "")
        email = tags.get("email") or tags.get("contact:email", "")
        instagram = tags.get("contact:instagram", "")
        facebook = tags.get("contact:facebook", "")
        linkedin = tags.get("contact:linkedin", "")
        stars = tags.get("stars", "")

        lat = element.get("lat") or (element.get("center") or {}).get("lat")
        lon = element.get("lon") or (element.get("center") or {}).get("lon")
        osm_id = element.get("id")
        osm_type = element.get("type", "node")
        maps_url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if osm_id else ""

        return PlaceResult(
            category=category,
            name=tags.get("name", ""),
            address=address,
            province_or_region=location,
            phone=phone,
            email=email,
            website=website,
            rating=None,
            user_ratings_total=None,
            stars=f"{stars} stelle" if stars else None,
            price_level="",
            instagram=instagram,
            facebook=facebook,
            linkedin=linkedin,
            google_maps_url=maps_url,
            latitude=lat,
            longitude=lon,
        )
