<?php

namespace App\Services;

use App\Models\Zone;
use App\Models\TelemetryLast;
use App\Models\ParameterPrediction;
use App\Services\PredictionService;
use App\Services\EffectiveTargetsService;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Log;
use Carbon\Carbon;

class AiService
{
    public function __construct(
        private PredictionService $predictionService,
        private EffectiveTargetsService $effectiveTargetsService
    ) {}

    /**
     * Получить телеметрию для зоны
     */
    public function getZoneTelemetry(Zone $zone): Collection
    {
        return TelemetryLast::query()
            ->join('sensors', 'telemetry_last.sensor_id', '=', 'sensors.id')
            ->where('sensors.zone_id', $zone->id)
            ->whereNotNull('sensors.zone_id')
            ->select([
                'sensors.type as metric_type',
                'telemetry_last.last_value as value',
                'telemetry_last.last_ts as timestamp',
                'telemetry_last.updated_at'
            ])
            ->get()
            ->keyBy('metric_type');
    }

    /**
     * Получить последние прогнозы для зоны
     */
    public function getZonePredictions(Zone $zone): Collection
    {
        return ParameterPrediction::query()
            ->where('zone_id', $zone->id)
            ->where('predicted_at', '>', Carbon::now())
            ->orderBy('created_at', 'desc')
            ->get()
            ->groupBy('metric_type')
            ->map(fn($group) => $group->first());
    }

    /**
     * Получить effective targets для зоны
     */
    public function getZoneTargets(Zone $zone): ?array
    {
        $targets = null;
        $activeCycle = $zone->activeGrowCycle;

        if ($activeCycle) {
            try {
                $effectiveTargets = $this->effectiveTargetsService->getEffectiveTargets($activeCycle->id);
                $targets = $effectiveTargets['targets'] ?? [];
            } catch (\Exception $e) {
                Log::warning('Failed to get effective targets for AI analysis', [
                    'zone_id' => $zone->id,
                    'cycle_id' => $activeCycle->id,
                    'error' => $e->getMessage(),
                ]);
            }
        }

        return $targets;
    }

    /**
     * Генерировать объяснение состояния зоны
     */
    public function explainZoneState(Zone $zone, Collection $telemetry, Collection $predictions, ?array $targets): array
    {
        $explanations = [];

        // Анализ телеметрии
        if ($telemetry->has('ph') && $targets && isset($targets['ph'])) {
            $phCurrent = $telemetry->get('ph')->value;
            $phTarget = $targets['ph']['target'] ?? null;

            if ($phTarget !== null) {
                $phDiff = $phCurrent - $phTarget;
                if (abs($phDiff) > 0.2) {
                    $explanations[] = [
                        'metric' => 'ph',
                        'status' => abs($phDiff) > 0.5 ? 'critical' : 'warning',
                        'message' => sprintf('pH %.2f (цель: %.2f)', $phCurrent, $phTarget),
                        'deviation' => $phDiff,
                    ];
                } else {
                    $explanations[] = [
                        'metric' => 'ph',
                        'status' => 'good',
                        'message' => sprintf('pH %.2f в норме', $phCurrent),
                        'deviation' => $phDiff,
                    ];
                }
            }
        }

        // Анализ других метрик аналогично...

        return $explanations;
    }

    /**
     * Генерировать рекомендации для зоны
     */
    public function generateRecommendations(Zone $zone, Collection $telemetry, ?array $targets, ?string $context): array
    {
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
                        'message' => sprintf('pH слишком низкий (%.2f, цель %.2f). Добавьте щелочь для повышения pH.', $phCurrent, $phTarget),
                    ];
                }
            }
        }

        // Рекомендации по EC аналогично...

        return $recommendations;
    }

    /**
     * Получить диагностическую информацию по всем зонам
     */
    public function getSystemDiagnostics(): array
    {
        $zones = Zone::query()
            ->whereIn('status', ['online', 'warning', 'RUNNING'])
            ->with(['activeGrowCycle'])
            ->get();

        $report = [
            'total_zones' => $zones->count(),
            'zones' => [],
        ];

        foreach ($zones as $zone) {
            $telemetry = $this->getZoneTelemetry($zone);
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

        return $report;
    }
}
