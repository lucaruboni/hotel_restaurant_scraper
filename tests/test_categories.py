"""Test della tassonomia delle categorie e della sua propagazione ai client."""

import pytest

from scraper.categories import CATEGORIES, CATEGORIE_VALIDE, categorie_per_sorgente
from scraper.core import ScrapeParams
from scraper.google_places import CATEGORY_INCLUDED_TYPE, CATEGORY_QUERY_TEMPLATES
from scraper.osm_places import CATEGORY_OSM_FILTER


def test_ogni_categoria_supporta_almeno_una_sorgente():
    for slug, meta in CATEGORIES.items():
        assert meta.sorgenti, f"{slug} non ha nessuna sorgente dichiarata"


def test_ogni_categoria_osm_ha_il_filtro_corrispondente():
    for slug in categorie_per_sorgente("osm"):
        assert slug in CATEGORY_OSM_FILTER, f"manca il filtro Overpass per '{slug}'"


def test_ogni_categoria_google_ha_il_template_di_ricerca():
    for slug in categorie_per_sorgente("google"):
        assert slug in CATEGORY_QUERY_TEMPLATES, f"manca il template Google per '{slug}'"
        # includedType è opzionale: alcune professioni non hanno un tipo Google dedicato.
        if slug in CATEGORY_INCLUDED_TYPE:
            assert CATEGORY_INCLUDED_TYPE[slug]


def test_categoria_slug_entro_32_caratteri():
    """Il campo Lead.categoria è String(32): uno slug più lungo verrebbe troncato."""
    for slug in CATEGORIE_VALIDE:
        assert len(slug) <= 32, slug


def test_validate_rifiuta_categoria_con_sorgente_incompatibile():
    params = ScrapeParams(locations=["Riccione"], categories=["avvocato"], source="osm")
    with pytest.raises(ValueError, match="avvocato"):
        params.validate()


def test_validate_accetta_categoria_con_sorgente_giusta():
    params = ScrapeParams(locations=["Riccione"], categories=["avvocato"], source="google")
    params.validate()  # non deve sollevare


def test_validate_accetta_categoria_ecommerce_su_osm():
    params = ScrapeParams(locations=["Riccione"], categories=["frantoio", "birrificio"], source="osm")
    params.validate()
