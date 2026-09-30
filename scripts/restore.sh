#!/usr/bin/env sh
# ============================================================
# UMOA Banking Intelligence — PostgreSQL restore into a NEW database
#
# Usage:  scripts/restore.sh <dump_file> <target_database>
#
# Environment:
#   PG_CONTAINER  name of the PostgreSQL container (default: umoa_postgres)
#
# Safety: the target database must NOT exist. The script never drops nor
# overwrites a database; to replace the live database, restore into a new one,
# verify it, then switch POSTGRES_DB (or rename databases) explicitly.
# pg_restore runs inside the container with its own credentials and stops at
# the first error (--exit-on-error, single transaction).
# ============================================================
set -eu

CONTAINER="${PG_CONTAINER:-umoa_postgres}"
DUMP="${1:-}"
TARGET="${2:-}"
if [ -z "$DUMP" ] || [ -z "$TARGET" ]; then
  echo "usage: scripts/restore.sh <dump_file> <target_database>" >&2
  exit 2
fi
[ -f "$DUMP" ] || { echo "restore: dump file not found" >&2; exit 2; }
case "$TARGET" in
  *[!A-Za-z0-9_]*) echo "restore: invalid database name" >&2; exit 2 ;;
esac

EXISTS="$(docker exec "$CONTAINER" sh -c "psql -U \"\$POSTGRES_USER\" -d postgres -tAc \"SELECT 1 FROM pg_database WHERE datname = '$TARGET'\"")"
if [ "$EXISTS" = "1" ]; then
  echo "restore: database '$TARGET' already exists — refusing to overwrite it" >&2
  exit 3
fi

docker exec "$CONTAINER" sh -c "createdb -U \"\$POSTGRES_USER\" \"$TARGET\""
docker exec -i "$CONTAINER" sh -c "pg_restore -U \"\$POSTGRES_USER\" -d \"$TARGET\" --no-owner --exit-on-error --single-transaction" < "$DUMP"
echo "restore: '$TARGET' restored from $(basename "$DUMP")"
