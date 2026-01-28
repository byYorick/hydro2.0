<?php

namespace Database\Seeders;

use App\Enums\GrowCycleStatus;
use App\Models\Greenhouse;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Zone;
use App\Services\GrowCycleService;
use Illuminate\Database\Seeder;

/**
 * Сидер для тестирования прогресса фаз выращивания
 *
 * Создает зоны с активными циклами выращивания на разных стадиях:
 * - Зона 1: Начало фазы (5% прогресса) - Фаза "Проращивание"
 * - Зона 2: Середина фазы (50% прогресса) - Фаза "Вегетация"
 * - Зона 3: Конец фазы (90% прогресса) - Фаза "Вегетация"
 * - Зона 4: Переход между фазами (99% прогресса) - Фаза "Проращивание"
 * - Зона 5: Цветение (30% прогресса) - Фаза "Цветение"
 * - Зона 6: Плодоношение (75% прогресса) - Фаза "Плодоношение"
 * - Зона 7: Завершенный цикл (100% прогресса) - Фаза "Плодоношение", статус PAUSED
 */
class ProgressTestSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание данных для тестирования прогресса фаз ===');

        $greenhouse = Greenhouse::firstOrCreate(
            ['uid' => 'gh-progress-test'],
            [
                'name' => 'Теплица для тестирования прогресса',
                'timezone' => 'Europe/Moscow',
                'type' => 'indoor',
                'description' => 'Теплица для тестирования визуализации прогресса фаз',
                'provisioning_token' => 'gh_'.\Illuminate\Support\Str::random(32),
            ]
        );

        $plant = Plant::firstOrCreate(
            ['slug' => 'tomato-test'],
            [
                'name' => 'Томат',
                'variety' => 'Тестовый сорт',
            ]
        );

        $recipe = Recipe::firstOrCreate(
            ['name' => 'Рецепт для тестирования прогресса'],
            [
                'description' => 'Рецепт с несколькими фазами для тестирования визуализации',
            ]
        );

        $recipe->plants()->syncWithoutDetaching([$plant->id]);

        $revision = RecipeRevision::firstOrCreate([
            'recipe_id' => $recipe->id,
            'revision_number' => 1,
        ], [
            'status' => 'PUBLISHED',
            'description' => 'Progress test revision',
            'created_by' => 1,
        ]);

        $phases = [
            [
                'phase_index' => 0,
                'name' => 'Проращивание',
                'duration_hours' => 168,
                'ph_min' => 5.8,
                'ph_max' => 6.0,
                'ec_min' => 0.8,
                'ec_max' => 1.0,
                'temp_air_target' => 23.0,
                'humidity_target' => 75.0,
            ],
            [
                'phase_index' => 1,
                'name' => 'Вегетация',
                'duration_hours' => 336,
                'ph_min' => 5.9,
                'ph_max' => 6.2,
                'ec_min' => 1.4,
                'ec_max' => 1.6,
                'temp_air_target' => 24.0,
                'humidity_target' => 65.0,
            ],
            [
                'phase_index' => 2,
                'name' => 'Цветение',
                'duration_hours' => 504,
                'ph_min' => 6.0,
                'ph_max' => 6.5,
                'ec_min' => 1.6,
                'ec_max' => 1.8,
                'temp_air_target' => 25.0,
                'humidity_target' => 55.0,
            ],
            [
                'phase_index' => 3,
                'name' => 'Плодоношение',
                'duration_hours' => 672,
                'ph_min' => 6.2,
                'ph_max' => 6.8,
                'ec_min' => 1.8,
                'ec_max' => 2.2,
                'temp_air_target' => 26.0,
                'humidity_target' => 50.0,
            ],
        ];

        foreach ($phases as $phaseData) {
            RecipeRevisionPhase::firstOrCreate(
                [
                    'recipe_revision_id' => $revision->id,
                    'phase_index' => $phaseData['phase_index'],
                ],
                array_merge($phaseData, [
                    'recipe_revision_id' => $revision->id,
                ])
            );
        }

        $zones = [];

        $zones[] = $this->createZoneWithProgress($greenhouse, 'Зона 1 - Начало фазы', $recipe, $revision, $plant, 0, 0.05, 'RUNNING');
        $zones[] = $this->createZoneWithProgress($greenhouse, 'Зона 2 - Середина фазы', $recipe, $revision, $plant, 1, 0.50, 'RUNNING');
        $zones[] = $this->createZoneWithProgress($greenhouse, 'Зона 3 - Конец фазы', $recipe, $revision, $plant, 1, 0.90, 'RUNNING');
        $zones[] = $this->createZoneWithProgress($greenhouse, 'Зона 4 - Переход между фазами', $recipe, $revision, $plant, 0, 0.99, 'RUNNING');
        $zones[] = $this->createZoneWithProgress($greenhouse, 'Зона 5 - Цветение', $recipe, $revision, $plant, 2, 0.30, 'RUNNING');
        $zones[] = $this->createZoneWithProgress($greenhouse, 'Зона 6 - Плодоношение', $recipe, $revision, $plant, 3, 0.75, 'RUNNING');
        $zones[] = $this->createZoneWithProgress($greenhouse, 'Зона 7 - Завершенный цикл', $recipe, $revision, $plant, 3, 1.0, 'PAUSED');

        $this->command->info('Создано зон: '.count($zones));
        $this->command->info('Рецепт: '.$recipe->name);
        $this->command->info('Фаз в рецепте: '.count($phases));
    }

    private function createZoneWithProgress(
        Greenhouse $greenhouse,
        string $zoneName,
        Recipe $recipe,
        RecipeRevision $revision,
        Plant $plant,
        int $phaseIndex,
        float $progressPercent,
        string $status
    ): Zone {
        $phase = RecipeRevisionPhase::where('recipe_revision_id', $revision->id)
            ->where('phase_index', $phaseIndex)
            ->first();

        if (! $phase) {
            throw new \RuntimeException("Фаза {$phaseIndex} не найдена в ревизии {$revision->id}");
        }

        $phaseDurationHours = $phase->duration_hours ?? 0;
        $elapsedHours = $phaseDurationHours * $progressPercent;
        $phaseStartedAt = now()->subHours($elapsedHours);

        $recipeStartedAt = $phaseStartedAt->copy();
        $prevPhases = RecipeRevisionPhase::where('recipe_revision_id', $revision->id)
            ->where('phase_index', '<', $phaseIndex)
            ->orderBy('phase_index')
            ->get();

        foreach ($prevPhases as $prevPhase) {
            $recipeStartedAt->subHours($prevPhase->duration_hours ?? 0);
        }

        $zoneUid = 'zone-progress-'.\Illuminate\Support\Str::slug($zoneName);
        $zone = Zone::firstOrCreate(
            ['uid' => $zoneUid],
            [
                'name' => $zoneName,
                'greenhouse_id' => $greenhouse->id,
                'status' => $status,
                'description' => "Зона для тестирования прогресса. Фаза: {$phase->name}, Прогресс: ".round($progressPercent * 100).'%',
            ]
        );

        $service = app(GrowCycleService::class);
        $cycle = $service->createCycle($zone, $revision, $plant->id, ['start_immediately' => true]);

        if ($phaseIndex > 0) {
            $service->setPhase($cycle, $phase, 'Seeder progress setup', 1);
        }

        $cycle->update([
            'status' => $status === 'RUNNING' ? GrowCycleStatus::RUNNING : GrowCycleStatus::PAUSED,
            'started_at' => $recipeStartedAt,
            'recipe_started_at' => $recipeStartedAt,
            'planting_at' => $recipeStartedAt,
            'phase_started_at' => $phaseStartedAt,
            'batch_label' => 'TEST-'.str_pad((string) $zone->id, 3, '0', STR_PAD_LEFT),
        ]);

        return $zone;
    }
}
