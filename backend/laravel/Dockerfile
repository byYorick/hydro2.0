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

# Copy dependency files first for better caching
COPY composer.json composer.lock* ./
COPY package.json package-lock.json* ./

# Install Composer dependencies (without scripts to avoid artisan requirement)
RUN if [ -f composer.json ]; then \
        composer install --no-dev --optimize-autoloader --no-interaction --prefer-dist --no-scripts || \
        composer install --optimize-autoloader --no-interaction --prefer-dist --no-scripts; \
    fi

# Install npm dependencies
RUN if [ -f package.json ]; then \
        npm ci --legacy-peer-deps || npm install --legacy-peer-deps; \
    fi

# Создать директорию для Vite кеша с правильными правами
RUN mkdir -p /app/node_modules/.vite && \
    chown -R application:application /app/node_modules/.vite || true

# Copy application files
COPY . .

# Run composer scripts now that all files are in place
RUN if [ -f composer.json ] && [ -f artisan ]; then \
        php artisan package:discover --ansi || true; \
        composer dump-autoload --optimize || true; \
    fi

# Build frontend assets
RUN if [ -f package.json ]; then \
        npm run build; \
    fi

# Copy supervisor config for Reverb and Vite
# Base image uses /opt/docker/etc/supervisor.d/ for configs
COPY supervisord.conf /etc/supervisor/supervisord.conf
COPY reverb-supervisor.conf /opt/docker/etc/supervisor.d/reverb.conf
COPY vite-supervisor.conf /opt/docker/etc/supervisor.d/vite.conf
RUN mkdir -p /var/log/supervisor /var/run /opt/docker/etc/supervisor.d
COPY start-reverb.sh /usr/local/bin/start-reverb.sh
RUN chmod +x /usr/local/bin/start-reverb.sh

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy PHP dev configuration (will be used if APP_ENV=local)
COPY php-dev.ini /usr/local/etc/php/conf.d/99-dev.ini

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]


