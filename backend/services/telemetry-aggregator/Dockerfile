FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости для asyncpg и supervisor
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    supervisor \
    && rm -rf /var/lib/apt/lists/* && \
    mkdir -p /var/log/supervisor /var/run /etc/supervisor/conf.d

# Копируем requirements
COPY telemetry-aggregator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем общие модули
COPY common /app/common

# Копируем код агрегатора
COPY telemetry-aggregator /app

# Копируем конфигурацию supervisor
COPY common/supervisord.conf /etc/supervisor/supervisord.conf
COPY telemetry-aggregator/supervisor.conf /etc/supervisor/conf.d/telemetry-aggregator.conf

ENV PYTHONUNBUFFERED=1

# Prometheus metrics порт
EXPOSE 9404

# Запускаем supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf", "-n"]

