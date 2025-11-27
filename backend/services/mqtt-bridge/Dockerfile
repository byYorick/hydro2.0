FROM python:3.11-slim
WORKDIR /app

# Устанавливаем supervisor
RUN apt-get update && apt-get install -y supervisor && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /var/log/supervisor /var/run /etc/supervisor/conf.d

# Копируем и устанавливаем зависимости
COPY mqtt-bridge/requirements.txt ./requirements.txt
# Копируем и устанавливаем тестовые зависимости
COPY requirements-test.txt ./requirements-test.txt
RUN pip install --no-cache-dir -r ./requirements.txt && \
    pip install --no-cache-dir -r ./requirements-test.txt

# Копируем код
COPY common /app/common
COPY mqtt-bridge /app

# Копируем конфигурацию supervisor
COPY common/supervisord.conf /etc/supervisor/supervisord.conf
COPY mqtt-bridge/supervisor.conf /etc/supervisor/conf.d/mqtt-bridge.conf

ENV PYTHONUNBUFFERED=1

# Запускаем supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf", "-n"]
