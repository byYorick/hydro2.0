<?php

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\PipelineMetricsService;
use Illuminate\Support\Facades\Broadcast;
use Illuminate\Support\Facades\Log;

$trackWsAuth = static function (string $channelType, string $result): void {
    PipelineMetricsService::trackWsAuth($channelType, $result);
};

// Канал для обновлений зон
Broadcast::channel('hydro.zones.{zoneId}', function ($user, $zoneId) use ($trackWsAuth) {
    if (! $user) {
        Log::warning('WebSocket channel authorization denied: unauthenticated', [
            'channel' => "hydro.zones.{$zoneId}",
            'origin' => request()->header('Origin'),
        ]);

        $trackWsAuth('zone', 'denied');
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

        $trackWsAuth('zone', 'denied');
        return false;
    }

    // Проверяем, что zoneId является числом
    if (! is_numeric($zoneId)) {
        Log::warning('WebSocket channel authorization denied: invalid zone ID', [
            'channel' => "hydro.zones.{$zoneId}",
            'user_id' => $user->id,
            'zone_id' => $zoneId,
        ]);

        $trackWsAuth('zone', 'denied');
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

            $trackWsAuth('zone', 'denied');
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

            $trackWsAuth('zone', 'denied');
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

        $trackWsAuth('zone', 'error');
        return false;
    }

    Log::debug('WebSocket channel authorized', [
        'channel' => "hydro.zones.{$zoneId}",
        'user_id' => $user->id,
        'user_role' => $userRole,
        'zone_id' => $zoneId,
    ]);

    $trackWsAuth('zone', 'success');
    return ['id' => $user->id, 'name' => $user->name];
});

// Канал для глобальных команд (приватный) - должен быть определен ДО *.commands.{zoneId}
$authorizeCommandsGlobal = static function ($user) use ($trackWsAuth) {
    $requestedChannel = (string) request()->input('channel_name', 'private-hydro.commands.global');

    if (! $user) {
        Log::warning('WebSocket channel authorization denied: unauthenticated', [
            'channel' => $requestedChannel,
            'origin' => request()->header('Origin'),
        ]);

        $trackWsAuth('commands', 'denied');
        return false;
    }

    // Проверяем роль пользователя
    $userRole = $user->role ?? 'viewer';
    $allowedRoles = ['viewer', 'operator', 'admin', 'agronomist', 'engineer'];

    if (! in_array($userRole, $allowedRoles)) {
        Log::warning('WebSocket channel authorization denied: invalid role', [
            'channel' => $requestedChannel,
            'user_id' => $user->id,
            'user_role' => $userRole,
            'origin' => request()->header('Origin'),
        ]);

        $trackWsAuth('commands', 'denied');
        return false;
    }

    Log::debug('WebSocket channel authorized', [
        'channel' => $requestedChannel,
        'user_id' => $user->id,
        'user_role' => $userRole,
    ]);

    $trackWsAuth('commands', 'success');
    return ['id' => $user->id, 'name' => $user->name];
};

Broadcast::channel('hydro.commands.global', $authorizeCommandsGlobal);
Broadcast::channel('commands.global', $authorizeCommandsGlobal);

