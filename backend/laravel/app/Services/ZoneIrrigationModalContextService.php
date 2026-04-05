<?php

namespace App\Services;

use App\Models\GrowCyclePhase;
use App\Models\Zone;
use Illuminate\Support\Facades\Log;
use Throwable;

/**
 * Цели pH/EC/темп для карточек списков + контекст модалки полива (дефолтная длительность, сводка коррекции).
 */
final class ZoneIrrigationModalContextService
{
    public function __construct(
        private readonly EffectiveTargetsService $effectiveTargets,
        private readonly IrrigationCorrectionSummaryPresenter $correctionSummary,
    ) {}

    /**
     * @return array{
     *   targets: array{ph: array{min: float|null, max: float|null}|null, ec: array{min: float|null, max: float|null}|null, temperature: array{min: float|null, max: float|null}|null},
     *   current_phase_targets: array<string, mixed>|null,
     *   irrigation_correction_summary: array<string, mixed>|null
     * }
     */
    public function buildForZone(Zone $zone): array
    {
        $cycle = $zone->activeGrowCycle;
        if (! $cycle) {
            return [
                'targets' => ['ph' => null, 'ec' => null, 'temperature' => null],
                'current_phase_targets' => null,
                'irrigation_correction_summary' => null,
            ];
        }

        $phase = $cycle->currentPhase;
        $currentPhaseTargets = $this->irrigationDurationHintFromGrowCyclePhase($phase);

        try {
            $effective = $this->effectiveTargets->getEffectiveTargets($cycle->id);
            $targets = $effective['targets'] ?? [];
            $climate = is_array($targets['climate_request'] ?? null) ? $targets['climate_request'] : [];
            $tempTarget = $climate['temp_air_target'] ?? null;
            $displayTargets = [
                'ph' => isset($targets['ph']) && is_array($targets['ph'])
                    ? [
                        'min' => isset($targets['ph']['min']) ? (float) $targets['ph']['min'] : null,
                        'max' => isset($targets['ph']['max']) ? (float) $targets['ph']['max'] : null,
                    ]
                    : null,
                'ec' => isset($targets['ec']) && is_array($targets['ec'])
                    ? [
                        'min' => isset($targets['ec']['min']) ? (float) $targets['ec']['min'] : null,
                        'max' => isset($targets['ec']['max']) ? (float) $targets['ec']['max'] : null,
                    ]
                    : null,
                'temperature' => $tempTarget !== null
                    ? ['min' => (float) $tempTarget - 2, 'max' => (float) $tempTarget + 2]
                    : null,
            ];
            $irrigation = is_array($targets['irrigation'] ?? null) ? $targets['irrigation'] : null;
            $summary = $this->correctionSummary->summarize((int) $zone->id, $irrigation);

            return [
                'targets' => $displayTargets,
                'current_phase_targets' => $currentPhaseTargets,
                'irrigation_correction_summary' => $summary,
            ];
        } catch (Throwable $e) {
            Log::debug('ZoneIrrigationModalContext: effective targets failed', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);

            return [
                'targets' => ['ph' => null, 'ec' => null, 'temperature' => null],
                'current_phase_targets' => $currentPhaseTargets,
                'irrigation_correction_summary' => $this->correctionSummary->summarize((int) $zone->id, null),
            ];
        }
    }

    /**
     * @return array<string, mixed>|null
     */
    private function irrigationDurationHintFromGrowCyclePhase(?GrowCyclePhase $phase): ?array
    {
        if ($phase === null || $phase->irrigation_duration_sec === null) {
            return null;
        }

        return [
            'irrigation_duration_sec' => (int) $phase->irrigation_duration_sec,
        ];
    }
}
