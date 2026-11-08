#!/usr/bin/env bash
# Install a client matching the PostgreSQL 16 server, plus archive tools.
set -euo pipefail
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl gnupg zip jq
. /etc/os-release
mkdir -p /usr/share/keyrings
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    | gpg --dearmor --batch --yes -o /usr/share/keyrings/postgresql.gpg
printf 'deb [signed-by=/usr/share/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' \
    "${VERSION_CODENAME}" > /etc/apt/sources.list.d/postgresql.list
apt-get update
apt-get install -y --no-install-recommends postgresql-client-16
apt-get clean
rm -rf /var/lib/apt/lists/*
