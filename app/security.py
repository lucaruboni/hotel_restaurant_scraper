"""Sicurezza: hashing password, sessioni firmate, CSRF, rate limiting del login.

Scelte:
- password con bcrypt (cost di default della libreria, salt per-utente);
- sessione in cookie firmato (itsdangerous) con scadenza: nessuno stato server;
- CSRF con token nel cookie di sessione + campo hidden nei form (double submit);
- rate limit del login in memoria per (IP, username) su finestra scorrevole.
"""

import hmac
import secrets
import time
from collections import defaultdict
from typing import Optional

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import settings

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="horeca-session")

# (ip, username) -> lista di timestamp dei tentativi falliti
_login_attempts: dict[tuple[str, str], list[float]] = defaultdict(list)

CSRF_FIELD = "csrf_token"


# --- Password ---------------------------------------------------------------

def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("La password deve essere lunga almeno 10 caratteri")
    # bcrypt lavora su massimo 72 byte: tronchiamo esplicitamente per evitare errori.
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --- Sessione ---------------------------------------------------------------

def create_session_token(user_id: int) -> str:
    """Crea il payload firmato del cookie di sessione, con token CSRF incluso."""
    return _serializer.dumps({"uid": user_id, "csrf": secrets.token_urlsafe(32)})


def read_session_token(token: str) -> Optional[dict]:
    try:
        return _serializer.loads(token, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None


def verify_csrf(session_data: Optional[dict], token_inviato: Optional[str]) -> bool:
    """Confronto a tempo costante fra il token del form e quello di sessione."""
    if not session_data or not token_inviato:
        return False
    atteso = session_data.get("csrf", "")
    if not atteso:
        return False
    return hmac.compare_digest(atteso, token_inviato)


# --- Rate limiting login ----------------------------------------------------

def login_rate_limited(ip: str, username: str) -> bool:
    chiave = (ip, username.lower())
    adesso = time.time()
    finestra = settings.login_window_seconds
    tentativi = [t for t in _login_attempts[chiave] if adesso - t < finestra]
    _login_attempts[chiave] = tentativi
    return len(tentativi) >= settings.login_max_attempts


def register_failed_login(ip: str, username: str) -> None:
    _login_attempts[(ip, username.lower())].append(time.time())


def reset_login_attempts(ip: str, username: str) -> None:
    _login_attempts.pop((ip, username.lower()), None)
