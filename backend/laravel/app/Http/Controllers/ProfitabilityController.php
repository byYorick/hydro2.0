<?php

namespace App\Http\Controllers;

use App\Models\Plant;
use App\Services\Profitability\ProfitabilityCalculator;
use Carbon\Carbon;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ProfitabilityController extends Controller
{
    public function __construct(private readonly ProfitabilityCalculator $profitability)
    {
    }

    public function calculate(Request $request): JsonResponse
    {
        $data = $request->validate([
            'plant_ids' => ['required', 'array'],
            'plant_ids.*' => ['integer', 'exists:plants,id'],
            'date' => ['nullable', 'date'],
        ]);

        // Получаем доступные зоны для пользователя
        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);
        
        $at = isset($data['date']) ? Carbon::parse($data['date']) : null;

        // Загружаем растения с зонами и фильтруем по доступным зонам
        $plants = Plant::query()
            ->whereIn('id', $data['plant_ids'])
            ->with('zones:id,greenhouse_id')
            ->get()
            ->filter(function (Plant $plant) use ($user, $accessibleZoneIds) {
                // Растения связаны с зонами через many-to-many
                // Проверяем, есть ли хотя бы одна доступная зона у растения
                $plantZoneIds = $plant->zones->pluck('id')->toArray();
                $hasAccessibleZone = !empty(array_intersect($plantZoneIds, $accessibleZoneIds));
                
                if ($hasAccessibleZone) {
                    return true;
                }
                
                // Если растение не привязано ни к одной доступной зоне, разрешаем доступ только админам
                return $user->isAdmin();
            });

        $results = $plants->map(fn (Plant $plant) => $this->profitability->calculatePlant($plant, $at))
            ->values();

        return response()->json([
            'status' => 'ok',
            'data' => $results,
        ], 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }

    public function plant(Request $request, Plant $plant): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Загружаем зоны растения
        $plant->load('zones');
        
        // Получаем доступные зоны для пользователя
        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);
        
        // Проверяем доступ к растению через зоны
        $plantZoneIds = $plant->zones->pluck('id')->toArray();
        $hasAccessibleZone = !empty(array_intersect($plantZoneIds, $accessibleZoneIds));
        
        if (!$hasAccessibleZone) {
            // Если растение не привязано ни к одной доступной зоне, разрешаем доступ только админам
            if (!$user->isAdmin()) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Forbidden: Access denied to this plant',
                ], 403);
            }
        }
        
        $request->validate([
            'date' => ['nullable', 'date'],
        ]);

        $at = $request->filled('date') ? Carbon::parse($request->input('date')) : null;

        return response()->json([
            'status' => 'ok',
            'data' => $this->profitability->calculatePlant($plant, $at),
        ], 200, [], JSON_PRESERVE_ZERO_FRACTION);
    }
}
