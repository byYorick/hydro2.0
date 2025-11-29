<?php

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

    // Проверяем роль пользователя
    // Это предотвращает ненужные запросы к БД для пользователей с недопустимыми ролями
    $userRole = $user->role ?? 'viewer';
    $allowedRoles = ['viewer', 'operator', 'admin', 'agronomist', 'engineer'];
    
    if (!in_array($userRole, $allowedRoles)) {
        Log::warning('WebSocket channel authorization denied: invalid role', [
            'channel' => "hydro.zones.{$zoneId}",
            'user_id' => $user->id,
            'user_role' => $userRole,
            'zone_id' => $zoneId,
            'origin' => request()->header('Origin'),
        ]);
        return false;
    }

    // Проверяем существование зоны с обработкой ошибок БД
    // Если таблицы не существуют или БД недоступна, возвращаем false вместо исключения
    // Это предотвращает 500 ошибки и возвращает 403 (unauthorized)
    try {
        $zone = Zone::find($zoneId);
        if (! $zone) {
            Log::warning('WebSocket channel authorization denied: zone not found', [
                'channel' => "hydro.zones.{$zoneId}",
                'user_id' => $user->id,
                'user_role' => $userRole,
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

// Канал для команд зоны (приватный)
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
    
    if (!in_array($userRole, $allowedRoles)) {
        Log::warning('WebSocket channel authorization denied: invalid role', [
            'channel' => "commands.{$zoneId}",
            'user_id' => $user->id,
            'user_role' => $userRole,
            'zone_id' => $zoneId,
            'origin' => request()->header('Origin'),
        ]);
        return false;
    }

    // Проверяем существование зоны с обработкой ошибок БД
    try {
        $zone = Zone::find($zoneId);
        if (! $zone) {
            Log::warning('WebSocket channel authorization denied: zone not found', [
                'channel' => "commands.{$zoneId}",
                'user_id' => $user->id,
                'user_role' => $userRole,
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

// Канал для глобальных команд (приватный)
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
    
    if (!in_array($userRole, $allowedRoles)) {
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
    
    if (!in_array($userRole, $allowedRoles)) {
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

// Канал для обновлений устройств (публичный, но требует авторизации)
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
    
    if (!in_array($userRole, $allowedRoles)) {
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
    
    if (!in_array($userRole, $allowedRoles)) {
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
