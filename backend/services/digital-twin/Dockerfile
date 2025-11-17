FROM python:3.11-slim

WORKDIR /app

# Копируем common модуль
COPY common /app/common
COPY digital-twin /app

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Запускаем сервис
CMD ["python", "main.py"]

