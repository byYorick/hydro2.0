<?php

namespace App\Console\Commands;

use App\Models\DeviceNode;
use App\Services\AlertService;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Log;

class ExpirePendingNodeBindings extends Command
{
    protected $signature = 'nodes:expire-pending-bindings
                            {--ttl-minutes= : Override config pending_bind_ttl_minutes}
                            {--dry-run : List expired pending binds without clearing them}';

    protected $description = 'Expire stuck pending_zone_id binds that exceeded TTL (offline / namespace mismatch)';

    public function handle(AlertService $alertService): int
    {
        $ttlMinutes = (int) ($this->option('ttl-minutes') ?: config('hydro.pending_bind_ttl_minutes', 30));
        $ttlMinutes = max(1, $ttlMinutes);
        $dryRun = (bool) $this->option('dry-run');
        $cutoff = now()->subMinutes($ttlMinutes);

        $this->info("Expiring pending binds older than {$ttlMinutes} minutes (cutoff: {$cutoff->toIso8601String()})");

        // Только pending_zone_set_at: legacy backfill выполнен в миграции
        // 2026_07_20_133319_add_pending_zone_set_at_to_nodes_table.
        $candidates = DeviceNode::query()
            ->whereNotNull('pending_zone_id')
            ->whereNull('zone_id')
            ->whereNotNull('pending_zone_set_at')
            ->where('pending_zone_set_at', '<', $cutoff)
            ->orderBy('id')
            ->get();

        if ($candidates->isEmpty()) {
            $this->info('No expired pending binds found');

            return self::SUCCESS;
        }

        $this->info("Found {$candidates->count()} expired pending bind(s)");
        $expired = 0;

        foreach ($candidates as $node) {
            $pendingZoneId = $node->pending_zone_id;
            $setAt = $node->pending_zone_set_at?->toIso8601String();

            if ($dryRun) {
                $this->line("dry-run: node_id={$node->id} uid={$node->uid} pending_zone_id={$pendingZoneId} set_at={$setAt}");

                continue;
            }

            $node->pending_zone_id = null;
            $node->save();

            Log::warning('Expired stuck pending zone bind', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'hardware_id' => $node->hardware_id,
                'expired_pending_zone_id' => $pendingZoneId,
                'pending_zone_set_at' => $setAt,
                'ttl_minutes' => $ttlMinutes,
                'reason' => 'pending_bind_ttl_exceeded',
            ]);

            try {
                $alertService->createOrUpdateActive([
                    'source' => 'backend',
                    'code' => 'node_pending_bind_expired',
                    'type' => 'Pending node bind expired',
                    'status' => 'ACTIVE',
                    'zone_id' => $pendingZoneId,
                    'node_uid' => $node->uid,
                    'details' => [
                        'node_id' => $node->id,
                        'hardware_id' => $node->hardware_id,
                        'expired_pending_zone_id' => $pendingZoneId,
                        'pending_zone_set_at' => $setAt,
                        'ttl_minutes' => $ttlMinutes,
                        'retry' => 'Re-assign node to zone via UI (PATCH zone_id) to restart pending bind',
                    ],
                ]);
            } catch (\Throwable $e) {
                Log::error('Failed to create alert for expired pending bind', [
                    'node_id' => $node->id,
                    'error' => $e->getMessage(),
                ]);
            }

            $expired++;
            $this->line("expired: node_id={$node->id} uid={$node->uid} pending_zone_id={$pendingZoneId}");
        }

        $this->info($dryRun ? "Dry-run complete ({$candidates->count()} candidate(s))" : "Expired {$expired} pending bind(s)");

        return self::SUCCESS;
    }
}
