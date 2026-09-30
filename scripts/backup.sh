#!/usr/bin/env sh
# ============================================================
# UMOA Banking Intelligence — PostgreSQL backup (custom format)
#
# Usage:  scripts/backup.sh [database] [output_file]
#   database     default: the container's POSTGRES_DB
#   output_file  default: backups/<database>_<UTC timestamp>.dump
#
# Environment:
#   PG_CONTAINER  name of the PostgreSQL container (default: umoa_postgres)
#
# pg_dump runs INSIDE the container with the container's own credentials:
# no password is passed on the command line, written to disk or printed.
# The dump contains the schema, constraints, indexes and every row, including
# provenance (documents, sources, deal_sources) and the audit trail
# (financial_data_review_events).
# ============================================================
set -eu

CONTAINER="${PG_CONTAINER:-umoa_postgres}"
DB="${1:-}"
if [ -z "$DB" ]; then
  DB="$(docker exec "$CONTAINER" sh -c 'printf %s "$POSTGRES_DB"')"
fi
case "$DB" in
  *[!A-Za-z0-9_]*|"") echo "backup: invalid database name" >&2; exit 2 ;;
esac

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${2:-backups/${DB}_${STAMP}.dump}"
mkdir -p "$(dirname "$OUT")"
TMP="${OUT}.partial"
# Never leave a truncated archive behind if pg_dump fails.
trap 'rm -f "$TMP"' EXIT

docker exec "$CONTAINER" sh -c "pg_dump -U \"\$POSTGRES_USER\" -d \"$DB\" --format=custom --no-owner" > "$TMP"
mv "$TMP" "$OUT"

# Integrity check: the archive must be readable by pg_restore.
docker exec -i "$CONTAINER" pg_restore --list > /dev/null < "$OUT"
echo "backup: $OUT ($(wc -c < "$OUT" | tr -d ' ') bytes)"
