#!/bin/bash
set -e

# Create .env file from .env.example if it doesn't exist
if [ ! -f /app/.env ] && [ -f /app/.env.example ]; then
    echo "Creating .env file from .env.example..."
    cp /app/.env.example /app/.env
fi

# Generate application key if not set
if [ ! -f /app/.env ] || ! grep -q "APP_KEY=base64:" /app/.env 2>/dev/null; then
    echo "Generating application key..."
    php artisan key:generate --force || true
fi

# Add VITE_* environment variables to .env file if they exist in environment
# This ensures Vite can access them during build
if [ -f /app/.env ]; then
    echo "Updating VITE_* variables in .env file..."
    # Remove existing VITE_* lines
    sed -i '/^VITE_/d' /app/.env 2>/dev/null || true
    
    # Add VITE_* variables from environment
    env | grep '^VITE_' | while read -r line; do
        if ! grep -q "^${line%%=*}=" /app/.env 2>/dev/null; then
            echo "$line" >> /app/.env
        fi
    done
    
    # Ensure VITE variables are set with defaults if not in environment
    if ! grep -q "^VITE_ENABLE_WS=" /app/.env 2>/dev/null; then
        echo "VITE_ENABLE_WS=true" >> /app/.env
    fi
    if ! grep -q "^VITE_REVERB_APP_KEY=" /app/.env 2>/dev/null; then
        echo "VITE_REVERB_APP_KEY=${REVERB_APP_KEY:-local}" >> /app/.env
    fi
    if ! grep -q "^VITE_PUSHER_APP_KEY=" /app/.env 2>/dev/null; then
        echo "VITE_PUSHER_APP_KEY=${REVERB_APP_KEY:-local}" >> /app/.env
    fi
    if ! grep -q "^VITE_REVERB_HOST=" /app/.env 2>/dev/null; then
        # For dev mode, use localhost so browser can connect from host
        echo "VITE_REVERB_HOST=localhost" >> /app/.env
    fi
    if ! grep -q "^VITE_WS_HOST=" /app/.env 2>/dev/null; then
        echo "VITE_WS_HOST=localhost" >> /app/.env
    fi
    if ! grep -q "^VITE_REVERB_PORT=" /app/.env 2>/dev/null; then
        echo "VITE_REVERB_PORT=${REVERB_PORT:-6001}" >> /app/.env
    fi
    if ! grep -q "^VITE_WS_PORT=" /app/.env 2>/dev/null; then
        echo "VITE_WS_PORT=${REVERB_PORT:-6001}" >> /app/.env
    fi
    if ! grep -q "^VITE_REVERB_SCHEME=" /app/.env 2>/dev/null; then
        echo "VITE_REVERB_SCHEME=${REVERB_SCHEME:-http}" >> /app/.env
    fi
    if ! grep -q "^VITE_WS_TLS=" /app/.env 2>/dev/null; then
        echo "VITE_WS_TLS=false" >> /app/.env
    fi
fi

# Configure PHP based on environment
if [ "${APP_ENV:-production}" = "local" ]; then
    echo "Development mode detected: configuring PHP for hot reload..."
    # Disable production PHP config and ensure dev config is active
    if [ -f /usr/local/etc/php/conf.d/99-prod.ini ]; then
        mv /usr/local/etc/php/conf.d/99-prod.ini /usr/local/etc/php/conf.d/99-prod.ini.disabled 2>/dev/null || true
    fi
    # Ensure dev PHP configuration is loaded (opcache disabled)
    if [ -f /usr/local/etc/php/conf.d/99-dev.ini ]; then
        echo "✓ Dev PHP configuration loaded (opcache should be disabled)"
        # Verify opcache is disabled
        php -r "echo 'opcache.enable: ' . (ini_get('opcache.enable') ? 'On' : 'Off') . PHP_EOL;" 2>/dev/null || true
    else
        echo "⚠ Dev PHP configuration not found, opcache may still be enabled"
    fi
    
    # Исправить права доступа для Vite кеша (совместимость с Ubuntu)
    mkdir -p /app/node_modules/.vite 2>/dev/null || true
    # Пытаемся использовать пользователя application, если он существует
    if id application >/dev/null 2>&1; then
        chown -R application:application /app/node_modules/.vite 2>/dev/null || true
        chown -R application:application /app/node_modules 2>/dev/null || true
    else
        # Если пользователя нет, используем более широкие права для Ubuntu
        chmod -R 777 /app/node_modules/.vite 2>/dev/null || true
        chmod -R 755 /app/node_modules 2>/dev/null || true
    fi
    chmod -R 755 /app/node_modules/.vite 2>/dev/null || true
