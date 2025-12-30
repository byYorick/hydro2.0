<?php

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use Illuminate\Support\Facades\Broadcast;
use Illuminate\Support\Facades\Log;

// Канал для обновлений зон
Broadcast::channel('hydro.zones.{zoneId}', function ($user, $zoneId) {
    if (! $user) {
        Log::warning('WebSocket channel authorization denied: unauthenticated', [
            'channel' => "hydro.zones.{$zoneId}",
            'origin' => request()->header('Origin'),
        ]);

        return false;
    }

    $userRole = $user->role ?? 'viewer';
    $allowedRoles = ['viewer', 'operator', 'admin', 'agronomist', 'engineer'];

    if (! in_array($userRole, $allowedRoles)) {
        Log::warning('WebSocket channel authorization denied: invalid role', [
            'channel' => "hydro.zones.{$zoneId}",
            'user_id' => $user->id,
            'user_role' => $userRole,
            'zone_id' => $zoneId,
            'origin' => request()->header('Origin'),
        ]);

        return false;
    }

    // Проверяем, что zoneId является числом
    if (! is_numeric($zoneId)) {
        Log::warning('WebSocket channel authorization denied: invalid zone ID', [
            'channel' => "hydro.zones.{$zoneId}",
            'user_id' => $user->id,
            'zone_id' => $zoneId,
        ]);

        return false;
    }

    try {
        $zone = Zone::find((int) $zoneId);
        if (! $zone) {
            Log::warning('WebSocket channel authorization denied: zone not found', [
                'channel' => "hydro.zones.{$zoneId}",
                'user_id' => $user->id,
                'user_role' => $userRole,
                'origin' => request()->header('Origin'),
            ]);

            return false;
        }

        // ВАЖНО: Проверяем доступ к конкретной зоне через ZoneAccessHelper
        // Это предотвращает подписку на события чужой зоны
        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            Log::warning('WebSocket channel authorization denied: no access to zone', [
                'channel' => "hydro.zones.{$zoneId}",
                'user_id' => $user->id,
                'user_role' => $userRole,
                'zone_id' => $zoneId,
                'origin' => request()->header('Origin'),
            ]);

            return false;
        }
    } catch (\Exception $e) {
        // Логируем ошибку БД, но возвращаем false вместо исключения
        // Это предотвращает 500 ошибки и возвращает 403 (unauthorized)
        Log::error('WebSocket channel authorization: database error', [
            'channel' => "hydro.zones.{$zoneId}",
            'user_id' => $user->id,
            'user_role' => $userRole,
            'error' => $e->getMessage(),
        ]);

        return false;
    }

    Log::debug('WebSocket channel authorized', [
        'channel' => "hydro.zones.{$zoneId}",
        'user_id' => $user->id,
        'user_role' => $userRole,
        'zone_id' => $zoneId,
    ]);

    return ['id' => $user->id, 'name' => $user->name];
});

// Канал для глобальных команд (приватный) - должен быть определен ДО commands.{zoneId}
Broadcast::channel('commands.global', function ($user) {
    if (! $user) {
        Log::warning('WebSocket channel authorization denied: unauthenticated', [
            'channel' => 'commands.global',
            'origin' => request()->header('Origin'),
        ]);

        return false;
    }

    // Проверяем роль пользователя
    $userRole = $user->role ?? 'viewer';
    $allowedRoles = ['viewer', 'operator', 'admin', 'agronomist', 'engineer'];

    if (! in_array($userRole, $allowedRoles)) {
        Log::warning('WebSocket channel authorization denied: invalid role', [
            'channel' => 'commands.global',
            'user_id' => $user->id,
            'user_role' => $userRole,
            'origin' => request()->header('Origin'),
        ]);

        return false;
    }

    Log::debug('WebSocket channel authorized', [
        'channel' => 'commands.global',
        'user_id' => $user->id,
        'user_role' => $userRole,
    ]);

    return ['id' => $user->id, 'name' => $user->name];
});

