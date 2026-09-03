# hotel_restaurant_scraper

Scraper in Python per trovare **hotel** e **ristoranti** in una provincia o
regione italiana, con i seguenti dati (quando disponibili):

- Nome e indirizzo
- Stelle (solo hotel, best-effort dal sito web)
- Sito web
- Email
- Numero di telefono
- Social: Instagram, Facebook, LinkedIn
- Valutazione Google e numero recensioni
- Fascia di prezzo
- Coordinate GPS e link Google Maps
- Recensioni (facoltativo, testo + voto + autore)

## Come funziona

1. **Google Places API (New)** viene usata per la ricerca (Text Search) e i
   dettagli del luogo (Place Details, incluse le recensioni). È la fonte più
   affidabile e conforme ai termini di servizio per nome, indirizzo,
   telefono, sito web, valutazione e recensioni.
2. Se un sito web è disponibile, lo scraper lo visita (homepage + pagina
   contatti, se trovata) per estrarre **email** e link ai **social**
   (Instagram/Facebook/LinkedIn), dati che Google non fornisce. Per gli
   hotel tenta anche di individuare le **stelle** cercando pattern come
   "4 stelle" nel testo del sito (best-effort: non tutte le strutture la
   indicano online).

## Requisiti

- Python 3.9+
- Una **API key di Google Places (New)**:
  1. Vai su https://console.cloud.google.com/
  2. Crea/seleziona un progetto, abilita **"Places API (New)"**
  3. Crea una API key (Credenziali → Crea credenziali → Chiave API)
  4. Attiva la fatturazione (Google offre una quota gratuita mensile;
     oltre quella si paga per richiesta — consulta i prezzi ufficiali)

## Installazione

```bash
pip install -r requirements.txt
cp .env.example .env
# modifica .env e inserisci la tua GOOGLE_PLACES_API_KEY
```

## Uso

```bash
# Hotel e ristoranti in una provincia
python -m scraper.main --location "Provincia di Firenze" --output firenze.csv

# Solo hotel in una regione, con recensioni
python -m scraper.main --location "Toscana" --types hotel --reviews --output hotel_toscana.csv

# Solo ristoranti, più risultati, anche export JSON
python -m scraper.main --location "Provincia di Milano" --types ristorante \
    --max-results 100 --output milano_ristoranti.csv --json milano_ristoranti.json
```

### Opzioni principali

| Opzione | Descrizione | Default |
|---|---|---|
| `--location` | Provincia o regione italiana (es. "Provincia di Torino", "Sicilia") | obbligatorio |
| `--types` | `hotel`, `ristorante` o `hotel,ristorante` | `hotel,ristorante` |
| `--max-results` | Numero massimo di risultati per categoria | `40` |
| `--reviews` | Recupera anche le recensioni (chiamata extra per luogo) | disattivo |
| `--max-reviews` | Numero di recensioni esportate per luogo | `3` |
| `--no-website-enrichment` | Salta la visita ai siti web (più veloce) | disattivo |
| `--output` | File CSV di output | `risultati.csv` |
| `--json` | File JSON opzionale di output | nessuno |
| `--sleep` | Pausa tra le richieste (secondi) | `0.2` |

## Note

- Il campo "stelle" per gli hotel **non è fornito da Google Places**: viene
  cercato nel testo del sito web della struttura e può risultare vuoto.
- Rispetta i limiti di utilizzo e i costi delle Google Places API: usa
  `--max-results` ragionevoli e monitora l'uso in Google Cloud Console.
- L'arricchimento dal sito web scarica solo homepage e (se trovata) la
  pagina contatti: non effettua crawling profondo del sito.
