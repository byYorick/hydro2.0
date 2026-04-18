<?php

declare(strict_types=1);

namespace App\Services;

use App\Models\GrowCycle;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Zone;
use App\Services\GrowCycle\GrowCycleAutomationCanceller;
use App\Services\GrowCycle\GrowCycleAutomationDispatcher;
use App\Services\GrowCycle\GrowCycleConfigSyncer;
use App\Services\GrowCycle\GrowCycleCreator;
use App\Services\GrowCycle\GrowCycleLifecycleService;
use App\Services\GrowCycle\GrowCyclePhaseService;
use App\Services\GrowCycle\GrowCycleStageTimelineService;
use Carbon\Carbon;
use Illuminate\Contracts\Pagination\LengthAwarePaginator;

/**
 * Тонкий фасад над специализированными сервисами grow cycle. Публичное API сохранено
 * для обратной совместимости с существующими потребителями (Controller, ZoneService,
 * Console commands, Seeders). Новая логика должна инъектить соответствующий
 * узкоспециализированный сервис напрямую, а не идти через этот фасад.
 *
 * См. декомпозицию в {@link \App\Services\GrowCycle\}:
 *  - {@see GrowCycleCreator}                — создание
 *  - {@see GrowCycleLifecycleService}       — start/pause/resume/harvest/abort/getByGreenhouse
 *  - {@see GrowCyclePhaseService}           — advance/set/changeRevision/advanceStage
 *  - {@see GrowCycleStageTimelineService}   — timeline + ETA harvest
 *  - {@see GrowCycleConfigSyncer}           — syncCycleConfigDocuments
 *  - {@see GrowCycleAutomationDispatcher}   — dispatch в AE3
 *  - {@see GrowCycleAutomationCanceller}    — cancel intents/tasks
 */
class GrowCycleService
{
    public function __construct(
        private readonly GrowCycleCreator $creator,
        private readonly GrowCycleLifecycleService $lifecycle,
        private readonly GrowCyclePhaseService $phase,
        private readonly GrowCycleStageTimelineService $timeline,
        private readonly GrowCycleConfigSyncer $configSyncer,
        private readonly GrowCycleAutomationDispatcher $dispatcher,
        private readonly GrowCycleAutomationCanceller $canceller,
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
        return $this->creator->createCycle($zone, $revision, $plantId, $data, $userId);
    }

    public function startCycle(GrowCycle $cycle, ?Carbon $plantingAt = null): GrowCycle
    {
        return $this->lifecycle->startCycle($cycle, $plantingAt);
    }

    /**
     * @param array<string, mixed> $data
     */
    public function syncCycleConfigDocuments(GrowCycle $cycle, array $data = [], ?int $userId = null): void
    {
        $this->configSyncer->syncCycleConfigDocuments($cycle, $data, $userId);
    }

    public function advanceStage(GrowCycle $cycle, ?string $targetStageCode = null): GrowCycle
    {
        return $this->phase->advanceStage($cycle, $targetStageCode);
    }

    public function computeExpectedHarvest(GrowCycle $cycle): void
    {
        $this->timeline->computeExpectedHarvest($cycle);
    }

    /**
     * @return array{segments: array<int, array{code: string, name: string, phase_indices: array<int>, duration_hours: float, ui_meta: array|null}>, total_hours: float}
     */
    public function buildStageTimeline(RecipeRevision $revision): array
    {
        return $this->timeline->buildStageTimeline($revision);
    }

    public function pause(GrowCycle $cycle, int $userId): GrowCycle
    {
        return $this->lifecycle->pause($cycle, $userId);
    }

    public function resume(GrowCycle $cycle, int $userId): GrowCycle
    {
        return $this->lifecycle->resume($cycle, $userId);
    }

    /**
     * @param array<string, mixed> $data
     */
    public function harvest(GrowCycle $cycle, array $data, int $userId): GrowCycle
    {
        return $this->lifecycle->harvest($cycle, $data, $userId);
    }

    /**
     * @param array<string, mixed> $data
     */
    public function abort(GrowCycle $cycle, array $data, int $userId): GrowCycle
    {
        return $this->lifecycle->abort($cycle, $data, $userId);
    }

    public function advancePhase(GrowCycle $cycle, ?int $userId): GrowCycle
    {
        return $this->phase->advancePhase($cycle, $userId);
    }

    public function setPhase(GrowCycle $cycle, RecipeRevisionPhase $newPhase, string $comment, int $userId): GrowCycle
    {
        return $this->phase->setPhase($cycle, $newPhase, $comment, $userId);
    }

    public function changeRecipeRevision(
        GrowCycle $cycle,
        RecipeRevision $newRevision,
        string $applyMode,
        int $userId,
    ): GrowCycle {
        return $this->phase->changeRecipeRevision($cycle, $newRevision, $applyMode, $userId);
    }

    public function getByGreenhouse(int $greenhouseId, int $perPage = 50): LengthAwarePaginator
    {
        return $this->lifecycle->getByGreenhouse($greenhouseId, $perPage);
    }
}
