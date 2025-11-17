FROM python:3.11-slim
WORKDIR /app
COPY mqtt-bridge/requirements.txt ./requirements.txt
# Копируем и устанавливаем тестовые зависимости
COPY requirements-test.txt ./requirements-test.txt
RUN pip install --no-cache-dir -r ./requirements.txt && \
    pip install --no-cache-dir -r ./requirements-test.txt
COPY common /app/common
COPY mqtt-bridge /app
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
