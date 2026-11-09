<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Ручные команды: rate limit и окно суммарной дозы
    |--------------------------------------------------------------------------
    |
    | rate_per_minute — сколько включающих актуатор ручных команд один
    | оператор может отправить в одну зону за минуту. Fail-safe OFF не
    | расходует лимит.
    |
    | dose_window_sec — окно суммарной дозы pH/EC по зоне. Потолок окна =
    | controllers.*.max_dose_ml × retry.max_*_correction_attempts
    | (тот же бюджет попыток, что у AE3 на цикл коррекции).
    |
    */

    'rate_per_minute' => (int) env('MANUAL_COMMAND_RATE_PER_MINUTE', 30),

    'dose_window_sec' => (int) env('MANUAL_DOSE_WINDOW_SEC', 3600),

];
