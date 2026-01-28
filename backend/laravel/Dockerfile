FROM webdevops/php-nginx:8.2

RUN apt-get update && \
    apt-get install -y curl ca-certificates gnupg supervisor chromium chromium-driver fonts-liberation && \
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

# Copy dependency files first for better caching
COPY composer.json composer.lock* ./
COPY package.json package-lock.json* ./

# Install Composer dependencies (without scripts to avoid artisan requirement)
# Use ARG to control dev dependencies installation
ARG INSTALL_DEV_DEPS=true
RUN if [ -f composer.json ]; then \
        if [ "$INSTALL_DEV_DEPS" = "true" ]; then \
            echo "Installing ALL Composer dependencies (including dev)..."; \
            composer install --optimize-autoloader --no-interaction --prefer-dist --no-scripts; \
        else \
            echo "Installing production Composer dependencies only..."; \
            composer install --no-dev --optimize-autoloader --no-interaction --prefer-dist --no-scripts; \
        fi \
    fi

# Install npm dependencies
RUN if [ -f package.json ]; then \
        npm ci --legacy-peer-deps || npm install --legacy-peer-deps; \
    fi

# Создать директорию для Vite кеша с правильными правами
# Используем более надежный способ для Ubuntu
RUN mkdir -p /app/node_modules/.vite && \
    chown -R application:application /app/node_modules/.vite 2>/dev/null || \
    (id application >/dev/null 2>&1 && chown -R application:application /app/node_modules/.vite) || \
    chmod -R 777 /app/node_modules/.vite || true

# Copy application files
COPY . .

# Ensure cache/storage dirs are writable for artisan commands during build
RUN mkdir -p /app/bootstrap/cache /app/storage && \
    chown -R application:application /app/bootstrap/cache /app/storage 2>/dev/null || \
    chmod -R 777 /app/bootstrap/cache /app/storage || true

# Run composer scripts now that all files are in place
RUN if [ -f composer.json ] && [ -f artisan ]; then \
        php artisan package:discover --ansi || true; \
        composer dump-autoload --optimize || true; \
    fi

# Build frontend assets for production
# VITE_* variables are passed as build args and used during build
# В dev режиме эти переменные НЕ устанавливаются, чтобы клиент использовал window.location (nginx прокси)
# Используем значения по умолчанию для production, но они будут переопределены в docker-compose
ARG VITE_REVERB_HOST=localhost
ARG VITE_WS_HOST=localhost
ARG VITE_REVERB_PORT=6001
ARG VITE_WS_PORT=6001
ARG VITE_REVERB_SCHEME=http
ARG VITE_WS_TLS=false
ARG VITE_ENABLE_WS=true
ARG VITE_REVERB_APP_KEY
ARG VITE_PUSHER_APP_KEY
ARG SKIP_FRONTEND_BUILD=false

# Устанавливаем переменные окружения только если они заданы (не пустые)
# В dev режиме они не заданы, чтобы клиент использовал window.location (nginx прокси)
ENV VITE_REVERB_HOST=${VITE_REVERB_HOST:-}
ENV VITE_WS_HOST=${VITE_WS_HOST:-}
ENV VITE_REVERB_PORT=${VITE_REVERB_PORT:-}
ENV VITE_WS_PORT=${VITE_WS_PORT:-}
ENV VITE_REVERB_SCHEME=${VITE_REVERB_SCHEME}
ENV VITE_WS_TLS=${VITE_WS_TLS}
ENV VITE_ENABLE_WS=${VITE_ENABLE_WS}
ENV VITE_REVERB_APP_KEY=${VITE_REVERB_APP_KEY}
ENV VITE_PUSHER_APP_KEY=${VITE_PUSHER_APP_KEY}

RUN if [ -f package.json ]; then \
        if [ "${SKIP_FRONTEND_BUILD}" = "true" ]; then \
            echo "Skipping frontend build (SKIP_FRONTEND_BUILD=true)"; \
        else \
            NODE_ENV=production npm run build; \
        fi; \
    fi

# Copy supervisor config for Reverb and Vite
# Base image uses /opt/docker/etc/supervisor.d/ for configs
COPY supervisord.conf /etc/supervisor/supervisord.conf
COPY reverb-supervisor.conf /opt/docker/etc/supervisor.d/reverb.conf
COPY vite-supervisor.conf /opt/docker/etc/supervisor.d/vite.conf
COPY queue-supervisor.conf /opt/docker/etc/supervisor.d/queue.conf
RUN mkdir -p /var/log/supervisor /var/log/reverb /var/run /opt/docker/etc/supervisor.d && \
    chmod 755 /var/log/supervisor /var/log/reverb /var/run /opt/docker/etc/supervisor.d && \
    chown -R application:application /var/log/supervisor /var/log/reverb /var/run 2>/dev/null || \
    chmod -R 777 /var/log/supervisor /var/log/reverb /var/run || true
COPY start-reverb.sh /usr/local/bin/start-reverb.sh
RUN chmod +x /usr/local/bin/start-reverb.sh

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy PHP configurations
COPY php-dev.ini /usr/local/etc/php/conf.d/99-dev.ini
COPY php-prod.ini /usr/local/etc/php/conf.d/99-prod.ini

# Copy nginx Vite proxy configuration
COPY nginx-vite-proxy.conf /opt/docker/etc/nginx/vhost.common.d/vite-proxy.conf

# Copy nginx FastCGI buffers configuration
COPY nginx-fastcgi-buffers.conf /opt/docker/etc/nginx/vhost.common.d/20-fastcgi-buffers.conf

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
