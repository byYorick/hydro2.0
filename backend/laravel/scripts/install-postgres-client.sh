#!/usr/bin/env bash
# Install a client matching the PostgreSQL 16 server, plus archive tools.
set -euo pipefail
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl gnupg zip jq
. /etc/os-release
mkdir -p /usr/share/keyrings
key_file=$(mktemp)
trap 'rm -f "$key_file"' EXIT
# Fetch from the APT repository itself; the website key endpoint can fail with
# HTTP/2 stream errors. Download fully before invoking gpg.
curl --http1.1 --fail --silent --show-error --location \
    --retry 3 --retry-all-errors --retry-delay 2 \
    --connect-timeout 15 --max-time 60 \
    --output "$key_file" https://apt.postgresql.org/pub/repos/apt/ACCC4CF8.asc
gpg --dearmor --batch --yes -o /usr/share/keyrings/postgresql.gpg "$key_file"
printf 'deb [signed-by=/usr/share/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' \
    "${VERSION_CODENAME}" > /etc/apt/sources.list.d/postgresql.list
apt-get update
apt-get install -y --no-install-recommends postgresql-client-16
apt-get clean
rm -rf /var/lib/apt/lists/*
