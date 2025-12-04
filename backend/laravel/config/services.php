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

];
