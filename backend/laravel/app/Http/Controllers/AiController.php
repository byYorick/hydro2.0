<?php

namespace App\Http\Controllers;

use App\Models\Zone;
use App\Models\TelemetryLast;
use App\Models\ParameterPrediction;
use App\Services\PredictionService;
use App\Services\EffectiveTargetsService;
use Illuminate\Http\Request;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Carbon\Carbon;

class AiController extends Controller
{
    public function __construct(
        private PredictionService $predictionService,
        private EffectiveTargetsService $effectiveTargetsService
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
            'metric_type' => ['required', 'string', 'in:ph,ec,temp_air,humidity_air'],
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

        // Получаем текущую телеметрию
        $telemetry = TelemetryLast::query()
            ->where('zone_id', $zone->id)
            ->get()
            ->keyBy('metric_type');

        // Получаем последние прогнозы
        $predictions = ParameterPrediction::query()
            ->where('zone_id', $zone->id)
            ->where('predicted_at', '>', Carbon::now())
            ->orderBy('created_at', 'desc')
            ->get()
            ->groupBy('metric_type')
            ->map(fn($group) => $group->first());

        // Получаем targets из активного цикла выращивания (новая модель)
        $targets = null;
        $activeCycle = $zone->activeGrowCycle;
        if ($activeCycle) {
            try {
                $effectiveTargets = $this->effectiveTargetsService->getEffectiveTargets($activeCycle->id);
                $targets = $effectiveTargets['targets'] ?? [];
            } catch (\Exception $e) {
                Log::warning('Failed to get effective targets for AI explain', [
                    'zone_id' => $zone->id,
                    'cycle_id' => $activeCycle->id,
                    'error' => $e->getMessage(),
                ]);
            }
        }

        // Простой анализ состояния (без LLM пока)
        $explanations = [];
        
        // Анализ pH
        if ($telemetry->has('ph') && $targets && isset($targets['ph']['target'])) {
            $phCurrent = $telemetry->get('ph')->value;
            $phTarget = $targets['ph']['target'];
            $phDiff = abs($phCurrent - $phTarget);
            
            if ($phDiff > 0.3) {
                $explanations[] = sprintf(
                    'pH отклоняется от цели: текущий %.2f, цель %.2f (разница %.2f). %s',
                    $phCurrent,
                    $phTarget,
                    $phDiff,
                    $phCurrent > $phTarget ? 'Рекомендуется добавить кислоту.' : 'Рекомендуется добавить щёлочь.'
                );
            } else {
                $explanations[] = sprintf('pH в норме: %.2f (цель %.2f)', $phCurrent, $phTarget);
            }
        }

        // Анализ EC
        if ($telemetry->has('ec') && $targets && isset($targets['ec']['target'])) {
            $ecCurrent = $telemetry->get('ec')->value;
            $ecTarget = $targets['ec']['target'];
            $ecDiff = abs($ecCurrent - $ecTarget);
            
            if ($ecDiff > 0.2) {
                $explanations[] = sprintf(
                    'EC отклоняется от цели: текущий %.2f, цель %.2f (разница %.2f). %s',
                    $ecCurrent,
                    $ecTarget,
                    $ecDiff,
                    $ecCurrent > $ecTarget ? 'Рекомендуется разбавить раствор.' : 'Рекомендуется добавить питательные вещества.'
                );
            } else {
                $explanations[] = sprintf('EC в норме: %.2f (цель %.2f)', $ecCurrent, $ecTarget);
            }
        }

        // Прогнозы
        $forecasts = [];
        foreach ($predictions as $metricType => $prediction) {
            $forecasts[] = sprintf(
                'Прогноз %s через %d минут: %.2f (уверенность %.0f%%)',
                $metricType,
                $prediction->horizon_minutes,
                $prediction->predicted_value,
                $prediction->confidence * 100
            );
        }

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

        // Получаем текущую телеметрию
        $telemetry = TelemetryLast::query()
            ->where('zone_id', $zone->id)
            ->get()
            ->keyBy('metric_type');

        // Получаем targets из активного цикла выращивания (новая модель)
        $targets = null;
        $activeCycle = $zone->activeGrowCycle;
        if ($activeCycle) {
            try {
                $effectiveTargets = $this->effectiveTargetsService->getEffectiveTargets($activeCycle->id);
                $targets = $effectiveTargets['targets'] ?? [];
            } catch (\Exception $e) {
                Log::warning('Failed to get effective targets for AI recommend', [
                    'zone_id' => $zone->id,
                    'cycle_id' => $activeCycle->id,
                    'error' => $e->getMessage(),
                ]);
            }
        }

        $recommendations = [];

        // Рекомендации по pH
        if ($telemetry->has('ph') && $targets && isset($targets['ph']['target'])) {
            $phCurrent = $telemetry->get('ph')->value;
            $phTarget = $targets['ph']['target'];
            $phDiff = $phCurrent - $phTarget;

            if (abs($phDiff) > 0.2) {
                if ($phCurrent > $phTarget) {
                    $recommendations[] = [
                        'type' => 'ph_correction',
                        'priority' => abs($phDiff) > 0.5 ? 'high' : 'medium',
                        'action' => 'add_acid',
                        'message' => sprintf('pH слишком высокий (%.2f, цель %.2f). Добавьте кислоту для снижения pH.', $phCurrent, $phTarget),
                    ];
                } else {
                    $recommendations[] = [
                        'type' => 'ph_correction',
                        'priority' => abs($phDiff) > 0.5 ? 'high' : 'medium',
                        'action' => 'add_base',
                        'message' => sprintf('pH слишком низкий (%.2f, цель %.2f). Добавьте щёлочь для повышения pH.', $phCurrent, $phTarget),
                    ];
                }
            }
        }

        // Рекомендации по EC
        if ($telemetry->has('ec') && $targets && isset($targets['ec']['target'])) {
            $ecCurrent = $telemetry->get('ec')->value;
            $ecTarget = $targets['ec']['target'];
            $ecDiff = $ecCurrent - $ecTarget;

            if (abs($ecDiff) > 0.2) {
                if ($ecCurrent > $ecTarget) {
                    $recommendations[] = [
                        'type' => 'ec_correction',
                        'priority' => abs($ecDiff) > 0.5 ? 'high' : 'medium',
                        'action' => 'dilute',
                        'message' => sprintf('EC слишком высокий (%.2f, цель %.2f). Разбавьте раствор чистой водой.', $ecCurrent, $ecTarget),
                    ];
                } else {
                    $recommendations[] = [
                        'type' => 'ec_correction',
                        'priority' => abs($ecDiff) > 0.5 ? 'high' : 'medium',
                        'action' => 'add_nutrients',
                        'message' => sprintf('EC слишком низкий (%.2f, цель %.2f). Добавьте питательные вещества.', $ecCurrent, $ecTarget),
                    ];
                }
            }
        }

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
        // Получаем все активные зоны
        $zones = Zone::query()
            ->whereIn('status', ['online', 'warning', 'RUNNING'])
            ->with(['activeGrowCycle'])
            ->get();

        $report = [
            'total_zones' => $zones->count(),
            'zones' => [],
        ];

        foreach ($zones as $zone) {
            $telemetry = TelemetryLast::query()
                ->where('zone_id', $zone->id)
                ->get()
                ->keyBy('metric_type');

            $issues = [];
            
            // Проверка наличия телеметрии
            if ($telemetry->isEmpty()) {
                $issues[] = 'Нет данных телеметрии';
            }

            // Проверка давности данных
            foreach ($telemetry as $metric) {
                if ($metric->updated_at && $metric->updated_at->lt(Carbon::now()->subHours(1))) {
                    $issues[] = sprintf('Данные %s устарели (последнее обновление: %s)', $metric->metric_type, $metric->updated_at->diffForHumans());
                }
            }

            $report['zones'][] = [
                'zone_id' => $zone->id,
                'zone_name' => $zone->name,
                'status' => $zone->status,
                'issues' => $issues,
                'has_active_cycle' => $zone->activeGrowCycle !== null,
            ];
        }

        return response()->json([
            'status' => 'ok',
            'data' => $report,
        ]);
    }
}
