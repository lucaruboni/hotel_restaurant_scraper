# HoReCa Leads — scraper + dashboard commerciale

Sistema di lead generation per hotel e ristoranti italiani, in due parti:

1. **Scraper** — trova hotel e ristoranti per comune, provincia o regione e ne
   estrae contatti, social, valutazioni e recensioni.
2. **Dashboard privata (FastAPI)** — con login, lancia lo scraper, importa i
   risultati **senza duplicati**, gestisce la **pipeline commerciale** e tiene
   una **scheda note** completa per ogni potenziale cliente.

---

## Dashboard

### Cosa fa

- **Login privato** (bcrypt, sessioni firmate, CSRF, rate limiting).
- **Avvio dello scraper** dall'interfaccia, con avanzamento live.
- **Import deduplicato**: le strutture già in archivio non vengono duplicate; i
  loro campi vuoti vengono completati con i nuovi dati.
- **CSV** scaricabile per ogni ricerca (solo i lead nuovi) e export CSV
  dell'elenco filtrato a schermo.
- **Pipeline commerciale**: nuovo → contattato → ha risposto → incontro fissato
  → incontro fatto → in trattativa → chiuso (vinto/perso).
- **Registro contatti**: quando, con quale canale (email, telefono, WhatsApp,
  Instagram, Facebook, LinkedIn, di persona) e con quale esito.
- **Metriche**: contattabilità, funnel, tasso di risposta per canale, incontri,
  trattative, conversione, valore pipeline, copertura per zona, da ricontattare.
- **Scheda note a pagina intera** per ogni cliente: note testuali, foto,
  screenshot, PDF e documenti, consultabili e modificabili in qualsiasi momento.

### Avvio con Docker

```bash
cp .env.example .env
# genera la chiave e incollala in SECRET_KEY:
python -c "import secrets; print(secrets.token_urlsafe(48))"
# (facoltativo) incolla la tua GOOGLE_PLACES_API_KEY

docker compose build
docker compose up dashboard        # http://localhost:8000

# primo utente
docker compose exec dashboard python -m app.cli create-user --email tu@esempio.it
```

### Avvio senza Docker

```bash
pip install -r requirements.txt
cp .env.example .env               # imposta SECRET_KEY

python -m app.cli create-user --email tu@esempio.it
uvicorn app.main:app --port 8000   # http://localhost:8000
```

### Comandi utili

```bash
python -m app.cli create-user --email tu@esempio.it --password '...'
python -m app.cli set-password --email tu@esempio.it
python -m app.cli list-users
pytest -q                          # 60 test
```

---

## Scraper da riga di comando

Utilizzabile anche da solo, senza dashboard.

```bash
# Più località insieme, sorgente gratuita OpenStreetMap
python -m scraper.main --location "Riccione, Misano Adriatico, Cattolica" --output out.csv

# Sorgente Google Places con recensioni
python -m scraper.main --location "Provincia di Rimini" --source google --reviews --output rimini.csv

# Con Docker
docker compose run --rm scraper --location "Riccione" --source google --output output/riccione.csv
```

### Sorgenti dati

| | `osm` (default) | `google` |
|---|---|---|
| API key | non serve | richiesta (Google Cloud, a consumo) |
| Copertura | dipende dai contributi OpenStreetMap | molto ampia |
| Valutazioni e recensioni | no | sì |
| Telefono/indirizzo | parziali | quasi sempre presenti |

In entrambi i casi, se la struttura ha un sito web lo scraper lo visita
(homepage + pagina contatti) per estrarre **email** e **social**, e per gli
hotel tenta di ricavare le **stelle**.

### Opzioni

| Opzione | Descrizione | Default |
|---|---|---|
| `--location` | Comune/provincia/regione; più zone separate da virgola | obbligatorio |
| `--types` | `hotel`, `ristorante` o entrambi | `hotel,ristorante` |
| `--source` | `osm` o `google` | `osm` |
| `--max-results` | Massimo risultati per categoria | `40` |
| `--reviews` | Scarica le recensioni (solo `google`) | disattivo |
| `--no-website-enrichment` | Salta la visita ai siti (più veloce) | disattivo |
| `--output` / `--json` | File di output | `risultati.csv` |
| `--no-ui` | Output semplice senza interfaccia | disattivo |

---

## Struttura del progetto

```
scraper/     motore di scraping e CLI (core.py è condiviso con la dashboard)
app/         dashboard FastAPI (router, servizi, modelli, template, static)
tests/       suite pytest (rete esterna sempre mockata)
CLAUDE.md    istruzioni di progetto per agenti AI e contributori
```

## Sicurezza

- Password con bcrypt; nessun segreto nel repository (`.env` è ignorato).
- Sessioni in cookie firmati `HttpOnly` + `SameSite=Lax`, `Secure` in produzione.
- CSRF obbligatorio su ogni scrittura, verificato in middleware (fail-closed).
- Upload: allowlist di tipi, limite 15 MB, nome su disco casuale, file serviti
  solo a utenti autenticati.
- Header di sicurezza (CSP, nosniff, X-Frame-Options, Referrer-Policy) su ogni
  risposta; documentazione API disabilitata.

## Note

- Le stelle degli hotel non sono fornite in modo affidabile da nessuna sorgente:
  vengono cercate nel sito della struttura e possono risultare vuote.
- Rispetta i limiti d'uso delle API (Nominatim/Overpass hanno rate limit
  pubblici; Google Places ha costi a consumo oltre la quota gratuita).
