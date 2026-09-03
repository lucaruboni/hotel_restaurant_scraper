# hotel_restaurant_scraper

Scraper in Python (con bella UI da terminale) per trovare **hotel** e
**ristoranti** in una provincia o regione italiana, con i seguenti dati
(quando disponibili):

- Nome e indirizzo
- Stelle (solo hotel, best-effort)
- Sito web
- Email
- Numero di telefono
- Social: Instagram, Facebook, LinkedIn
- Valutazione e numero recensioni (sorgente Google)
- Fascia di prezzo
- Coordinate GPS e link mappa
- Recensioni (facoltativo, solo sorgente Google: testo + voto + autore)

## Come funziona

Due sorgenti dati selezionabili con `--source`:

- **`osm` (default, gratis, nessuna API key)** — usa OpenStreetMap
  (Nominatim per geocodificare la provincia/regione + Overpass API per
  cercare gli hotel/ristoranti nell'area). Non fornisce rating/recensioni,
  e la copertura dipende da quanto è mappata la zona su OSM.
- **`google`** — usa **Google Places API (New)** (Text Search + Place
  Details, incluse le recensioni). Più completo e affidabile, ma richiede
  una API key con fatturazione attiva.

In entrambi i casi, se un sito web è disponibile, lo scraper lo visita
(homepage + pagina contatti, se trovata) per estrarre **email** e link ai
**social** (Instagram/Facebook/LinkedIn), dati che né OSM né Google
forniscono in modo affidabile. Per gli hotel tenta anche di individuare le
**stelle** cercando pattern come "4 stelle" nel testo del sito.

Durante l'esecuzione l'interfaccia da terminale (libreria `rich`) mostra un
banner con i parametri, una progress bar live per categoria, i risultati
trovati man mano (con indicatori email/social) e una tabella di riepilogo
finale con statistiche e percorso del file salvato.

## Uso con Docker (consigliato)

Non serve installare Python o dipendenze sulla tua macchina.

```bash
cp .env.example .env   # necessario solo se usi --source google

docker compose build

# Hotel e ristoranti in una provincia (sorgente OSM, gratis)
docker compose run --rm scraper --location "Provincia di Lucca" --output output/lucca.csv

# Solo hotel in una regione, sorgente Google con recensioni
docker compose run --rm scraper --location "Toscana" --types hotel \
    --source google --reviews --output output/hotel_toscana.csv
```

I file CSV/JSON generati compaiono nella cartella locale `./output`
(montata come volume nel container).

## Uso senza Docker

Richiede Python 3.9+.

```bash
pip install -r requirements.txt
cp .env.example .env   # necessario solo se usi --source google

python -m scraper.main --location "Provincia di Firenze" --output firenze.csv
```

### Google Places API (opzionale, solo per `--source google`)

1. Vai su https://console.cloud.google.com/
2. Crea/seleziona un progetto, abilita **"Places API (New)"**
3. Crea una API key (Credenziali → Crea credenziali → Chiave API)
4. Attiva la fatturazione (quota gratuita mensile inclusa; oltre si paga a
   consumo — consulta i prezzi ufficiali Google)
5. Inserisci la chiave in `.env` come `GOOGLE_PLACES_API_KEY`

## Esempi

```bash
# Hotel e ristoranti in una provincia (OSM, default)
python -m scraper.main --location "Provincia di Firenze" --output firenze.csv

# Solo hotel in una regione, sorgente Google con recensioni
python -m scraper.main --location "Toscana" --types hotel --source google \
    --reviews --output hotel_toscana.csv

# Solo ristoranti, più risultati, anche export JSON
python -m scraper.main --location "Provincia di Milano" --types ristorante \
    --max-results 100 --output milano_ristoranti.csv --json milano_ristoranti.json

# Output semplice (senza UI grafica), utile per log/CI
python -m scraper.main --location "Sicilia" --no-ui
```

### Opzioni principali

| Opzione | Descrizione | Default |
|---|---|---|
| `--location` | Provincia, regione o comune italiano; più zone insieme separate da virgola, es. "Riccione, Misano Adriatico, Cattolica" | obbligatorio |
| `--types` | `hotel`, `ristorante` o `hotel,ristorante` | `hotel,ristorante` |
| `--source` | `osm` (gratis) o `google` (richiede API key) | `osm` |
| `--max-results` | Numero massimo di risultati per categoria | `40` |
| `--reviews` | Recupera anche le recensioni (solo `--source google`) | disattivo |
| `--max-reviews` | Numero di recensioni esportate per luogo | `3` |
| `--no-website-enrichment` | Salta la visita ai siti web (più veloce) | disattivo |
| `--output` | File CSV di output | `risultati.csv` |
| `--json` | File JSON opzionale di output | nessuno |
| `--sleep` | Pausa tra le richieste (secondi) | `0.2` |
| `--no-ui` | Disattiva l'interfaccia grafica da terminale | disattivo |

## Note

- Il campo "stelle" per gli hotel non è fornito in modo affidabile da
  nessuna delle due sorgenti: viene cercato nel testo del sito web della
  struttura (o nel tag `stars` di OSM, se presente) e può risultare vuoto.
- La sorgente `osm` è gratuita ma dipende dalla completezza dei dati su
  OpenStreetMap per quella zona: alcune strutture potrebbero mancare o
  avere pochi contatti compilati.
- Rispetta i limiti di utilizzo delle API (Nominatim/Overpass hanno rate
  limit pubblici; Google Places ha costi a consumo oltre la quota
  gratuita): usa `--max-results` ragionevoli.
- L'arricchimento dal sito web scarica solo homepage e (se trovata) la
  pagina contatti: non effettua crawling profondo del sito.
