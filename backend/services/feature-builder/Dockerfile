FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y supervisor && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /var/log/supervisor /var/run /etc/supervisor/conf.d

COPY feature-builder/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r ./requirements.txt

COPY common /app/common
COPY feature-builder /app

COPY common/supervisord.conf /etc/supervisor/supervisord.conf
COPY feature-builder/supervisor.conf /etc/supervisor/conf.d/feature-builder.conf

ENV PYTHONUNBUFFERED=1

EXPOSE 9410

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf", "-n"]
