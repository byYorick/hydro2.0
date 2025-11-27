FROM python:3.11-slim
WORKDIR /app

# Устанавливаем supervisor
RUN apt-get update && apt-get install -y supervisor && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /var/log/supervisor /var/run /etc/supervisor/conf.d

# Копируем и устанавливаем зависимости
COPY automation-engine/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r ./requirements.txt

# Копируем код
COPY common /app/common
COPY automation-engine /app

# Копируем конфигурацию supervisor
COPY common/supervisord.conf /etc/supervisor/supervisord.conf
COPY automation-engine/supervisor.conf /etc/supervisor/conf.d/automation-engine.conf

ENV PYTHONUNBUFFERED=1

# Запускаем supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf", "-n"]
