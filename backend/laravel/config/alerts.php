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
];

