"""Test della resilienza del client Overpass: la rete è sempre mockata.

Le istanze pubbliche di Overpass rispondono 406/429/504 quando sono sotto
carico, anche a query valide: il client deve ritentare invece di fallire.
"""

import pytest

from scraper import config, osm_places
from scraper.osm_places import OSMPlacesClient, OverpassNonDisponibile


class RispostaFinta:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self.text = "" if status_code == 200 else "<html>Not Acceptable</html>"
        self._payload = payload or {"elements": []}

    def json(self):
        return self._payload

    def raise_for_status(self):
        raise AssertionError("non deve essere chiamato sugli stati ritentabili")


@pytest.fixture(autouse=True)
def _niente_attese(monkeypatch):
    """Azzera le attese di backoff per non rallentare la suite."""
    monkeypatch.setattr(osm_places.time, "sleep", lambda _s: None)


def _client_con_risposte(monkeypatch, risposte, url_singolo=True):
    if url_singolo:
        monkeypatch.setattr(config, "OVERPASS_URLS", ["https://overpass.test/api"])
    chiamate = []

    def finta_post(url, data=None, timeout=None):
        chiamate.append(url)
        return risposte.pop(0)

    client = OSMPlacesClient()
    monkeypatch.setattr(client.session, "post", finta_post)
    return client, chiamate


ELEMENTO = {
    "type": "node", "id": 1, "lat": 44.0, "lon": 12.6,
    "tags": {"name": "Hotel Mock", "addr:street": "Via Mock", "phone": "0541 1"},
}


def test_ritenta_dopo_406_e_poi_riesce(monkeypatch):
    risposte = [
        RispostaFinta(406),
        RispostaFinta(429),
        RispostaFinta(200, {"elements": [ELEMENTO]}),
    ]
    client, chiamate = _client_con_risposte(monkeypatch, risposte)

    elementi = list(client.search_places(3600042788, "hotel", max_results=5))

    assert len(chiamate) == 3, "deve aver ritentato due volte prima di riuscire"
    assert [e["tags"]["name"] for e in elementi] == ["Hotel Mock"]


def test_passa_al_mirror_quando_il_primo_endpoint_e_irraggiungibile(monkeypatch):
    import requests

    monkeypatch.setattr(
        config, "OVERPASS_URLS", ["https://primo.test/api", "https://mirror.test/api"]
    )
    chiamate = []

    def finta_post(url, data=None, timeout=None):
        chiamate.append(url)
        if url == "https://primo.test/api":
            raise requests.ConnectionError("host irraggiungibile")
        return RispostaFinta(200, {"elements": [ELEMENTO]})

    client = OSMPlacesClient()
    monkeypatch.setattr(client.session, "post", finta_post)

    elementi = list(client.search_places(3600042788, "hotel", max_results=5))

    assert chiamate == ["https://primo.test/api", "https://mirror.test/api"], (
        "su endpoint irraggiungibile deve passare subito al mirror, senza insistere"
    )
    assert len(elementi) == 1


def test_errore_esplicito_quando_tutti_gli_endpoint_rifiutano(monkeypatch):
    monkeypatch.setattr(config, "OVERPASS_URLS", ["https://uno.test/api"])
    monkeypatch.setattr(config, "OVERPASS_TENTATIVI", 2)

    client = OSMPlacesClient()
    monkeypatch.setattr(
        client.session, "post", lambda url, data=None, timeout=None: RispostaFinta(406)
    )

    with pytest.raises(OverpassNonDisponibile) as exc:
        list(client.search_places(3600042788, "hotel", max_results=5))

    messaggio = str(exc.value)
    assert "sovraccarico" in messaggio
    assert "HTTP 406" in messaggio, "il messaggio deve riportare l'ultimo esito reale"


def test_retry_after_viene_rispettato():
    resp = RispostaFinta(429)
    resp.headers["Retry-After"] = "12"
    assert OSMPlacesClient._attesa(resp, tentativo=1) == 12.0

    resp_senza_header = RispostaFinta(429)
    assert OSMPlacesClient._attesa(resp_senza_header, tentativo=2) == (
        config.OVERPASS_ATTESA_BASE * 2
    )


def test_user_agent_osm_non_finge_di_essere_un_browser():
    """Overpass risponde 406 ai client che si spacciano per Mozilla."""
    assert "Mozilla" not in config.OSM_USER_AGENT
    assert "HotelRestaurantScraper" in config.OSM_USER_AGENT
    assert OSMPlacesClient().session.headers["User-Agent"] == config.OSM_USER_AGENT
