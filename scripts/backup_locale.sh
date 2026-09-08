#!/usr/bin/env bash
# Backup del database (lead, utenti, note) dall'istanza Oracle a questo
# computer. Va lanciato QUI, sul tuo PC — non sul server.
#
# Uso:
#   ./scripts/backup_locale.sh
#
# Prima di usarlo la prima volta, personalizza le variabili qui sotto.
set -euo pipefail

# --- Da personalizzare -------------------------------------------------
CHIAVE_SSH="$HOME/Scaricati/wine_utility/ssh-key-2026-05-06.key"
HOST="ubuntu@sommelier-1"
CARTELLA_REMOTA="~/hotel_restaurant_scraper_nuovo/data/horeca.db"
CARTELLA_BACKUP="$HOME/backup-horeca-leads"
GIORNI_DA_TENERE=30
# -------------------------------------------------------------------------

mkdir -p "$CARTELLA_BACKUP"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DESTINAZIONE="$CARTELLA_BACKUP/horeca-$TIMESTAMP.db"

echo "==> Scarico il database da $HOST..."
scp -i "$CHIAVE_SSH" "$HOST:$CARTELLA_REMOTA" "$DESTINAZIONE"

echo "==> Salvato in $DESTINAZIONE ($(du -h "$DESTINAZIONE" | cut -f1))"

echo "==> Elimino i backup più vecchi di $GIORNI_DA_TENERE giorni..."
find "$CARTELLA_BACKUP" -name "horeca-*.db" -mtime "+$GIORNI_DA_TENERE" -delete

echo "==> Backup presenti:"
ls -lh "$CARTELLA_BACKUP"
