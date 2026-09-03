"""CLI: scraper di hotel e ristoranti per provincia/regione italiana.

Esempio:
    python -m scraper.main --location "Provincia di Firenze" --types hotel,ristorante \
        --max-results 40 --output risultati.csv
"""

import argparse
import logging
import sys
import time

from .google_places import GooglePlacesClient
from .site_enrichment import enrich_from_website
from .exporter import export_csv, export_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Trova hotel e ristoranti in una provincia o regione italiana, "
        "con stelle (hotel), sito, email, telefono, social e recensioni."
    )
    parser.add_argument(
        "--location",
        required=True,
        help='Provincia o regione italiana, es. "Provincia di Firenze" o "Toscana"',
    )
    parser.add_argument(
        "--types",
        default="hotel,ristorante",
        help="Categorie da cercare separate da virgola: hotel,ristorante (default: entrambe)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=40,
        help="Numero massimo di risultati per categoria (default: 40)",
    )
    parser.add_argument(
        "--reviews",
        action="store_true",
        help="Recupera anche le recensioni (richiede una chiamata Place Details per luogo)",
    )
    parser.add_argument(
        "--max-reviews",
        type=int,
        default=3,
        help="Numero massimo di recensioni da esportare per luogo (default: 3)",
    )
    parser.add_argument(
        "--no-website-enrichment",
        action="store_true",
        help="Salta la visita al sito web per email/social (più veloce, meno dati)",
    )
    parser.add_argument(
        "--output",
        default="risultati.csv",
        help="Percorso file di output CSV (default: risultati.csv)",
    )
    parser.add_argument(
        "--json",
        default="",
        help="Percorso opzionale per esportare anche in JSON",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.2,
        help="Pausa in secondi tra le richieste (rispetto rate limit / cortesia verso i siti)",
    )
    return parser.parse_args()


def run(args):
    categories = [c.strip().lower() for c in args.types.split(",") if c.strip()]
    valid_categories = {"hotel", "ristorante"}
    for c in categories:
        if c not in valid_categories:
            logger.error("Categoria non valida: %s (valide: hotel, ristorante)", c)
            sys.exit(1)

    try:
        client = GooglePlacesClient()
    except ValueError as exc:
        logger.error(str(exc))
        sys.exit(1)

    all_results = []

    for category in categories:
        logger.info("Ricerca '%s' in '%s'...", category, args.location)
        count = 0
        for place in client.search_places(
            location=args.location,
            category=category,
            max_results=args.max_results,
        ):
            result = client.parse_place(place, category=category, location=args.location)
            place_id = place.get("id")

            if args.reviews and place_id:
                try:
                    details = client.get_details(place_id)
                    result.reviews = client.parse_reviews(details, max_reviews=args.max_reviews)
                except Exception as exc:
                    logger.warning("Impossibile recuperare recensioni per %s: %s", result.name, exc)
                time.sleep(args.sleep)

            if not args.no_website_enrichment and result.website:
                try:
                    enrichment = enrich_from_website(result.website, is_hotel=(category == "hotel"))
                    result.email = enrichment["email"]
                    result.instagram = enrichment["instagram"]
                    result.facebook = enrichment["facebook"]
                    result.linkedin = enrichment["linkedin"]
                    if enrichment["stars"]:
                        result.stars = enrichment["stars"]
                except Exception as exc:
                    logger.warning("Impossibile analizzare il sito %s: %s", result.website, exc)

            all_results.append(result)
            count += 1
            logger.info("  [%d] %s", count, result.name)
            time.sleep(args.sleep)

    export_csv(all_results, args.output, max_reviews=args.max_reviews)
    logger.info("Esportati %d risultati in %s", len(all_results), args.output)

    if args.json:
        export_json(all_results, args.json)
        logger.info("Esportati anche in JSON: %s", args.json)


def main():
    args = parse_args()
    run(args)


if __name__ == "__main__":
    main()
