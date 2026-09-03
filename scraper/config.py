"""Configurazione e caricamento variabili d'ambiente."""

import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()

REQUEST_TIMEOUT = 15  # secondi
USER_AGENT = (
    "Mozilla/5.0 (compatible; HotelRestaurantScraper/1.0; "
    "+https://github.com/lucaruboni/hotel_restaurant_scraper)"
)
