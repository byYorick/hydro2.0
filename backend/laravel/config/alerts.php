<?php

return [
    /*
    |--------------------------------------------------------------------------
    | Alert Rate Limiting
    |--------------------------------------------------------------------------
    |
    | Настройки rate limiting для предотвращения спама алертов при частых ошибках.
    | Критичные ошибки из whitelist не подлежат rate limiting.
    |
    */

    'rate_limiting' => [
        'enabled' => env('ALERTS_RATE_LIMIT_ENABLED', true),
        'max_per_minute' => env('ALERTS_MAX_PER_MINUTE', 10),
        'critical_codes' => env('ALERTS_CRITICAL_CODES', [
            'infra_sensor_failure',
            'infra_pump_failure',
            'infra_controller_failure',
            'infra_power_failure',
            'infra_network_failure',
        ]),
    ],

    /*
    |--------------------------------------------------------------------------
    | Telegram external alerting (этап E / AGRO_AUTONOMY_MASTER_PLAN)
    |--------------------------------------------------------------------------
    |
    | Критичные бизнес- и инфраструктурные алерты доставляются в Telegram Bot API.
    | Дедупликация по code+zone_id предотвращает спам при повторных срабатываниях.
    |
    */

    'telegram' => [
        'enabled' => env('ALERTS_TELEGRAM_ENABLED', true),
        'dedup_ttl_seconds' => (int) env('ALERTS_TELEGRAM_DEDUP_TTL_SECONDS', 60),
        'severities' => ['critical', 'error', 'warning'],
    ],
];
