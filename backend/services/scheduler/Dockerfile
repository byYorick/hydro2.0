FROM python:3.11-slim
WORKDIR /app
COPY scheduler/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r ./requirements.txt
COPY common /app/common
COPY scheduler /app
ENV PYTHONUNBUFFERED=1
CMD ["python", "-u", "main.py"]

