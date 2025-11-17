FROM python:3.11-slim
WORKDIR /app
COPY automation-engine/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r ./requirements.txt
COPY common /app/common
COPY automation-engine /app
ENV PYTHONUNBUFFERED=1
CMD ["python", "-u", "main.py"]
