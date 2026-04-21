<?php

namespace App\Services\LaunchFlow;

use App\Models\User;
use App\Models\Zone;

/**
 * Строит backend-driven manifest шагов для `<GrowCycleLauncher>`.
 */
class LaunchFlowManifestBuilder
{
    public function __construct(private readonly LaunchFlowReadinessEnricher $readiness)
    {
    }

    /**
     * @return array{
     *   zone_id: int|null,
     *   role: string|null,
     *   steps: list<array<string, mixed>>,
     *   role_hints: array<string, list<string>>,
     *   readiness: array<string, mixed>
     * }
     */
    public function build(?Zone $zone, ?User $user): array
    {
        $readiness = $zone ? $this->readiness->forZone($zone) : [
            'ready' => false,
            'blockers' => [],
            'warnings' => [],
        ];

        $hasZone = $zone !== null;
        $hasBlockers = ! empty($readiness['blockers']);

        $steps = [
            [
                'id' => 'zone',
                'title' => 'Зона',
                'description' => 'Выбор или создание зоны',
                'visible' => ! $hasZone,
                'required' => ! $hasZone,
            ],
            [
                'id' => 'recipe',
                'title' => 'Рецепт и растение',
                'description' => 'Выбор активного рецепта и плана посадки',
                'visible' => true,
                'required' => true,
                'depends_on' => $hasZone ? [] : ['zone'],
                'validation' => [
                    'required_fields' => ['recipe_revision_id', 'plant_id', 'planting_at'],
                ],
            ],
            [
                'id' => 'automation',
                'title' => 'Автоматика',
                'description' => 'Overrides расписаний полива, света, климата',
                'visible' => true,
                'required' => false,
                'depends_on' => ['recipe'],
            ],
            [
                'id' => 'calibration',
                'title' => 'Калибровки и настройки',
                'description' => 'Sensor / pump / process calibration, correction config, PID',
                'visible' => $hasZone,
                'required' => $hasBlockers,
                'depends_on' => ['recipe'],
            ],
            [
                'id' => 'preview',
                'title' => 'Подтверждение',
                'description' => 'Просмотр diff и запуск цикла',
                'visible' => true,
                'required' => true,
                'depends_on' => ['recipe'],
            ],
        ];

        return [
            'zone_id' => $zone?->id,
            'role' => $this->resolveRole($user),
            'steps' => $steps,
            'role_hints' => [
                'operator' => ['recipe', 'preview'],
                'viewer' => [],
                'agronomist' => ['recipe', 'automation', 'preview'],
                'engineer' => ['zone', 'recipe', 'automation', 'calibration', 'preview'],
                'admin' => ['zone', 'recipe', 'automation', 'calibration', 'preview'],
            ],
            'readiness' => $readiness,
        ];
    }

    private function resolveRole(?User $user): ?string
    {
        if (! $user) {
            return null;
        }
        $role = $user->role ?? null;

        return is_string($role) ? $role : null;
    }
}
