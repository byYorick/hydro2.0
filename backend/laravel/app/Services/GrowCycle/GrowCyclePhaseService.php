<?php

declare(strict_types=1);

namespace App\Services\GrowCycle;

use App\Enums\GrowCycleStatus;
use App\Events\GrowCycleUpdated;
use App\Models\GrowCycle;
use App\Models\GrowCycleTransition;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\ZoneEvent;
use App\Services\AutomationConfigCompiler;
use App\Services\AutomationConfigRegistry;
use App\Services\GrowCycle\Support\CorrelationIdResolver;
use App\Services\GrowCycle\Support\PhaseSnapshotCreator;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Переходы между phases и stages: advancePhase, advanceStage, setPhase, changeRecipeRevision.
 * Каждый переход создаёт снапшот, логирует transition + zone event, пересчитывает effective
 * bundle (AE3 → актуальные targets) и отменяет stale pending intents предыдущей фазы.
 */
class GrowCyclePhaseService
{
    public function __construct(
        private readonly AutomationConfigCompiler $automationConfigCompiler,
        private readonly GrowCycleStageTimelineService $timeline,
        private readonly GrowCycleAutomationCanceller $canceller,
        private readonly PhaseSnapshotCreator $snapshotCreator,
        private readonly CorrelationIdResolver $correlation,
    ) {}

    public function advanceStage(GrowCycle $cycle, ?string $targetStageCode = null): GrowCycle
    {
        if ($cycle->status !== GrowCycleStatus::RUNNING) {
            throw new \DomainException('Cycle must be RUNNING to advance stage');
        }

        return DB::transaction(function () use ($cycle, $targetStageCode) {
            $revision = $cycle->recipeRevision;
            if (! $revision) {
                throw new \DomainException('Cycle must have a recipe revision to advance stage');
            }

            $timeline = $this->timeline->buildStageTimeline($revision);
            $segments = $timeline['segments'];

            if (empty($segments)) {
                throw new \DomainException('No stages available for this recipe revision');
            }

            if ($targetStageCode) {
                $targetIndex = collect($segments)->search(
                    fn (array $segment) => $segment['code'] === $targetStageCode
                );
                if ($targetIndex === false) {
                    throw new \DomainException("Stage {$targetStageCode} not found in recipe revision");
                }
            } else {
                $currentPhaseIndex = $cycle->currentPhase?->phase_index;
                $currentIndex = null;
                if ($currentPhaseIndex !== null) {
                    foreach ($segments as $index => $segment) {
                        if (in_array($currentPhaseIndex, $segment['phase_indices'], true)) {
                            $currentIndex = $index;
                            break;
                        }
                    }
                }
                $targetIndex = $currentIndex === null ? 0 : $currentIndex + 1;
                if (! isset($segments[$targetIndex])) {
                    throw new \DomainException('No next stage available');
                }
            }

            $targetSegment = $segments[$targetIndex];
            $oldStageCode = $cycle->current_stage_code;

            $cycle->update([
                'current_stage_code' => $targetSegment['code'],
                'current_stage_started_at' => now(),
            ]);
            $cycle->refresh();

            GrowCycleUpdated::dispatch($cycle, 'STAGE_ADVANCED');

            Log::info('Grow cycle stage advanced', [
                'cycle_id' => $cycle->id,
                'old_stage_code' => $oldStageCode,
                'new_stage_code' => $targetSegment['code'],
            ]);

            return $cycle->fresh();
        });
    }

