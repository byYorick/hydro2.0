<?php

namespace Database\Seeders;

use App\Models\GrowStageTemplate;
use App\Models\Recipe;
use App\Models\RecipeRevisionPhase;
use Illuminate\Database\Seeder;
use Illuminate\Support\Str;

/**
 * Сидер для шаблонов стадий роста и их привязки к фазам ревизий
 */
class ExtendedGrowStagesSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание шаблонов стадий роста ===');

        $stagesCreated = $this->seedGrowStageTemplates();
        $phasesUpdated = $this->assignStagesToPhases();

        $this->command->info("Создано шаблонов стадий: {$stagesCreated}");
        $this->command->info("Обновлено фаз: {$phasesUpdated}");
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

    private function assignStagesToPhases(): int
    {
        $updated = 0;

        $templates = GrowStageTemplate::orderBy('order_index')->get();
        if ($templates->isEmpty()) {
            $this->command->warn('Шаблоны стадий не найдены.');

            return 0;
        }

        $phases = RecipeRevisionPhase::with('recipeRevision.recipe')->get();
        if ($phases->isEmpty()) {
            $this->command->warn('Фазы ревизий не найдены.');

            return 0;
        }

        foreach ($phases as $phase) {
            if ($phase->stage_template_id) {
                continue;
            }

            $recipe = $phase->recipeRevision?->recipe;
            if (! $recipe) {
                continue;
            }

            $template = $this->resolveStageTemplate($recipe, $phase, $templates);
            if (! $template) {
                continue;
            }

            $phase->update(['stage_template_id' => $template->id]);
            $updated++;
        }

        return $updated;
    }

    private function resolveStageTemplate(Recipe $recipe, RecipeRevisionPhase $phase, $templates): ?GrowStageTemplate
    {
        $phaseName = Str::lower($phase->name ?? '');
        $recipeName = Str::lower($recipe->name ?? '');

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
            return match ($phase->phase_index) {
                0 => $templates->firstWhere('code', 'GERMINATION'),
                1 => $templates->firstWhere('code', 'VEG'),
                default => $templates->firstWhere('code', 'HARVEST'),
            } ?? $templates->first();
        }

        if (str_contains($recipeName, 'томат') || str_contains($recipeName, 'tomato')) {
            return match ($phase->phase_index) {
                0 => $templates->firstWhere('code', 'PLANTING'),
                1 => $templates->firstWhere('code', 'VEG'),
                default => $templates->firstWhere('code', 'FRUIT'),
            } ?? $templates->first();
        }

        $fallbackCode = match ($phase->phase_index) {
            0 => 'GERMINATION',
            1 => 'VEG',
            2 => 'FLOWER',
            3 => 'FRUIT',
            default => 'VEG',
        };

        return $templates->firstWhere('code', $fallbackCode) ?? $templates->first();
    }
}
