#!/bin/bash
# PostgreSQL Init Script для настройки WAL архивирования
# Этот скрипт выполняется при первой инициализации БД

set -euo pipefail

# Создание директории для WAL архива
mkdir -p /wal_archive
chmod 700 /wal_archive

# Настройка PostgreSQL для WAL архивирования
# Этот скрипт будет выполнен через docker-entrypoint-initdb.d
cat > /docker-entrypoint-initdb.d/01-wal-archive.sh <<'INITEOF'
#!/bin/bash
set -e

# Настройка WAL архивирования через ALTER SYSTEM
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    ALTER SYSTEM SET archive_mode = 'on';
    ALTER SYSTEM SET wal_level = 'replica';
    ALTER SYSTEM SET archive_command = 'test ! -f /wal_archive/%f && cp %p /wal_archive/%f';
EOSQL
INITEOF

chmod +x /docker-entrypoint-initdb.d/01-wal-archive.sh

echo "WAL архивирование настроено"

