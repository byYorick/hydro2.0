<?php

namespace Database\Seeders;

use App\Enums\GrowCycleStatus;
use App\Models\GrowCycle;
use App\Models\Recipe;
use App\Models\RecipePhase;
use App\Models\Zone;
use App\Models\ZoneRecipeInstance;
use Illuminate\Database\Seeder;

/**
 * Расширенный сидер для рецептов, фаз и циклов выращивания
 */
class ExtendedRecipesCyclesSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание расширенных рецептов и циклов ===');

        // Создаем рецепты с фазами
        $recipes = $this->seedRecipes();
        
        // Создаем экземпляры рецептов в зонах
        $this->seedRecipeInstances($recipes);
        
        // Создаем циклы выращивания
        $this->seedGrowCycles($recipes);

        $this->command->info("Создано рецептов: " . Recipe::count());
        $this->command->info("Создано фаз: " . RecipePhase::count());
        $this->command->info("Создано экземпляров рецептов: " . ZoneRecipeInstance::count());
        $this->command->info("Создано циклов выращивания: " . GrowCycle::count());
    }

    private function seedRecipes(): array
    {
        $recipes = [];

        $recipeConfigs = [
            [
                'name' => 'Рецепт Салата Стандартный',
                'description' => 'Полный цикл выращивания салата от семени до урожая',
                'phases' => [
                    [
                        'phase_index' => 0,
                        'name' => 'Проращивание',
                        'duration_hours' => 72,
                        'targets' => [
                            'ph' => ['min' => 5.8, 'max' => 6.0],
                            'ec' => ['min' => 0.8, 'max' => 1.0],
                            'temperature' => ['min' => 20, 'max' => 22],
                            'humidity' => ['min' => 70, 'max' => 80],
                        ],
                    ],
                    [
                        'phase_index' => 1,
                        'name' => 'Вегетативная',
                        'duration_hours' => 336,
                        'targets' => [
                            'ph' => ['min' => 5.9, 'max' => 6.2],
                            'ec' => ['min' => 1.4, 'max' => 1.6],
                            'temperature' => ['min' => 20, 'max' => 24],
                            'humidity' => ['min' => 55, 'max' => 65],
                        ],
                    ],
                    [
                        'phase_index' => 2,
                        'name' => 'Созревание',
                        'duration_hours' => 720,
                        'targets' => [
                            'ph' => ['min' => 6.0, 'max' => 6.5],
                            'ec' => ['min' => 1.6, 'max' => 1.8],
                            'temperature' => ['min' => 20, 'max' => 24],
                            'humidity' => ['min' => 55, 'max' => 65],
                        ],
                    ],
                ],
            ],
            [
                'name' => 'Рецепт Томата Производственный',
                'description' => 'Оптимизированный рецепт для промышленного выращивания томатов',
                'phases' => [
                    [
                        'phase_index' => 0,
                        'name' => 'Рассада',
                        'duration_hours' => 336,
                        'targets' => [
                            'ph' => ['min' => 6.0, 'max' => 6.3],
                            'ec' => ['min' => 1.2, 'max' => 1.5],
                            'temperature' => ['min' => 22, 'max' => 24],
                            'humidity' => ['min' => 60, 'max' => 70],
                        ],
                    ],
                    [
                        'phase_index' => 1,
                        'name' => 'Вегетативная',
                        'duration_hours' => 720,
                        'targets' => [
                            'ph' => ['min' => 6.2, 'max' => 6.5],
                            'ec' => ['min' => 1.8, 'max' => 2.2],
                            'temperature' => ['min' => 22, 'max' => 26],
                            'humidity' => ['min' => 60, 'max' => 70],
                        ],
                    ],
                    [
                        'phase_index' => 2,
                        'name' => 'Плодоношение',
                        'duration_hours' => 1008,
                        'targets' => [
                            'ph' => ['min' => 6.3, 'max' => 6.8],
                            'ec' => ['min' => 2.2, 'max' => 2.5],
                            'temperature' => ['min' => 22, 'max' => 26],
                            'humidity' => ['min' => 60, 'max' => 70],
                        ],
                    ],
                ],
            ],
            [
                'name' => 'Рецепт Базилика Быстрый',
                'description' => 'Быстрый цикл выращивания базилика',
                'phases' => [
                    [
                        'phase_index' => 0,
                        'name' => 'Проращивание',
                        'duration_hours' => 120,
                        'targets' => [
                            'ph' => ['min' => 5.8, 'max' => 6.2],
                            'ec' => ['min' => 1.0, 'max' => 1.2],
                            'temperature' => ['min' => 22, 'max' => 26],
                            'humidity' => ['min' => 60, 'max' => 70],
                        ],
                    ],
                    [
                        'phase_index' => 1,
                        'name' => 'Рост',
                        'duration_hours' => 480,
                        'targets' => [
                            'ph' => ['min' => 5.8, 'max' => 6.5],
                            'ec' => ['min' => 1.0, 'max' => 1.6],
                            'temperature' => ['min' => 22, 'max' => 26],
                            'humidity' => ['min' => 55, 'max' => 65],
                        ],
                    ],
                ],
            ],
            [
                'name' => 'Рецепт Микрозелени',
                'description' => 'Короткий цикл для микрозелени',
                'phases' => [
                    [
                        'phase_index' => 0,
                        'name' => 'Проращивание',
                        'duration_hours' => 48,
                        'targets' => [
                            'ph' => ['min' => 5.8, 'max' => 6.2],
                            'ec' => ['min' => 0.8, 'max' => 1.0],
                            'temperature' => ['min' => 18, 'max' => 22],
                            'humidity' => ['min' => 50, 'max' => 60],
                        ],
                    ],
                    [
                        'phase_index' => 1,
                        'name' => 'Рост',
                        'duration_hours' => 168,
                        'targets' => [
                            'ph' => ['min' => 5.8, 'max' => 6.2],
                            'ec' => ['min' => 0.8, 'max' => 1.2],
                            'temperature' => ['min' => 18, 'max' => 22],
                            'humidity' => ['min' => 50, 'max' => 60],
                        ],
                    ],
                ],
            ],
            [
                'name' => 'Рецепт Огурца',
                'description' => 'Рецепт для выращивания огурцов',
                'phases' => [
                    [
                        'phase_index' => 0,
                        'name' => 'Рассада',
                        'duration_hours' => 336,
                        'targets' => [
                            'ph' => ['min' => 5.5, 'max' => 6.0],
                            'ec' => ['min' => 1.5, 'max' => 2.0],
                            'temperature' => ['min' => 22, 'max' => 26],
                            'humidity' => ['min' => 65, 'max' => 75],
                        ],
                    ],
                    [
                        'phase_index' => 1,
                        'name' => 'Вегетативная',
                        'duration_hours' => 720,
                        'targets' => [
                            'ph' => ['min' => 5.5, 'max' => 6.5],
                            'ec' => ['min' => 2.0, 'max' => 2.5],
                            'temperature' => ['min' => 22, 'max' => 26],
                            'humidity' => ['min' => 65, 'max' => 75],
                        ],
                    ],
                    [
                        'phase_index' => 2,
                        'name' => 'Плодоношение',
                        'duration_hours' => 1200,
                        'targets' => [
                            'ph' => ['min' => 5.5, 'max' => 6.5],
                            'ec' => ['min' => 2.5, 'max' => 3.0],
                            'temperature' => ['min' => 22, 'max' => 26],
                            'humidity' => ['min' => 65, 'max' => 75],
                        ],
                    ],
                ],
            ],
        ];

        foreach ($recipeConfigs as $recipeConfig) {
            $recipe = Recipe::firstOrCreate(
                ['name' => $recipeConfig['name']],
                [
                    'description' => $recipeConfig['description'],
                    'metadata' => [
                        'created_by' => 'system',
                        'version' => '1.0',
                    ],
                ]
            );

            // Создаем фазы рецепта
            foreach ($recipeConfig['phases'] as $phaseData) {
                RecipePhase::firstOrCreate(
                    [
                        'recipe_id' => $recipe->id,
                        'phase_index' => $phaseData['phase_index'],
                    ],
                    $phaseData
                );
            }

            $recipes[] = $recipe;
        }

        return $recipes;
    }

    private function seedRecipeInstances(array $recipes): void
    {
        $zones = Zone::where('status', 'RUNNING')->get();
        
        foreach ($zones as $zone) {
            // Не создаем экземпляр, если он уже существует
            if ($zone->recipeInstance) {
                continue;
            }

            $recipe = $recipes[array_rand($recipes)];
            $startedAt = now()->subDays(rand(1, 30));

            ZoneRecipeInstance::create([
                'zone_id' => $zone->id,
                'recipe_id' => $recipe->id,
                'started_at' => $startedAt,
                'current_phase_index' => $this->calculateCurrentPhase($recipe, $startedAt),
            ]);
        }
    }

    private function seedGrowCycles(array $recipes): void
    {
        $zones = Zone::all();

        foreach ($zones as $zone) {
            // Создаем несколько циклов для каждой зоны
            $cycleCount = match ($zone->status) {
                'RUNNING' => rand(1, 3),
                'PAUSED' => rand(0, 2),
                'STOPPED' => rand(0, 1),
                default => 0,
            };

            for ($i = 0; $i < $cycleCount; $i++) {
                $recipe = $recipes[array_rand($recipes)];
                $status = $this->getRandomCycleStatus($zone->status);
                
                $startedAt = now()->subDays(rand(1, 60));
                $expectedHarvestAt = $startedAt->copy()->addDays(rand(30, 90));
                
                $actualHarvestAt = null;
                if (in_array($status, [GrowCycleStatus::HARVESTED, GrowCycleStatus::ABORTED])) {
                    $actualHarvestAt = $expectedHarvestAt->copy()->subDays(rand(-5, 5));
                }

                GrowCycle::create([
                    'greenhouse_id' => $zone->greenhouse_id,
                    'zone_id' => $zone->id,
                    'recipe_id' => $recipe->id,
                    'zone_recipe_instance_id' => $zone->recipeInstance?->id,
                    'status' => $status,
                    'started_at' => $startedAt,
                    'recipe_started_at' => $startedAt,
                    'expected_harvest_at' => $expectedHarvestAt,
                    'actual_harvest_at' => $actualHarvestAt,
                    'batch_label' => 'BATCH-' . strtoupper(substr(md5($zone->id . $i . time()), 0, 8)),
                    'notes' => "Цикл выращивания #{$i} для зоны {$zone->name}",
                    'settings' => [
                        'auto_mode' => true,
                        'notifications' => true,
                    ],
                    'current_stage_code' => $this->getCurrentStageCode($recipe, $startedAt),
                    'current_stage_started_at' => $startedAt,
                    'planting_at' => $startedAt,
                ]);
            }
        }
    }

    private function calculateCurrentPhase(Recipe $recipe, \DateTime $startedAt): int
    {
        $phases = $recipe->phases()->orderBy('phase_index')->get();
        $elapsedHours = now()->diffInHours($startedAt, false);
        
        if ($elapsedHours < 0) {
            return 0;
        }

        $cumulativeHours = 0;
        foreach ($phases as $phase) {
            $cumulativeHours += $phase->duration_hours ?? 0;
            if ($elapsedHours < $cumulativeHours) {
                return $phase->phase_index;
            }
        }

        return $phases->last()->phase_index ?? 0;
    }

    private function getRandomCycleStatus(string $zoneStatus): GrowCycleStatus
    {
        return match ($zoneStatus) {
            'RUNNING' => [
                GrowCycleStatus::RUNNING,
                GrowCycleStatus::RUNNING,
                GrowCycleStatus::RUNNING,
                GrowCycleStatus::PAUSED,
                GrowCycleStatus::HARVESTED,
            ][rand(0, 4)],
            'PAUSED' => [
                GrowCycleStatus::PAUSED,
                GrowCycleStatus::PAUSED,
                GrowCycleStatus::PLANNED,
            ][rand(0, 2)],
            'STOPPED' => [
                GrowCycleStatus::ABORTED,
                GrowCycleStatus::HARVESTED,
                GrowCycleStatus::ABORTED,
            ][rand(0, 2)],
            default => GrowCycleStatus::PLANNED,
        };
    }

    private function getCurrentStageCode(Recipe $recipe, \DateTime $startedAt): ?string
    {
        $phases = $recipe->phases()->orderBy('phase_index')->get();
        $currentPhaseIndex = $this->calculateCurrentPhase($recipe, $startedAt);
        $currentPhase = $phases->firstWhere('phase_index', $currentPhaseIndex);
        
        return $currentPhase ? $currentPhase->name : null;
    }
}

