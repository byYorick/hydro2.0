<?php

namespace Database\Seeders;

use App\Enums\GrowCycleStatus;
use App\Models\GrowCycle;
use App\Models\GrowStageTemplate;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use App\Models\Zone;
use App\Services\GrowCycleService;
use Illuminate\Database\Seeder;
use Illuminate\Support\Collection;
use Illuminate\Support\Str;

/**
 * Расширенный сидер для рецептов, фаз и циклов выращивания
 */
class ExtendedRecipesCyclesSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание расширенных рецептов и циклов ===');

        $templates = $this->ensureStageTemplates();
        $revisions = $this->seedRecipes($templates);
        $this->seedGrowCycles($revisions);

        $this->command->info('Создано рецептов: '.Recipe::count());
        $this->command->info('Создано ревизий: '.RecipeRevision::count());
        $this->command->info('Создано фаз: '.RecipeRevisionPhase::count());
        $this->command->info('Создано циклов выращивания: '.GrowCycle::count());
    }

    private function ensureStageTemplates(): Collection
    {
        $templates = GrowStageTemplate::orderBy('order_index')->get();
        if ($templates->isNotEmpty()) {
            return $templates;
        }

        $stageTemplates = [
            [
                'name' => 'Посадка',
                'code' => 'PLANTING',
                'order_index' => 0,
                'default_duration_days' => 1,
                'ui_meta' => [
                    'color' => '#4CAF50',
                    'icon' => 'seedling',
                    'description' => 'Начальная стадия посадки семян или рассады',
                ],
            ],
            [
                'name' => 'Укоренение',
                'code' => 'ROOTING',
                'order_index' => 1,
                'default_duration_days' => 7,
                'ui_meta' => [
                    'color' => '#8BC34A',
                    'icon' => 'roots',
                    'description' => 'Стадия развития корневой системы',
                ],
            ],
            [
                'name' => 'Проращивание',
                'code' => 'GERMINATION',
                'order_index' => 2,
                'default_duration_days' => 3,
                'ui_meta' => [
                    'color' => '#CDDC39',
                    'icon' => 'sprout',
                    'description' => 'Стадия проращивания семян',
                ],
            ],
            [
                'name' => 'Вегетативная',
                'code' => 'VEG',
                'order_index' => 3,
                'default_duration_days' => 21,
                'ui_meta' => [
                    'color' => '#2196F3',
                    'icon' => 'leaf',
                    'description' => 'Стадия активного роста листьев и стеблей',
                ],
            ],
            [
                'name' => 'Цветение',
                'code' => 'FLOWER',
                'order_index' => 4,
                'default_duration_days' => 14,
                'ui_meta' => [
                    'color' => '#E91E63',
                    'icon' => 'flower',
                    'description' => 'Стадия цветения растений',
                ],
            ],
            [
                'name' => 'Плодоношение',
                'code' => 'FRUIT',
                'order_index' => 5,
                'default_duration_days' => 30,
                'ui_meta' => [
                    'color' => '#FF9800',
                    'icon' => 'fruit',
                    'description' => 'Стадия формирования и созревания плодов',
                ],
            ],
            [
                'name' => 'Сбор',
                'code' => 'HARVEST',
                'order_index' => 6,
                'default_duration_days' => 7,
                'ui_meta' => [
                    'color' => '#795548',
                    'icon' => 'harvest',
                    'description' => 'Стадия сбора урожая',
                ],
            ],
        ];

        foreach ($stageTemplates as $template) {
            GrowStageTemplate::firstOrCreate(
                ['code' => $template['code']],
                $template
            );
        }

        return GrowStageTemplate::orderBy('order_index')->get();
    }

    private function seedRecipes(Collection $templates): array
    {
        $revisions = [];

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

        $createdBy = User::where('role', 'admin')->value('id') ?? User::value('id');

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

            $revision = RecipeRevision::firstOrCreate(
                [
                    'recipe_id' => $recipe->id,
                    'revision_number' => 1,
                ],
                [
                    'status' => 'PUBLISHED',
                    'description' => 'Автоматически созданная ревизия',
                    'created_by' => $createdBy,
                    'published_at' => now(),
                ]
            );

            // Создаем фазы рецепта
            foreach ($recipeConfig['phases'] as $phaseData) {
                $targets = $phaseData['targets'] ?? [];
                $ph = $targets['ph'] ?? [];
                $ec = $targets['ec'] ?? [];
                $temperature = $targets['temperature'] ?? [];
                $humidity = $targets['humidity'] ?? [];
                $stageTemplate = $this->resolveStageTemplate($recipe, $phaseData, $templates);

                RecipeRevisionPhase::firstOrCreate(
                    [
                        'recipe_revision_id' => $revision->id,
                        'phase_index' => $phaseData['phase_index'],
                    ],
                    [
                        'name' => $phaseData['name'],
                        'stage_template_id' => $stageTemplate?->id,
                        'ph_target' => $this->averageTarget($ph),
                        'ph_min' => $ph['min'] ?? null,
                        'ph_max' => $ph['max'] ?? null,
                        'ec_target' => $this->averageTarget($ec),
                        'ec_min' => $ec['min'] ?? null,
                        'ec_max' => $ec['max'] ?? null,
                        'temp_air_target' => $this->averageTarget($temperature),
                        'humidity_target' => $this->averageTarget($humidity),
                        'duration_hours' => $phaseData['duration_hours'],
                        'progress_model' => 'TIME',
                        'irrigation_mode' => 'RECIRC',
                        'irrigation_interval_sec' => rand(900, 3600),
                        'irrigation_duration_sec' => rand(30, 120),
                    ]
                );
            }

            $revisions[] = $revision;
        }

        return $revisions;
    }

    private function seedGrowCycles(array $revisions): void
    {
        $zones = Zone::all();
        if ($zones->isEmpty()) {
            $this->command->warn('Зоны не найдены. Запустите ExtendedGreenhousesZonesSeeder сначала.');

            return;
        }

        $plants = Plant::all();
        if ($plants->isEmpty()) {
            $this->command->warn('Растения не найдены. Запустите PlantTaxonomySeeder сначала.');

            return;
        }

        if (empty($revisions)) {
            $this->command->warn('Ревизии рецептов не найдены.');

            return;
        }

        $growCycleService = app(GrowCycleService::class);
        $userId = User::where('role', 'admin')->value('id') ?? User::value('id');

        foreach ($zones as $zone) {
            if ($zone->activeGrowCycle) {
                continue;
            }

            $revision = $revisions[array_rand($revisions)];
            $plant = $plants->random();
            $startedAt = now()->subDays(rand(1, 30));

            try {
                $cycle = $growCycleService->createCycle(
                    $zone,
                    $revision,
                    $plant->id,
                    [
                        'planting_at' => $startedAt->format('Y-m-d H:i:s'),
                        'start_immediately' => $zone->status !== 'STOPPED',
                        'batch_label' => 'BATCH-'.Str::upper(Str::random(6)),
                        'notes' => "Цикл выращивания для зоны {$zone->name}",
                    ],
                    $userId
                );

                if ($zone->status === 'PAUSED' && $userId) {
                    $growCycleService->pause($cycle, $userId);
                }

                if ($zone->status === 'STOPPED' && $userId && $cycle->status === GrowCycleStatus::RUNNING) {
                    $growCycleService->abort($cycle, ['reason' => 'zone_stopped'], $userId);
                }
            } catch (\Throwable $e) {
                $this->command->warn("Не удалось создать цикл для зоны {$zone->id}: {$e->getMessage()}");
            }
        }
    }

    private function resolveStageTemplate(Recipe $recipe, array $phaseData, Collection $templates): ?GrowStageTemplate
    {
        $phaseName = Str::lower($phaseData['name'] ?? '');
        $recipeName = Str::lower($recipe->name);

        if (str_contains($phaseName, 'проращ') || str_contains($phaseName, 'germin')) {
            return $templates->firstWhere('code', 'GERMINATION') ?? $templates->first();
        }

        if (str_contains($phaseName, 'рассад') || str_contains($phaseName, 'посад')) {
            return $templates->firstWhere('code', 'PLANTING') ?? $templates->first();
        }

        if (str_contains($phaseName, 'вегет') || str_contains($phaseName, 'рост')) {
            return $templates->firstWhere('code', 'VEG') ?? $templates->first();
        }

        if (str_contains($phaseName, 'цвет')) {
            return $templates->firstWhere('code', 'FLOWER') ?? $templates->first();
        }

        if (str_contains($phaseName, 'плод') || str_contains($phaseName, 'созрев')) {
            return $templates->firstWhere('code', 'FRUIT') ?? $templates->first();
        }

        if (str_contains($phaseName, 'сбор') || str_contains($phaseName, 'harvest')) {
            return $templates->firstWhere('code', 'HARVEST') ?? $templates->first();
        }

        if (str_contains($recipeName, 'салат') || str_contains($recipeName, 'lettuce')) {
            return match ($phaseData['phase_index']) {
                0 => $templates->firstWhere('code', 'GERMINATION'),
                1 => $templates->firstWhere('code', 'VEG'),
                default => $templates->firstWhere('code', 'HARVEST'),
            } ?? $templates->first();
        }

        if (str_contains($recipeName, 'томат') || str_contains($recipeName, 'tomato')) {
            return match ($phaseData['phase_index']) {
                0 => $templates->firstWhere('code', 'PLANTING'),
                1 => $templates->firstWhere('code', 'VEG'),
                default => $templates->firstWhere('code', 'FRUIT'),
            } ?? $templates->first();
        }

        $fallbackCode = match ($phaseData['phase_index']) {
            0 => 'GERMINATION',
            1 => 'VEG',
            2 => 'FLOWER',
            3 => 'FRUIT',
            default => 'VEG',
        };

        return $templates->firstWhere('code', $fallbackCode) ?? $templates->first();
    }

    private function averageTarget(array $target): ?float
    {
        $min = $target['min'] ?? null;
        $max = $target['max'] ?? null;

        if ($min === null && $max === null) {
            return null;
        }

        if ($min === null) {
            return (float) $max;
        }

        if ($max === null) {
            return (float) $min;
        }

        return round(((float) $min + (float) $max) / 2, 2);
    }
}
