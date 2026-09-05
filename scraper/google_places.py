"""Client per Google Places API (New) - Text Search e Place Details."""

import time
import logging
from typing import Iterator, Optional

import requests

from . import config
from .models import PlaceResult, Review

logger = logging.getLogger(__name__)

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

SEARCH_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.rating,places.userRatingCount,"
    "places.nationalPhoneNumber,places.internationalPhoneNumber,"
    "places.websiteUri,places.priceLevel,places.googleMapsUri,"
    "nextPageToken"
)

DETAILS_FIELD_MASK = (
    "id,displayName,formattedAddress,location,rating,userRatingCount,"
    "nationalPhoneNumber,internationalPhoneNumber,websiteUri,priceLevel,"
    "googleMapsUri,reviews"
)

PRICE_LEVEL_MAP = {
    "PRICE_LEVEL_FREE": "Gratis",
    "PRICE_LEVEL_INEXPENSIVE": "€",
    "PRICE_LEVEL_MODERATE": "€€",
    "PRICE_LEVEL_EXPENSIVE": "€€€",
    "PRICE_LEVEL_VERY_EXPENSIVE": "€€€€",
}

CATEGORY_QUERY_TEMPLATES = {
    "hotel": "hotel a {location}",
    "ristorante": "ristorante a {location}",
    "fotografo": "fotografo professionista a {location}",
    "social_media_manager": "social media manager freelance a {location}",
    "avvocato": "studio legale avvocato a {location}",
    "commercialista": "studio commercialista a {location}",
    "architetto": "studio di architettura a {location}",
    "geometra": "studio tecnico geometra a {location}",
}

# Tipo Google Places (New) da includere nella ricerca, dove esiste un tipo
# ufficiale corrispondente (tabella: https://developers.google.com/maps/
# documentation/places/web-service/supported_types#table1). Un includedType
# non esistente fa fallire l'intera richiesta con 400 INVALID_ARGUMENT, non
# solo quella categoria: verificato dal vivo che "architect" NON è un tipo
# valido (a differenza di "lawyer" e "accounting"). Le professioni senza un
# tipo dedicato (fotografo, social media manager, architetto, geometra)
# cercano con il solo testo, senza `includedType`.
CATEGORY_INCLUDED_TYPE = {
    "hotel": "lodging",
    "ristorante": "restaurant",
    "avvocato": "lawyer",
    "commercialista": "accounting",
}


class GooglePlacesClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GOOGLE_PLACES_API_KEY
        if not self.api_key:
            raise ValueError(
                "GOOGLE_PLACES_API_KEY mancante. Impostala nel file .env "
                "(vedi .env.example)."
            )
        self.session = requests.Session()

    def _headers(self, field_mask: str) -> dict:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
        }

    def search_places(
        self,
        location: str,
        category: str,
        max_results: int = 60,
        language_code: str = "it",
        region_code: str = "IT",
    ) -> Iterator[dict]:
        """Ricerca luoghi per categoria (vedi `scraper.categories.CATEGORIES`) in una
        zona italiana. Effettua la paginazione automatica fino a max_results (max 20
        per pagina, API-side).
        """
        query = CATEGORY_QUERY_TEMPLATES[category].format(location=location)
        body = {
            "textQuery": query,
            "languageCode": language_code,
            "regionCode": region_code,
            "pageSize": min(20, max_results),
        }
        included_type = CATEGORY_INCLUDED_TYPE.get(category)
        if included_type:
            body["includedType"] = included_type

        fetched = 0
        page_token = None
        while fetched < max_results:
            if page_token:
                body["pageToken"] = page_token
                # Il token richiede qualche secondo prima di essere valido.
                time.sleep(2)

            resp = self.session.post(
                SEARCH_URL,
                json=body,
                headers=self._headers(SEARCH_FIELD_MASK),
                timeout=config.REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                logger.error("Errore Text Search (%s): %s", resp.status_code, resp.text)
                resp.raise_for_status()

            data = resp.json()
            places = data.get("places", [])
            for place in places:
                if fetched >= max_results:
                    break
                yield place
                fetched += 1

            page_token = data.get("nextPageToken")
            if not page_token or not places:
                break

    def get_details(self, place_id: str, language_code: str = "it") -> dict:
        url = DETAILS_URL.format(place_id=place_id)
        resp = self.session.get(
            url,
            params={"languageCode": language_code},
            headers=self._headers(DETAILS_FIELD_MASK),
            timeout=config.REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.error("Errore Place Details (%s): %s", resp.status_code, resp.text)
            resp.raise_for_status()
        return resp.json()

    @staticmethod
    def parse_place(place: dict, category: str, location: str) -> PlaceResult:
        display_name = (place.get("displayName") or {}).get("text", "")
        loc = place.get("location") or {}
        result = PlaceResult(
            category=category,
            name=display_name,
            address=place.get("formattedAddress", ""),
            province_or_region=location,
            phone=place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber", ""),
            website=place.get("websiteUri", ""),
            rating=place.get("rating"),
            user_ratings_total=place.get("userRatingCount"),
            price_level=PRICE_LEVEL_MAP.get(place.get("priceLevel", ""), ""),
            google_maps_url=place.get("googleMapsUri", ""),
            latitude=loc.get("latitude"),
            longitude=loc.get("longitude"),
        )
        return result

    @staticmethod
    def parse_reviews(details: dict, max_reviews: int = 5) -> list:
        reviews = []
        for r in (details.get("reviews") or [])[:max_reviews]:
            author = (r.get("authorAttribution") or {}).get("displayName", "")
            text = (r.get("text") or {}).get("text", "") or (r.get("originalText") or {}).get("text", "")
            reviews.append(
                Review(
                    author=author,
                    rating=r.get("rating"),
                    text=text,
                    relative_time=r.get("relativePublishTimeDescription", ""),
                )
            )
        return reviews
