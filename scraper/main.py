"""CLI: scraper di hotel e ristoranti per provincia, regione o comune italiano.

Esempio:
    python -m scraper.main --location "Riccione, Cattolica" --source google \
        --max-results 40 --output risultati.csv
"""

import argparse
import logging
import sys
import time

from . import ui
from .core import ScrapeCallbacks, ScrapeParams, parse_categories, parse_locations, scrape
from .exporter import export_csv, export_json

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Trova hotel e ristoranti in una provincia, regione o comune italiano, "
        "con stelle (hotel), sito, email, telefono, social e recensioni."
    )
    parser.add_argument(
        "--location",
        required=True,
        help='Provincia, regione o comune italiano. Per più zone insieme separale con '
        'una virgola, es. "Riccione, Misano Adriatico, Cattolica"',
    )
    parser.add_argument(
        "--types",
        default="hotel,ristorante",
        help="Categorie da cercare separate da virgola: hotel,ristorante (default: entrambe)",
    )
    parser.add_argument(
        "--source",
        choices=["osm", "google"],
        default="osm",
        help="Sorgente dati: 'osm' (OpenStreetMap, gratis, nessuna chiave) o "
        "'google' (Google Places, richiede GOOGLE_PLACES_API_KEY). Default: osm",
    )
    parser.add_argument("--max-results", type=int, default=40,
                        help="Numero massimo di risultati per categoria (default: 40)")
    parser.add_argument("--reviews", action="store_true",
                        help="Recupera anche le recensioni (solo sorgente 'google')")
    parser.add_argument("--max-reviews", type=int, default=3,
                        help="Numero massimo di recensioni da esportare per luogo (default: 3)")
    parser.add_argument("--no-website-enrichment", action="store_true",
                        help="Salta la visita al sito web per email/social (più veloce)")
    parser.add_argument("--output", default="risultati.csv",
                        help="Percorso file di output CSV (default: risultati.csv)")
    parser.add_argument("--json", default="",
                        help="Percorso opzionale per esportare anche in JSON")
    parser.add_argument("--sleep", type=float, default=0.2,
                        help="Pausa in secondi tra le richieste")
    parser.add_argument("--no-ui", action="store_true",
                        help="Disattiva l'interfaccia grafica da terminale (output semplice)")
    return parser.parse_args()


def run(args):
    locations = parse_locations(args.location)
    categories = parse_categories(args.types)

    params = ScrapeParams(
        locations=locations,
        categories=categories,
        source=args.source,
        max_results=args.max_results,
        reviews=args.reviews,
        max_reviews=args.max_reviews,
        website_enrichment=not args.no_website_enrichment,
        sleep=args.sleep,
    )
    try:
        params.validate()
    except ValueError as exc:
        ui.print_error(str(exc))
        sys.exit(1)

    if not args.no_ui:
        ui.print_banner(", ".join(locations), categories, args.source, args.max_results)

    start = time.time()
    progress = ui.make_progress()
    stato = {"task": None}

    def on_task_start(location: str, category: str, total: int):
        stato["task"] = progress.add_task(f"[cyan]Ricerca {category} in {location[:40]}", total=total)

    def on_place(result):
        if stato["task"] is not None:
            progress.advance(stato["task"])
        if not args.no_ui:
            ui.print_place_found(
                result.name,
                result.category,
                has_email=bool(result.email),
                has_social=bool(result.instagram or result.facebook or result.linkedin),
            )

    def on_skip():
        if stato["task"] is not None:
            progress.advance(stato["task"])

    callbacks = ScrapeCallbacks(
        on_task_start=on_task_start,
        on_place=on_place,
        on_skip=on_skip,
        on_warning=ui.print_warning,
    )

    try:
        with progress:
            risultati = scrape(params, callbacks)
    except Exception as exc:
        ui.print_error(f"Scraping fallito: {exc}")
        sys.exit(1)

    elapsed = time.time() - start

    export_csv(risultati, args.output, max_reviews=args.max_reviews)
    if args.json:
        export_json(risultati, args.json)

    if not args.no_ui:
        ui.print_summary(risultati, args.output, elapsed)
    else:
        print(f"Esportati {len(risultati)} risultati in {args.output}")


def main():
    run(parse_args())


if __name__ == "__main__":
    main()
