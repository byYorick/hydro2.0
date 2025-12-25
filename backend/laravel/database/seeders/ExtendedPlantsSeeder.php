<?php

namespace Database\Seeders;

use App\Models\Plant;
use App\Models\PlantCostItem;
use App\Models\PlantPriceVersion;
use App\Models\PlantSalePrice;
use App\Models\Recipe;
use Illuminate\Database\Seeder;
use Illuminate\Support\Str;

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

        $costItemTypes = [
            ['name' => 'Семена', 'category' => 'materials', 'unit' => 'шт'],
            ['name' => 'Субстрат', 'category' => 'materials', 'unit' => 'кг'],
            ['name' => 'Удобрения', 'category' => 'materials', 'unit' => 'л'],
            ['name' => 'Электроэнергия', 'category' => 'utilities', 'unit' => 'кВт·ч'],
            ['name' => 'Вода', 'category' => 'utilities', 'unit' => 'л'],
            ['name' => 'Труд', 'category' => 'labor', 'unit' => 'час'],
        ];

        foreach ($costItemTypes as $itemData) {
            $exists = PlantCostItem::where('plant_id', $plant->id)
                ->where('name', $itemData['name'])
                ->exists();

            if ($exists) {
                continue;
            }

            PlantCostItem::create([
                'plant_id' => $plant->id,
                'name' => $itemData['name'],
                'category' => $itemData['category'],
                'unit' => $itemData['unit'],
                'cost_per_unit' => rand(10, 100) / 10,
                'quantity_per_cycle' => rand(1, 10),
            ]);

            $created++;
        }

        return $created;
    }

    private function seedSalePrices(Plant $plant): int
    {
        $created = 0;

        // Создаем цены продажи за последние 3 месяца
        for ($monthsAgo = 3; $monthsAgo >= 0; $monthsAgo--) {
            $effectiveFrom = now()->subMonths($monthsAgo)->startOfMonth();

            $exists = PlantSalePrice::where('plant_id', $plant->id)
                ->whereDate('effective_from', $effectiveFrom->toDateString())
                ->exists();

            if ($exists) {
                continue;
            }

            PlantSalePrice::create([
                'plant_id' => $plant->id,
                'effective_from' => $effectiveFrom,
                'currency' => 'RUB',
                'wholesale_price_per_kg' => rand(300, 600),
                'retail_price_per_kg' => rand(500, 1000),
                'wholesale_price_per_unit' => rand(20, 50),
                'retail_price_per_unit' => rand(30, 80),
            ]);

            $created++;
        }

        return $created;
    }

    private function linkPlantsToRecipes(Plant $plant, $recipes): int
    {
        $created = 0;

        // Связываем растение с 1-3 рецептами
        $recipeCount = rand(1, min(3, $recipes->count()));
        $selectedRecipes = $recipes->random($recipeCount);

        foreach ($selectedRecipes as $recipe) {
            // Проверяем, есть ли уже связь
            $exists = $plant->recipes()
                ->where('recipe_id', $recipe->id)
                ->exists();

            if ($exists) {
                continue;
            }

            $plant->recipes()->attach($recipe->id, [
                'season' => ['spring', 'summer', 'autumn', 'winter', 'all_year'][rand(0, 4)],
                'site_type' => ['indoor', 'outdoor', 'both'][rand(0, 2)],
                'is_default' => rand(0, 1) === 1,
                'metadata' => [
                    'recommended' => true,
                    'created_by' => 'system',
                ],
            ]);

            $created++;
        }

        return $created;
    }
}

