"""Configurazione e caricamento variabili d'ambiente."""

import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()

REQUEST_TIMEOUT = 15  # secondi
# User-Agent per la visita ai siti delle strutture: molti CMS rifiutano i client
# non-browser, quindi qui ci presentiamo come un browser.
USER_AGENT = (
    "Mozilla/5.0 (compatible; HotelRestaurantScraper/1.0; "
    "+https://github.com/lucaruboni/hotel_restaurant_scraper)"
)

# User-Agent per le API OpenStreetMap (Nominatim/Overpass). La loro policy
# impone un UA identificativo con un contatto; Overpass inoltre risponde
# 406 Not Acceptable a chi si spaccia per "Mozilla/5.0", quindi qui il nome
# dell'applicazione deve restare in chiaro.
OSM_USER_AGENT = (
    "HotelRestaurantScraper/1.0 "
    "(+https://github.com/lucaruboni/hotel_restaurant_scraper)"
)


# Endpoint Overpass, in ordine di preferenza. L'istanza pubblica principale
# rifiuta le richieste sotto carico (406/429/504): in quel caso si ritenta con
# backoff e poi si passa al mirror successivo. Sovrascrivibile via env con un
# elenco separato da virgole.
OVERPASS_URLS = [
    u.strip()
    for u in os.getenv(
        "OVERPASS_URLS",
        "https://overpass-api.de/api/interpreter,"
        "https://overpass.kumi.systems/api/interpreter,"
        "https://overpass.private.coffee/api/interpreter",
    ).split(",")
    if u.strip()
]

# Tentativi per ciascun endpoint Overpass e attesa base (secondi) fra i tentativi.
OVERPASS_TENTATIVI = int(os.getenv("OVERPASS_TENTATIVI", "3"))
OVERPASS_ATTESA_BASE = float(os.getenv("OVERPASS_ATTESA_BASE", "5"))
