<?php

namespace App\Services;

use App\Exceptions\ZoneNotReadyException;
use App\Models\GrowCycle;
use App\Models\RecipeRevision;
use App\Models\Zone;
use Carbon\Carbon;

/**
 * Оркестрирует создание и запуск grow cycle: готовит зону, создаёт цикл,
 * синхронизирует config-документы и (опционально) запускает.
 *
 * Контроллеры GrowCycleController::store() и ::start() делегируют бизнес-поток
 * сюда — сами остаются тонкими обёртками с HTTP-валидацией и авторизацией.
 */
class GrowCycleOrchestrator
{
    public function __construct(
        private GrowCycleService $growCycleService,
        private ZoneReadinessService $zoneReadinessService,
        private ZoneService $zoneService,
    ) {}

    /**
     * Создаёт цикл, синхронизирует конфиги и, если запрошено, стартует.
     *
     * @param  array<string, mixed>  $data  Валидированный payload запроса store().
     * @throws ZoneNotReadyException Если start_immediately=true и зона не готова.
     * @throws \DomainException Бизнес-ошибка (пробрасывается из GrowCycleService).
     */
    public function createCycle(Zone $zone, array $data, int $userId): GrowCycle
    {
        $startImmediately = (bool) ($data['start_immediately'] ?? false);

        if ($startImmediately) {
            $this->ensureZoneReadyToStart($zone);
        }

        $revision = RecipeRevision::findOrFail($data['recipe_revision_id']);
        $createPayload = $data;
        $createPayload['start_immediately'] = false;

        $cycle = $this->growCycleService->createCycle(
            $zone,
            $revision,
            $data['plant_id'],
            $createPayload,
            $userId,
        );

        $this->growCycleService->syncCycleConfigDocuments($cycle, $data, $userId);

        if ($startImmediately) {
            $plantingAt = ! empty($data['planting_at'])
                ? Carbon::parse($data['planting_at'])
                : now();
            $cycle = $this->growCycleService->startCycle($cycle->fresh(), $plantingAt);
        }

        return $cycle->refresh()->load('recipeRevision', 'currentPhase', 'plant');
    }

    /**
     * Запускает уже созданный цикл (endpoint POST /grow-cycles/{id}/start).
     *
     * @throws ZoneNotReadyException Если зона не готова.
     * @throws \DomainException Бизнес-ошибка.
     */
    public function startExistingCycle(GrowCycle $cycle): GrowCycle
    {
        $this->ensureZoneReadyToStart($cycle->zone);

        return $this->growCycleService->startCycle($cycle);
    }

    /**
     * Выполняет pre-flight готовность зоны: bootstrap + readiness check.
     *
     * @throws ZoneNotReadyException
     */
    private function ensureZoneReadyToStart(Zone $zone): void
    {
        $zone->loadMissing('nodes.channels');
        $this->zoneService->ensureAe3AutomationBootstrap($zone);

        $readiness = $this->zoneReadinessService->checkZoneReadiness($zone);
        if (($readiness['ready'] ?? false) !== true) {
            throw new ZoneNotReadyException($readiness);
        }
    }
}
