<?php

declare(strict_types=1);

namespace App\Services\GrowCycle;

use App\Models\DeviceNode;
use App\Models\GrowCycle;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationRuntimeConfigService;
use Carbon\Carbon;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\Response;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

/**
 * Диспатчит `/zones/{id}/start-cycle` в AE3 после коммита нового grow cycle.
 *
 * Публикует intent в `zone_automation_intents` для durability, затем POST-ит
 * в automation-engine с retry/backoff для transient 404 (zone not yet propagated).
 * При окончательном fail помечает intent failed с структурированным error_code.
 */
class GrowCycleAutomationDispatcher
{
    private const TWO_TANK_REQUIRED_NODE_TYPES = ['irrig', 'ph', 'ec'];

    private const TWO_TANK_REQUIRED_CHANNELS_BY_TYPE = [
        'irrig' => [
            'pump_main',
            'valve_clean_fill',
            'valve_solution_fill',
            'valve_solution_supply',
            'valve_irrigation',
            'level_clean_max',
            'level_clean_min',
            'level_solution_max',
            'level_solution_min',
        ],
        'ph' => ['ph_sensor'],
        'ec' => ['ec_sensor'],
    ];

    public function __construct(
        private readonly AutomationRuntimeConfigService $runtimeConfig,
        private readonly AutomationConfigDocumentService $documents,
    ) {}

