<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Third Party Services
    |--------------------------------------------------------------------------
    |
    | This file is for storing the credentials for third party services such
    | as Mailgun, Postmark, AWS and more. This file provides the de facto
    | location for this type of information, allowing packages to have
    | a conventional file to locate the various service credentials.
    |
    */

    'postmark' => [
        'token' => env('POSTMARK_TOKEN'),
    ],

    'ses' => [
        'key' => env('AWS_ACCESS_KEY_ID'),
        'secret' => env('AWS_SECRET_ACCESS_KEY'),
        'region' => env('AWS_DEFAULT_REGION', 'us-east-1'),
    ],

    'slack' => [
        'notifications' => [
            'bot_user_oauth_token' => env('SLACK_BOT_USER_OAUTH_TOKEN'),
            'channel' => env('SLACK_BOT_USER_DEFAULT_CHANNEL'),
        ],
    ],

    'python_bridge' => [
        'base_url' => env('PY_API_URL', 'http://mqtt-bridge:9000'),
        'token' => env('PY_API_TOKEN'),
        'ingest_token' => env('PY_INGEST_TOKEN'),
        'verify_ssl' => env('PY_API_VERIFY_SSL', true),
        'timeout' => env('PY_API_TIMEOUT', 10), // таймаут в секундах
        'retry_attempts' => env('PY_API_RETRY_ATTEMPTS', 2), // количество попыток
        'retry_delay' => env('PY_API_RETRY_DELAY', 1), // задержка между попытками в секундах
    ],

    'alertmanager' => [
        'webhook_secret' => env('ALERTMANAGER_WEBHOOK_SECRET'),
        'allowed_ips' => env('ALERTMANAGER_ALLOWED_IPS') ? explode(',', env('ALERTMANAGER_ALLOWED_IPS')) : [],
    ],

    'history_logger' => [
        'url' => env('HISTORY_LOGGER_URL', 'http://history-logger:9300'),
        'token' => env('HISTORY_LOGGER_API_TOKEN') ?? env('PY_INGEST_TOKEN'), // Токен для аутентификации
    ],

    'digital_twin' => [
        'url' => env('DIGITAL_TWIN_URL', 'http://digital-twin:8003'),
    ],

    'node_sim_manager' => [
        'url' => env('NODE_SIM_MANAGER_URL', 'http://node-sim-manager:9100'),
        'token' => env('NODE_SIM_MANAGER_TOKEN'),
        'timeout' => env('NODE_SIM_MANAGER_TIMEOUT', 10),
        'mqtt_host' => env('NODE_SIM_MQTT_HOST', env('MQTT_HOST', 'mqtt')),
        'mqtt_port' => env('NODE_SIM_MQTT_PORT', env('MQTT_PORT', 1883)),
        'mqtt_username' => env('NODE_SIM_MQTT_USERNAME', env('MQTT_USERNAME')),
        'mqtt_password' => env('NODE_SIM_MQTT_PASSWORD', env('MQTT_PASSWORD')),
        'mqtt_tls' => env('NODE_SIM_MQTT_TLS', false),
        'mqtt_ca_certs' => env('NODE_SIM_MQTT_CA_CERTS'),
        'mqtt_keepalive' => env('NODE_SIM_MQTT_KEEPALIVE', env('MQTT_KEEPALIVE', 60)),
        'telemetry_interval_seconds' => env('NODE_SIM_TELEMETRY_INTERVAL', 5.0),
        'heartbeat_interval_seconds' => env('NODE_SIM_HEARTBEAT_INTERVAL', 30.0),
        'status_interval_seconds' => env('NODE_SIM_STATUS_INTERVAL', 60.0),
    ],

    'mqtt' => [
        // Для ESP32 нод (внешние подключения) используем MQTT_EXTERNAL_HOST
        // Это должен быть IP адрес хоста, на котором запущен MQTT брокер
        // Если не указан, используется MQTT_HOST (по умолчанию 'mqtt' для внутренних подключений)
        'host' => env('MQTT_EXTERNAL_HOST') ? env('MQTT_EXTERNAL_HOST') : env('MQTT_HOST', 'mqtt'),
        // ВАЖНО: port и keepalive должны быть числами (int), а не строками, для валидации в прошивке
        'port' => (int) env('MQTT_PORT', 1883),
        'keepalive' => (int) env('MQTT_KEEPALIVE', 30),
        'username' => env('MQTT_USERNAME'),
        'password' => env('MQTT_PASSWORD'),
        'client_id' => env('MQTT_CLIENT_ID'),
    ],

    'wifi' => [
        'ssid' => env('WIFI_SSID', 'HydroFarm'),
        'password' => env('WIFI_PASSWORD', ''),
    ],

    'node_registration' => [
        'allowed_ips' => env('NODE_REGISTRATION_ALLOWED_IPS', '10.0.0.0/8,172.16.0.0/12,192.168.0.0/16'),
    ],

];
