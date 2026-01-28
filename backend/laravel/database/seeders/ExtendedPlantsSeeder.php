<?php

namespace Database\Seeders;

use App\Models\Plant;
use App\Models\PlantCostItem;
use App\Models\PlantPriceVersion;
use App\Models\PlantSalePrice;
use App\Models\Recipe;
use Illuminate\Database\Seeder;

/**
 * Расширенный сидер для растений
 * Расширяет данные растений, добавляя цены, стоимость и связи с рецептами
 */
class ExtendedPlantsSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Расширение данных растений ===');

        $plants = Plant::all();
        if ($plants->isEmpty()) {
            $this->command->warn('Растения не найдены. Запустите PlantTaxonomySeeder сначала.');
            return;
        }

        $recipes = Recipe::all();
        if ($recipes->isEmpty()) {
            $this->command->warn('Рецепты не найдены. Запустите ExtendedRecipesCyclesSeeder сначала.');
        }

        $priceVersionsCreated = 0;
        $costItemsCreated = 0;
        $salePricesCreated = 0;
        $recipeLinksCreated = 0;

        foreach ($plants as $plant) {
            // Добавляем дополнительные версии цен
            $priceVersionsCreated += $this->seedPriceVersions($plant);
            
            // Добавляем статьи затрат
            $costItemsCreated += $this->seedCostItems($plant);
            
            // Добавляем цены продажи
            $salePricesCreated += $this->seedSalePrices($plant);
            
            // Связываем с рецептами
            if ($recipes->isNotEmpty()) {
                $recipeLinksCreated += $this->linkPlantsToRecipes($plant, $recipes);
            }
        }

        $this->command->info("Создано версий цен: {$priceVersionsCreated}");
        $this->command->info("Создано статей затрат: {$costItemsCreated}");
        $this->command->info("Создано цен продажи: {$salePricesCreated}");
        $this->command->info("Создано связей с рецептами: {$recipeLinksCreated}");
    }

    private function seedPriceVersions(Plant $plant): int
    {
        $created = 0;

        // Создаем версии цен за последние 6 месяцев
        for ($monthsAgo = 6; $monthsAgo >= 0; $monthsAgo--) {
            $effectiveFrom = now()->subMonths($monthsAgo)->startOfMonth();

            $exists = PlantPriceVersion::where('plant_id', $plant->id)
                ->whereDate('effective_from', $effectiveFrom->toDateString())
                ->exists();

            if ($exists) {
                continue;
            }

            PlantPriceVersion::create([
                'plant_id' => $plant->id,
                'effective_from' => $effectiveFrom,
                'currency' => 'RUB',
                'seedling_cost' => rand(10, 20),
                'substrate_cost' => rand(5, 15),
                'nutrient_cost' => rand(3, 8),
                'labor_cost' => rand(5, 10),
                'wholesale_price' => rand(40, 80),
                'retail_price' => rand(60, 120),
                'source' => ['seed', 'cutting', 'seedling'][rand(0, 2)],
            ]);

            $created++;
        }

        return $created;
    }

    private function seedCostItems(Plant $plant): int
    {
        $created = 0;

        // Получаем последнюю версию цены для привязки
        $priceVersion = PlantPriceVersion::where('plant_id', $plant->id)
            ->orderBy('effective_from', 'desc')
            ->first();

        $costItemTypes = [
            ['type' => 'seedling', 'notes' => 'Семена'],
            ['type' => 'substrate', 'notes' => 'Субстрат'],
            ['type' => 'nutrient', 'notes' => 'Удобрения'],
            ['type' => 'labor', 'notes' => 'Труд'],
            ['type' => 'utilities', 'notes' => 'Электроэнергия и вода'],
        ];

        foreach ($costItemTypes as $itemData) {
            $exists = PlantCostItem::where('plant_id', $plant->id)
                ->where('type', $itemData['type'])
                ->exists();

            if ($exists) {
                continue;
            }

            PlantCostItem::create([
                'plant_id' => $plant->id,
                'plant_price_version_id' => $priceVersion?->id,
                'type' => $itemData['type'],
                'amount' => rand(10, 100),
                'currency' => 'RUB',
                'notes' => $itemData['notes'],
                'metadata' => [
                    'created_by' => 'system',
                ],
            ]);

            $created++;
        }

        return $created;
    }

    private function seedSalePrices(Plant $plant): int
    {
        $created = 0;

        // Получаем последнюю версию цены для привязки
        $priceVersion = PlantPriceVersion::where('plant_id', $plant->id)
            ->orderBy('effective_from', 'desc')
            ->first();

        if (!$priceVersion) {
            return 0;
        }

        $channels = ['wholesale', 'retail', 'online', 'marketplace'];

        foreach ($channels as $channel) {
            $exists = PlantSalePrice::where('plant_id', $plant->id)
                ->where('channel', $channel)
                ->where('is_active', true)
                ->exists();

            if ($exists) {
                continue;
            }

            PlantSalePrice::create([
                'plant_id' => $plant->id,
                'plant_price_version_id' => $priceVersion->id,
                'channel' => $channel,
                'price' => match ($channel) {
                    'wholesale' => rand(300, 600),
                    'retail' => rand(500, 1000),
                    'online' => rand(400, 800),
                    'marketplace' => rand(450, 900),
                    default => rand(300, 1000),
                },
                'currency' => 'RUB',
                'is_active' => true,
                'metadata' => [
                    'created_by' => 'system',
                ],
            ]);

            $created++;
        }

        return $created;
    }

    private function linkPlantsToRecipes(Plant $plant, $recipes): int
    {
        $created = 0;

        $selectedRecipes = $recipes->filter(function (Recipe $recipe) use ($plant) {
            $metadata = $recipe->metadata ?? [];
            $slugs = $metadata['crop_slugs'] ?? [];

            return is_array($slugs) && in_array($plant->slug, $slugs, true);
        });

        if ($selectedRecipes->isEmpty()) {
            return 0;
        }

        $hasDefault = $plant->recipes()->wherePivot('is_default', true)->exists();

        foreach ($selectedRecipes as $recipe) {
            // Проверяем, есть ли уже связь
            $exists = $plant->recipes()
                ->where('recipe_id', $recipe->id)
                ->exists();

            if ($exists) {
                continue;
            }

            $plant->recipes()->attach($recipe->id, [
                'season' => 'all_year',
                'site_type' => 'indoor',
                'is_default' => ! $hasDefault,
                'metadata' => json_encode([
                    'recommended' => true,
                    'created_by' => 'system',
                ], JSON_UNESCAPED_UNICODE),
            ]);

            $hasDefault = true;
            $created++;
        }

        return $created;
    }
}
