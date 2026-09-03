"""Arricchimento dati visitando il sito web della struttura:
email, link social (Instagram/Facebook/LinkedIn) e stelle hotel (best-effort).
"""

import re
import logging
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from . import config

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
STARS_RE = re.compile(r"(\d)\s*(?:[-\s]?stelle|\*{1,5}\s*stelle|star hotel)", re.IGNORECASE)

SOCIAL_DOMAINS = {
    "instagram": "instagram.com",
    "facebook": "facebook.com",
    "linkedin": "linkedin.com",
}

CANDIDATE_PATHS = ["", "contatti", "contact", "chi-siamo", "about", "about-us"]

EXCLUDED_EMAIL_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


def _fetch(url: str) -> Optional[str]:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
            return resp.text
    except requests.RequestException as exc:
        logger.debug("Impossibile scaricare %s: %s", url, exc)
    return None


def enrich_from_website(website: str, is_hotel: bool = False) -> dict:
    """Ritorna dict con email, instagram, facebook, linkedin, stars (se trovati)."""
    result = {"email": "", "instagram": "", "facebook": "", "linkedin": "", "stars": ""}
    if not website:
        return result

    if not website.startswith(("http://", "https://")):
        website = "https://" + website

    visited_html = []
    for path in CANDIDATE_PATHS:
        url = urljoin(website if website.endswith("/") else website + "/", path)
        html = _fetch(url)
        if html:
            visited_html.append(html)
        if result["email"] and (result["instagram"] or result["facebook"] or result["linkedin"]):
            break
        if not html:
            continue

        soup = BeautifulSoup(html, "lxml")

        if not result["email"]:
            mailto = soup.select_one('a[href^="mailto:"]')
            if mailto:
                addr = mailto["href"].replace("mailto:", "").split("?")[0].strip()
                if EMAIL_RE.match(addr):
                    result["email"] = addr
            if not result["email"]:
                text_matches = EMAIL_RE.findall(html)
                for m in text_matches:
                    if not m.lower().endswith(EXCLUDED_EMAIL_SUFFIXES):
                        result["email"] = m
                        break

        for key, domain in SOCIAL_DOMAINS.items():
            if result[key]:
                continue
            link = soup.select_one(f'a[href*="{domain}"]')
            if link and link.get("href"):
                result[key] = link["href"]

        if is_hotel and not result["stars"]:
            match = STARS_RE.search(html)
            if match:
                result["stars"] = f"{match.group(1)} stelle"

        # Prova a seguire il link "contatti" nella homepage se non ancora trovato
        if path == "" and not (result["email"] and any([result["instagram"], result["facebook"], result["linkedin"]])):
            contact_link = None
            for a in soup.find_all("a", href=True):
                label = (a.get_text() or "").strip().lower()
                if any(k in label for k in ("contatt", "contact")):
                    contact_link = urljoin(url, a["href"])
                    break
            if contact_link and contact_link not in CANDIDATE_PATHS:
                html2 = _fetch(contact_link)
                if html2:
                    soup2 = BeautifulSoup(html2, "lxml")
                    if not result["email"]:
                        mailto2 = soup2.select_one('a[href^="mailto:"]')
                        if mailto2:
                            addr = mailto2["href"].replace("mailto:", "").split("?")[0].strip()
                            if EMAIL_RE.match(addr):
                                result["email"] = addr
                        if not result["email"]:
                            for m in EMAIL_RE.findall(html2):
                                if not m.lower().endswith(EXCLUDED_EMAIL_SUFFIXES):
                                    result["email"] = m
                                    break
                    for key, domain in SOCIAL_DOMAINS.items():
                        if result[key]:
                            continue
                        link2 = soup2.select_one(f'a[href*="{domain}"]')
                        if link2 and link2.get("href"):
                            result[key] = link2["href"]

    return result
