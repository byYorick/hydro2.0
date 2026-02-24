<?php

namespace App\Services;

use App\Enums\GrowCycleStatus;
use App\Events\GrowCycleUpdated;
use App\Events\ZoneUpdated;
use App\Models\GrowCycle;
use App\Models\GrowCyclePhase;
use App\Models\GrowCycleTransition;
use App\Models\GrowStageTemplate;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Zone;
use App\Models\ZoneEvent;
use Carbon\Carbon;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\Response;
use Illuminate\Contracts\Pagination\LengthAwarePaginator;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

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
        if (! $firstPhase) {
            throw new \DomainException('Revision has no phases');
        }

        return DB::transaction(function () use ($zone, $revision, $firstPhase, $plantId, $data, $userId) {
            $plantingAt = isset($data['planting_at']) && $data['planting_at']
                ? Carbon::parse($data['planting_at'])
                : now();

            $startImmediately = $data['start_immediately'] ?? false;
            $phaseStartedAt = $startImmediately ? $plantingAt : null;
            $settings = is_array($data['settings'] ?? null) ? $data['settings'] : [];

            $irrigation = is_array($data['irrigation'] ?? null) ? $data['irrigation'] : [];
            if (!empty($irrigation)) {
                $settings['irrigation'] = [
                    'system_type' => $irrigation['system_type'] ?? 'drip',
                    'interval_minutes' => (int) ($irrigation['interval_minutes'] ?? 30),
                    'duration_seconds' => (int) ($irrigation['duration_seconds'] ?? 120),
                    'clean_tank_fill_l' => (int) ($irrigation['clean_tank_fill_l'] ?? 300),
                    'nutrient_tank_target_l' => (int) ($irrigation['nutrient_tank_target_l'] ?? 280),
                ];
            }

            // Сначала создаем цикл без current_phase_id (временно null)
            $cycle = GrowCycle::create([
                'greenhouse_id' => $zone->greenhouse_id,
                'zone_id' => $zone->id,
                'plant_id' => $plantId,
                'recipe_revision_id' => $revision->id,
                'current_phase_id' => null, // Временно null, обновим после создания снапшота
                'current_step_id' => null,
                'status' => $startImmediately ? GrowCycleStatus::RUNNING : GrowCycleStatus::PLANNED,
                'planting_at' => $plantingAt,
                'phase_started_at' => $phaseStartedAt,
                'batch_label' => $data['batch_label'] ?? null,
                'notes' => $data['notes'] ?? null,
                'settings' => !empty($settings) ? $settings : null,
                'started_at' => $startImmediately ? $plantingAt : null,
            ]);

            // Теперь создаем снапшот первой фазы с ID цикла
            $firstPhaseSnapshot = $this->createPhaseSnapshot($cycle, $firstPhase, $phaseStartedAt);

            // Обновляем цикл с ID снапшота фазы
            $cycle->update(['current_phase_id' => $firstPhaseSnapshot->id]);

            // Логируем создание
            GrowCycleTransition::create([
                'grow_cycle_id' => $cycle->id,
                'from_phase_id' => null,
                'to_phase_id' => $firstPhase->id,
                'trigger_type' => 'CYCLE_CREATED',
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

            if ($startImmediately) {
                $this->syncZoneStatus($zone, 'RUNNING');
            }

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

        $startedCycle = DB::transaction(function () use ($cycle, $plantingAt) {
            $plantingAt = $plantingAt ?? now();
            $plantingAt->setMicrosecond(0);

            // Обновляем phase_started_at для текущей фазы
            if ($cycle->current_phase_id) {
                $currentPhase = GrowCyclePhase::find($cycle->current_phase_id);
                if ($currentPhase) {
                    $currentPhase->update(['started_at' => $plantingAt]);
                }
            }

            $cycle->update([
                'status' => GrowCycleStatus::RUNNING,
                'planting_at' => $plantingAt,
                'started_at' => $plantingAt,
                'recipe_started_at' => $plantingAt,
                'phase_started_at' => $plantingAt, // Устанавливаем phase_started_at при старте
            ]);
            $this->syncZoneStatus($cycle->zone, 'RUNNING');

            // В новой модели фазы уже установлены при создании цикла через createPhaseSnapshot()
            // Вычисляем ожидаемую дату сбора
            $this->computeExpectedHarvest($cycle);

            Log::info('Grow cycle started', [
                'cycle_id' => $cycle->id,
                'planting_at' => $plantingAt,
            ]);

            return $cycle->fresh();
        });

        $this->dispatchAutomationStartCycle($startedCycle);

        return $startedCycle->fresh();
    }

    private function dispatchAutomationStartCycle(GrowCycle $cycle): void
    {
        if (! $this->isGrowCycleStartDispatchEnabled()) {
            return;
        }

        $zoneId = (int) $cycle->zone_id;
        $cycleId = (int) $cycle->id;
        if ($zoneId <= 0 || $cycleId <= 0) {
            return;
        }

        $cfg = $this->automationStartCycleConfig();
        $idempotencyKey = $this->buildGrowCycleStartIdempotencyKey($zoneId, $cycleId);

        $this->upsertGrowCycleStartIntent(
            zoneId: $zoneId,
            cycleId: $cycleId,
            idempotencyKey: $idempotencyKey
        );

        $response = $this->postAutomationStartCycle(
            zoneId: $zoneId,
            idempotencyKey: $idempotencyKey,
            cfg: $cfg
        );

        $taskId = trim((string) data_get($response, 'data.task_id', ''));
        Log::info('Grow cycle start-cycle dispatched to automation-engine', [
            'zone_id' => $zoneId,
            'cycle_id' => $cycleId,
            'idempotency_key' => $idempotencyKey,
            'task_id' => $taskId !== '' ? $taskId : null,
            'accepted' => (bool) data_get($response, 'data.accepted', false),
            'deduplicated' => (bool) data_get($response, 'data.deduplicated', false),
        ]);
    }

    private function isGrowCycleStartDispatchEnabled(): bool
    {
        if (app()->runningInConsole()) {
            return false;
        }

        return (bool) config('services.automation_engine.grow_cycle_start_dispatch_enabled', false);
    }

    /**
     * @return array{api_url: string, timeout_sec: float, scheduler_id: string, token: string}
     */
    private function automationStartCycleConfig(): array
    {
        return [
            'api_url' => rtrim((string) config('services.automation_engine.api_url', 'http://automation-engine:9405'), '/'),
            'timeout_sec' => max(1.0, (float) config('services.automation_engine.timeout', 2.0)),
            'scheduler_id' => (string) config('services.automation_engine.scheduler_id', 'laravel-scheduler'),
            'token' => trim((string) config('services.automation_engine.scheduler_api_token', '')),
        ];
    }

    private function buildGrowCycleStartIdempotencyKey(int $zoneId, int $cycleId): string
    {
        $base = sprintf('grow-cycle-start|zone:%d|cycle:%d', $zoneId, $cycleId);
        $digest = substr(hash('sha256', $base), 0, 24);

        return sprintf('gcs:z%d:c%d:%s', $zoneId, $cycleId, $digest);
    }

    private function upsertGrowCycleStartIntent(int $zoneId, int $cycleId, string $idempotencyKey): void
    {
        $now = Carbon::now('UTC')->setMicroseconds(0);
        $intentPayload = [
            'source' => 'laravel_grow_cycle_start',
            'task_type' => 'diagnostics',
            'workflow' => 'cycle_start',
            'topology' => 'two_tank_drip_substrate_trays',
            'grow_cycle_id' => $cycleId,
            'task_payload' => [
                'workflow' => 'cycle_start',
                'topology' => 'two_tank_drip_substrate_trays',
                'source' => 'laravel_grow_cycle_start',
                'trigger' => 'grow_cycle_start_api',
                'grow_cycle_id' => $cycleId,
            ],
        ];

        DB::table('zone_automation_intents')->upsert(
            [[
                'zone_id' => $zoneId,
                'intent_type' => 'DIAGNOSTICS_TICK',
                'payload' => json_encode($intentPayload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'idempotency_key' => $idempotencyKey,
                'status' => 'pending',
                'not_before' => $now,
                'retry_count' => 0,
                'max_retries' => 3,
                'created_at' => $now,
                'updated_at' => $now,
            ]],
            ['idempotency_key'],
            [
                'zone_id',
                'intent_type',
                'payload',
                'status',
                'not_before',
                'updated_at',
            ]
        );

        $intentExists = DB::table('zone_automation_intents')
            ->where('idempotency_key', $idempotencyKey)
            ->exists();

        Log::info('Grow cycle start intent upserted', [
            'zone_id' => $zoneId,
            'cycle_id' => $cycleId,
            'idempotency_key' => $idempotencyKey,
            'intent_exists' => $intentExists,
        ]);
    }

    /**
     * @param  array{api_url: string, timeout_sec: float, scheduler_id: string, token: string}  $cfg
     * @return array<string, mixed>
     */
    private function postAutomationStartCycle(int $zoneId, string $idempotencyKey, array $cfg): array
    {
        if ($cfg['token'] === '') {
            throw new \RuntimeException('automation_engine_scheduler_token_missing');
        }

        $headers = [
            'Accept' => 'application/json',
            'X-Trace-Id' => Str::lower((string) Str::uuid()),
            'X-Scheduler-Id' => $cfg['scheduler_id'],
            'Authorization' => 'Bearer '.$cfg['token'],
        ];

        try {
            /** @var Response $response */
            $response = Http::acceptJson()
                ->timeout($cfg['timeout_sec'])
                ->withHeaders($headers)
                ->post($cfg['api_url'].'/zones/'.$zoneId.'/start-cycle', [
                    'source' => 'laravel_grow_cycle_start',
                    'idempotency_key' => $idempotencyKey,
                ]);
        } catch (ConnectionException $e) {
            throw new \RuntimeException('automation_engine_start_cycle_connection_error: '.$e->getMessage(), 0, $e);
        }

        if (! $response->successful()) {
            throw new \RuntimeException(sprintf(
                'automation_engine_start_cycle_http_error_v2:%d:%s',
                $response->status(),
                (string) $response->body()
            ));
        }

        $decoded = $response->json();
        if (! is_array($decoded)) {
            throw new \RuntimeException('automation_engine_start_cycle_invalid_payload');
        }

        return $decoded;
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
            $revision = $cycle->recipeRevision;
            if (! $revision) {
                throw new \DomainException('Cycle must have a recipe revision to advance stage');
            }

            $timeline = $this->buildStageTimeline($revision);
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
     * Вычислить ожидаемую дату сбора урожая
     */
    public function computeExpectedHarvest(GrowCycle $cycle): void
    {
        $revision = $cycle->recipeRevision;
        if (! $revision) {
            return;
        }

        $plantingAt = $cycle->planting_at ?? $cycle->started_at;
        if (! $plantingAt) {
            return;
        }

        $timeline = $this->buildStageTimeline($revision);
        $totalHours = $timeline['total_hours'];
        if ($totalHours > 0) {
            $baseTime = $plantingAt instanceof Carbon ? $plantingAt->copy() : Carbon::parse($plantingAt);
            $expectedHarvestAt = $baseTime->addSeconds((int) round($totalHours * 3600));
            $cycle->update(['expected_harvest_at' => $expectedHarvestAt]);
        }
    }

    /**
     * Построить последовательность стадий по фазам ревизии
     *
     * @return array{segments: array<int, array{code: string, name: string, phase_indices: array<int>, duration_hours: float, ui_meta: array|null}>, total_hours: float}
     */
    public function buildStageTimeline(RecipeRevision $revision): array
    {
        $templates = GrowStageTemplate::orderBy('order_index')->get();
        if ($templates->isEmpty()) {
            $this->createDefaultStageTemplates();
            $templates = GrowStageTemplate::orderBy('order_index')->get();
        }

        $templatesById = $templates->keyBy('id');
        $templatesByCode = $templates->keyBy('code');

        $phases = $revision->phases()->orderBy('phase_index')->get();
        $segments = [];
        $totalSeconds = 0;

        foreach ($phases as $phase) {
            $template = $this->resolveStageTemplate($revision, $phase, $templatesById, $templatesByCode);
            $code = $template?->code ?? 'VEG';
            $name = $template?->name ?? 'Вегетация';
            $uiMeta = $template?->ui_meta;

            $durationHours = (float) ($phase->duration_hours
                ?? ($phase->duration_days ? $phase->duration_days * 24 : 0));
            $durationSeconds = (int) round($durationHours * 3600);
            $durationHoursNormalized = $durationSeconds / 3600;

            $totalSeconds += $durationSeconds;

            $lastIndex = count($segments) - 1;
            if ($lastIndex >= 0 && $segments[$lastIndex]['code'] === $code) {
                $segments[$lastIndex]['phase_indices'][] = $phase->phase_index;
                $segments[$lastIndex]['duration_hours'] += $durationHoursNormalized;
            } else {
                $segments[] = [
                    'code' => $code,
                    'name' => $name,
                    'phase_indices' => [$phase->phase_index],
                    'duration_hours' => $durationHoursNormalized,
                    'ui_meta' => $uiMeta,
                ];
            }
        }

        return [
            'segments' => $segments,
            'total_hours' => $totalSeconds / 3600,
        ];
    }

    private function resolveStageTemplate(
        RecipeRevision $revision,
        RecipeRevisionPhase $phase,
        \Illuminate\Support\Collection $templatesById,
        \Illuminate\Support\Collection $templatesByCode
    ): ?GrowStageTemplate {
        if ($phase->stage_template_id && $templatesById->has($phase->stage_template_id)) {
            return $templatesById->get($phase->stage_template_id);
        }

        $code = $this->inferStageCode($revision->recipe?->name ?? '', $phase->name ?? '', $phase->phase_index);

        return $templatesByCode->get($code)
            ?? $templatesByCode->get('VEG')
            ?? $templatesById->first();
    }

    private function inferStageCode(string $recipeName, string $phaseName, int $phaseIndex): string
    {
        $normalizedPhase = mb_strtolower(trim($phaseName));
        $normalizedRecipe = mb_strtolower(trim($recipeName));

        $mapping = [
            'GERMINATION' => ['проращ', 'germin'],
            'PLANTING' => ['посадка', 'посев', 'seed', 'семена', 'sowing'],
            'ROOTING' => ['укоренение', 'rooting', 'root', 'seedling', 'рассада', 'ростки', 'sprouting'],
            'VEG' => ['вега', 'вегетация', 'vegetative', 'veg', 'growth', 'рост', 'вегетативный', 'vegetation'],
            'FLOWER' => ['цветение', 'flowering', 'flower', 'bloom', 'blooming', 'цвет', 'floral'],
            'FRUIT' => ['плод', 'созрев', 'fruit'],
            'HARVEST' => ['сбор', 'harvest', 'finishing', 'finish', 'урожай', 'harvesting'],
        ];

        foreach ($mapping as $code => $keywords) {
            foreach ($keywords as $keyword) {
                if ($normalizedPhase !== '' && str_contains($normalizedPhase, $keyword)) {
                    return $code;
                }
            }
        }

        if (str_contains($normalizedRecipe, 'салат') || str_contains($normalizedRecipe, 'lettuce')) {
            return match ($phaseIndex) {
                0 => 'GERMINATION',
                1 => 'VEG',
                default => 'HARVEST',
            };
        }

        if (str_contains($normalizedRecipe, 'томат') || str_contains($normalizedRecipe, 'tomato')) {
            return match ($phaseIndex) {
                0 => 'GERMINATION',
                1 => 'VEG',
                2 => 'FLOWER',
                default => 'FRUIT',
            };
        }

        $fallbacks = ['PLANTING', 'ROOTING', 'VEG', 'FLOWER', 'FRUIT', 'HARVEST'];

        return $fallbacks[min($phaseIndex, count($fallbacks) - 1)] ?? 'VEG';
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
            $this->syncZoneStatus($zone, 'PAUSED');

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
            $this->syncZoneStatus($zone, 'RUNNING');

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
            $this->syncZoneStatus($zone, 'NEW');

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
            $this->syncZoneStatus($zone, 'NEW');

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

    private function syncZoneStatus(Zone $zone, string $status): void
    {
        if ($zone->status === $status) {
            return;
        }

        $zone->update(['status' => $status]);
        $zone->refresh();
        event(new ZoneUpdated($zone));
    }

    /**
     * Переход на следующую фазу
     */
    public function advancePhase(GrowCycle $cycle, int $userId): GrowCycle
    {
        $revision = $cycle->recipeRevision;
        if (! $revision) {
            throw new \DomainException('Cycle has no recipe revision');
        }

        $currentPhase = $cycle->currentPhase;
        if (! $currentPhase) {
            throw new \DomainException('Cycle has no current phase');
        }

        // Получаем шаблон текущей фазы для поиска следующей
        $currentPhaseTemplate = $currentPhase->recipeRevisionPhase;
        if (! $currentPhaseTemplate) {
            throw new \DomainException('Current phase has no template reference');
        }

        // Находим следующую фазу в шаблоне
        $nextPhaseTemplate = $revision->phases()
            ->where('phase_index', '>', $currentPhaseTemplate->phase_index)
            ->orderBy('phase_index')
            ->first();

        if (! $nextPhaseTemplate) {
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
                'trigger_type' => 'MANUAL',
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
        if (! $revision) {
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
                'trigger_type' => 'MANUAL',
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

                if (! $firstPhaseTemplate) {
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
                    'trigger_type' => 'RECIPE_REVISION_CHANGED',
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
     * @param  GrowCycle|null  $cycle  Цикл (может быть null при создании цикла)
     * @param  RecipeRevisionPhase  $templatePhase  Шаблонная фаза
     * @param  Carbon|null  $startedAt  Время начала фазы
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
            'nutrient_program_code' => $templatePhase->nutrient_program_code,
            'nutrient_mode' => $templatePhase->nutrient_mode,
            'nutrient_npk_ratio_pct' => $templatePhase->nutrient_npk_ratio_pct,
            'nutrient_calcium_ratio_pct' => $templatePhase->nutrient_calcium_ratio_pct,
            'nutrient_magnesium_ratio_pct' => $templatePhase->nutrient_magnesium_ratio_pct,
            'nutrient_micro_ratio_pct' => $templatePhase->nutrient_micro_ratio_pct,
            'nutrient_npk_dose_ml_l' => $templatePhase->nutrient_npk_dose_ml_l,
            'nutrient_calcium_dose_ml_l' => $templatePhase->nutrient_calcium_dose_ml_l,
            'nutrient_magnesium_dose_ml_l' => $templatePhase->nutrient_magnesium_dose_ml_l,
            'nutrient_micro_dose_ml_l' => $templatePhase->nutrient_micro_dose_ml_l,
            'nutrient_npk_product_id' => $templatePhase->nutrient_npk_product_id,
            'nutrient_calcium_product_id' => $templatePhase->nutrient_calcium_product_id,
            'nutrient_magnesium_product_id' => $templatePhase->nutrient_magnesium_product_id,
            'nutrient_micro_product_id' => $templatePhase->nutrient_micro_product_id,
            'nutrient_dose_delay_sec' => $templatePhase->nutrient_dose_delay_sec,
            'nutrient_ec_stop_tolerance' => $templatePhase->nutrient_ec_stop_tolerance,
            'nutrient_solution_volume_l' => $templatePhase->nutrient_solution_volume_l,
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
