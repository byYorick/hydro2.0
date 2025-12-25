<?php

namespace Database\Seeders;

use App\Models\GrowCycle;
use App\Models\Harvest;
use App\Models\Recipe;
use App\Models\Zone;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;

/**
 * Расширенный сидер для урожаев и аналитики
 */
class ExtendedHarvestsSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание расширенных урожаев ===');

        $zones = Zone::all();
        if ($zones->isEmpty()) {
            $this->command->warn('Зоны не найдены.');
            return;
        }

        $harvestsCreated = 0;
        $analyticsCreated = 0;

        foreach ($zones as $zone) {
            $harvestsCreated += $this->seedHarvestsForZone($zone);
            $analyticsCreated += $this->seedRecipeAnalytics($zone);
        }

        $this->command->info("Создано урожаев: {$harvestsCreated}");
        $this->command->info("Создано аналитики: {$analyticsCreated}");
        $this->command->info("Всего урожаев: " . Harvest::count());
    }

    private function seedHarvestsForZone(Zone $zone): int
    {
        $created = 0;

        // Создаем урожаи для завершенных циклов
        $cycles = GrowCycle::where('zone_id', $zone->id)
            ->whereIn('status', ['COMPLETED', 'HARVESTED'])
            ->get();

        foreach ($cycles as $cycle) {
            // Проверяем, есть ли уже урожай для этого цикла
            $exists = Harvest::where('zone_id', $zone->id)
                ->where('recipe_id', $cycle->recipe_id)
                ->whereDate('harvest_date', $cycle->actual_harvest_at?->toDateString() ?? now()->toDateString())
                ->exists();

            if ($exists) {
                continue;
            }

            $harvestDate = $cycle->actual_harvest_at ?? $cycle->expected_harvest_at ?? now()->subDays(rand(1, 30));

            Harvest::create([
                'zone_id' => $zone->id,
                'recipe_id' => $cycle->recipe_id,
                'harvest_date' => $harvestDate,
                'yield_weight_kg' => rand(50, 500) / 10,
                'yield_count' => rand(100, 1000),
                'quality_score' => rand(70, 100) / 10,
                'notes' => [
                    'comment' => "Урожай из зоны {$zone->name}",
                    'batch_label' => $cycle->batch_label ?? 'BATCH-' . rand(1000, 9999),
                    'cycle_id' => $cycle->id,
                ],
                'created_at' => $harvestDate,
                'updated_at' => $harvestDate,
            ]);

            $created++;
        }

        // Создаем дополнительные исторические урожаи
        $historicalCount = match ($zone->status) {
            'RUNNING' => rand(3, 10),
            'PAUSED' => rand(1, 5),
            'STOPPED' => rand(0, 2),
            default => 0,
        };

        for ($i = 0; $i < $historicalCount; $i++) {
            $recipe = Recipe::inRandomOrder()->first();
            if (!$recipe) {
                continue;
            }

            $harvestDate = now()->subDays(rand(30, 180));

            Harvest::create([
                'zone_id' => $zone->id,
                'recipe_id' => $recipe->id,
                'harvest_date' => $harvestDate,
                'yield_weight_kg' => rand(50, 500) / 10,
                'yield_count' => rand(100, 1000),
                'quality_score' => rand(70, 100) / 10,
                'notes' => [
                    'comment' => "Исторический урожай из зоны {$zone->name}",
                    'batch_label' => 'BATCH-' . rand(1000, 9999),
                ],
                'created_at' => $harvestDate,
                'updated_at' => $harvestDate,
            ]);

            $created++;
        }

        return $created;
    }

    private function seedRecipeAnalytics(Zone $zone): int
    {
        $created = 0;

        $recipes = Recipe::all();
        if ($recipes->isEmpty()) {
            return 0;
        }

        foreach ($recipes as $recipe) {
            // Проверяем, есть ли уже аналитика для этого рецепта в зоне
            $exists = DB::table('recipe_analytics')
                ->where('zone_id', $zone->id)
                ->where('recipe_id', $recipe->id)
                ->exists();

            if ($exists) {
                continue;
            }

            $cycles = GrowCycle::where('zone_id', $zone->id)
                ->where('recipe_id', $recipe->id)
                ->whereIn('status', ['COMPLETED', 'HARVESTED'])
                ->get();

            $harvests = Harvest::where('zone_id', $zone->id)
                ->where('recipe_id', $recipe->id)
                ->get();

            $avgYield = $harvests->avg('yield_weight_kg') ?? rand(50, 200) / 10;
            $avgQuality = $harvests->avg('quality_score') ?? rand(70, 95) / 10;
            $totalCycles = $cycles->count();
            $successRate = $totalCycles > 0 ? rand(80, 100) / 100 : 0;

            DB::table('recipe_analytics')->insert([
                'zone_id' => $zone->id,
                'recipe_id' => $recipe->id,
                'total_cycles' => $totalCycles,
                'completed_cycles' => $cycles->where('status', 'COMPLETED')->count(),
                'avg_yield_kg' => $avgYield,
                'avg_quality_score' => $avgQuality,
                'success_rate' => $successRate,
                'avg_cycle_duration_days' => $cycles->avg(function ($cycle) {
                    if ($cycle->started_at && $cycle->actual_harvest_at) {
                        return $cycle->started_at->diffInDays($cycle->actual_harvest_at);
                    }
                    return rand(30, 90);
                }) ?? rand(30, 90),
                'metadata' => json_encode([
                    'last_updated' => now()->toIso8601String(),
                    'zone_name' => $zone->name,
                ]),
                'created_at' => now()->subDays(rand(1, 30)),
                'updated_at' => now()->subDays(rand(1, 30)),
            ]);

            $created++;
        }

        return $created;
    }
}

