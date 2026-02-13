<?php

return [
    /*
    |--------------------------------------------------------------------------
    | Access Control Mode
    |--------------------------------------------------------------------------
    |
    | legacy  - исторический режим: все авторизованные non-admin видят все зоны.
    | shadow  - возвращает legacy-решение, но логирует расхождение со strict mode.
    | enforce - применяет strict mode через user_zones/user_greenhouses.
    |
    */
    'mode' => env('ACCESS_CONTROL_MODE', 'legacy'),

    /*
    |--------------------------------------------------------------------------
    | Shadow Audit Log Channel
    |--------------------------------------------------------------------------
    |
    | Канал используется для логирования расхождений legacy vs strict в shadow
    | режиме. По умолчанию использует канал access_shadow из logging.php.
    |
    */
    'shadow_log_channel' => env('ACCESS_CONTROL_SHADOW_LOG_CHANNEL', 'access_shadow'),
];
