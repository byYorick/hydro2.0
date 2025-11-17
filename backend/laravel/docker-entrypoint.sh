#!/bin/bash
set -e

# Start supervisor for Reverb (only if REVERB_AUTO_START is set)
if [ "${REVERB_AUTO_START:-true}" = "true" ]; then
    echo "Starting supervisor for Laravel Reverb..."
    /usr/bin/supervisord -c /etc/supervisor/supervisord.conf &
    sleep 2
    echo "Supervisor started, Reverb should be running"
fi

# Execute the main command (nginx/php-fpm from base image)
exec "$@"

