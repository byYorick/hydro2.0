<?php

namespace App\Services;

use App\Models\Command;
use Carbon\Carbon;
use Carbon\CarbonInterface;

/**
 * Собирает диагностический payload для command_status TIMEOUT.
 */
class CommandTimeoutDiagnosticsBuilder
{
    /**
     * @return array<string, mixed>
     */
    public function fromCommand(Command $command): array
    {
        $command->loadMissing('node');
        $node = $command->node;
        $nodeLastSeenAt = $node?->last_seen_at ? Carbon::parse($node->last_seen_at) : null;
        $nodeLastSeenAgeSec = $nodeLastSeenAt instanceof CarbonInterface
            ? (int) max(0, $nodeLastSeenAt->diffInSeconds(now()))
            : null;
        $nodeStatus = $node?->status ? strtolower((string) $node->status) : null;
        $nodeOfflineTimeoutSec = max(1, (int) env('NODE_OFFLINE_TIMEOUT_SEC', 120));
        $timeoutMinutes = (int) config('commands.timeout_minutes', 5);

        return [
            'command_id' => $command->id,
            'command' => $command->cmd,
            'source' => $command->source,
            'channel' => $command->channel,
            'node_uid' => $node?->uid,
            'node_status' => $nodeStatus,
            'node_last_seen_at' => $nodeLastSeenAt?->toIso8601String(),
            'node_last_seen_age_sec' => $nodeLastSeenAgeSec,
            'node_stale_online_candidate' => $nodeStatus === 'online'
                && $nodeLastSeenAgeSec !== null
                && $nodeLastSeenAgeSec >= $nodeOfflineTimeoutSec,
            'timeout_minutes' => $timeoutMinutes,
            'sent_at' => $command->sent_at,
        ];
    }
}