// Канал для команд зоны (приватный) - должен быть определен ПОСЛЕ *.commands.global
$authorizeCommandsZone = static function ($user, $zoneId) use ($trackWsAuth) {
    $requestedChannel = (string) request()->input('channel_name', "private-hydro.commands.{$zoneId}");

    if (! $user) {
        Log::warning('WebSocket channel authorization denied: unauthenticated', [
            'channel' => $requestedChannel,
            'origin' => request()->header('Origin'),
        ]);

        $trackWsAuth('commands', 'denied');
        return false;
    }

    // Проверяем роль пользователя
    $userRole = $user->role ?? 'viewer';
    $allowedRoles = ['viewer', 'operator', 'admin', 'agronomist', 'engineer'];

    if (! in_array($userRole, $allowedRoles)) {
        Log::warning('WebSocket channel authorization denied: invalid role', [
            'channel' => $requestedChannel,
            'user_id' => $user->id,
            'user_role' => $userRole,
            'zone_id' => $zoneId,
            'origin' => request()->header('Origin'),
        ]);

        $trackWsAuth('commands', 'denied');
        return false;
    }

    // Проверяем, что zoneId является числом (не "global" или другой строкой)
    if (! is_numeric($zoneId)) {
        Log::warning('WebSocket channel authorization denied: invalid zone ID', [
            'channel' => $requestedChannel,
            'user_id' => $user->id,
            'zone_id' => $zoneId,
        ]);

        $trackWsAuth('commands', 'denied');
        return false;
    }

    // Проверяем существование зоны с обработкой ошибок БД
    try {
        $zone = Zone::find((int) $zoneId);
        if (! $zone) {
            Log::warning('WebSocket channel authorization denied: zone not found', [
                'channel' => $requestedChannel,
                'user_id' => $user->id,
                'user_role' => $userRole,
                'origin' => request()->header('Origin'),
            ]);

            $trackWsAuth('commands', 'denied');
            return false;
        }

        // ВАЖНО: Проверяем доступ к конкретной зоне через ZoneAccessHelper
        // Это предотвращает подписку на команды чужой зоны
        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            Log::warning('WebSocket channel authorization denied: no access to zone', [
                'channel' => $requestedChannel,
                'user_id' => $user->id,
                'user_role' => $userRole,
                'zone_id' => $zoneId,
                'origin' => request()->header('Origin'),
            ]);

            $trackWsAuth('commands', 'denied');
            return false;
        }
    } catch (\Exception $e) {
        // Логируем ошибку БД, но возвращаем false вместо исключения
        Log::error('WebSocket channel authorization: database error', [
            'channel' => $requestedChannel,
            'user_id' => $user->id,
            'user_role' => $userRole,
            'error' => $e->getMessage(),
        ]);

        $trackWsAuth('commands', 'error');
        return false;
    }

    Log::debug('WebSocket channel authorized', [
        'channel' => $requestedChannel,
        'user_id' => $user->id,
        'user_role' => $userRole,
        'zone_id' => $zoneId,
    ]);

    $trackWsAuth('commands', 'success');
    return ['id' => $user->id, 'name' => $user->name];
};

Broadcast::channel('hydro.commands.{zoneId}', $authorizeCommandsZone);
Broadcast::channel('commands.{zoneId}', $authorizeCommandsZone);


// Канал для глобальных событий (приватный)
Broadcast::channel('hydro.events.global', function ($user) use ($trackWsAuth) {
    if (! $user) {
        Log::warning('WebSocket channel authorization denied: unauthenticated', [
            'channel' => 'hydro.events.global',
            'origin' => request()->header('Origin'),
        ]);

        $trackWsAuth('events', 'denied');
        return false;
    }

    // Проверяем роль пользователя
    $userRole = $user->role ?? 'viewer';
    $allowedRoles = ['viewer', 'operator', 'admin', 'agronomist', 'engineer'];

    if (! in_array($userRole, $allowedRoles)) {
        Log::warning('WebSocket channel authorization denied: invalid role', [
            'channel' => 'hydro.events.global',
            'user_id' => $user->id,
            'user_role' => $userRole,
            'origin' => request()->header('Origin'),
        ]);

        $trackWsAuth('events', 'denied');
        return false;
    }

    Log::debug('WebSocket channel authorized', [
        'channel' => 'hydro.events.global',
        'user_id' => $user->id,
        'user_role' => $userRole,
    ]);

    $trackWsAuth('events', 'success');
    return ['id' => $user->id, 'name' => $user->name];
});

// Канал для обновлений устройств без зоны (публичный, но требует авторизации)
Broadcast::channel('hydro.devices', function ($user) use ($trackWsAuth) {
    if (! $user) {
        Log::warning('WebSocket channel authorization denied: unauthenticated', [
            'channel' => 'hydro.devices',
            'origin' => request()->header('Origin'),
        ]);

        $trackWsAuth('devices', 'denied');
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

        $trackWsAuth('devices', 'denied');
        return false;
    }

    Log::debug('WebSocket channel authorized', [
        'channel' => 'hydro.devices',
        'user_id' => $user->id,
        'user_role' => $userRole,
    ]);

    $trackWsAuth('devices', 'success');
    return ['id' => $user->id, 'name' => $user->name];
});

// Канал для алертов (публичный, но требует авторизации)
Broadcast::channel('hydro.alerts', function ($user) use ($trackWsAuth) {
    if (! $user) {
        Log::warning('WebSocket channel authorization denied: unauthenticated', [
            'channel' => 'hydro.alerts',
            'origin' => request()->header('Origin'),
        ]);

        $trackWsAuth('alerts', 'denied');
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

        $trackWsAuth('alerts', 'denied');
        return false;
    }

    Log::debug('WebSocket channel authorized', [
        'channel' => 'hydro.alerts',
        'user_id' => $user->id,
        'user_role' => $userRole,
    ]);

    $trackWsAuth('alerts', 'success');
    return ['id' => $user->id, 'name' => $user->name];
});
