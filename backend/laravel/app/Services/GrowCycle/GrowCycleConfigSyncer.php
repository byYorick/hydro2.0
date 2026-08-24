<?php

declare(strict_types=1);

namespace App\Services\GrowCycle;

use App\Models\GrowCycle;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\ZoneService;

/**
 * Синхронизирует automation config documents (cycle.start_snapshot, phase_overrides,
 * config_overrides) при создании/изменении цикла. Compiler кладёт их в
 * automation_effective_bundles.
 *
 * cycle.start_snapshot пишется с первой фазы цикла (orderBy phase_index), не с
 * current_phase_id. Химические ключи (ph_target/ec_target и min/max) в документ не входят: SoT
 * агрохимии — колонки grow_cycle_phases текущей фазы. AE3 runtime читает pH/EC
 * из SQL JOIN (PgZoneSnapshotReadModel), не из cycle.start_snapshot.phase.
 */
class GrowCycleConfigSyncer
{
    public function __construct(
        private readonly AutomationConfigDocumentService $documents,
        private readonly ZoneService $zoneService,
    ) {}

    /**
     * @param  array<string, mixed>  $data
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
