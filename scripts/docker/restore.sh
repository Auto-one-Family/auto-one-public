#!/bin/bash
set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup.sql.gz|latest>"
    ls -1t backups/*.sql.gz 2>/dev/null | head -5
    exit 1
fi

FILE="$1"
[ "$FILE" = "latest" ] && FILE=$(ls -1t backups/*.sql.gz | head -1)

echo "WARNING: This will DESTROY all data!"
read -p "Continue? [y/N] " -n 1 -r
echo
[[ ! $REPLY =~ ^[Yy]$ ]] && exit 0

docker stop automationone-server 2>/dev/null || true
docker exec automationone-postgres psql -U god_kaiser -d postgres -c "DROP DATABASE IF EXISTS god_kaiser_db;"
docker exec automationone-postgres psql -U god_kaiser -d postgres -c "CREATE DATABASE god_kaiser_db OWNER god_kaiser;"
gunzip -c "$FILE" | docker exec -i automationone-postgres psql -U god_kaiser -d god_kaiser_db
docker start automationone-server

echo "Restore complete"
