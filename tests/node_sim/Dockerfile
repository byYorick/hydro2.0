FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код node_sim
COPY node_sim/ /app/node_sim/

# Устанавливаем рабочую директорию для модуля
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# По умолчанию запускаем симулятор
# Команда может быть переопределена в docker-compose
CMD ["python", "-m", "node_sim.cli", "run", "--config", "/app/config/sim.yaml"]

