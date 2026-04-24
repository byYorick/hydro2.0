<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\User;

/**
 * Резолвит feature-flag для конкретного пользователя с учётом cohort-based
 * rollout (по ролям) и глобального switch-а.
 *
 * Конфигурация — {@see config/features.php}.
 */
class FeatureFlags
{
    public const SCHEDULER_COCKPIT_UI = 'scheduler_cockpit_ui';

    /**
     * Возвращает состояние флага для заданного пользователя. Если
     * пользователь не передан — игнорируем rollout по ролям и отвечаем
     * только по глобальному переключателю.
     */
    public static function isEnabled(string $flag, ?User $user = null): bool
    {
        $config = config("features.{$flag}");

        if (! is_array($config)) {
            // Обратная совместимость: плоский bool конфиг.
            return (bool) $config;
        }

        if (! empty($config['enabled_globally'])) {
            return true;
        }

        if ($user === null) {
            return false;
        }

        $role = is_string($user->role ?? null) && $user->role !== ''
            ? $user->role
            : 'viewer';

        $allowedRoles = is_array($config['enabled_for_roles'] ?? null)
            ? $config['enabled_for_roles']
            : [];

        return in_array($role, $allowedRoles, true);
    }
}
