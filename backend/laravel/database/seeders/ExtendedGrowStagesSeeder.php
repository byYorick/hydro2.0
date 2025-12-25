<?php

namespace Database\Seeders;

use App\Models\GrowStageTemplate;
use App\Models\Recipe;
use App\Models\RecipeStageMap;
use Illuminate\Database\Seeder;

/**
 * Сидер для шаблонов стадий роста и их маппинга к рецептам
 */
class ExtendedGrowStagesSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание шаблонов стадий роста ===');

        $stagesCreated = $this->seedGrowStageTemplates();
        $mapsCreated = $this->seedRecipeStageMaps();

        $this->command->info("Создано шаблонов стадий: {$stagesCreated}");
        $this->command->info("Создано маппингов: {$mapsCreated}");
    }

    private function seedGrowStageTemplates(): int
    {
        $created = 0;

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
            $created++;
        }

        return $created;
    }

    private function seedRecipeStageMaps(): int
    {
        $created = 0;

        $recipes = Recipe::all();
        $stageTemplates = GrowStageTemplate::orderBy('order_index')->get();

        if ($recipes->isEmpty() || $stageTemplates->isEmpty()) {
            $this->command->warn('Рецепты или шаблоны стадий не найдены.');
            return 0;
        }

        foreach ($recipes as $recipe) {
            $phases = $recipe->phases()->orderBy('phase_index')->get();
            
            if ($phases->isEmpty()) {
                continue;
            }

            // Маппим стадии в зависимости от типа рецепта
            $stageMapping = $this->getStageMappingForRecipe($recipe, $phases, $stageTemplates);

            foreach ($stageMapping as $index => $mapping) {
                RecipeStageMap::firstOrCreate(
                    [
                        'recipe_id' => $recipe->id,
                        'stage_template_id' => $mapping['stage_template_id'],
                        'order_index' => $index,
                    ],
                    [
                        'start_offset_days' => $mapping['start_offset_days'],
                        'end_offset_days' => $mapping['end_offset_days'],
                        'phase_indices' => $mapping['phase_indices'],
                        'targets_override' => $mapping['targets_override'],
                    ]
                );
                $created++;
            }
        }

        return $created;
    }

    private function getStageMappingForRecipe(Recipe $recipe, $phases, $stageTemplates): array
    {
        $recipeName = strtolower($recipe->name);
        $mapping = [];

        // Определяем маппинг в зависимости от типа рецепта
        if (str_contains($recipeName, 'салат') || str_contains($recipeName, 'lettuce')) {
            // Для салата: Проращивание -> Вегетативная -> Сбор
            $mapping = [
                [
                    'stage_template_id' => $stageTemplates->firstWhere('code', 'GERMINATION')->id,
                    'start_offset_days' => 0,
                    'end_offset_days' => 3,
                    'phase_indices' => [0],
                    'targets_override' => null,
                ],
                [
                    'stage_template_id' => $stageTemplates->firstWhere('code', 'VEG')->id,
                    'start_offset_days' => 3,
                    'end_offset_days' => 21,
                    'phase_indices' => [1],
                    'targets_override' => null,
                ],
                [
                    'stage_template_id' => $stageTemplates->firstWhere('code', 'HARVEST')->id,
                    'start_offset_days' => 21,
                    'end_offset_days' => 30,
                    'phase_indices' => [2],
                    'targets_override' => null,
                ],
            ];
        } elseif (str_contains($recipeName, 'томат') || str_contains($recipeName, 'tomato')) {
            // Для томата: Посадка -> Вегетативная -> Цветение -> Плодоношение -> Сбор
            $mapping = [
                [
                    'stage_template_id' => $stageTemplates->firstWhere('code', 'PLANTING')->id,
                    'start_offset_days' => 0,
                    'end_offset_days' => 1,
                    'phase_indices' => [0],
                    'targets_override' => null,
                ],
                [
                    'stage_template_id' => $stageTemplates->firstWhere('code', 'VEG')->id,
                    'start_offset_days' => 1,
                    'end_offset_days' => 15,
                    'phase_indices' => [1],
                    'targets_override' => null,
                ],
                [
                    'stage_template_id' => $stageTemplates->firstWhere('code', 'FLOWER')->id,
                    'start_offset_days' => 15,
                    'end_offset_days' => 30,
                    'phase_indices' => [2],
                    'targets_override' => null,
                ],
                [
                    'stage_template_id' => $stageTemplates->firstWhere('code', 'FRUIT')->id,
                    'start_offset_days' => 30,
                    'end_offset_days' => 60,
                    'phase_indices' => [2],
                    'targets_override' => null,
                ],
            ];
        } else {
            // Общий маппинг для остальных рецептов
            $cumulativeDays = 0;
            foreach ($phases as $phaseIndex => $phase) {
                $durationDays = ($phase->duration_hours ?? 0) / 24;
                
                // Выбираем подходящую стадию
                $stageCode = match ($phaseIndex) {
                    0 => 'GERMINATION',
                    1 => 'VEG',
                    2 => 'FLOWER',
                    3 => 'FRUIT',
                    default => 'VEG',
                };

                $stageTemplate = $stageTemplates->firstWhere('code', $stageCode);
                if (!$stageTemplate) {
                    $stageTemplate = $stageTemplates->first();
                }

                $mapping[] = [
                    'stage_template_id' => $stageTemplate->id,
                    'start_offset_days' => $cumulativeDays,
                    'end_offset_days' => $cumulativeDays + $durationDays,
                    'phase_indices' => [$phaseIndex],
                    'targets_override' => null,
                ];

                $cumulativeDays += $durationDays;
            }
        }

        return $mapping;
    }
}

