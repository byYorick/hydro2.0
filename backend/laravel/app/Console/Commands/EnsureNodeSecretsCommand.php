<?php

namespace App\Console\Commands;

use App\Jobs\PublishNodeConfigJob;
use App\Models\DeviceNode;
use App\Services\NodeSecretService;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Log;

/**
 * Backfill per-node HMAC secrets (nodes.config.node_secret).
 *
 * Idempotent: nodes that already have a non-empty node_secret are skipped.
 * Never logs the secret value.
 *
 * Firmware note: nodes that still use the shared NODE_DEFAULT_SECRET in NVS will
 * reject HMAC until they receive the new secret via NodeConfig. By default this
 * command dispatches PublishNodeConfigJob for assigned/pending nodes (best-effort).
 * Use --no-republish only when you intentionally defer config publish.
 */
class EnsureNodeSecretsCommand extends Command
{
    protected $signature = 'nodes:ensure-secrets
                            {--dry-run : List nodes missing secrets without writing}
                            {--no-republish : Skip PublishNodeConfigJob after backfill}';

    protected $description = 'Ensure every node has config.node_secret; optionally republish NodeConfig to firmware';

    public function handle(NodeSecretService $nodeSecretService): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $noRepublish = (bool) $this->option('no-republish');

        $this->info('Scanning nodes for missing config.node_secret…');

        $candidates = DeviceNode::query()
            ->where(function ($query): void {
                $query->whereNull('config')
                    ->orWhereRaw("COALESCE(config->>'node_secret', '') = ''");
            })
            ->orderBy('id')
            ->get();

        if ($candidates->isEmpty()) {
            $this->info('All nodes already have node_secret');

            return self::SUCCESS;
        }

        $this->info("Found {$candidates->count()} node(s) without node_secret");

        $ensured = 0;
        $republishQueued = 0;

        foreach ($candidates as $node) {
            if ($dryRun) {
                $this->line("dry-run: node_id={$node->id} uid={$node->uid} zone_id=".($node->zone_id ?? 'null'));

                continue;
            }

            $nodeSecretService->ensureOnNode($node);
            $node->save();
            $ensured++;

            Log::info('Backfilled per-node node_secret', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
            ]);

            $this->line("ensured: node_id={$node->id} uid={$node->uid}");

            if ($noRepublish) {
                continue;
            }

            $assigned = $node->zone_id !== null || $node->pending_zone_id !== null;
            if (! $assigned) {
                continue;
            }

            try {
                PublishNodeConfigJob::dispatch($node->id);
                $republishQueued++;
                Log::info('Queued NodeConfig republish after secret backfill', [
                    'node_id' => $node->id,
                    'node_uid' => $node->uid,
                    'zone_id' => $node->zone_id,
                    'pending_zone_id' => $node->pending_zone_id,
                ]);
            } catch (\Throwable $e) {
                Log::warning('Failed to queue NodeConfig republish after secret backfill', [
                    'node_id' => $node->id,
                    'node_uid' => $node->uid,
                    'error' => $e->getMessage(),
                ]);
                $this->warn("republish queue failed: node_id={$node->id} uid={$node->uid}");
            }
        }

        if ($dryRun) {
            $this->info("Dry-run complete ({$candidates->count()} candidate(s))");
            $this->comment('Backfill + republish are paired so firmware receives the new secret via NodeConfig.');

            return self::SUCCESS;
        }

        $this->info("Ensured secrets for {$ensured} node(s)");
        if ($noRepublish) {
            $this->warn('Skipped NodeConfig republish (--no-republish). Firmware may still use legacy shared secret until config is published.');
        } else {
            $this->info("Queued NodeConfig republish for {$republishQueued} assigned/pending node(s)");
        }

        return self::SUCCESS;
    }
}
