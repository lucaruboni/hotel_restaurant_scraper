"""Engine e sessione SQLAlchemy."""

import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

logger = logging.getLogger(__name__)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency FastAPI: apre e chiude una sessione per richiesta."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Crea le tabelle mancanti e aggiunge le colonne mancanti a quelle esistenti.

    `create_all` crea solo le tabelle assenti: su un database già popolato non
    altera quelle esistenti. Senza questo passo, ogni nuova colonna aggiunta a
    un modello (es. `ScrapeJob.annullamento_richiesto`) romperebbe le
    installazioni con dati reali già in archivio. La sincronizzazione è
    sempre additiva: aggiunge colonne mancanti, non rinomina né elimina nulla.
    """
    from . import models  # noqa: F401  (registra i modelli sul metadata)

    Base.metadata.create_all(bind=engine)
    _aggiungi_colonne_mancanti(engine)


def _aggiungi_colonne_mancanti(engine_) -> None:
    inspector = inspect(engine_)
    with engine_.begin() as conn:
        for tabella in Base.metadata.sorted_tables:
            if not inspector.has_table(tabella.name):
                continue
            colonne_esistenti = {col["name"] for col in inspector.get_columns(tabella.name)}
            for colonna in tabella.columns:
                if colonna.name in colonne_esistenti:
                    continue
                tipo_ddl = colonna.type.compile(dialect=engine_.dialect)
                default_sql = ""
                if colonna.default is not None and getattr(colonna.default, "is_scalar", False):
                    valore = colonna.default.arg
                    if isinstance(valore, bool):
                        default_sql = f" DEFAULT {1 if valore else 0}"
                    elif isinstance(valore, (int, float)):
                        default_sql = f" DEFAULT {valore}"
                    elif isinstance(valore, str):
                        default_sql = " DEFAULT '{}'".format(valore.replace("'", "''"))
                logger.info("Aggiungo la colonna mancante %s.%s", tabella.name, colonna.name)
                conn.execute(
                    text(f'ALTER TABLE "{tabella.name}" ADD COLUMN "{colonna.name}" {tipo_ddl}{default_sql}')
                )