    public function dispatchAutomationStartCycle(GrowCycle $cycle): void
    {
        if (! $this->isEnabled()) {
            return;
        }

        $zoneId = (int) $cycle->zone_id;
        $cycleId = (int) $cycle->id;
        if ($zoneId <= 0 || $cycleId <= 0) {
            return;
        }

        if (! $this->shouldDispatchForZone($zoneId)) {
            return;
        }

        try {
            $cfg = $this->automationStartCycleConfig();
            $idempotencyKey = $this->buildIdempotencyKey($zoneId, $cycleId);

            $this->upsertStartIntent($zoneId, $cycleId, $idempotencyKey);

            $attempt = 0;
            $maxAttempts = $this->maxAttempts();
            $lastError = null;

            while ($attempt < $maxAttempts) {
                $attempt++;

                try {
                    $response = $this->postStartCycle($zoneId, $idempotencyKey, $cfg);
                    $taskId = trim((string) data_get($response, 'data.task_id', ''));
                    Log::info('Grow cycle start-cycle dispatched to automation-engine', [
                        'zone_id' => $zoneId,
                        'cycle_id' => $cycleId,
                        'idempotency_key' => $idempotencyKey,
                        'task_id' => $taskId !== '' ? $taskId : null,
                        'accepted' => (bool) data_get($response, 'data.accepted', false),
                        'deduplicated' => (bool) data_get($response, 'data.deduplicated', false),
                        'attempt' => $attempt,
                    ]);

                    return;
                } catch (\Throwable $e) {
                    $lastError = $e;
                    if ($attempt >= $maxAttempts || ! $this->shouldRetry($e, $zoneId)) {
                        break;
                    }

                    usleep($this->retryDelayMs($attempt) * 1000);
                }
            }

            $this->markIntentFailed($zoneId, $idempotencyKey, $lastError);

            Log::warning('Grow cycle start-cycle dispatch failed after cycle commit', [
                'zone_id' => $zoneId,
                'cycle_id' => $cycleId,
                'idempotency_key' => $idempotencyKey,
                'attempts' => $attempt,
                'error' => $lastError?->getMessage(),
                'exception_type' => $lastError !== null ? get_class($lastError) : null,
            ]);
        } catch (\Throwable $e) {
            Log::warning('Grow cycle start-cycle dispatch failed before request dispatch', [
                'zone_id' => $zoneId,
                'cycle_id' => $cycleId,
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);
        }
    }

    public function buildIdempotencyKey(int $zoneId, int $cycleId): string
    {
        $base = sprintf('grow-cycle-start|zone:%d|cycle:%d', $zoneId, $cycleId);
        $digest = substr(hash('sha256', $base), 0, 24);

        return sprintf('gcs:z%d:c%d:%s', $zoneId, $cycleId, $digest);
    }

    protected function isEnabled(): bool
    {
        return (bool) $this->runtimeConfig->automationEngineValue('grow_cycle_start_dispatch_enabled', false);
    }

    protected function shouldDispatchForZone(int $zoneId): bool
    {
        $zone = Zone::query()->find($zoneId);
        if (! $zone) {
            return false;
        }

        if (strtolower(trim((string) $zone->automation_runtime)) !== 'ae3') {
            Log::info('Skipping grow cycle start-cycle dispatch for non-AE3 zone', [
                'zone_id' => $zoneId,
                'automation_runtime' => $zone->automation_runtime,
            ]);

            return false;
        }

        $missingRequirements = $this->resolveMissingRequirements($zoneId);
        if ($missingRequirements === []) {
            return true;
        }

        Log::info('Skipping grow cycle start-cycle dispatch because zone topology is not ready', [
            'zone_id' => $zoneId,
            'missing_requirements' => $missingRequirements,
        ]);

        return false;
    }

    /**
     * @return list<string>
     */
    private function resolveMissingRequirements(int $zoneId): array
    {
        $onlineNodes = DeviceNode::query()
            ->where('zone_id', $zoneId)
            ->where('status', 'online')
            ->get(['id', 'type']);

        $missingRequirements = [];
        $nodeIdsByType = [];

        foreach ($onlineNodes as $node) {
            $type = strtolower(trim((string) $node->type));
            if ($type === '') {
                continue;
            }
            $nodeIdsByType[$type] ??= [];
            $nodeIdsByType[$type][] = (int) $node->id;
        }

        foreach (self::TWO_TANK_REQUIRED_NODE_TYPES as $requiredType) {
            if (empty($nodeIdsByType[$requiredType])) {
                $missingRequirements[] = 'node_type:'.$requiredType;
            }
        }

        foreach (self::TWO_TANK_REQUIRED_CHANNELS_BY_TYPE as $type => $requiredChannels) {
            $nodeIds = $nodeIdsByType[$type] ?? [];
            if ($nodeIds === []) {
                continue;
            }

            $availableChannels = NodeChannel::query()
                ->whereIn('node_id', $nodeIds)
                ->where('is_active', true)
                ->pluck('channel')
                ->map(static fn ($channel): string => strtolower(trim((string) $channel)))
                ->filter(static fn (string $channel): bool => $channel !== '')
                ->unique()
                ->all();

            foreach ($requiredChannels as $requiredChannel) {
                if (! in_array($requiredChannel, $availableChannels, true)) {
                    $missingRequirements[] = sprintf('channel:%s:%s', $type, $requiredChannel);
                }
            }
        }

        sort($missingRequirements);

        return $missingRequirements;
    }

    private function shouldRetry(\Throwable $error, int $zoneId): bool
    {
        $message = $error->getMessage();

        $isTransientZoneNotFound = str_contains($message, 'automation_engine_start_cycle_http_error_v2:404:')
            && str_contains($message, sprintf("Zone '%d' not found", $zoneId));
        if ($isTransientZoneNotFound) {
            return true;
        }

        $isZoneBusy = str_contains($message, 'automation_engine_start_cycle_http_error_v2:409:')
            && str_contains($message, '"start_cycle_zone_busy"');

        return $isZoneBusy;
    }

    private function maxAttempts(): int
    {
        return 5;
    }

    protected function retryDelayMs(int $attempt): int
    {
        return min(750, max(1, $attempt) * 150);
    }

    /**
     * @return array{api_url: string, timeout_sec: float, scheduler_id: string, token: string}
     */
    protected function automationStartCycleConfig(): array
    {
        $schedulerCfg = $this->runtimeConfig->schedulerConfig();

        return [
            'api_url' => (string) ($schedulerCfg['api_url'] ?? 'http://automation-engine:9405'),
            'timeout_sec' => (float) ($schedulerCfg['timeout_sec'] ?? 2.0),
            'scheduler_id' => (string) ($schedulerCfg['scheduler_id'] ?? 'laravel-scheduler'),
            'token' => trim((string) ($schedulerCfg['token'] ?? '')),
        ];
    }

    private function upsertStartIntent(int $zoneId, int $cycleId, string $idempotencyKey): void
    {
        $this->documents->ensureZoneDefaults($zoneId);

        $now = Carbon::now('UTC')->setMicroseconds(0);

        DB::table('zone_automation_intents')->upsert(
            [[
                'zone_id' => $zoneId,
                'intent_type' => 'DIAGNOSTICS_TICK',
                'task_type' => 'cycle_start',
                'topology' => 'two_tank_drip_substrate_trays',
                'irrigation_mode' => null,
                'irrigation_requested_duration_sec' => null,
                'intent_source' => 'laravel_grow_cycle_start',
                'idempotency_key' => $idempotencyKey,
                'status' => 'pending',
                'not_before' => $now,
                'retry_count' => 0,
                'max_retries' => 3,
                'created_at' => $now,
                'updated_at' => $now,
            ]],
            ['zone_id', 'idempotency_key'],
            [
                'zone_id',
                'intent_type',
                'task_type',
                'topology',
                'irrigation_mode',
                'irrigation_requested_duration_sec',
                'intent_source',
                'status',
                'not_before',
                'updated_at',
            ]
        );

        $intentExists = DB::table('zone_automation_intents')
            ->where('zone_id', $zoneId)
            ->where('idempotency_key', $idempotencyKey)
            ->exists();

        Log::info('Grow cycle start intent upserted', [
            'zone_id' => $zoneId,
            'cycle_id' => $cycleId,
            'idempotency_key' => $idempotencyKey,
            'intent_exists' => $intentExists,
        ]);
    }

    private function markIntentFailed(int $zoneId, string $idempotencyKey, ?\Throwable $error): void
    {
        $now = Carbon::now('UTC')->setMicroseconds(0);

        DB::table('zone_automation_intents')
            ->where('zone_id', $zoneId)
            ->where('idempotency_key', $idempotencyKey)
            ->whereIn('status', ['pending', 'claimed'])
            ->update([
                'status' => 'failed',
                'completed_at' => $now,
                'updated_at' => $now,
                'error_code' => $this->errorCode($error),
                'error_message' => $error?->getMessage(),
            ]);
    }

    private function errorCode(?\Throwable $error): string
    {
        $message = trim((string) $error?->getMessage());

        if ($message === '') {
            return 'automation_engine_start_cycle_dispatch_failed';
        }

        if (str_starts_with($message, 'automation_engine_start_cycle_connection_error:')) {
            return 'automation_engine_start_cycle_connection_error';
        }

        if (str_contains($message, 'automation_engine_start_cycle_http_error_v2:404:')
            && str_contains($message, "Zone '")) {
            return 'automation_engine_start_cycle_zone_not_found';
        }

        if (str_starts_with($message, 'automation_engine_start_cycle_http_error_v2:')) {
            if (str_contains($message, 'automation_engine_start_cycle_http_error_v2:409:')
                && str_contains($message, '"start_cycle_zone_busy"')) {
                return 'automation_engine_start_cycle_zone_busy';
            }

            return 'automation_engine_start_cycle_http_error';
        }

        return 'automation_engine_start_cycle_dispatch_failed';
    }

    /**
     * @param  array{api_url: string, timeout_sec: float, scheduler_id: string, token: string}  $cfg
     * @return array<string, mixed>
     */
    protected function postStartCycle(int $zoneId, string $idempotencyKey, array $cfg): array
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
}
