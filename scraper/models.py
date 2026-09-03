"""Modelli dati per i risultati dello scraper."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Review:
    author: str = ""
    rating: Optional[float] = None
    text: str = ""
    relative_time: str = ""


@dataclass
class PlaceResult:
    category: str  # "hotel" o "ristorante"
    name: str = ""
    address: str = ""
    province_or_region: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    stars: Optional[str] = None  # solo per hotel, best-effort
    price_level: Optional[str] = None
    instagram: str = ""
    facebook: str = ""
    linkedin: str = ""
    google_maps_url: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    reviews: list = field(default_factory=list)  # list[Review]

    def to_row(self, max_reviews: int = 3) -> dict:
        row = {
            "categoria": self.category,
            "nome": self.name,
            "indirizzo": self.address,
            "zona_ricerca": self.province_or_region,
            "telefono": self.phone,
            "email": self.email,
            "sito_web": self.website,
            "valutazione_google": self.rating if self.rating is not None else "",
            "numero_recensioni": self.user_ratings_total if self.user_ratings_total is not None else "",
            "stelle_hotel": self.stars or "",
            "fascia_prezzo": self.price_level or "",
            "instagram": self.instagram,
            "facebook": self.facebook,
            "linkedin": self.linkedin,
            "google_maps_url": self.google_maps_url,
            "latitudine": self.latitude if self.latitude is not None else "",
            "longitudine": self.longitude if self.longitude is not None else "",
        }
        for i in range(max_reviews):
            r = self.reviews[i] if i < len(self.reviews) else None
            row[f"recensione_{i+1}_autore"] = r.author if r else ""
            row[f"recensione_{i+1}_voto"] = r.rating if r and r.rating is not None else ""
            row[f"recensione_{i+1}_testo"] = r.text if r else ""
        return row
