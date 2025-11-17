FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости для asyncpg
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements
COPY telemetry-aggregator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем общие модули
COPY common /app/common

# Копируем код агрегатора
COPY telemetry-aggregator/main.py .

# Prometheus metrics порт
EXPOSE 9404

CMD ["python", "main.py"]