    /**
     * `$userId` может быть null для системных переходов (cron phases:auto-advance).
     */
    public function advancePhase(GrowCycle $cycle, ?int $userId): GrowCycle
    {
        $revision = $cycle->recipeRevision;
        if (! $revision) {
            throw new \DomainException('Cycle has no recipe revision');
        }

        $currentPhase = $cycle->currentPhase;
        if (! $currentPhase) {
            throw new \DomainException('Cycle has no current phase');
        }

        $currentPhaseTemplate = $currentPhase->recipeRevisionPhase;
        if (! $currentPhaseTemplate) {
            throw new \DomainException('Current phase has no template reference');
        }

        $nextPhaseTemplate = $revision->phases()
            ->where('phase_index', '>', $currentPhaseTemplate->phase_index)
            ->orderBy('phase_index')
            ->first();

        if (! $nextPhaseTemplate) {
            throw new \DomainException('No next phase available');
        }

        return DB::transaction(function () use ($cycle, $currentPhase, $currentPhaseTemplate, $nextPhaseTemplate, $userId) {
            // Row-level lock против параллельного advancePhase (двойной snapshot + race на current_phase_id).
            $cycle = GrowCycle::query()->whereKey($cycle->id)->lockForUpdate()->firstOrFail();

            $nextPhaseSnapshot = $this->snapshotCreator->create($cycle, $nextPhaseTemplate, now());

            $cycle->update([
                'current_phase_id' => $nextPhaseSnapshot->id,
                'current_step_id' => null,
                'phase_started_at' => now(),
                'step_started_at' => null,
            ]);

            // AE3 получит актуальные targets/ratios/ec_dosing_mode/nutrient_mode под новую фазу.
            $this->automationConfigCompiler->compileAffectedScopes(
                AutomationConfigRegistry::SCOPE_GROW_CYCLE,
                (int) $cycle->id,
            );

            // Pending IRRIGATE_ONCE/LIGHTING_TICK предыдущей фазы с устаревшими параметрами.
            // Активные (claimed/running/waiting_command) AE3 завершит сам.
            $this->canceller->cancelStalePendingIntentsOnPhaseAdvance((int) $cycle->zone_id);

            $zone = $cycle->zone;

            GrowCycleTransition::create([
                'grow_cycle_id' => $cycle->id,
                'from_phase_id' => $currentPhaseTemplate->id,
                'to_phase_id' => $nextPhaseTemplate->id,
                'from_step_id' => $cycle->current_step_id,
                'to_step_id' => null,
                'trigger_type' => 'MANUAL',
                'triggered_by' => $userId,
                'comment' => 'Advanced to next phase',
            ]);

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_PHASE_ADVANCED',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $cycle->id,
                'payload_json' => [
                    'cycle_id' => $cycle->id,
                    'from_phase_id' => $currentPhase->id,
                    'to_phase_id' => $nextPhaseSnapshot->id,
                    'from_phase_template_id' => $currentPhaseTemplate->id,
                    'to_phase_template_id' => $nextPhaseTemplate->id,
                    'user_id' => $userId,
                    'source' => 'web',
                    'correlation_id' => $this->correlation->resolve(),
                ],
            ]);

            broadcast(new GrowCycleUpdated($cycle->fresh(), 'PHASE_ADVANCED'));

            return $cycle->fresh()->load('currentPhase', 'currentStep');
        });
    }

    public function setPhase(GrowCycle $cycle, RecipeRevisionPhase $newPhase, string $comment, int $userId): GrowCycle
    {
        $revision = $cycle->recipeRevision;
        if (! $revision) {
            throw new \DomainException('Cycle has no recipe revision');
        }

        if ($newPhase->recipe_revision_id !== $revision->id) {
            throw new \DomainException('Phase does not belong to cycle\'s recipe revision');
        }

        $currentPhase = $cycle->currentPhase;
        $currentPhaseTemplate = $currentPhase?->recipeRevisionPhase;

        return DB::transaction(function () use ($cycle, $currentPhase, $currentPhaseTemplate, $newPhase, $comment, $userId) {
            $cycle = GrowCycle::query()->whereKey($cycle->id)->lockForUpdate()->firstOrFail();

            $newPhaseSnapshot = $this->snapshotCreator->create($cycle, $newPhase, now());

            $cycle->update([
                'current_phase_id' => $newPhaseSnapshot->id,
                'current_step_id' => null,
                'phase_started_at' => now(),
                'step_started_at' => null,
            ]);

            $this->automationConfigCompiler->compileAffectedScopes(
                AutomationConfigRegistry::SCOPE_GROW_CYCLE,
                (int) $cycle->id,
            );

            $this->canceller->cancelStalePendingIntentsOnPhaseAdvance((int) $cycle->zone_id);

            $zone = $cycle->zone;

            GrowCycleTransition::create([
                'grow_cycle_id' => $cycle->id,
                'from_phase_id' => $currentPhaseTemplate?->id,
                'to_phase_id' => $newPhase->id,
                'from_step_id' => $cycle->current_step_id,
                'to_step_id' => null,
                'trigger_type' => 'MANUAL',
                'triggered_by' => $userId,
                'comment' => $comment,
            ]);

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_PHASE_SET',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $cycle->id,
                'payload_json' => [
                    'cycle_id' => $cycle->id,
                    'from_phase_id' => $currentPhase?->id,
                    'to_phase_id' => $newPhase->id,
                    'user_id' => $userId,
                    'source' => 'web',
                    'comment' => $comment,
                ],
            ]);

            broadcast(new GrowCycleUpdated($cycle->fresh(), 'PHASE_SET'));

            return $cycle->fresh()->load('currentPhase', 'currentStep');
        });
    }

    /**
     * Сменить ревизию рецепта.
     *
     * - 'now'         — обновляет recipe_revision_id И создаёт snapshot первой фазы
     *                   новой ревизии. AE3 сразу видит новые targets/ratios/extensions.
     * - 'next_phase'  — обновляет ТОЛЬКО recipe_revision_id. Bundle пересчитывается,
     *                   но текущий snapshot старой фазы остаётся. Новые параметры
     *                   применяются на следующем advancePhase().
     */
    public function changeRecipeRevision(
        GrowCycle $cycle,
        RecipeRevision $newRevision,
        string $applyMode,
        int $userId,
    ): GrowCycle {
        if ($newRevision->status !== 'PUBLISHED') {
            throw new \DomainException('Only PUBLISHED revisions can be applied to cycles');
        }

        return DB::transaction(function () use ($cycle, $newRevision, $applyMode, $userId) {
            $cycle = GrowCycle::query()->whereKey($cycle->id)->lockForUpdate()->firstOrFail();
            $zone = $cycle->zone;
            $oldRevisionId = $cycle->recipe_revision_id;

            if ($applyMode === 'now') {
                $firstPhaseTemplate = $newRevision->phases()->orderBy('phase_index')->first();
                if (! $firstPhaseTemplate) {
                    throw new \DomainException('Revision has no phases');
                }

                $oldPhaseSnapshot = $cycle->currentPhase;
                $oldPhaseTemplateId = $oldPhaseSnapshot?->recipeRevisionPhase?->id;

                $firstPhaseSnapshot = $this->snapshotCreator->create($cycle, $firstPhaseTemplate, now());

                $cycle->update([
                    'recipe_revision_id' => $newRevision->id,
                    'current_phase_id' => $firstPhaseSnapshot->id,
                    'current_step_id' => null,
                    'phase_started_at' => now(),
                    'step_started_at' => null,
                ]);

                GrowCycleTransition::create([
                    'grow_cycle_id' => $cycle->id,
                    'from_phase_id' => $oldPhaseTemplateId,
                    'to_phase_id' => $firstPhaseTemplate->id,
                    'trigger_type' => 'RECIPE_REVISION_CHANGED',
                    'triggered_by' => $userId,
                    'comment' => "Changed recipe revision from {$oldRevisionId} to {$newRevision->id}",
                ]);

                ZoneEvent::create([
                    'zone_id' => $zone->id,
                    'type' => 'CYCLE_RECIPE_REVISION_CHANGED',
                    'entity_type' => 'grow_cycle',
                    'entity_id' => (string) $cycle->id,
                    'payload_json' => [
                        'cycle_id' => $cycle->id,
                        'from_revision_id' => $oldRevisionId,
                        'to_revision_id' => $newRevision->id,
                        'apply_mode' => 'now',
                        'user_id' => $userId,
                        'source' => 'web',
                        'correlation_id' => $this->correlation->resolve(),
                    ],
                ]);
            } else {
                $cycle->update(['recipe_revision_id' => $newRevision->id]);

                ZoneEvent::create([
                    'zone_id' => $zone->id,
                    'type' => 'CYCLE_RECIPE_REVISION_CHANGED',
                    'entity_type' => 'grow_cycle',
                    'entity_id' => (string) $cycle->id,
                    'payload_json' => [
                        'cycle_id' => $cycle->id,
                        'from_revision_id' => $oldRevisionId,
                        'to_revision_id' => $newRevision->id,
                        'apply_mode' => 'next_phase',
                        'user_id' => $userId,
                        'source' => 'web',
                        'correlation_id' => $this->correlation->resolve(),
                    ],
                ]);
            }

            $this->automationConfigCompiler->compileAffectedScopes(
                AutomationConfigRegistry::SCOPE_GROW_CYCLE,
                (int) $cycle->id,
            );

            broadcast(new GrowCycleUpdated($cycle->fresh(), 'RECIPE_REVISION_CHANGED'));

            return $cycle->fresh()->load('recipeRevision', 'currentPhase');
        });
    }
}
