<?php

namespace App\Services\AutomationScheduler;

use App\Models\LaravelSchedulerZoneCursor;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\Log;

class ZoneCursorStore
{
    public function getCursorAt(int $zoneId): ?CarbonImmutable
    {
        if ($zoneId <= 0) {
            return null;
        }

        try {
            $cursor = LaravelSchedulerZoneCursor::query()
                ->where('zone_id', $zoneId)
                ->first(['cursor_at']);
        } catch (\Throwable $e) {
            Log::warning('Failed to load laravel scheduler zone cursor', [
                'zone_id' => $zoneId,
                'error' => $e->getMessage(),
            ]);

            return null;
        }

        if (! $cursor || ! $cursor->cursor_at) {
            return null;
        }

        return CarbonImmutable::instance($cursor->cursor_at)->utc()->setMicroseconds(0);
    }

    /**
     * @param  array<string, mixed>  $metadata
     */
    public function upsertCursor(int $zoneId, CarbonImmutable $cursorAt, string $catchupPolicy, array $metadata = []): void
    {
        if ($zoneId <= 0) {
            return;
        }

        try {
            LaravelSchedulerZoneCursor::query()->updateOrCreate(
                ['zone_id' => $zoneId],
                [
                    'cursor_at' => $cursorAt,
                    'catchup_policy' => strtolower(trim($catchupPolicy)),
                    'metadata' => $metadata,
                ],
            );
        } catch (\Throwable $e) {
            Log::warning('Failed to upsert laravel scheduler zone cursor', [
                'zone_id' => $zoneId,
                'error' => $e->getMessage(),
            ]);
        }
    }
}