// Канал для команд зоны (приватный) - должен быть определен ПОСЛЕ commands.global
Broadcast::channel('commands.{zoneId}', function ($user, $zoneId) {
    if (! $user) {
        Log::warning('WebSocket channel authorization denied: unauthenticated', [
            'channel' => "commands.{$zoneId}",
            'origin' => request()->header('Origin'),
        ]);

        return false;
    }

    // Проверяем роль пользователя
    $userRole = $user->role ?? 'viewer';
    $allowedRoles = ['viewer', 'operator', 'admin', 'agronomist', 'engineer'];

    if (! in_array($userRole, $allowedRoles)) {
        Log::warning('WebSocket channel authorization denied: invalid role', [
            'channel' => "commands.{$zoneId}",
            'user_id' => $user->id,
            'user_role' => $userRole,
            'zone_id' => $zoneId,
            'origin' => request()->header('Origin'),
        ]);

        return false;
    }

    // Проверяем, что zoneId является числом (не "global" или другой строкой)
    if (! is_numeric($zoneId)) {
        Log::warning('WebSocket channel authorization denied: invalid zone ID', [
            'channel' => "commands.{$zoneId}",
            'user_id' => $user->id,
            'zone_id' => $zoneId,
        ]);

        return false;
    }

    // Проверяем существование зоны с обработкой ошибок БД
    try {
        $zone = Zone::find((int) $zoneId);
        if (! $zone) {
            Log::warning('WebSocket channel authorization denied: zone not found', [
                'channel' => "commands.{$zoneId}",
                'user_id' => $user->id,
                'user_role' => $userRole,
                'origin' => request()->header('Origin'),
            ]);

            return false;
        }

        // ВАЖНО: Проверяем доступ к конкретной зоне через ZoneAccessHelper
        // Это предотвращает подписку на команды чужой зоны
        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            Log::warning('WebSocket channel authorization denied: no access to zone', [
                'channel' => "commands.{$zoneId}",
                'user_id' => $user->id,
                'user_role' => $userRole,
                'zone_id' => $zoneId,
                'origin' => request()->header('Origin'),
            ]);

            return false;
        }
    } catch (\Exception $e) {
        // Логируем ошибку БД, но возвращаем false вместо исключения
        Log::error('WebSocket channel authorization: database error', [
            'channel' => "commands.{$zoneId}",
            'user_id' => $user->id,
            'user_role' => $userRole,
            'error' => $e->getMessage(),
        ]);

        return false;
    }

    Log::debug('WebSocket channel authorized', [
        'channel' => "commands.{$zoneId}",
        'user_id' => $user->id,
        'user_role' => $userRole,
        'zone_id' => $zoneId,
    ]);

    return ['id' => $user->id, 'name' => $user->name];
});


// Канал для глобальных событий (приватный)
Broadcast::channel('events.global', function ($user) {
    if (! $user) {
        Log::warning('WebSocket channel authorization denied: unauthenticated', [
            'channel' => 'events.global',
            'origin' => request()->header('Origin'),
        ]);

        return false;
    }

    // Проверяем роль пользователя
    $userRole = $user->role ?? 'viewer';
    $allowedRoles = ['viewer', 'operator', 'admin', 'agronomist', 'engineer'];

    if (! in_array($userRole, $allowedRoles)) {
        Log::warning('WebSocket channel authorization denied: invalid role', [
            'channel' => 'events.global',
            'user_id' => $user->id,
            'user_role' => $userRole,
            'origin' => request()->header('Origin'),
        ]);

        return false;
    }

    Log::debug('WebSocket channel authorized', [
        'channel' => 'events.global',
        'user_id' => $user->id,
        'user_role' => $userRole,
    ]);

    return ['id' => $user->id, 'name' => $user->name];
});

// Канал для обновлений устройств без зоны (публичный, но требует авторизации)
Broadcast::channel('hydro.devices', function ($user) {
    if (! $user) {
        Log::warning('WebSocket channel authorization denied: unauthenticated', [
            'channel' => 'hydro.devices',
            'origin' => request()->header('Origin'),
        ]);

        return false;
    }

    // Проверяем роль пользователя
    $userRole = $user->role ?? 'viewer';
    $allowedRoles = ['viewer', 'operator', 'admin', 'agronomist', 'engineer'];

    if (! in_array($userRole, $allowedRoles)) {
        Log::warning('WebSocket channel authorization denied: invalid role', [
            'channel' => 'hydro.devices',
            'user_id' => $user->id,
            'user_role' => $userRole,
            'origin' => request()->header('Origin'),
        ]);

        return false;
    }

    Log::debug('WebSocket channel authorized', [
        'channel' => 'hydro.devices',
        'user_id' => $user->id,
        'user_role' => $userRole,
    ]);

    return ['id' => $user->id, 'name' => $user->name];
});

// Канал для алертов (публичный, но требует авторизации)
Broadcast::channel('hydro.alerts', function ($user) {
    if (! $user) {
        Log::warning('WebSocket channel authorization denied: unauthenticated', [
            'channel' => 'hydro.alerts',
            'origin' => request()->header('Origin'),
        ]);

        return false;
    }

    // Проверяем роль пользователя
    $userRole = $user->role ?? 'viewer';
    $allowedRoles = ['viewer', 'operator', 'admin', 'agronomist', 'engineer'];

    if (! in_array($userRole, $allowedRoles)) {
        Log::warning('WebSocket channel authorization denied: invalid role', [
            'channel' => 'hydro.alerts',
            'user_id' => $user->id,
            'user_role' => $userRole,
            'origin' => request()->header('Origin'),
        ]);

        return false;
    }

    Log::debug('WebSocket channel authorized', [
        'channel' => 'hydro.alerts',
        'user_id' => $user->id,
        'user_role' => $userRole,
    ]);

    return ['id' => $user->id, 'name' => $user->name];
});
