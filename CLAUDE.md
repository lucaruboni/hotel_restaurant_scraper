# CLAUDE.md — Istruzioni di progetto per agenti AI

Questo file è la fonte di verità per chiunque (umano o agente) lavori su questo
repository. Leggilo **prima** di scrivere codice.

---

## 1. Cos'è questo progetto

Un sistema di **lead generation per il mercato italiano**, nato per il settore
HoReCa (hotel e ristoranti) e poi esteso a tre profili commerciali distinti,
composto da due parti:

1. **Scraper** (`scraper/`) — CLI che trova potenziali clienti per
   provincia / regione / comune e ne estrae: nome, indirizzo, telefono, email,
   sito web, social (Instagram/Facebook/LinkedIn), stelle (hotel), valutazioni
   e recensioni. Le categorie sono definite in `scraper/categories.py`, unica
   fonte di verità condivisa da CLI e dashboard, raggruppate in tre profili:
   - **ricettivo**: hotel, ristoranti, bar, campeggi/glamping, villaggi
     turistici — sorgente `osm` (OpenStreetMap, gratis);
   - **professionisti**: fotografi, social media manager, avvocati,
     commercialisti, architetti, geometri — sorgente `google` (OSM li copre
     troppo poco per essere utile);
   - **ecommerce**: produttori e botteghe artigiane candidati a un e-commerce
     che spesso non hanno ancora (frantoi, aziende agricole, pasticcerie,
     torrefazioni, birrifici, vivai, botteghe artigiane) — sorgente `osm`.
   Ogni categoria dichiara le sorgenti con cui è cercabile: aggiungerne una
   nuova richiede di toccare `scraper/categories.py` più il filtro OSM o il
   template di ricerca Google, non il resto della codebase.
2. **Dashboard privata** (`app/`) — applicazione FastAPI con login che
   permette di lanciare lo scraper, importare i risultati deduplicati nel
   database, gestire la **pipeline commerciale** (contattato → risposto →
   incontro → trattativa → chiuso) e tenere una **scheda note** completa per
   ogni potenziale cliente (testi, foto, screenshot, file).

L'obiettivo di business: trovare strutture ricettive, contattarle, tracciare
ogni interazione e chiudere contratti. Ogni scelta tecnica deve servire questo
obiettivo.

---

## 2. Come devi lavorare: i cappelli da indossare

Su ogni task indossa **tutti** i cappelli pertinenti, in quest'ordine.

### 🧠 Ingegnere del software esperto
- Progetta prima di scrivere: modello dati, confini dei moduli, flussi.
- Nessuna logica duplicata: la logica di scraping vive in `scraper/core.py` ed
  è condivisa fra CLI e web. Se ti serve copiare-incollare, estrai una funzione.
- Errori espliciti: niente `except: pass`. Logga o propaga con contesto.
- Le migrazioni dello schema sono esplicite; non rompere dati esistenti.

### 🐍 Programmatore Python esperto
- Python 3.11+, type hints ovunque nelle firme pubbliche.
- Dataclass / Pydantic per i dati strutturati, mai dict anonimi che girano fra
  i moduli.
- Nomi e docstring in italiano (il committente è italiano), codice idiomatico.
- Dipendenze minime e motivate: ogni pacchetto nuovo va giustificato.

### ⚡ Programmatore FastAPI esperto
- Router separati per dominio (`app/routers/`), servizi separati dalla vista
  (`app/services/`), niente query SQL nei template.
- Dependency injection per sessione DB e utente corrente (`app/deps.py`).
- I job lunghi (scraping) non bloccano il request loop: girano in background
  con stato persistito su DB e polling lato UI.
- Risposte HTML server-rendered (Jinja2) + HTMX per gli aggiornamenti
  parziali. Nessun build step JS: deve funzionare con `docker compose up`.

### 🔒 Cyber security expert
Regole non negoziabili:
- **Mai** committare segreti. `.env` è in `.gitignore`; `SECRET_KEY` e
  `GOOGLE_PLACES_API_KEY` arrivano solo da variabili d'ambiente.
- Password con **bcrypt** (mai MD5/SHA nudi, mai plaintext).
- Sessioni: cookie firmati, `HttpOnly`, `SameSite=Lax`, `Secure` in
  produzione, con scadenza.
- **CSRF token** su ogni form POST. Rate limiting sul login.
- Upload file: allowlist di estensioni/MIME, limite di dimensione, nome su
  disco generato con UUID (mai il nome utente), serviti solo da endpoint
  autenticati — mai da una directory statica pubblica.
- Query solo via ORM parametrizzato. Autoescape Jinja2 sempre attivo.
- Header di sicurezza (CSP, `X-Content-Type-Options`, `Referrer-Policy`,
  `X-Frame-Options`) su ogni risposta.
- Ogni risorsa (lead, nota, allegato) va verificata come appartenente
  all'utente/organizzazione prima di leggerla o modificarla.

### 🎨 UI/UX design expert (standard 2026/2027)
- Design system a token CSS (`app/static/css/app.css`): colori semantici,
  spaziature su scala, raggi, ombre. Niente valori magici sparsi.
- Dark mode e light mode entrambe curate, con `prefers-color-scheme` e switch
  manuale persistito.
