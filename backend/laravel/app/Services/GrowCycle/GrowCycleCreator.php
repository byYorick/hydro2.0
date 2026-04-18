<?php

declare(strict_types=1);

namespace App\Services\GrowCycle;

use App\Enums\GrowCycleStatus;
use App\Events\GrowCycleUpdated;
use App\Models\GrowCycle;
use App\Models\GrowCyclePhase;
use App\Models\GrowCycleTransition;
use App\Models\RecipeRevision;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Services\GrowCycle\Support\CorrelationIdResolver;
use App\Services\GrowCycle\Support\PhaseSnapshotCreator;
use Carbon\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Создаёт grow cycle в статусе PLANNED из опубликованной recipe revision.
 * Опционально сразу запускает через {@see GrowCycleLifecycleService::startCycle}.
 */
class GrowCycleCreator
{
    public function __construct(
        private readonly PhaseSnapshotCreator $snapshotCreator,
        private readonly CorrelationIdResolver $correlation,
        private readonly GrowCycleLifecycleService $lifecycle,
    ) {}

    /**
     * @param array<string, mixed> $data
     */
    public function createCycle(
        Zone $zone,
        RecipeRevision $revision,
        int $plantId,
        array $data = [],
        ?int $userId = null,
    ): GrowCycle {
        $activeCycle = $zone->activeGrowCycle;
        if ($activeCycle) {
            throw new \DomainException('Zone already has an active cycle. Please pause, harvest, or abort it first.');
        }

        if ($revision->status !== 'PUBLISHED') {
            throw new \DomainException('Only PUBLISHED revisions can be used for new cycles');
        }

        $firstPhase = $revision->phases()->orderBy('phase_index')->first();
        if (! $firstPhase) {
            throw new \DomainException('Revision has no phases');
        }

        $plantingAt = isset($data['planting_at']) && $data['planting_at']
            ? Carbon::parse($data['planting_at'])
            : now();
        $startImmediately = (bool) ($data['start_immediately'] ?? false);

        $createdCycle = DB::transaction(function () use ($zone, $revision, $firstPhase, $plantId, $data, $userId, $plantingAt) {
            $settings = is_array($data['settings'] ?? null) ? $data['settings'] : [];

            $irrigation = is_array($data['irrigation'] ?? null) ? $data['irrigation'] : [];
            if (! empty($irrigation)) {
                $settings['irrigation'] = [
                    'system_type' => $irrigation['system_type'] ?? 'drip',
                    'interval_minutes' => (int) ($irrigation['interval_minutes'] ?? 30),
                    'duration_seconds' => (int) ($irrigation['duration_seconds'] ?? 120),
                    'clean_tank_fill_l' => (int) ($irrigation['clean_tank_fill_l'] ?? 300),
                    'nutrient_tank_target_l' => (int) ($irrigation['nutrient_tank_target_l'] ?? 280),
                ];
                if (array_key_exists('irrigation_batch_l', $irrigation) && $irrigation['irrigation_batch_l'] !== null) {
                    $settings['irrigation']['irrigation_batch_l'] = (float) $irrigation['irrigation_batch_l'];
                }
            }

            $cycle = GrowCycle::create([
                'greenhouse_id' => $zone->greenhouse_id,
                'zone_id' => $zone->id,
                'plant_id' => $plantId,
                'recipe_revision_id' => $revision->id,
                'current_phase_id' => null,
                'current_step_id' => null,
                'status' => GrowCycleStatus::PLANNED,
                'planting_at' => $plantingAt,
                'phase_started_at' => null,
                'batch_label' => $data['batch_label'] ?? null,
                'notes' => $data['notes'] ?? null,
                'settings' => ! empty($settings) ? $settings : null,
                'started_at' => null,
            ]);

            $firstPhaseSnapshot = $this->snapshotCreator->create($cycle, $firstPhase, null);
            $cycle->update(['current_phase_id' => $firstPhaseSnapshot->id]);

            GrowCycleTransition::create([
                'grow_cycle_id' => $cycle->id,
                'from_phase_id' => null,
                'to_phase_id' => $firstPhase->id,
                'trigger_type' => 'CYCLE_CREATED',
                'triggered_by' => $userId,
                'comment' => 'Cycle created',
            ]);

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_CREATED',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $cycle->id,
                'payload_json' => [
                    'cycle_id' => $cycle->id,
                    'recipe_revision_id' => $revision->id,
                    'plant_id' => $plantId,
                    'user_id' => $userId,
                    'source' => 'web',
                    'correlation_id' => $this->correlation->resolve(),
                ],
            ]);

            broadcast(new GrowCycleUpdated($cycle->fresh(), 'CREATED'));

            Log::info('Grow cycle created', [
                'cycle_id' => $cycle->id,
                'zone_id' => $zone->id,
                'recipe_revision_id' => $revision->id,
            ]);

            return $cycle->load('recipeRevision', 'currentPhase', 'plant');
        });

        if (! $startImmediately) {
            return $createdCycle;
        }

        return $this->lifecycle->startCycle($createdCycle->fresh(), $plantingAt->copy());
    }
}
