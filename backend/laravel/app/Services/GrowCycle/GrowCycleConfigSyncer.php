<?php

declare(strict_types=1);

namespace App\Services\GrowCycle;

use App\Models\GrowCycle;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\ZoneService;

/**
 * Синхронизирует automation config documents (cycle_start_snapshot, phase_overrides,
 * config_overrides) при создании/изменении цикла — AE3 читает эти документы через
 * effective bundle.
 */
class GrowCycleConfigSyncer
{
    public function __construct(
        private readonly AutomationConfigDocumentService $documents,
        private readonly ZoneService $zoneService,
    ) {}

    /**
     * @param array<string, mixed> $data
     */
    public function syncCycleConfigDocuments(GrowCycle $cycle, array $data = [], ?int $userId = null): void
    {
        $zone = $cycle->zone;
        if ($zone === null) {
            $zone = Zone::query()->find($cycle->zone_id);
        }
        if ($zone !== null) {
            $this->zoneService->ensureAe3AutomationBootstrap($zone);
        }

        $firstPhase = $cycle->phases()->orderBy('phase_index')->first();

        $phasePayload = $firstPhase ? [
            'phase_id' => $firstPhase->recipe_revision_phase_id,
            'phase_index' => $firstPhase->phase_index,
            'name' => $firstPhase->name,
            'ph_target' => $firstPhase->ph_target,
            'ph_min' => $firstPhase->ph_min,
            'ph_max' => $firstPhase->ph_max,
            'ec_target' => $firstPhase->ec_target,
            'ec_min' => $firstPhase->ec_min,
            'ec_max' => $firstPhase->ec_max,
            'irrigation_mode' => $firstPhase->irrigation_mode,
            'irrigation_interval_sec' => $firstPhase->irrigation_interval_sec,
            'irrigation_duration_sec' => $firstPhase->irrigation_duration_sec,
            'extensions' => is_array($firstPhase->extensions) ? $firstPhase->extensions : [],
        ] : [];

        $documents = [
            AutomationConfigRegistry::NAMESPACE_CYCLE_START_SNAPSHOT => [
                'cycle_id' => (int) $cycle->id,
                'zone_id' => (int) $cycle->zone_id,
                'recipe_revision_id' => (int) $cycle->recipe_revision_id,
                'phase' => $phasePayload,
            ],
            AutomationConfigRegistry::NAMESPACE_CYCLE_PHASE_OVERRIDES => [],
        ];

        $configOverrides = $data['config_overrides'] ?? null;
        if (is_array($configOverrides) && $configOverrides !== []) {
            $documents[AutomationConfigRegistry::NAMESPACE_CYCLE_CONFIG_OVERRIDES] = $configOverrides;
        }

        $this->documents->upsertCycleDocuments((int) $cycle->id, $documents, $userId);
    }
}
