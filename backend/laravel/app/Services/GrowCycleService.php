<?php

namespace App\Services;

use App\Events\GrowCycleUpdated;
use App\Models\GrowCycle;
use App\Models\GrowCyclePhase;
use App\Models\GrowCycleTransition;
use App\Models\GrowStageTemplate;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\RecipeStageMap;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Enums\GrowCycleStatus;
use Carbon\Carbon;
use Illuminate\Contracts\Pagination\LengthAwarePaginator;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class GrowCycleService
{
    /**
     * Создать новый цикл выращивания (новая модель с recipe_revision_id)
     */
    public function createCycle(
        Zone $zone,
        RecipeRevision $revision,
        int $plantId,
        array $data = [],
        ?int $userId = null
    ): GrowCycle {
        // Проверяем, что в зоне нет активного цикла
        $activeCycle = $zone->activeGrowCycle;
        if ($activeCycle) {
            throw new \DomainException('Zone already has an active cycle. Please pause, harvest, or abort it first.');
        }

        // Проверяем, что ревизия опубликована
        if ($revision->status !== 'PUBLISHED') {
            throw new \DomainException('Only PUBLISHED revisions can be used for new cycles');
        }

        // Получаем первую фазу
        $firstPhase = $revision->phases()->orderBy('phase_index')->first();
        if (!$firstPhase) {
            throw new \DomainException('Revision has no phases');
        }

        return DB::transaction(function () use ($zone, $revision, $firstPhase, $plantId, $data, $userId) {
            $plantingAt = isset($data['planting_at']) && $data['planting_at'] 
                ? Carbon::parse($data['planting_at']) 
                : now();

            $startImmediately = $data['start_immediately'] ?? false;

            // Создаем снапшот первой фазы
            $firstPhaseSnapshot = $this->createPhaseSnapshot(null, $firstPhase, $startImmediately ? $plantingAt : null);

            $cycle = GrowCycle::create([
                'greenhouse_id' => $zone->greenhouse_id,
                'zone_id' => $zone->id,
                'plant_id' => $plantId,
                'recipe_revision_id' => $revision->id,
                'current_phase_id' => $firstPhaseSnapshot->id,
                'current_step_id' => null,
                'status' => $startImmediately ? GrowCycleStatus::RUNNING : GrowCycleStatus::PLANNED,
                'planting_at' => $plantingAt,
                'phase_started_at' => $startImmediately ? $plantingAt : null,
                'batch_label' => $data['batch_label'] ?? null,
                'notes' => $data['notes'] ?? null,
                'started_at' => $startImmediately ? $plantingAt : null,
            ]);

            // Обновляем снапшот с ID цикла
            $firstPhaseSnapshot->update(['grow_cycle_id' => $cycle->id]);

            // Логируем создание
            GrowCycleTransition::create([
                'grow_cycle_id' => $cycle->id,
                'from_phase_id' => null,
                'to_phase_id' => $firstPhase->id,
                'trigger' => 'CYCLE_CREATED',
                'triggered_by' => $userId,
                'comment' => 'Cycle created',
            ]);

            // Записываем событие
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
                ],
            ]);

            // Отправляем WebSocket broadcast
            broadcast(new GrowCycleUpdated($cycle->fresh(), 'CREATED'));

            Log::info('Grow cycle created', [
                'cycle_id' => $cycle->id,
                'zone_id' => $zone->id,
                'recipe_revision_id' => $revision->id,
            ]);

            return $cycle->load('recipeRevision', 'currentPhase', 'plant');
        });
    }

    /**
     * Запустить цикл (посадка)
     */
    public function startCycle(GrowCycle $cycle, ?Carbon $plantingAt = null): GrowCycle
    {
        if ($cycle->status !== GrowCycleStatus::PLANNED) {
            throw new \DomainException('Cycle must be in PLANNED status to start');
        }

        return DB::transaction(function () use ($cycle, $plantingAt) {
            $plantingAt = $plantingAt ?? now();
            
            $cycle->update([
                'status' => GrowCycleStatus::RUNNING,
                'planting_at' => $plantingAt,
                'started_at' => $plantingAt,
                'recipe_started_at' => $plantingAt,
            ]);

            // В новой модели фазы уже установлены при создании цикла через createPhaseSnapshot()
            // Вычисляем ожидаемую дату сбора
            $this->computeExpectedHarvest($cycle);

            Log::info('Grow cycle started', [
                'cycle_id' => $cycle->id,
                'planting_at' => $plantingAt,
            ]);

            return $cycle->fresh();
        });
    }

    /**
     * Переход на следующую стадию (автоматически или вручную)
     */
    public function advanceStage(GrowCycle $cycle, ?string $targetStageCode = null): GrowCycle
    {
        if ($cycle->status !== GrowCycleStatus::RUNNING) {
            throw new \DomainException('Cycle must be RUNNING to advance stage');
        }

        return DB::transaction(function () use ($cycle, $targetStageCode) {
            $recipe = $cycle->recipe;
            if (!$recipe) {
                throw new \DomainException('Cycle must have a recipe to advance stage');
            }

            $stageMaps = $recipe->stageMaps()->orderBy('order_index')->get();
            
            if ($targetStageCode) {
                // Ручной переход на указанную стадию
                $targetMap = $stageMaps->firstWhere('stageTemplate.code', $targetStageCode);
                if (!$targetMap) {
                    throw new \DomainException("Stage {$targetStageCode} not found in recipe stage map");
                }
            } else {
                // Автоматический переход на следующую стадию
                $currentMap = $stageMaps->firstWhere('stageTemplate.code', $cycle->current_stage_code);
                if (!$currentMap) {
                    // Если текущей стадии нет в маппинге, берем первую
                    $targetMap = $stageMaps->first();
                } else {
                    $currentIndex = $currentMap->order_index;
                    $targetMap = $stageMaps->firstWhere('order_index', $currentIndex + 1);
                }

                if (!$targetMap) {
                    throw new \DomainException('No next stage available');
                }
            }

            $stageTemplate = $targetMap->stageTemplate;
            
            $oldStageCode = $cycle->current_stage_code;
            
            $cycle->update([
                'current_stage_code' => $stageTemplate->code,
                'current_stage_started_at' => now(),
            ]);
            
            $cycle->refresh();

            // Отправляем событие об обновлении цикла для автоматического обновления targets в AE
            GrowCycleUpdated::dispatch($cycle, 'STAGE_ADVANCED');

            Log::info('Grow cycle stage advanced', [
                'cycle_id' => $cycle->id,
                'old_stage_code' => $oldStageCode,
                'new_stage_code' => $stageTemplate->code,
            ]);

            return $cycle->fresh();
        });
    }

    /**
     * @deprecated Этот метод использует legacy модель RecipeStageMap и zone_recipe_instances.
     * В новой модели фазы устанавливаются при создании цикла через createPhaseSnapshot().
     * Метод оставлен для обратной совместимости, но больше не используется.
     */
    public function computeStageFromRecipeInstance(GrowCycle $cycle): void
    {
        // В новой модели фазы уже установлены при создании цикла
        // Этот метод больше не нужен, но оставлен для обратной совместимости
        Log::warning('computeStageFromRecipeInstance called but deprecated - phases are set via snapshots', [
            'cycle_id' => $cycle->id,
        ]);
    }

    /**
     * Вычислить ожидаемую дату сбора урожая
     */
    public function computeExpectedHarvest(GrowCycle $cycle): void
    {
        $recipe = $cycle->recipe;
        if (!$recipe) {
            return;
        }

        $stageMaps = $recipe->stageMaps()->with('stageTemplate')->orderBy('order_index')->get();
        
        if ($stageMaps->isEmpty()) {
            return;
        }

        $plantingAt = $cycle->planting_at ?? $cycle->started_at;
        if (!$plantingAt) {
            return;
        }

        // Находим последнюю стадию (обычно HARVEST)
        $lastMap = $stageMaps->last();
        $harvestOffset = $lastMap->end_offset_days ?? $lastMap->start_offset_days;

        if ($harvestOffset) {
            $expectedHarvestAt = Carbon::parse($plantingAt)->addDays($harvestOffset);
            $cycle->update(['expected_harvest_at' => $expectedHarvestAt]);
        } else {
            // Если offset не задан, вычисляем на основе default_duration_days стадий
            $totalDays = 0;
            foreach ($stageMaps as $map) {
                $duration = $map->end_offset_days 
                    ? ($map->end_offset_days - ($map->start_offset_days ?? 0))
                    : ($map->stageTemplate->default_duration_days ?? 0);
                $totalDays += $duration;
            }
            
            if ($totalDays > 0) {
                $expectedHarvestAt = Carbon::parse($plantingAt)->addDays($totalDays);
                $cycle->update(['expected_harvest_at' => $expectedHarvestAt]);
            }
        }
    }

    /**
     * Убедиться, что у рецепта есть stage-map (создать автоматически, если нет)
     */
    public function ensureRecipeStageMap(Recipe $recipe): void
    {
        if ($recipe->stageMaps()->exists()) {
            return;
        }

        // Автоматически генерируем stage-map на основе фаз рецепта
        $phases = $recipe->phases()->orderBy('phase_index')->get();
        
        if ($phases->isEmpty()) {
            return;
        }

        // Получаем стандартные шаблоны стадий
        $templates = GrowStageTemplate::orderBy('order_index')->get();
        
        if ($templates->isEmpty()) {
            // Если шаблонов нет, создаем базовые
            $this->createDefaultStageTemplates();
            $templates = GrowStageTemplate::orderBy('order_index')->get();
        }

        // Маппим фазы на стадии
        $phaseCount = $phases->count();
        $stageCount = $templates->count();
        
        $phasesPerStage = max(1, (int) ceil($phaseCount / $stageCount));
        
        $orderIndex = 0;
        $phaseIndex = 0;
        
        foreach ($templates as $template) {
            $phaseIndices = [];
            for ($i = 0; $i < $phasesPerStage && $phaseIndex < $phaseCount; $i++) {
                $phaseIndices[] = $phases[$phaseIndex]->phase_index;
                $phaseIndex++;
            }

            if (!empty($phaseIndices) || $orderIndex === 0) {
                // Первая стадия всегда создается, даже если фаз нет
                RecipeStageMap::create([
                    'recipe_id' => $recipe->id,
                    'stage_template_id' => $template->id,
                    'order_index' => $orderIndex,
                    'phase_indices' => $phaseIndices,
                    'start_offset_days' => $orderIndex === 0 ? 0 : null, // Первая стадия начинается с 0
                ]);
                $orderIndex++;
            }
        }
    }

    /**
     * Создать стандартные шаблоны стадий
     */
    private function createDefaultStageTemplates(): void
    {
        $defaultStages = [
            ['name' => 'Посадка', 'code' => 'PLANTING', 'order' => 0, 'duration' => 1, 'color' => '#10b981', 'icon' => '🌱'],
            ['name' => 'Укоренение', 'code' => 'ROOTING', 'order' => 1, 'duration' => 7, 'color' => '#3b82f6', 'icon' => '🌿'],
            ['name' => 'Вега', 'code' => 'VEG', 'order' => 2, 'duration' => 21, 'color' => '#22c55e', 'icon' => '🌳'],
            ['name' => 'Цветение', 'code' => 'FLOWER', 'order' => 3, 'duration' => 14, 'color' => '#f59e0b', 'icon' => '🌸'],
            ['name' => 'Плодоношение', 'code' => 'FRUIT', 'order' => 4, 'duration' => 21, 'color' => '#ef4444', 'icon' => '🍅'],
            ['name' => 'Сбор', 'code' => 'HARVEST', 'order' => 5, 'duration' => 1, 'color' => '#8b5cf6', 'icon' => '✂️'],
        ];

        foreach ($defaultStages as $stage) {
            GrowStageTemplate::create([
                'name' => $stage['name'],
                'code' => $stage['code'],
                'order_index' => $stage['order'],
                'default_duration_days' => $stage['duration'],
                'ui_meta' => [
                    'color' => $stage['color'],
                    'icon' => $stage['icon'],
                    'description' => $stage['name'],
                ],
            ]);
        }
    }

    /**
     * Приостановить цикл
     */
    public function pause(GrowCycle $cycle, int $userId): GrowCycle
    {
        if ($cycle->status !== GrowCycleStatus::RUNNING) {
            throw new \DomainException('Cycle is not running');
        }

        return DB::transaction(function () use ($cycle, $userId) {
            $cycle->update(['status' => GrowCycleStatus::PAUSED]);
            $cycle->refresh();

            $zone = $cycle->zone;

            // Записываем событие в zone_events
            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_PAUSED',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $cycle->id,
                'payload_json' => [
                    'cycle_id' => $cycle->id,
                    'user_id' => $userId,
                    'source' => 'web',
                ],
            ]);

            // Отправляем WebSocket broadcast
            broadcast(new GrowCycleUpdated($cycle, 'PAUSED'));

            Log::info('Grow cycle paused', [
                'zone_id' => $zone->id,
                'cycle_id' => $cycle->id,
                'user_id' => $userId,
            ]);

            return $cycle->fresh();
        });
    }

    /**
     * Возобновить цикл
     */
    public function resume(GrowCycle $cycle, int $userId): GrowCycle
    {
        if ($cycle->status !== GrowCycleStatus::PAUSED) {
            throw new \DomainException('Cycle is not paused');
        }

        return DB::transaction(function () use ($cycle, $userId) {
            $cycle->update(['status' => GrowCycleStatus::RUNNING]);
            $cycle->refresh();

            $zone = $cycle->zone;

            // Записываем событие в zone_events
            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_RESUMED',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $cycle->id,
                'payload_json' => [
                    'cycle_id' => $cycle->id,
                    'user_id' => $userId,
                    'source' => 'web',
                ],
            ]);

            // Отправляем WebSocket broadcast
            broadcast(new GrowCycleUpdated($cycle, 'RESUMED'));

            Log::info('Grow cycle resumed', [
                'zone_id' => $zone->id,
                'cycle_id' => $cycle->id,
                'user_id' => $userId,
            ]);

            return $cycle->fresh();
        });
    }

    /**
     * Зафиксировать сбор (harvest) - закрывает цикл
     */
    public function harvest(GrowCycle $cycle, array $data, int $userId): GrowCycle
    {
        if ($cycle->status === GrowCycleStatus::HARVESTED || $cycle->status === GrowCycleStatus::ABORTED) {
            throw new \DomainException('Cycle is already completed');
        }

        return DB::transaction(function () use ($cycle, $data, $userId) {
            $cycle->update([
                'status' => GrowCycleStatus::HARVESTED,
                'actual_harvest_at' => now(),
                'batch_label' => $data['batch_label'] ?? $cycle->batch_label,
                'notes' => $data['notes'] ?? $cycle->notes,
            ]);
            $cycle->refresh();

            $zone = $cycle->zone;

            // Записываем событие в zone_events
            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_HARVESTED',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $cycle->id,
                'payload_json' => [
                    'cycle_id' => $cycle->id,
                    'user_id' => $userId,
                    'source' => 'web',
                    'batch_label' => $cycle->batch_label,
                ],
            ]);

            // Отправляем WebSocket broadcast
            broadcast(new GrowCycleUpdated($cycle, 'HARVESTED'));

            Log::info('Grow cycle harvested', [
                'zone_id' => $zone->id,
                'cycle_id' => $cycle->id,
                'user_id' => $userId,
            ]);

            return $cycle->fresh();
        });
    }

    /**
     * Аварийная остановка цикла
     */
    public function abort(GrowCycle $cycle, array $data, int $userId): GrowCycle
    {
        if ($cycle->status === GrowCycleStatus::HARVESTED || $cycle->status === GrowCycleStatus::ABORTED) {
            throw new \DomainException('Cycle is already completed');
        }

        return DB::transaction(function () use ($cycle, $data, $userId) {
            $cycle->update([
                'status' => GrowCycleStatus::ABORTED,
                'notes' => $data['notes'] ?? $cycle->notes,
            ]);
            $cycle->refresh();

            $zone = $cycle->zone;

            // Записываем событие в zone_events
            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_ABORTED',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $cycle->id,
                'payload_json' => [
                    'cycle_id' => $cycle->id,
                    'user_id' => $userId,
                    'source' => 'web',
                    'reason' => $data['notes'] ?? 'Emergency abort',
                ],
            ]);

            // Отправляем WebSocket broadcast
            broadcast(new GrowCycleUpdated($cycle, 'ABORTED'));

            Log::info('Grow cycle aborted', [
                'zone_id' => $zone->id,
                'cycle_id' => $cycle->id,
                'user_id' => $userId,
            ]);

            return $cycle->fresh();
        });
    }

    /**
     * Переход на следующую фазу
     */
    public function advancePhase(GrowCycle $cycle, int $userId): GrowCycle
    {
        $revision = $cycle->recipeRevision;
        if (!$revision) {
            throw new \DomainException('Cycle has no recipe revision');
        }

        $currentPhase = $cycle->currentPhase;
        if (!$currentPhase) {
            throw new \DomainException('Cycle has no current phase');
        }

        // Получаем шаблон текущей фазы для поиска следующей
        $currentPhaseTemplate = $currentPhase->recipeRevisionPhase;
        if (!$currentPhaseTemplate) {
            throw new \DomainException('Current phase has no template reference');
        }

        // Находим следующую фазу в шаблоне
        $nextPhaseTemplate = $revision->phases()
            ->where('phase_index', '>', $currentPhaseTemplate->phase_index)
            ->orderBy('phase_index')
            ->first();

        if (!$nextPhaseTemplate) {
            throw new \DomainException('No next phase available');
        }

        return DB::transaction(function () use ($cycle, $currentPhase, $currentPhaseTemplate, $nextPhaseTemplate, $userId) {
            // Создаем снапшот следующей фазы
            $nextPhaseSnapshot = $this->createPhaseSnapshot($cycle, $nextPhaseTemplate, now());

            // Обновляем цикл
            $cycle->update([
                'current_phase_id' => $nextPhaseSnapshot->id,
                'current_step_id' => null,
                'phase_started_at' => now(),
                'step_started_at' => null,
            ]);

            $zone = $cycle->zone;

            // Логируем переход (используем шаблоны для истории переходов)
            GrowCycleTransition::create([
                'grow_cycle_id' => $cycle->id,
                'from_phase_id' => $currentPhaseTemplate->id, // Шаблон для истории
                'to_phase_id' => $nextPhaseTemplate->id, // Шаблон для истории
                'from_step_id' => $cycle->current_step_id,
                'to_step_id' => null,
                'trigger' => 'MANUAL',
                'triggered_by' => $userId,
                'comment' => 'Advanced to next phase',
            ]);

            // Записываем событие в zone_events
            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'CYCLE_PHASE_ADVANCED',
                'entity_type' => 'grow_cycle',
                'entity_id' => (string) $cycle->id,
                'payload_json' => [
                    'cycle_id' => $cycle->id,
                    'from_phase_id' => $currentPhase->id, // Снапшот
                    'to_phase_id' => $nextPhaseSnapshot->id, // Снапшот
                    'from_phase_template_id' => $currentPhaseTemplate->id, // Шаблон для истории
                    'to_phase_template_id' => $nextPhaseTemplate->id, // Шаблон для истории
                    'user_id' => $userId,
                    'source' => 'web',
                ],
            ]);

            // Отправляем WebSocket broadcast
            broadcast(new GrowCycleUpdated($cycle->fresh(), 'PHASE_ADVANCED'));

            return $cycle->fresh()->load('currentPhase', 'currentStep');
        });
    }

    /**
     * Установить конкретную фазу (manual switch с комментарием)
     */
    public function setPhase(GrowCycle $cycle, RecipeRevisionPhase $newPhase, string $comment, int $userId): GrowCycle
    {
        $revision = $cycle->recipeRevision;
        if (!$revision) {
            throw new \DomainException('Cycle has no recipe revision');
        }

        // Проверяем, что фаза принадлежит ревизии
        if ($newPhase->recipe_revision_id !== $revision->id) {
            throw new \DomainException('Phase does not belong to cycle\'s recipe revision');
        }

        $currentPhase = $cycle->currentPhase;
        $currentPhaseTemplate = $currentPhase?->recipeRevisionPhase;

        return DB::transaction(function () use ($cycle, $currentPhaseTemplate, $newPhase, $comment, $userId) {
            // Создаем снапшот новой фазы
            $newPhaseSnapshot = $this->createPhaseSnapshot($cycle, $newPhase, now());

            // Обновляем цикл
            $cycle->update([
                'current_phase_id' => $newPhaseSnapshot->id,
                'current_step_id' => null,
                'phase_started_at' => now(),
                'step_started_at' => null,
            ]);

            $zone = $cycle->zone;

            // Логируем переход (используем шаблоны для истории переходов)
            GrowCycleTransition::create([
                'grow_cycle_id' => $cycle->id,
                'from_phase_id' => $currentPhaseTemplate?->id, // Шаблон для истории
                'to_phase_id' => $newPhase->id, // Шаблон для истории
                'from_step_id' => $cycle->current_step_id,
                'to_step_id' => null,
                'trigger' => 'MANUAL',
                'triggered_by' => $userId,
                'comment' => $comment,
            ]);

            // Записываем событие в zone_events
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

            // Отправляем WebSocket broadcast
            broadcast(new GrowCycleUpdated($cycle->fresh(), 'PHASE_SET'));

            return $cycle->fresh()->load('currentPhase', 'currentStep');
        });
    }

    /**
     * Сменить ревизию рецепта
     */
    public function changeRecipeRevision(
        GrowCycle $cycle,
        RecipeRevision $newRevision,
        string $applyMode,
        int $userId
    ): GrowCycle {
        // Проверяем, что ревизия опубликована
        if ($newRevision->status !== 'PUBLISHED') {
            throw new \DomainException('Only PUBLISHED revisions can be applied to cycles');
        }

        return DB::transaction(function () use ($cycle, $newRevision, $applyMode, $userId) {
            $zone = $cycle->zone;
            $oldRevisionId = $cycle->recipe_revision_id;

            if ($applyMode === 'now') {
                // Применяем сейчас: меняем ревизию и сбрасываем фазу на первую
                $firstPhaseTemplate = $newRevision->phases()->orderBy('phase_index')->first();
                
                if (!$firstPhaseTemplate) {
                    throw new \DomainException('Revision has no phases');
                }

                $oldPhaseSnapshot = $cycle->currentPhase;
                $oldPhaseTemplateId = $oldPhaseSnapshot?->recipeRevisionPhase?->id;

                // Создаем снапшот первой фазы новой ревизии
                $firstPhaseSnapshot = $this->createPhaseSnapshot($cycle, $firstPhaseTemplate, now());

                $cycle->update([
                    'recipe_revision_id' => $newRevision->id,
                    'current_phase_id' => $firstPhaseSnapshot->id,
                    'current_step_id' => null,
                    'phase_started_at' => now(),
                    'step_started_at' => null,
                ]);

                // Логируем переход (используем шаблоны для истории переходов)
                GrowCycleTransition::create([
                    'grow_cycle_id' => $cycle->id,
                    'from_phase_id' => $oldPhaseTemplateId, // Шаблон для истории
                    'to_phase_id' => $firstPhaseTemplate->id, // Шаблон для истории
                    'trigger' => 'RECIPE_REVISION_CHANGED',
                    'triggered_by' => $userId,
                    'comment' => "Changed recipe revision from {$oldRevisionId} to {$newRevision->id}",
                ]);

                // Записываем событие
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
                    ],
                ]);
            } else {
                // Применяем с следующей фазы: только меняем ревизию, фазу не трогаем
                $cycle->update([
                    'recipe_revision_id' => $newRevision->id,
                ]);

                // Записываем событие
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
                    ],
                ]);
            }

            // Отправляем WebSocket broadcast
            broadcast(new GrowCycleUpdated($cycle->fresh(), 'RECIPE_REVISION_CHANGED'));

            return $cycle->fresh()->load('recipeRevision', 'currentPhase');
        });
    }

    /**
     * Получить все циклы для теплицы
     */
    public function getByGreenhouse(int $greenhouseId, int $perPage = 50): LengthAwarePaginator
    {
        return GrowCycle::where('greenhouse_id', $greenhouseId)
            ->with(['zone', 'plant', 'recipeRevision.phases', 'currentPhase', 'currentStep'])
            ->orderBy('started_at', 'desc')
            ->paginate($perPage);
    }

    /**
     * Создать снапшот фазы из шаблона
     * 
     * @param GrowCycle|null $cycle Цикл (может быть null при создании цикла)
     * @param RecipeRevisionPhase $templatePhase Шаблонная фаза
     * @param Carbon|null $startedAt Время начала фазы
     * @return GrowCyclePhase
     */
    private function createPhaseSnapshot(?GrowCycle $cycle, RecipeRevisionPhase $templatePhase, ?Carbon $startedAt = null): GrowCyclePhase
    {
        return GrowCyclePhase::create([
            'grow_cycle_id' => $cycle?->id,
            'recipe_revision_phase_id' => $templatePhase->id,
            'phase_index' => $templatePhase->phase_index,
            'name' => $templatePhase->name,
            'ph_target' => $templatePhase->ph_target,
            'ph_min' => $templatePhase->ph_min,
            'ph_max' => $templatePhase->ph_max,
            'ec_target' => $templatePhase->ec_target,
            'ec_min' => $templatePhase->ec_min,
            'ec_max' => $templatePhase->ec_max,
            'irrigation_mode' => $templatePhase->irrigation_mode,
            'irrigation_interval_sec' => $templatePhase->irrigation_interval_sec,
            'irrigation_duration_sec' => $templatePhase->irrigation_duration_sec,
            'lighting_photoperiod_hours' => $templatePhase->lighting_photoperiod_hours,
            'lighting_start_time' => $templatePhase->lighting_start_time,
            'mist_interval_sec' => $templatePhase->mist_interval_sec,
            'mist_duration_sec' => $templatePhase->mist_duration_sec,
            'mist_mode' => $templatePhase->mist_mode,
            'temp_air_target' => $templatePhase->temp_air_target,
            'humidity_target' => $templatePhase->humidity_target,
            'co2_target' => $templatePhase->co2_target,
            'progress_model' => $templatePhase->progress_model,
            'duration_hours' => $templatePhase->duration_hours,
            'duration_days' => $templatePhase->duration_days,
            'base_temp_c' => $templatePhase->base_temp_c,
            'target_gdd' => $templatePhase->target_gdd,
            'dli_target' => $templatePhase->dli_target,
            'extensions' => $templatePhase->extensions,
            'started_at' => $startedAt,
        ]);
    }
}

