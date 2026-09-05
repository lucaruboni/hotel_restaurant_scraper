#!/usr/bin/env bash
# Aggiorna il server all'ultima versione pubblicata su GitHub e riavvia la
# dashboard. Va lanciato dalla cartella del progetto sul server (non in locale).
#
# Uso:
#   ./scripts/deploy.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Verifico modifiche locali non salvate..."
if [ -n "$(git status --porcelain)" ]; then
  echo "ATTENZIONE: ci sono modifiche locali non committate in questa cartella."
  echo "Il deploy si ferma qui per non perderle. Salvale o scartale prima di riprovare:"
  git status --short
  exit 1
fi

echo "==> Scarico l'ultima versione da GitHub..."
git pull --ff-only

echo "==> Ricostruisco l'immagine..."
docker compose build dashboard

echo "==> Riavvio la dashboard..."
docker compose up -d dashboard

echo "==> Attendo che risponda..."
sleep 3
PORTA="$(grep -E '^DASHBOARD_PORT=' .env 2>/dev/null | cut -d= -f2)"
PORTA="${PORTA:-8010}"
if curl -fsS -o /dev/null "http://127.0.0.1:${PORTA}/login"; then
  echo "✔ Deploy completato: la dashboard risponde su http://127.0.0.1:${PORTA}/login"
else
  echo "✘ La dashboard non risponde dopo il deploy. Controlla i log:"
  echo "  docker compose logs --tail=50 dashboard"
  exit 1
fi
