FROM python:3.11-slim
WORKDIR /app

ARG INSTALL_DEV_DEPS=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends supervisor \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/log/supervisor /var/run /etc/supervisor/conf.d

COPY mqtt-bridge/requirements.txt ./requirements.txt
COPY mqtt-bridge/requirements-dev.txt ./requirements-dev.txt
COPY requirements-test.txt ./requirements-test.txt
RUN if [ "$INSTALL_DEV_DEPS" = "true" ]; then \
        pip install --no-cache-dir -r ./requirements-dev.txt \
            -r ./requirements-test.txt; \
    else \
        pip install --no-cache-dir -r ./requirements.txt; \
    fi \
    && find /usr/local -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true \
    && rm -rf /root/.cache/pip

COPY common /app/common
COPY mqtt-bridge /app

RUN if [ "$INSTALL_DEV_DEPS" != "true" ]; then \
        rm -rf /app/tests /app/requirements-dev.txt /app/requirements-test.txt \
        && find /app -type d -name 'tests' -exec rm -rf {} + 2>/dev/null || true \
        && find /app -type f -name 'test_*.py' -delete 2>/dev/null || true \
        && find /app -type f -name '*_test.py' -delete 2>/dev/null || true; \
    fi

COPY common/supervisord.conf /etc/supervisor/supervisord.conf
COPY mqtt-bridge/supervisor.conf /etc/supervisor/conf.d/mqtt-bridge.conf

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf", "-n"]
