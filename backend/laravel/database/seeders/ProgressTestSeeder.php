<?php

namespace Database\Seeders;

use App\Models\GrowCycle;
use App\Models\Greenhouse;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipePhase;
use App\Models\Zone;
use App\Models\ZoneRecipeInstance;
use Illuminate\Database\Seeder;
use Illuminate\Support\Carbon;

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
 * 
 * Использование:
 * php artisan db:seed --class=ProgressTestSeeder
 * 
 * Или через DatabaseSeeder (автоматически в local/dev окружении):
 * php artisan db:seed
 */
class ProgressTestSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание данных для тестирования прогресса фаз ===');

        // Создаем теплицу для тестирования
        $greenhouse = Greenhouse::firstOrCreate(
            ['uid' => 'gh-progress-test'],
            [
                'name' => 'Теплица для тестирования прогресса',
                'timezone' => 'Europe/Moscow',
                'type' => 'indoor',
                'description' => 'Теплица для тестирования визуализации прогресса фаз',
                'provisioning_token' => 'gh_' . \Illuminate\Support\Str::random(32),
            ]
        );

        // Создаем растение
        $plant = Plant::firstOrCreate(
            ['slug' => 'tomato-test'],
            [
                'name' => 'Томат',
                'variety' => 'Тестовый сорт',
            ]
        );

        // Создаем рецепт с фазами
        $recipe = Recipe::firstOrCreate(
            ['name' => 'Рецепт для тестирования прогресса'],
            [
                'description' => 'Рецепт с несколькими фазами для тестирования визуализации',
            ]
        );

        // Создаем фазы рецепта
        $phases = [
            [
                'phase_index' => 0,
                'name' => 'Проращивание',
                'duration_hours' => 168, // 7 дней
                'targets' => [
                    'ph' => ['min' => 5.8, 'max' => 6.0],
                    'ec' => ['min' => 0.8, 'max' => 1.0],
                    'temp_air' => ['min' => 22, 'max' => 25],
                    'humidity_air' => ['min' => 70, 'max' => 80],
                ],
            ],
            [
                'phase_index' => 1,
                'name' => 'Вегетация',
                'duration_hours' => 336, // 14 дней
                'targets' => [
                    'ph' => ['min' => 5.9, 'max' => 6.2],
                    'ec' => ['min' => 1.4, 'max' => 1.6],
                    'temp_air' => ['min' => 23, 'max' => 26],
                    'humidity_air' => ['min' => 60, 'max' => 70],
                ],
            ],
            [
                'phase_index' => 2,
                'name' => 'Цветение',
                'duration_hours' => 504, // 21 день
                'targets' => [
                    'ph' => ['min' => 6.0, 'max' => 6.5],
                    'ec' => ['min' => 1.6, 'max' => 1.8],
                    'temp_air' => ['min' => 24, 'max' => 27],
                    'humidity_air' => ['min' => 50, 'max' => 60],
                ],
            ],
            [
                'phase_index' => 3,
                'name' => 'Плодоношение',
                'duration_hours' => 672, // 28 дней
                'targets' => [
                    'ph' => ['min' => 6.2, 'max' => 6.8],
                    'ec' => ['min' => 1.8, 'max' => 2.2],
                    'temp_air' => ['min' => 25, 'max' => 28],
                    'humidity_air' => ['min' => 45, 'max' => 55],
                ],
            ],
        ];

        foreach ($phases as $phaseData) {
            RecipePhase::firstOrCreate(
                [
                    'recipe_id' => $recipe->id,
                    'phase_index' => $phaseData['phase_index'],
                ],
                $phaseData
            );
        }

        // Создаем зоны с разным прогрессом
        $zones = [];

        // Зона 1: Начало первой фазы (5% прогресса)
        $zone1 = $this->createZoneWithProgress(
            $greenhouse,
            'Зона 1 - Начало фазы',
            $recipe,
            $plant,
            0, // Фаза 0 (Проращивание)
            0.05, // 5% прогресса
            'RUNNING'
        );
        $zones[] = $zone1;

        // Зона 2: Середина второй фазы (50% прогресса)
        $zone2 = $this->createZoneWithProgress(
            $greenhouse,
            'Зона 2 - Середина фазы',
            $recipe,
            $plant,
            1, // Фаза 1 (Вегетация)
            0.50, // 50% прогресса
            'RUNNING'
        );
        $zones[] = $zone2;

        // Зона 3: Конец второй фазы (90% прогресса)
        $zone3 = $this->createZoneWithProgress(
            $greenhouse,
            'Зона 3 - Конец фазы',
            $recipe,
            $plant,
            1, // Фаза 1 (Вегетация)
            0.90, // 90% прогресса
            'RUNNING'
        );
        $zones[] = $zone3;

        // Зона 4: Переход между фазами (99% прогресса первой фазы)
        $zone4 = $this->createZoneWithProgress(
            $greenhouse,
            'Зона 4 - Переход между фазами',
            $recipe,
            $plant,
            0, // Фаза 0 (Проращивание)
            0.99, // 99% прогресса (почти переход)
            'RUNNING'
        );
        $zones[] = $zone4;

        // Зона 5: Третья фаза (Цветение) - 30% прогресса
        $zone5 = $this->createZoneWithProgress(
            $greenhouse,
            'Зона 5 - Цветение',
            $recipe,
            $plant,
            2, // Фаза 2 (Цветение)
            0.30, // 30% прогресса
            'RUNNING'
        );
        $zones[] = $zone5;

        // Зона 6: Последняя фаза (Плодоношение) - 75% прогресса
        $zone6 = $this->createZoneWithProgress(
            $greenhouse,
            'Зона 6 - Плодоношение',
            $recipe,
            $plant,
            3, // Фаза 3 (Плодоношение)
            0.75, // 75% прогресса
            'RUNNING'
        );
        $zones[] = $zone6;

        // Зона 7: Завершенный цикл
        $zone7 = $this->createZoneWithProgress(
            $greenhouse,
            'Зона 7 - Завершенный цикл',
            $recipe,
            $plant,
            3, // Фаза 3 (Плодоношение)
            1.0, // 100% прогресса
            'PAUSED'
        );
        $zones[] = $zone7;

        $this->command->info('Создано зон: ' . count($zones));
        $this->command->info('Рецепт: ' . $recipe->name);
        $this->command->info('Фаз в рецепте: ' . count($phases));
    }

    /**
     * Создает зону с заданным прогрессом фазы
     */
    private function createZoneWithProgress(
        Greenhouse $greenhouse,
        string $zoneName,
        Recipe $recipe,
        Plant $plant,
        int $phaseIndex,
        float $progressPercent, // 0.0 - 1.0
        string $status
    ): Zone {
        // Получаем фазу рецепта
        $phase = RecipePhase::where('recipe_id', $recipe->id)
            ->where('phase_index', $phaseIndex)
            ->first();

        if (!$phase) {
            throw new \Exception("Фаза {$phaseIndex} не найдена в рецепте {$recipe->id}");
        }

        // Вычисляем время начала фазы (в прошлом, чтобы был прогресс)
        $phaseDurationHours = $phase->duration_hours;
        $elapsedHours = $phaseDurationHours * $progressPercent;
        $phaseStartedAt = now()->subHours($elapsedHours);
        $phaseEndsAt = $phaseStartedAt->copy()->addHours($phaseDurationHours);

        // Вычисляем общее время начала рецепта (сумма всех предыдущих фаз)
        $recipeStartedAt = $phaseStartedAt->copy();
        for ($i = 0; $i < $phaseIndex; $i++) {
            $prevPhase = RecipePhase::where('recipe_id', $recipe->id)
                ->where('phase_index', $i)
                ->first();
            if ($prevPhase) {
                $recipeStartedAt->subHours($prevPhase->duration_hours);
            }
        }

        // Создаем зону
        $zoneUid = 'zone-progress-' . \Illuminate\Support\Str::slug($zoneName);
        $zone = Zone::firstOrCreate(
            ['uid' => $zoneUid],
            [
                'name' => $zoneName,
                'greenhouse_id' => $greenhouse->id,
                'status' => $status,
                'description' => "Зона для тестирования прогресса. Фаза: {$phase->name}, Прогресс: " . round($progressPercent * 100) . '%',
            ]
        );

        // Создаем экземпляр рецепта
        $recipeInstance = ZoneRecipeInstance::updateOrCreate(
            ['zone_id' => $zone->id],
            [
                'recipe_id' => $recipe->id,
                'started_at' => $recipeStartedAt,
                'current_phase_index' => $phaseIndex,
            ]
        );

        // Создаем активный цикл выращивания
        $growCycleStatus = $status === 'RUNNING' 
            ? \App\Enums\GrowCycleStatus::RUNNING 
            : \App\Enums\GrowCycleStatus::PAUSED;
            
        GrowCycle::updateOrCreate(
            [
                'zone_id' => $zone->id,
            ],
            [
                'greenhouse_id' => $greenhouse->id,
                'recipe_id' => $recipe->id,
                'zone_recipe_instance_id' => $recipeInstance->id,
                'plant_id' => $plant->id,
                'status' => $growCycleStatus,
                'started_at' => $recipeStartedAt,
                'recipe_started_at' => $recipeStartedAt,
                'planting_at' => $recipeStartedAt,
                'current_stage_code' => "PHASE_{$phaseIndex}",
                'current_stage_started_at' => $phaseStartedAt,
                'batch_label' => 'TEST-' . str_pad((string)$zone->id, 3, '0', STR_PAD_LEFT),
                'settings' => [
                    'subsystems' => [
                        'ph' => ['enabled' => true],
                        'ec' => ['enabled' => true],
                        'climate' => ['enabled' => true],
                        'irrigation' => ['enabled' => true],
                    ],
                ],
            ]
        );

        return $zone;
    }
}

