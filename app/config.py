"""Impostazioni dell'applicazione, lette da variabili d'ambiente."""

import os
import secrets
import warnings
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool_env(nome: str, default: bool = False) -> bool:
    valore = os.getenv(nome)
    if valore is None:
        return default
    return valore.strip().lower() in {"1", "true", "yes", "si", "sì", "on"}


class Settings:
    """Configurazione runtime. Nessun segreto è mai hardcoded nel repository."""

    def __init__(self) -> None:
        self.app_name = "HoReCa Leads"
        self.environment = os.getenv("APP_ENV", "development")

        self.secret_key = os.getenv("SECRET_KEY", "")
        if not self.secret_key:
            if self.environment == "production":
                raise RuntimeError(
                    "SECRET_KEY obbligatoria in produzione: impostala nel file .env"
                )
            # In sviluppo generiamo una chiave effimera: le sessioni decadono al riavvio.
            self.secret_key = secrets.token_urlsafe(48)
            warnings.warn(
                "SECRET_KEY non impostata: ne uso una temporanea (solo sviluppo). "
                "Imposta SECRET_KEY nel .env per mantenere le sessioni fra i riavvii.",
                stacklevel=2,
            )

        self.data_dir = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
        self.upload_dir = self.data_dir / "uploads"
        self.export_dir = self.data_dir / "exports"
        for directory in (self.data_dir, self.upload_dir, self.export_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self.database_url = os.getenv("DATABASE_URL", f"sqlite:///{self.data_dir / 'horeca.db'}")

        # Sicurezza sessione
        self.session_cookie = "horeca_session"
        self.session_max_age = int(os.getenv("SESSION_MAX_AGE", 60 * 60 * 12))  # 12 ore
        self.cookie_secure = _bool_env("COOKIE_SECURE", self.environment == "production")

        # Rate limiting login
        self.login_max_attempts = int(os.getenv("LOGIN_MAX_ATTEMPTS", 8))
        self.login_window_seconds = int(os.getenv("LOGIN_WINDOW_SECONDS", 300))

        # Upload
        self.max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", 15 * 1024 * 1024))  # 15 MB
        self.allowed_upload_types = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "application/pdf": ".pdf",
            "text/plain": ".txt",
            "text/csv": ".csv",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        }

        # Scraper
        self.google_api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
        self.max_results_cap = int(os.getenv("MAX_RESULTS_CAP", 200))

        # MCP: accesso in sola lettura per Claude (routine, segmenti, metriche).
        # Vuoto per default: l'endpoint /mcp resta chiuso finché non lo imposti.
        self.mcp_api_key = os.getenv("MCP_API_KEY", "").strip()


settings = Settings()
