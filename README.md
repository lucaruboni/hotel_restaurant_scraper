# HoReCa Leads — scraper + dashboard commerciale

Sistema di lead generation per il mercato italiano, in due parti:

1. **Scraper** — trova hotel, ristoranti, professionisti e potenziali clienti
   e-commerce per comune, provincia o regione e ne estrae contatti, social,
   valutazioni e recensioni.
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
docker compose up dashboard        # http://localhost:8010 (vedi DASHBOARD_PORT in .env)

# primo utente
docker compose exec dashboard python -m app.cli create-user --username tuonickname
```

### Avvio senza Docker

```bash
pip install -r requirements.txt
cp .env.example .env               # imposta SECRET_KEY

python -m app.cli create-user --username tuonickname
uvicorn app.main:app --port 8010   # http://localhost:8010
```

### Comandi utili

```bash
python -m app.cli create-user --username tuonickname --password '...'
python -m app.cli set-password --username tuonickname
python -m app.cli set-username --username vecchio --nuovo-username nuovo
python -m app.cli deactivate-user --username tuonickname
python -m app.cli delete-user --username tuonickname
python -m app.cli list-users
pytest -q                          # 65 test
```

### Esposizione privata su un server cloud (Tailscale)

La dashboard contiene dati commerciali reali: su un'istanza con IP pubblico
(es. Oracle Cloud, AWS, ecc.) **non deve mai essere raggiungibile da
internet**. `docker-compose.yml` pubblica la porta solo su `127.0.0.1`:
resta invisibile dall'esterno finché non la esponi esplicitamente sulla tua
rete privata Tailscale.

```bash
# 1. Installa Tailscale sul server (una volta sola)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up          # apre un link: autenticati con il tuo account Tailscale

# 2. Avvia la dashboard (bind solo su localhost, come da docker-compose.yml)
docker compose up -d dashboard

# 3. Esponila SOLO sulla tua tailnet, con HTTPS automatico
sudo tailscale serve --bg https / http://127.0.0.1:8010
```

Da questo momento la dashboard è raggiungibile solo dai tuoi dispositivi
collegati alla stessa rete Tailscale, all'indirizzo mostrato da:

```bash
tailscale status   # mostra il nome macchina, es. sommelier.tuo-tailnet.ts.net
```

apri quindi `https://sommelier.tuo-tailnet.ts.net` da un browser su un
dispositivo che ha fatto login sulla stessa rete Tailscale.

**Non usare `tailscale funnel`** al posto di `serve`: `funnel` pubblica la
porta sull'internet pubblico (l'opposto di quello che vogliamo qui). Se in
futuro un firewall/Security List del cloud provider dovesse comunque avere
la porta 8010 aperta verso l'esterno, chiudila: con il binding a
`127.0.0.1` il rischio è già escluso a livello di container, ma vale la
pena verificarlo anche a livello di rete.

Per fermare l'esposizione: `sudo tailscale serve --https=443 off`.

### Collegare Claude in sola lettura (MCP)

La dashboard espone un endpoint MCP (`/mcp`) che un connettore remoto in
Claude può leggere per costruire una routine, senza che tu debba incollare
dati a mano. È **sola lettura**: nessuno strumento aggiorna stati, registra
interazioni o cancella nulla — per quello resta la dashboard.

```bash
# Genera una chiave e incollala in .env alla riga MCP_API_KEY=
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
docker compose up -d dashboard   # riavvia per caricare la chiave
```

Senza `MCP_API_KEY` impostata, `/mcp` risponde sempre `401` — è chiuso di
default. In Claude (Desktop o web), aggiungi un connettore remoto con:

- **URL**: `https://sommelier-1.tail1583df.ts.net:9443/mcp/` (o l'indirizzo
  Tailscale della tua istanza)
- **Autenticazione**: header `Authorization: Bearer <la tua MCP_API_KEY>`

Raggiungibile solo da un dispositivo collegato alla stessa rete Tailscale
(vedi sopra) — Claude deve girare su una macchina in quella rete, non è
accessibile da internet. Gli strumenti disponibili:

| Strumento | Cosa restituisce |
|---|---|
| `routine_di_oggi` | Nuovi lead da contattare, da ricontattare, incontri fissati, trattative aperte |
| `conteggi_segmenti` | Quanti lead in ciascun segmento (con/senza contatto, contattati, in trattativa, chiusi persi/vinti) |
| `elenco_lead` | Lead filtrati per segmento/categoria/zona/ricerca testuale |
| `metriche_generali` | KPI della dashboard: contattabilità, tassi di risposta/chiusura, valore pipeline |

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

### Categorie

Le categorie sono definite in [`scraper/categories.py`](scraper/categories.py), unica
fonte di verità condivisa da CLI e dashboard, raggruppate in tre profili di ricerca:

| Profilo | Categorie | Sorgente |
|---|---|---|
| **Ricettivo** | hotel, ristorante, bar, campeggio (campeggi e glamping), villaggio_turistico | `osm` (hotel/ristorante anche `google`) |
| **Professionisti** | fotografo, social_media_manager, avvocato, commercialista, architetto, geometra | solo `google` — su OSM sono quasi sempre assenti |
| **Ecommerce** | frantoio, azienda_agricola, pasticceria, torrefazione, birrificio, vivaio, bottega_artigiana | `osm` |

Ogni categoria dichiara le sorgenti con cui è cercabile; selezionarne una con
la sorgente sbagliata (es. `avvocato` con `osm`) restituisce un errore
esplicito invece di una ricerca silenziosamente vuota.

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
| `--types` | Categorie separate da virgola, vedi tabella sopra | `hotel,ristorante` |
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
