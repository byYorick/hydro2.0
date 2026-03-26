# Keep TimescaleDB pinned to the extension version already stored in the dev volume.
FROM timescale/timescaledb:2.26.0-pg16

RUN apk add --no-cache build-base git postgresql16-dev clang19 llvm19

RUN git clone --branch v1.6.4 --depth 1 https://github.com/citusdata/pg_cron.git /tmp/pg_cron \
    && make -C /tmp/pg_cron \
    && make -C /tmp/pg_cron install \
    && rm -rf /tmp/pg_cron
