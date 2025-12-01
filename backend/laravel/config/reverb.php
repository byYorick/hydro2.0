<?php

// Парсим allowed origins с учетом окружения
// В production REVERB_ALLOWED_ORIGINS обязателен и не должен содержать *
$allowedOrigins = env('REVERB_ALLOWED_ORIGINS');

// Определяем окружение безопасным способом (без вызова app() на верхнем уровне)
$appEnv = env('APP_ENV', 'local');
$isProduction = in_array(strtolower($appEnv), ['production', 'prod']);

if ($isProduction) {
    if (! $allowedOrigins) {
        throw new \RuntimeException('REVERB_ALLOWED_ORIGINS must be set in production environment');
    }
    $parsedAllowedOrigins = array_values(array_filter(array_map('trim', explode(',', $allowedOrigins))));
    // Проверяем, что нет wildcard в production
    if (in_array('*', $parsedAllowedOrigins)) {
        throw new \RuntimeException('REVERB_ALLOWED_ORIGINS cannot contain "*" in production environment. Set explicit origins.');
    }
} else {
    // В dev окружении используем дефолтные значения с wildcard для удобства разработки
    $parsedAllowedOrigins = $allowedOrigins
        ? array_values(array_filter(array_map('trim', explode(',', $allowedOrigins))))
        : [
            env('APP_URL', 'http://localhost'),
            env('FRONTEND_URL', 'http://localhost:5173'),
            'http://localhost:8080',
            'http://127.0.0.1:8080',
            'http://127.0.0.1:5173',
            'http://localhost',
            'http://127.0.0.1',
            'null',
            '*',
        ];
}

$clientOptions = [];

if (env('REVERB_CLIENT_OPTIONS')) {
    try {
        $clientOptions = json_decode(env('REVERB_CLIENT_OPTIONS'), true, 512, JSON_THROW_ON_ERROR | JSON_INVALID_UTF8_IGNORE) ?: [];
    } catch (\Throwable $e) {
        $clientOptions = [];
    }
}

return [

    /*
    |--------------------------------------------------------------------------
    | Default Reverb Server
    |--------------------------------------------------------------------------
    */

    'default' => env('REVERB_SERVER', 'reverb'),

    /*
    |--------------------------------------------------------------------------
    | Reverb Servers
    |--------------------------------------------------------------------------
    */

    'servers' => [

        'reverb' => [
            // host - адрес для прослушивания сервера (0.0.0.0 для всех интерфейсов)
            'host' => env('REVERB_SERVER_HOST', env('REVERB_HOST', '0.0.0.0')),
            'port' => env('REVERB_SERVER_PORT', env('REVERB_PORT', 6001)),
            'path' => env('REVERB_SERVER_PATH', ''),
            // hostname - адрес для клиентских подключений (localhost, не 0.0.0.0)
            // Используется для генерации URL для клиентов
            'hostname' => env('REVERB_CLIENT_HOST', env('REVERB_HOST', 'localhost')),
            'options' => [
                'tls' => [],
                'debug' => env('REVERB_DEBUG', false),
                'verbose' => env('REVERB_VERBOSE', env('REVERB_DEBUG', false)),
            ],
            'max_request_size' => env('REVERB_MAX_REQUEST_SIZE', 10_000),
            'scaling' => [
                'enabled' => env('REVERB_SCALING_ENABLED', false),
                'channel' => env('REVERB_SCALING_CHANNEL', 'reverb'),
                'server' => [
                    'url' => env('REDIS_URL'),
                    'host' => env('REDIS_HOST', '127.0.0.1'),
                    'port' => env('REDIS_PORT', '6379'),
                    'username' => env('REDIS_USERNAME'),
                    'password' => env('REDIS_PASSWORD'),
                    'database' => env('REDIS_DB', '0'),
                    'timeout' => env('REDIS_TIMEOUT', 60),
                ],
            ],
            'pulse_ingest_interval' => env('REVERB_PULSE_INGEST_INTERVAL', 15),
            'telescope_ingest_interval' => env('REVERB_TELESCOPE_INGEST_INTERVAL', 15),
        ],

    ],

    /*
    |--------------------------------------------------------------------------
    | Reverb Applications
    |--------------------------------------------------------------------------
    */

    'apps' => [

        'provider' => 'config',

        'apps' => [
            [
                'key' => env('REVERB_APP_KEY'),
                'secret' => env('REVERB_APP_SECRET'),
                'app_id' => env('REVERB_APP_ID'),
                'options' => array_filter([
                    // host для клиента должен быть localhost (не 0.0.0.0 или 127.0.0.1)
                    // В dev режиме через nginx прокси используется localhost:8080
                    'host' => env('REVERB_CLIENT_HOST', env('REVERB_HOST', 'localhost')),
                    'port' => env('REVERB_PORT', 6001),
                    'scheme' => env('REVERB_SCHEME', 'http'),
                    'useTLS' => env('REVERB_SCHEME', 'http') === 'https',
                    'path' => env('REVERB_CLIENT_PATH', env('REVERB_SERVER_PATH', '')),
                ]),
                'allowed_origins' => $parsedAllowedOrigins,
                'ping_interval' => env('REVERB_APP_PING_INTERVAL', 30),
                'activity_timeout' => env('REVERB_APP_ACTIVITY_TIMEOUT', 60),
                'max_connections' => env('REVERB_APP_MAX_CONNECTIONS', 1000),
                'max_message_size' => env('REVERB_APP_MAX_MESSAGE_SIZE', 100_000),
                'client_options' => $clientOptions,
            ],
        ],

    ],

];