else
    echo "Production mode detected: optimizing Laravel and PHP..."
    # Ensure production PHP config is active
    if [ -f /usr/local/etc/php/conf.d/99-prod.ini.disabled ]; then
        mv /usr/local/etc/php/conf.d/99-prod.ini.disabled /usr/local/etc/php/conf.d/99-prod.ini 2>/dev/null || true
    fi
    if [ -f /usr/local/etc/php/conf.d/99-dev.ini ]; then
        mv /usr/local/etc/php/conf.d/99-dev.ini /usr/local/etc/php/conf.d/99-dev.ini.disabled 2>/dev/null || true
    fi
    
    # Optimize Laravel for production (non-blocking)
    echo "Optimizing Laravel application..."
    # Run optimizations in background to not block container startup
    (php artisan config:cache 2>&1 || echo "⚠ config:cache failed") &
    (php artisan view:cache 2>&1 || echo "⚠ view:cache failed") &
    # Route cache may fail if routes have issues, so we skip it for now
    # php artisan route:cache || echo "⚠ route:cache failed"
    (php artisan event:cache 2>&1 || echo "⚠ event:cache failed (Laravel 11+)") &
    wait
    
    # Clear OPcache to ensure fresh start
    php -r "if (function_exists('opcache_reset')) { opcache_reset(); echo 'OPcache reset\n'; }" || true
    
    echo "✓ Production optimizations applied"
fi

# Copy supervisor configs to base image supervisor directory
# Base image uses /opt/docker/etc/supervisor.d/ for configs
# Создаем директорию если её нет (для Ubuntu совместимости)
mkdir -p /opt/docker/etc/supervisor.d /var/log/supervisor /var/run 2>/dev/null || true
chmod 755 /opt/docker/etc/supervisor.d /var/log/supervisor /var/run 2>/dev/null || true

if [ -f /app/reverb-supervisor.conf ] && [ ! -f /opt/docker/etc/supervisor.d/reverb.conf ]; then
    echo "Copying reverb supervisor config to base image directory..."
    cp /app/reverb-supervisor.conf /opt/docker/etc/supervisor.d/reverb.conf
    chmod 644 /opt/docker/etc/supervisor.d/reverb.conf 2>/dev/null || true
fi

# Vite supervisor only in development mode
if [ "${APP_ENV:-production}" = "local" ]; then
    if [ -f /app/vite-supervisor.conf ] && [ ! -f /opt/docker/etc/supervisor.d/vite.conf ]; then
        echo "Copying vite supervisor config to base image directory (dev mode)..."
        cp /app/vite-supervisor.conf /opt/docker/etc/supervisor.d/vite.conf
        chmod 644 /opt/docker/etc/supervisor.d/vite.conf 2>/dev/null || true
    fi
    # Copy update-vite-hot script and supervisor config
    if [ -f /app/update-vite-hot.sh ]; then
        chmod +x /app/update-vite-hot.sh 2>/dev/null || true
    fi
    if [ -f /app/update-vite-hot-supervisor.conf ] && [ ! -f /opt/docker/etc/supervisor.d/update-vite-hot.conf ]; then
        echo "Copying update-vite-hot supervisor config..."
        cp /app/update-vite-hot-supervisor.conf /opt/docker/etc/supervisor.d/update-vite-hot.conf
        chmod 644 /opt/docker/etc/supervisor.d/update-vite-hot.conf 2>/dev/null || true
    fi
else
    # Disable Vite supervisor in production - use built assets instead
    if [ -f /opt/docker/etc/supervisor.d/vite.conf ]; then
        echo "Disabling Vite supervisor in production mode..."
        mv /opt/docker/etc/supervisor.d/vite.conf /opt/docker/etc/supervisor.d/vite.conf.disabled 2>/dev/null || true
    fi
    # Ensure public/hot file doesn't exist (would trigger Vite dev server)
    if [ -f /app/public/hot ]; then
        echo "Removing public/hot file (production mode uses built assets)..."
        rm -f /app/public/hot
    fi
fi

# В dev режиме создаем файл hot с правильным URL для прокси
if [ "${APP_ENV:-production}" = "local" ]; then
    # Убеждаемся, что директория public доступна для записи
    chmod 777 /app/public 2>/dev/null || true
    chown -R application:application /app/public 2>/dev/null || true
    
    # Всегда перезаписываем файл hot с правильным значением (не шаблоном)
    echo "Creating /app/public/hot file with proxy URL..."
    echo "http://localhost:8080" > /app/public/hot
    chmod 666 /app/public/hot 2>/dev/null || chmod 777 /app/public/hot 2>/dev/null || true
    chown application:application /app/public/hot 2>/dev/null || true
    echo "✓ Created /app/public/hot with http://localhost:8080"
fi
fi

# Убеждаемся, что директории для supervisor существуют и имеют правильные права (Ubuntu совместимость)
mkdir -p /var/log/supervisor /var/run 2>/dev/null || true
chmod 755 /var/log/supervisor /var/run 2>/dev/null || true
# Исправляем права на сокет supervisor для Ubuntu
if [ -S /var/run/supervisor.sock ]; then
    chmod 700 /var/run/supervisor.sock 2>/dev/null || true
fi

# Execute the main command (nginx/php-fpm from base image)
# Base image entrypoint will start supervisord with all configs including ours
if [ $# -eq 0 ]; then
    # Call base image entrypoint to start nginx/php-fpm and supervisor
    exec /opt/docker/bin/entrypoint.sh supervisord
else
    # Execute the provided command
    exec "$@"
fi