- Gerarchia tipografica chiara, densità informativa alta ma respirata,
  micro-interazioni sobrie (transizioni 150–250ms), zero animazioni gratuite.
- Accessibilità: contrasto AA, focus visibile, navigazione da tastiera,
  `aria-label` sui controlli icona, target touch ≥ 44px.
- Responsive reale: la tabella lead diventa lista su mobile.
- La **scheda note** è una pagina intera pensata per la lettura e la scrittura:
  colonna di contenuto leggibile, allegati in galleria, salvataggio senza
  perdere il contesto.

### 📈 Marketing expert
- Le metriche devono rispondere a domande di business, non essere numeri
  decorativi: quanti lead contattabili ho (con email/telefono)? qual è il tasso
  di risposta per canale? dove si blocca il funnel?
- Segmentazione utile: per località, per categoria (hotel/ristorante), per
  stelle/fascia di prezzo, per qualità del contatto.

### 💼 Venditore esperto
- La pipeline riflette un processo di vendita reale:
  `nuovo → contattato → risposto → incontro fissato → incontro fatto →
  in trattativa → chiuso (vinto/perso)`.
- Ogni interazione registra **quando**, **come** (canale) e **con quale esito**:
  serve per non ripetersi e per suonare coerenti alla chiamata successiva.
- La scheda note esiste per la **coerenza commerciale**: chi ho sentito, cosa
  gli ho promesso, quali obiezioni ha fatto, quando ricontattarlo.

### 🧪 Test expert
- `pytest` con database SQLite temporaneo per test, mai il DB reale.
- Copri: autenticazione (login, logout, accesso negato), CSRF, deduplica lead,
  transizioni di pipeline, upload allegati, calcolo metriche.
- Le chiamate di rete esterne (Google/OSM/siti web) sono **sempre mockate** nei
  test: la suite deve girare offline.
- `pytest -q` deve passare prima di ogni commit.

---

## 3. Architettura

```
scraper/                 CLI e motore di scraping
  core.py                API programmatica condivisa (CLI + web)
  google_places.py       sorgente Google Places API (New)
  osm_places.py          sorgente OpenStreetMap (Nominatim + Overpass)
  site_enrichment.py     estrazione email/social/stelle dal sito della struttura
  models.py              PlaceResult, Review
  exporter.py            export CSV/JSON
  ui.py                  interfaccia terminale (rich)
  main.py                entrypoint CLI

app/                     dashboard FastAPI
  main.py                app factory, middleware, montaggio router
  config.py              impostazioni da env
  database.py            engine + sessione SQLAlchemy
  models.py              User, Lead, Interaction, Note, Attachment, ScrapeJob
  security.py            hashing password, sessioni firmate, CSRF, rate limit
  deps.py                dipendenze FastAPI (utente corrente, DB)
  mcp_server.py           server MCP in sola lettura per Claude (routine, segmenti, metriche)
  services/
    leads.py             import deduplicato, filtri, export CSV
    metrics.py           KPI e funnel
    scrape_runner.py     esecuzione job in background
  routers/               auth, dashboard, leads, notes, scrape
  templates/             Jinja2
  static/                CSS e JS (nessun build step)

tests/                   pytest
```

**Regola di dipendenza:** `app/` può importare `scraper/`; `scraper/` non deve
mai importare `app/`. Lo scraper resta utilizzabile da solo via CLI.

---

## 4. Deduplica dei lead (regola centrale)

Un lead è identificato dalla sua `dedup_key`, calcolata in
`app/services/leads.py`:

1. se c'è il sito web → dominio normalizzato;
2. altrimenti se c'è il telefono → solo cifre, normalizzato;
3. altrimenti → `nome normalizzato + | + indirizzo normalizzato`.

Normalizzazione: minuscolo, accenti rimossi, punteggiatura e spazi multipli
compressi, prefissi tipo "hotel"/"ristorante" mantenuti (fanno parte del nome).

All'import: se la `dedup_key` esiste già, il lead **non** viene duplicato — i
campi vuoti dell'esistente vengono arricchiti con i nuovi dati (mai
sovrascritti se già valorizzati), e il contatore `new_leads` non aumenta.
Il CSV salvato da un job contiene **solo i lead nuovi** di quel job.

---

## 5. Comandi

```bash
# Test (devono passare prima di ogni commit)
pytest -q

# Dashboard in locale
uvicorn app.main:app --reload --port 8000

# Creazione primo utente
python -m app.cli create-user --username tuonickname --password '...'

# Scraper da CLI
python -m scraper.main --location "Riccione, Cattolica" --source google --output out.csv

# Tutto con Docker
docker compose up dashboard          # dashboard su http://localhost:8000
docker compose run --rm scraper --location "Riccione" --source google
```

---

## 6. Convenzioni

- Messaggi di commit in italiano, imperativi, con corpo che spiega il perché.
- Branch di lavoro: `claude/italian-hotel-restaurant-scraper-0ktjlu`.
- Nessun dato reale di clienti nel repository (il DB e `output/` sono ignorati).
- Prima di dichiarare una funzionalità completa: eseguila davvero e mostra
  l'esito. Se qualcosa non è stato testato, dillo esplicitamente.
