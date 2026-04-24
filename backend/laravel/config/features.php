<?php

declare(strict_types=1);

/**
 * Feature-flag конфигурация с поддержкой role-based rollout.
 *
 * Каждый флаг описывает 2 измерения:
 *   - `enabled_globally` — если true, флаг включён для всех пользователей вне
 *     зависимости от роли (стадия "всем пользователям"/GA).
 *   - `enabled_for_roles` — список ролей, для которых флаг включён в
 *     rollout-режиме. Используется, пока флаг не переведён на `enabled_globally`.
 *
 * Резолв — через {@see \App\Support\FeatureFlags::isEnabled()}.
 */
return [
    'scheduler_cockpit_ui' => [
        'enabled_globally' => (bool) env('FEATURE_SCHEDULER_COCKPIT_UI', false),
        // Rollout cohort-1: engineer + admin. Переключение на следующие когорты —
        // через `FEATURE_SCHEDULER_COCKPIT_UI_ROLES` в .env.
        'enabled_for_roles' => array_values(array_filter(array_map(
            'trim',
            explode(',', (string) env('FEATURE_SCHEDULER_COCKPIT_UI_ROLES', 'engineer,admin')),
        ), static fn (string $role): bool => $role !== '')),
    ],
];
