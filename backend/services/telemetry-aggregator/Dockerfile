FROM python:3.11-slim
WORKDIR /app

ARG INSTALL_DEV_DEPS=false

# gcc не нужен: asyncpg ставится из wheel; postgresql-client не используется сервисом
RUN apt-get update \
    && apt-get install -y --no-install-recommends supervisor \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/log/supervisor /var/run /etc/supervisor/conf.d

COPY telemetry-aggregator/requirements.txt ./requirements.txt
COPY telemetry-aggregator/requirements-dev.txt ./requirements-dev.txt
RUN if [ "$INSTALL_DEV_DEPS" = "true" ]; then \
        pip install --no-cache-dir -r ./requirements-dev.txt; \
    else \
        pip install --no-cache-dir -r ./requirements.txt; \
    fi \
    && find /usr/local -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true \
    && rm -rf /root/.cache/pip

COPY common /app/common
COPY telemetry-aggregator /app

RUN if [ "$INSTALL_DEV_DEPS" != "true" ]; then \
        rm -rf /app/tests /app/requirements-dev.txt \
        && find /app -type d -name 'tests' -exec rm -rf {} + 2>/dev/null || true \
        && find /app -type f -name 'test_*.py' -delete 2>/dev/null || true \
        && find /app -type f -name '*_test.py' -delete 2>/dev/null || true; \
    fi

COPY common/supervisord.conf /etc/supervisor/supervisord.conf
COPY telemetry-aggregator/supervisor.conf /etc/supervisor/conf.d/telemetry-aggregator.conf

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 9404

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf", "-n"]
