FROM timescale/timescaledb:latest-pg16

RUN apk add --no-cache build-base git postgresql16-dev clang19 llvm19

RUN git clone --branch v1.6.4 --depth 1 https://github.com/citusdata/pg_cron.git /tmp/pg_cron \
    && make -C /tmp/pg_cron \
    && make -C /tmp/pg_cron install \
    && rm -rf /tmp/pg_cron
