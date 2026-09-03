"""CLI: scraper di hotel e ristoranti per provincia/regione italiana.

Esempio:
    python -m scraper.main --location "Provincia di Firenze" --types hotel,ristorante \
        --max-results 40 --output risultati.csv
"""

import argparse
import logging
import sys
import time

from .site_enrichment import enrich_from_website
from .exporter import export_csv, export_json
from . import ui

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Trova hotel e ristoranti in una provincia o regione italiana, "
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
    parser.add_argument(
        "--max-results",
        type=int,
        default=40,
        help="Numero massimo di risultati per categoria (default: 40)",
    )
    parser.add_argument(
        "--reviews",
        action="store_true",
        help="Recupera anche le recensioni (solo sorgente 'google', chiamata extra per luogo)",
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
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Disattiva l'interfaccia grafica da terminale (output semplice, utile per log/CI)",
    )
    return parser.parse_args()


def _enrich_result(result, category, no_website_enrichment):
    if no_website_enrichment or not result.website:
        return
    try:
        enrichment = enrich_from_website(result.website, is_hotel=(category == "hotel"))
        if not result.email:
            result.email = enrichment["email"]
        if not result.instagram:
            result.instagram = enrichment["instagram"]
        if not result.facebook:
            result.facebook = enrichment["facebook"]
        if not result.linkedin:
            result.linkedin = enrichment["linkedin"]
        if enrichment["stars"] and not result.stars:
            result.stars = enrichment["stars"]
    except Exception as exc:
        logger.debug("Errore arricchimento sito %s: %s", result.website, exc)


def run_osm(args, categories, locations):
    from .osm_places import OSMPlacesClient

    client = OSMPlacesClient()
    all_results = []
    seen = set()
    progress = ui.make_progress()
    with progress:
        for location in locations:
            area = client.geocode_area(location)
            if not area:
                ui.print_warning(
                    f"Zona '{location}' non trovata su OpenStreetMap, la salto. "
                    "Prova con un nome più preciso, es. 'Riccione' o 'Provincia di Rimini'."
                )
                continue

            for category in categories:
                places = list(client.search_places(area["area_id"], category, max_results=args.max_results))
                task = progress.add_task(f"[cyan]Ricerca {category} in {area['display_name'][:40]}", total=len(places))

                for element in places:
                    result = client.parse_place(element, category=category, location=location)
                    key = (result.category, result.name.lower(), result.address.lower())
                    if key in seen:
                        progress.advance(task)
                        continue
                    seen.add(key)

                    _enrich_result(result, category, args.no_website_enrichment)

                    all_results.append(result)
                    progress.advance(task)
                    if not args.no_ui:
                        ui.print_place_found(
                            result.name,
                            category,
                            has_email=bool(result.email),
                            has_social=bool(result.instagram or result.facebook or result.linkedin),
                        )
                    time.sleep(args.sleep)

    return all_results


def run_google(args, categories, locations):
    from .google_places import GooglePlacesClient

    try:
        client = GooglePlacesClient()
    except ValueError as exc:
        ui.print_error(str(exc))
        sys.exit(1)

    all_results = []
    seen = set()
    progress = ui.make_progress()
    with progress:
        for location in locations:
            for category in categories:
                task = progress.add_task(f"[cyan]Ricerca {category} in {location}", total=args.max_results)
                for place in client.search_places(location=location, category=category, max_results=args.max_results):
                    result = client.parse_place(place, category=category, location=location)
                    key = (result.category, result.name.lower(), result.address.lower())
                    if key in seen:
                        progress.advance(task)
                        continue
                    seen.add(key)

                    place_id = place.get("id")
                    if args.reviews and place_id:
                        try:
                            details = client.get_details(place_id)
                            result.reviews = client.parse_reviews(details, max_reviews=args.max_reviews)
                        except Exception as exc:
                            ui.print_warning(f"Recensioni non disponibili per {result.name}: {exc}")
                        time.sleep(args.sleep)

                    _enrich_result(result, category, args.no_website_enrichment)

                    all_results.append(result)
                    progress.advance(task)
                    if not args.no_ui:
                        ui.print_place_found(
                            result.name,
                            category,
                            has_email=bool(result.email),
                            has_social=bool(result.instagram or result.facebook or result.linkedin),
                        )
                    time.sleep(args.sleep)

    return all_results


def run(args):
    categories = [c.strip().lower() for c in args.types.split(",") if c.strip()]
    valid_categories = {"hotel", "ristorante"}
    for c in categories:
        if c not in valid_categories:
            ui.print_error(f"Categoria non valida: {c} (valide: hotel, ristorante)")
            sys.exit(1)

    locations = [loc.strip() for loc in args.location.split(",") if loc.strip()]
    if not locations:
        ui.print_error("Nessuna zona valida specificata in --location")
        sys.exit(1)

    if not args.no_ui:
        ui.print_banner(", ".join(locations), categories, args.source, args.max_results)

    start = time.time()
    if args.source == "google":
        all_results = run_google(args, categories, locations)
    else:
        all_results = run_osm(args, categories, locations)
    elapsed = time.time() - start

    export_csv(all_results, args.output, max_reviews=args.max_reviews)
    if args.json:
        export_json(all_results, args.json)

    if not args.no_ui:
        ui.print_summary(all_results, args.output, elapsed)
    else:
        print(f"Esportati {len(all_results)} risultati in {args.output}")


def main():
    args = parse_args()
    run(args)


if __name__ == "__main__":
    main()
