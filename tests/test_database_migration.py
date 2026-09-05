"""Test della sincronizzazione additiva dello schema.

Riproduce il problema reale incontrato in produzione: un database SQLite già
popolato (con la tabella `scrape_jobs` creata da una versione precedente del
modello) a cui viene aggiunta una nuova colonna al modello Python. `create_all`
da solo non l'avrebbe aggiunta, e ogni query sulla tabella sarebbe fallita con
`OperationalError: no such column`.
"""

import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.database import Base, _aggiungi_colonne_mancanti


def test_aggiunge_una_colonna_mancante_a_una_tabella_esistente():
    from app import models  # noqa: F401  (registra i modelli sul metadata)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "vecchio.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)

        # Simula un database creato PRIMA che 'annullamento_richiesto' esistesse:
        # tutte le tabelle come da modello attuale, tranne una colonna in meno.
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE scrape_jobs_vecchia AS SELECT "
                "id, user_id, localita, categorie, sorgente, max_results, "
                "con_recensioni, con_arricchimento, stato, trovati, nuovi, "
                "duplicati, errore, csv_path, created_at, started_at, finished_at "
                "FROM scrape_jobs"
            ))
            conn.execute(text("DROP TABLE scrape_jobs"))
            conn.execute(text("ALTER TABLE scrape_jobs_vecchia RENAME TO scrape_jobs"))
            conn.execute(text(
                "INSERT INTO scrape_jobs (localita, categorie, sorgente, stato) "
                "VALUES ('Riccione', 'hotel', 'osm', 'in_corso')"
            ))

        colonne_prima = {c["name"] for c in inspect(engine).get_columns("scrape_jobs")}
        assert "annullamento_richiesto" not in colonne_prima

        _aggiungi_colonne_mancanti(engine)

        colonne_dopo = {c["name"] for c in inspect(engine).get_columns("scrape_jobs")}
        assert "annullamento_richiesto" in colonne_dopo

        # La riga preesistente non deve sparire, e il default deve applicarsi
        # anche a lei (non deve restare NULL su un booleano).
        with engine.connect() as conn:
            riga = conn.execute(text(
                "SELECT localita, annullamento_richiesto FROM scrape_jobs"
            )).one()
        assert riga.localita == "Riccione"
        assert riga.annullamento_richiesto == 0


def test_e_idempotente_su_uno_schema_gia_aggiornato():
    from app import models  # noqa: F401

    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{Path(tmp) / 'nuovo.db'}", future=True)
        Base.metadata.create_all(bind=engine)

        _aggiungi_colonne_mancanti(engine)  # non deve sollevare né duplicare colonne

        colonne = [c["name"] for c in inspect(engine).get_columns("scrape_jobs")]
        assert colonne.count("annullamento_richiesto") == 1
