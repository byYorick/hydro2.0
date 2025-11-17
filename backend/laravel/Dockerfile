FROM webdevops/php-nginx:8.2

RUN apt-get update && \
    apt-get install -y curl ca-certificates gnupg supervisor && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" >/etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y nodejs && \
    npm --version && node --version && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV WEB_DOCUMENT_ROOT=/app/public
EXPOSE 80

# Copy supervisor config for Reverb
COPY supervisord.conf /etc/supervisor/supervisord.conf
COPY reverb-supervisor.conf /etc/supervisor/conf.d/reverb.conf
RUN mkdir -p /var/log/supervisor /var/run
COPY start-reverb.sh /usr/local/bin/start-reverb.sh
RUN chmod +x /usr/local/bin/start-reverb.sh


