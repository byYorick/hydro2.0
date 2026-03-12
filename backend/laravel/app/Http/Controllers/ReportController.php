<?php

namespace App\Http\Controllers;

use App\Models\Recipe;
use App\Models\Zone;
use App\Models\RecipeAnalytics;
use App\Models\Harvest;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\DB;

class ReportController extends Controller
{
    /**
     * Получить аналитику по рецепту
     */
    public function recipeAnalytics(Request $request, Recipe $recipe)
    {
        $query = RecipeAnalytics::where('recipe_id', $recipe->id)
            ->with(['zone', 'recipe']);

        if ($request->filled('zone_id')) {
            $query->where('zone_id', $request->integer('zone_id'));
        }

        if ($request->filled('start_date')) {
            $query->where('start_date', '>=', $request->date('start_date'));
        }

        if ($request->filled('end_date')) {
            $query->where('end_date', '<=', $request->date('end_date'));
        }

        $analytics = $query->latest('start_date')->paginate(25);

        // Рассчитать средние показатели
        $stats = RecipeAnalytics::where('recipe_id', $recipe->id)
            ->selectRaw('
                AVG(efficiency_score) as avg_efficiency,
                AVG(avg_ph_deviation) as avg_ph_deviation_overall,
                AVG(avg_ec_deviation) as avg_ec_deviation_overall,
                AVG(alerts_count) as avg_alerts_count,
                AVG(total_duration_hours) as avg_duration_hours,
                COUNT(*) as total_runs
            ')
            ->first();

        return response()->json([
            'status' => 'ok',
            'data' => $analytics,
            'stats' => $stats,
        ]);
    }

    /**
     * Получить историю урожаев зоны
     */
    public function zoneHarvests(Request $request, Zone $zone)
    {
        // Eager loading для предотвращения N+1 запросов
        $query = Harvest::where('zone_id', $zone->id)
            ->with(['recipe:id,name']); // Загружаем рецепт

        if ($request->filled('recipe_id')) {
            $query->where('recipe_id', $request->integer('recipe_id'));
        }

        if ($request->filled('start_date')) {
            $query->where('harvest_date', '>=', $request->date('start_date'));
        }

        if ($request->filled('end_date')) {
            $query->where('harvest_date', '<=', $request->date('end_date'));
        }

        $harvests = $query->latest('harvest_date')->paginate(25);

        // Статистика по урожаям
        $stats = Harvest::where('zone_id', $zone->id)
            ->selectRaw('
                SUM(yield_weight_kg) as total_weight_kg,
                AVG(yield_weight_kg) as avg_weight_kg,
                SUM(yield_count) as total_count,
                AVG(quality_score) as avg_quality_score,
                COUNT(*) as total_harvests
            ')
            ->first();

        return response()->json([
            'status' => 'ok',
            'data' => $harvests,
            'stats' => $stats,
        ]);
    }

    /**
     * Сравнение эффективности рецептов
     */
    public function compareRecipes(Request $request)
    {
        $recipeIds = $request->validate([
            'recipe_ids' => ['required', 'array', 'min:2'],
            'recipe_ids.*' => ['integer', 'exists:recipes,id'],
        ])['recipe_ids'];

        $startDate = $request->date('start_date');
        $endDate = $request->date('end_date');
        $zoneId = $request->integer('zone_id');

        $query = RecipeAnalytics::whereIn('recipe_id', $recipeIds)
            ->with(['recipe', 'zone']);

        if ($startDate) {
            $query->where('start_date', '>=', $startDate);
        }

        if ($endDate) {
            $query->where('end_date', '<=', $endDate);
        }

        if ($zoneId) {
            $query->where('zone_id', $zoneId);
        }

        $comparison = RecipeAnalytics::whereIn('recipe_id', $recipeIds)
            ->when($startDate, fn($q) => $q->where('start_date', '>=', $startDate))
            ->when($endDate, fn($q) => $q->where('end_date', '<=', $endDate))
            ->when($zoneId, fn($q) => $q->where('zone_id', $zoneId))
            ->selectRaw('
                recipe_id,
                AVG(efficiency_score) as avg_efficiency,
                AVG(avg_ph_deviation) as avg_ph_deviation,
                AVG(avg_ec_deviation) as avg_ec_deviation,
                AVG(alerts_count) as avg_alerts_count,
                AVG(total_duration_hours) as avg_duration_hours,
                COUNT(*) as runs_count
            ')
            ->groupBy('recipe_id')
            ->get();

        // Добавить информацию о рецептах
        $recipes = Recipe::whereIn('id', $recipeIds)->get()->keyBy('id');
        $comparison = $comparison->map(function ($item) use ($recipes) {
            $item->recipe = $recipes->get($item->recipe_id);
            return $item;
        });

        return response()->json([
            'status' => 'ok',
            'data' => $comparison,
        ]);
    }

    /**
     * Создать запись об урожае
     */
    public function storeHarvest(Request $request)
    {
        $data = $request->validate([
            'zone_id' => ['required', 'integer', 'exists:zones,id'],
            'recipe_id' => ['nullable', 'integer', 'exists:recipes,id'],
            'harvest_date' => ['required', 'date'],
            'yield_weight_kg' => ['nullable', 'numeric', 'min:0'],
            'yield_count' => ['nullable', 'integer', 'min:0'],
            'quality_score' => ['nullable', 'numeric', 'between:0,10'],
            'notes' => ['nullable', 'array'],
        ]);

        $harvest = Harvest::create($data);

        // Если есть recipe_id, можно обновить аналитику
        if ($harvest->recipe_id) {
            try {
                // Проверяем, есть ли активный recipe instance для зоны
                $zone = Zone::find($harvest->zone_id);
                if ($zone && $zone->recipeInstance) {
                    \App\Jobs\CalculateRecipeAnalyticsJob::dispatch($harvest->zone_id);
                }
            } catch (\Exception $e) {
                // В тестах Job может не работать - игнорируем ошибку
                if (!app()->environment('testing')) {
                    \Log::warning('Failed to dispatch CalculateRecipeAnalyticsJob', [
                        'zone_id' => $harvest->zone_id,
                        'error' => $e->getMessage(),
                    ]);
                }
            }
        }

        return response()->json([
            'status' => 'ok',
            'data' => $harvest,
        ], Response::HTTP_CREATED);
    }
}

