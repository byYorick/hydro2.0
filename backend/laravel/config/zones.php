<?php

return [
    /*
    |--------------------------------------------------------------------------
    | Zone Readiness Configuration
    |--------------------------------------------------------------------------
    |
    | Настройки проверки готовности зоны к запуску grow-cycle.
    | 
    */

    'readiness' => [
        // Обязательные bindings для работы зоны
        // Может быть переопределено через переменную окружения ZONE_REQUIRED_BINDINGS
        // Формат: 'main_pump,ph_control,ec_control' или массив ['main_pump', 'ph_control']
        'required_bindings' => env('ZONE_REQUIRED_BINDINGS') 
            ? (is_string(env('ZONE_REQUIRED_BINDINGS')) 
                ? explode(',', env('ZONE_REQUIRED_BINDINGS')) 
                : env('ZONE_REQUIRED_BINDINGS'))
            : ['main_pump', 'drain'], // По умолчанию требуется основной насос и дренаж

        // Строгий режим проверки готовности
        // Если true - зона не может стартовать без обязательных bindings
        'strict_mode' => env('ZONE_READINESS_STRICT', true),

        // E2E режим - автоматически отключает strict проверки для тестирования
        'e2e_mode' => env('APP_ENV') === 'e2e',
    ],
];
