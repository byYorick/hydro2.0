<?php

namespace App\Services\GreenhouseClimate;

use App\Models\Greenhouse;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class GreenhouseClimateDispatchService
{
    /**
     * Создаёт intent (если ещё нет) и будит automation-engine для просроченных теплиц.
     */
    public function dispatchDue(): void
    {
        $base = rtrim((string) config('services.automation_engine.api_url'), '/');
        $token = (string) config('services.automation_engine.scheduler_api_token');
        if ($base === '' || $token === '') {
            return;
        }

        $timeout = (float) config('services.automation_engine.timeout', 2.0);
        $ids = Greenhouse::query()->pluck('id')->all();
        $now = CarbonImmutable::now('UTC');

        foreach ($ids as $greenhouseId) {
            $greenhouseId = (int) $greenhouseId;
            $pendingIntent = $this->pendingIntent($greenhouseId);
            if ($pendingIntent === null && ! $this->shouldDispatch($greenhouseId, $now)) {
                continue;
            }

            $activeIntent = $pendingIntent ?? $this->createPendingIntent($greenhouseId, $now);
            if ($activeIntent === null || $activeIntent->status !== 'pending') {
                continue;
            }

            $idempotencyKey = (string) $activeIntent->idempotency_key;
            $url = $base.'/greenhouses/'.$greenhouseId.'/start-climate-tick';
            try {
                $response = Http::timeout($timeout)
                    ->withToken($token)
                    ->acceptJson()
                    ->post($url, [
                        'source' => 'laravel_scheduler',
                        'idempotency_key' => $idempotencyKey,
                    ]);
                if (! $response->successful()) {
                    Log::warning('greenhouse_climate_dispatch_http_error', [
                        'greenhouse_id' => $greenhouseId,
                        'status' => $response->status(),
                        'body' => $response->body(),
                    ]);
                }
            } catch (\Throwable $e) {
                Log::warning('greenhouse_climate_dispatch_exception', [
                    'greenhouse_id' => $greenhouseId,
                    'error' => $e->getMessage(),
                ]);
            }
        }
    }

    private function pendingIntent(int $greenhouseId): ?object
    {
        return DB::table('greenhouse_automation_intents')
            ->where('greenhouse_id', $greenhouseId)
            ->whereIn('status', ['pending', 'claimed', 'running'])
            ->orderBy('id')
            ->first();
    }

    private function createPendingIntent(int $greenhouseId, CarbonImmutable $now): ?object
    {
        $idempotencyKey = sprintf('gh-climate-%d-%s', $greenhouseId, $now->format('YmdHi'));
        DB::table('greenhouse_automation_intents')->insertOrIgnore([
            'greenhouse_id' => $greenhouseId,
            'intent_type' => 'GREENHOUSE_CLIMATE_TICK',
            'task_type' => 'greenhouse_climate_tick',
            'intent_source' => 'laravel_scheduler',
            'idempotency_key' => $idempotencyKey,
            'status' => 'pending',
            'not_before' => $now,
            'retry_count' => 0,
            'max_retries' => 3,
            'created_at' => $now,
            'updated_at' => $now,
        ]);

        return $this->pendingIntent($greenhouseId);
    }

    private function shouldDispatch(int $greenhouseId, CarbonImmutable $now): bool
    {
        $row = DB::table('greenhouse_automation_state')->where('greenhouse_id', $greenhouseId)->first();
        if ($row === null) {
            return true;
        }
        $next = $row->next_scheduled_tick_at ?? null;
        if ($next === null) {
            return true;
        }

        return CarbonImmutable::parse((string) $next, 'UTC')->lte($now);
    }
}
