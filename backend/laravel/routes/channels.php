<?php

use Illuminate\Support\Facades\Broadcast;
use Illuminate\Support\Facades\Log;

// Канал для обновлений зон
Broadcast::channel('hydro.zones.{zoneId}', function ($user, $zoneId) {
    $authorized = $user !== null;
    if (! $authorized) {
        Log::info('WebSocket channel authorization denied', [
            'channel' => "hydro.zones.{$zoneId}",
            'user_id' => $user?->id,
            'origin' => request()->header('Origin'),
        ]);
    }

    return $authorized; // viewer+ могут слушать
});

// Канал для команд зоны (приватный)
Broadcast::channel('commands.{zoneId}', function ($user, $zoneId) {
    $authorized = $user !== null;
    if (! $authorized) {
        Log::info('WebSocket channel authorization denied', [
            'channel' => "commands.{$zoneId}",
            'user_id' => $user?->id,
            'origin' => request()->header('Origin'),
        ]);
    }

    return $authorized; // viewer+ могут слушать статусы команд
});

// Канал для глобальных команд (приватный)
Broadcast::channel('commands.global', function ($user) {
    $authorized = $user !== null;
    if (! $authorized) {
        Log::info('WebSocket channel authorization denied', [
            'channel' => 'commands.global',
            'user_id' => $user?->id,
            'origin' => request()->header('Origin'),
        ]);
    }

    return $authorized; // viewer+ могут слушать статусы команд
});

// Канал для глобальных событий (приватный)
Broadcast::channel('events.global', function ($user) {
    $authorized = $user !== null;
    if (! $authorized) {
        Log::info('WebSocket channel authorization denied', [
            'channel' => 'events.global',
            'user_id' => $user?->id,
            'origin' => request()->header('Origin'),
        ]);
    }

    return $authorized;
});

// Канал для обновлений устройств (публичный, но требует авторизации)
Broadcast::channel('hydro.devices', function ($user) {
    $authorized = $user !== null;
    if (! $authorized) {
        Log::info('WebSocket channel authorization denied', [
            'channel' => 'hydro.devices',
            'user_id' => $user?->id,
            'origin' => request()->header('Origin'),
        ]);
    }

    return $authorized; // Требует авторизации
});

// Канал для алертов (публичный, но требует авторизации)
Broadcast::channel('hydro.alerts', function ($user) {
    $authorized = $user !== null;
    if (! $authorized) {
        Log::info('WebSocket channel authorization denied', [
            'channel' => 'hydro.alerts',
            'user_id' => $user?->id,
            'origin' => request()->header('Origin'),
        ]);
    }

    return $authorized; // Требует авторизации
});
