FROM python:3.11-slim

WORKDIR /app

COPY node-emulator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY node-emulator/node_emulator.py .

CMD ["python", "node_emulator.py"]

