<?php

return [
    /*
    |--------------------------------------------------------------------------
    | Command Timeout Configuration
    |--------------------------------------------------------------------------
    |
    | Настройки автоматической обработки timeout для команд.
    |
    */

    'timeout_minutes' => env('COMMAND_TIMEOUT_MINUTES', 5),

    /*
    | Порог, после которого online-узел с устаревшим last_seen_at считается
    | кандидатом в stale. Совпадает с history-logger monitor_offline_nodes.
    */
    'node_offline_timeout_sec' => (int) env('NODE_OFFLINE_TIMEOUT_SEC', 120),
];
