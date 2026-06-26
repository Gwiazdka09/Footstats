#!/usr/bin/env bash
# Backup produkcyjnej bazy Neon (PostgreSQL) -> GCS.
#
# Prod data żyje w Neon (nie w SQLite). Ten skrypt robi off-site pg_dump
# (redundancja niezależna od natywnego PITR Neona) i wrzuca skompresowany
# zrzut do GCS. Conn string bierzemy z GC Secret Manager (DATABASE_URL) —
# workflow jest już uwierzytelniony do GCP przez WIF, więc bez nowego sekretu.
#
# Graceful: brak DATABASE_URL / pg_dump -> WARNING + exit 0 (nie blokuje CI,
# ale głośno sygnalizuje że backup nie powstał — bez fałszywego sukcesu/porażki).
set -uo pipefail

BUCKET="${BUCKET_NAME:?BUCKET_NAME env var required}"
SECRET_NAME="${DB_SECRET_NAME:-DATABASE_URL}"
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
DEST="gs://${BUCKET}/backups/neon_${TIMESTAMP}.sql.gz"
LATEST="gs://${BUCKET}/backups/neon_latest.sql.gz"

# DATABASE_URL: najpierw env (gdyby ustawiony jako GH secret), inaczej Secret Manager.
DB_URL="${DATABASE_URL:-}"
if [[ -z "$DB_URL" ]]; then
  DB_URL=$(gcloud secrets versions access latest --secret="$SECRET_NAME" 2>/dev/null || true)
fi

if [[ -z "$DB_URL" ]]; then
  echo "::warning::Brak DATABASE_URL (env i Secret Manager '$SECRET_NAME' puste) — pomijam backup Neon. Sprawdź nazwę sekretu / uprawnienia WIF."
  exit 0
fi

# Neon = PG17. pg_wrapper (/usr/bin/pg_dump) bywa zawodny i bierze starszą wersję
# (server version mismatch). Wybierz NAJNOWSZY zainstalowany binarny pg_dump wprost.
PG_DUMP=$(ls -1 /usr/lib/postgresql/*/bin/pg_dump 2>/dev/null | sort -V | tail -1)
PG_DUMP="${PG_DUMP:-$(command -v pg_dump || true)}"
if [[ -z "$PG_DUMP" ]]; then
  echo "::warning::pg_dump niedostępny w runnerze — pomijam backup. Dodaj krok instalacji postgresql-client."
  exit 0
fi
echo "Using pg_dump: $PG_DUMP ($("$PG_DUMP" --version))"

echo "Backing up Neon -> $DEST"
# --no-owner/--no-privileges: zrzut przenośny (restore na dowolne konto/rolę).
if "$PG_DUMP" "$DB_URL" --no-owner --no-privileges | gzip | gcloud storage cp - "$DEST"; then
  gcloud storage cp "$DEST" "$LATEST"
  echo "Backup complete: $DEST"
else
  echo "::error::pg_dump/upload nieudany dla Neon."
  exit 1
fi
