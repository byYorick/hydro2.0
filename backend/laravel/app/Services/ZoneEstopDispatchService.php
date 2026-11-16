<?php

namespace App\Services;

use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\Zone;

/** One node-wide fail-safe command per actuator node, exclusively via HL. */
class ZoneEstopDispatchService
{
    public function __construct(private readonly PythonBridgeService $bridge) {}

    public function dispatch(Zone $zone, string $action): array
    {
        $commands = [];
        $nodes = DeviceNode::query()->where('zone_id', $zone->id)
            ->where(function ($query): void {
                $query->whereIn('type', ['ph', 'ec', 'irrig', 'pump', 'relay', 'climate', 'storage_irrigation'])
                    ->orWhereHas('channels', fn ($channels) => $channels->whereRaw("LOWER(type) = 'actuator'"));
            })->orderBy('id')->get();
        foreach ($nodes as $node) {
            try {
                $id = $this->bridge->sendNodeCommand($node, [
                    'cmd' => $action === 'engage' ? 'enter_safe_mode' : 'exit_safe_mode',
                    'channel' => 'system',
                    'params' => [],
                ]);
                $commands[] = ['node_uid' => $node->uid, 'cmd_id' => $id];
            } catch (\Throwable $exception) {
                report($exception);
                // Keep the latch and make failure visible; never equate HTTP acceptance with OFF.
                $commands[] = ['node_uid' => $node->uid, 'cmd_id' => null, 'error' => 'send_failed'];
            }
        }

        return ['action' => $action, 'commands' => $commands];
    }

    public function outcome(?array $dispatch): string
    {
        if ($dispatch === null) {
            return 'pending';
        }
        $entries = $dispatch['commands'] ?? [];
        $ids = array_values(array_filter(array_column($entries, 'cmd_id')));
        $states = $ids === [] ? collect() : Command::query()->whereIn('cmd_id', $ids)->pluck('status', 'cmd_id');
        $pending = false;
        foreach ($entries as $entry) {
            if (isset($entry['error'])) {
                return 'failed';
            }
            $status = strtoupper((string) ($states[$entry['cmd_id'] ?? ''] ?? 'PENDING'));
            if (in_array($status, ['PENDING', 'QUEUED', 'SENT', 'ACK', 'RUNNING'], true)) {
                $pending = true;
            } elseif ($status !== 'DONE') {
                return 'failed';
            }
        }

        return $pending ? 'pending' : 'confirmed';
    }
}
