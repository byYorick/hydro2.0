<?php

namespace Database\Seeders;

use App\Models\Plant;
use App\Models\PlantCycle;
use App\Models\Recipe;
use App\Models\Zone;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;

/**
 * Сидер для связей растений с зонами и рецептами
 */
class ExtendedPlantRelationsSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание связей растений ===');

        $plants = Plant::all();
        $zones = Zone::all();
        $recipes = Recipe::all();

        if ($plants->isEmpty() || $zones->isEmpty() || $recipes->isEmpty()) {
            $this->command->warn('Растения, зоны или рецепты не найдены.');
            return;
        }

        $plantZoneCreated = $this->seedPlantZone($plants, $zones);
        $plantRecipeCreated = $this->seedPlantRecipe($plants, $recipes);
        $plantCyclesCreated = $this->seedPlantCycles($plants, $zones);

        $this->command->info("Создано связей plant_zone: {$plantZoneCreated}");
        $this->command->info("Создано связей plant_recipe: {$plantRecipeCreated}");
        $this->command->info("Создано циклов растений: {$plantCyclesCreated}");
    }

    private function seedPlantZone($plants, $zones): int
    {
        $created = 0;

        foreach ($zones as $zone) {
            if ($zone->status !== 'RUNNING') {
                continue;
            }

            // Связываем зону с 1-2 растениями
            $plantCount = rand(1, 2);
            $selectedPlants = $plants->random(min($plantCount, $plants->count()));

            foreach ($selectedPlants as $plant) {
                $exists = DB::table('plant_zone')
                    ->where('plant_id', $plant->id)
                    ->where('zone_id', $zone->id)
                    ->exists();

                if ($exists) {
                    continue;
                }

                DB::table('plant_zone')->insert([
                    'plant_id' => $plant->id,
                    'zone_id' => $zone->id,
                    'assigned_at' => now()->subDays(rand(1, 30)),
                    'metadata' => json_encode([
                        'assigned_by' => 'system',
                        'notes' => "Растение {$plant->name} назначено в зону {$zone->name}",
                    ]),
                    'created_at' => now()->subDays(rand(1, 30)),
                    'updated_at' => now()->subDays(rand(1, 30)),
                ]);

                $created++;
            }
        }

        return $created;
    }

    private function seedPlantRecipe($plants, $recipes): int
    {
        $created = 0;

        foreach ($plants as $plant) {
            // Связываем растение с 1-3 рецептами
            $recipeCount = rand(1, min(3, $recipes->count()));
            $selectedRecipes = $recipes->random($recipeCount);

            foreach ($selectedRecipes as $recipe) {
                $exists = DB::table('plant_recipe')
                    ->where('plant_id', $plant->id)
                    ->where('recipe_id', $recipe->id)
                    ->exists();

                if ($exists) {
                    continue;
                }

                DB::table('plant_recipe')->insert([
                    'plant_id' => $plant->id,
                    'recipe_id' => $recipe->id,
                    'season' => ['spring', 'summer', 'autumn', 'winter', 'all_year'][rand(0, 4)],
                    'site_type' => ['indoor', 'outdoor', 'both'][rand(0, 2)],
                    'is_default' => rand(0, 1) === 1,
                    'metadata' => json_encode([
                        'recommended' => true,
                        'created_by' => 'system',
                    ]),
                    'created_at' => now()->subDays(rand(1, 30)),
                    'updated_at' => now()->subDays(rand(1, 30)),
                ]);

                $created++;
            }
        }

        return $created;
    }

    private function seedPlantCycles($plants, $zones): int
    {
        $created = 0;

        foreach ($plants as $plant) {
            // Создаем циклы для растений в активных зонах
            $activeZones = $zones->where('status', 'RUNNING')->random(min(2, $zones->where('status', 'RUNNING')->count()));

            foreach ($activeZones as $zone) {
                // Проверяем, есть ли связь plant_zone
                $hasRelation = DB::table('plant_zone')
                    ->where('plant_id', $plant->id)
                    ->where('zone_id', $zone->id)
                    ->exists();

                if (!$hasRelation) {
                    continue;
                }

                // Получаем цикл выращивания для зоны
                $growCycle = \App\Models\GrowCycle::where('zone_id', $zone->id)
                    ->where('plant_id', $plant->id)
                    ->first();

                PlantCycle::create([
                    'plant_id' => $plant->id,
                    'cycle_id' => $growCycle?->id,
                    'zone_id' => $zone->id,
                    'season' => ['spring', 'summer', 'autumn', 'winter'][rand(0, 3)],
                    'settings' => [
                        'auto_mode' => true,
                        'notifications' => true,
                    ],
                    'metrics_snapshot' => [
                        'avg_ph' => rand(58, 65) / 10,
                        'avg_ec' => rand(15, 25) / 10,
                        'avg_temperature' => rand(20, 25),
                        'avg_humidity' => rand(55, 70),
                    ],
                ]);

                $created++;
            }
        }

        return $created;
    }
}

