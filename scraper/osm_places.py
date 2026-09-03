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

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

CATEGORY_OSM_FILTER = {
    "hotel": '["tourism"="hotel"]',
    "ristorante": '["amenity"="restaurant"]',
}


class OSMPlacesClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT})

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
        resp = self.session.post(OVERPASS_URL, data={"data": query}, timeout=90)
        if resp.status_code != 200:
            logger.error("Errore Overpass (%s): %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
        data = resp.json()
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
