<?php

namespace App\Http\Controllers;

use App\Models\Zone;
use App\Services\AiService;
use App\Services\PredictionService;
use Illuminate\Http\Request;
use Illuminate\Http\JsonResponse;

class AiController extends Controller
{
    public function __construct(
        private AiService $aiService,
        private PredictionService $predictionService
    ) {
    }

    /**
     * POST /api/ai/predict
     * Генерация прогноза параметра для зоны
     */
    public function predict(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'zone_id' => ['required', 'integer', 'exists:zones,id'],
            'metric_type' => ['required', 'string', 'in:PH,EC,TEMPERATURE,HUMIDITY'],
            'horizon_minutes' => ['nullable', 'integer', 'min:1', 'max:1440'], // до 24 часов
        ]);

        $zone = Zone::findOrFail($validated['zone_id']);
        $horizonMinutes = $validated['horizon_minutes'] ?? 60;

        $prediction = $this->predictionService->predict(
            $zone,
            $validated['metric_type'],
            $horizonMinutes
        );

        if (!$prediction) {
            return response()->json([
                'status' => 'error',
                'message' => 'Failed to generate prediction. Not enough data.',
            ], 422);
        }

        return response()->json([
            'status' => 'ok',
            'data' => [
                'predicted_value' => $prediction->predicted_value,
                'confidence' => $prediction->confidence,
                'predicted_at' => $prediction->predicted_at->toIso8601String(),
                'horizon_minutes' => $prediction->horizon_minutes,
            ],
        ]);
    }

    /**
     * POST /api/ai/explain_zone
     * Объяснение текущего состояния зоны
     */
    public function explainZone(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'zone_id' => ['required', 'integer', 'exists:zones,id'],
        ]);

        $zone = Zone::findOrFail($validated['zone_id']);

        // Получаем данные через AiService
        $telemetry = $this->aiService->getZoneTelemetry($zone);
        $predictions = $this->aiService->getZonePredictions($zone);
        $targets = $this->aiService->getZoneTargets($zone);

        // Генерируем объяснения
        $explanations = $this->aiService->explainZoneState($zone, $telemetry, $predictions, $targets);
        $forecasts = $predictions->map(fn ($prediction) => [
            'metric_type' => $prediction->metric_type,
            'predicted_value' => $prediction->predicted_value,
            'confidence' => $prediction->confidence,
            'predicted_at' => $prediction->predicted_at?->toIso8601String(),
            'horizon_minutes' => $prediction->horizon_minutes,
        ])->values();

        return response()->json([
            'status' => 'ok',
            'data' => [
                'zone_id' => $zone->id,
                'zone_name' => $zone->name,
                'status' => $zone->status,
                'explanations' => $explanations,
                'forecasts' => $forecasts,
                'telemetry' => $telemetry->map(fn($t) => [
                    'metric_type' => $t->metric_type,
                    'value' => $t->value,
                    'updated_at' => $t->updated_at?->toIso8601String(),
                ])->values(),
            ],
        ]);
    }

    /**
     * POST /api/ai/recommend
     * Получение рекомендаций для зоны
     */
    public function recommend(Request $request): JsonResponse
    {
        $validated = $request->validate([
            'zone_id' => ['required', 'integer', 'exists:zones,id'],
            'context' => ['nullable', 'string'], // ph_high, ph_low, ec_high, ec_low
        ]);

        $zone = Zone::findOrFail($validated['zone_id']);

        // Получаем данные через AiService
        $telemetry = $this->aiService->getZoneTelemetry($zone);
        $targets = $this->aiService->getZoneTargets($zone);

        // Генерируем рекомендации
        $recommendations = $this->aiService->generateRecommendations($zone, $telemetry, $targets, $validated['context'] ?? null);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'zone_id' => $zone->id,
                'recommendations' => $recommendations,
            ],
        ]);
    }

    /**
     * POST /api/ai/diagnostics
     * Полный диагностический отчёт по теплице
     */
    public function diagnostics(Request $request): JsonResponse
    {
        $report = $this->aiService->getSystemDiagnostics();

        return response()->json([
            'status' => 'ok',
            'data' => $report,
        ]);
    }
}
