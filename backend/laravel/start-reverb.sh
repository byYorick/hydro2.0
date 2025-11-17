#!/bin/bash
# Start Reverb in background via supervisor
if [ "${REVERB_AUTO_START:-true}" = "true" ]; then
    echo "Starting Laravel Reverb via supervisor..."
    /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
fi

