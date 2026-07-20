<?php

namespace App\Services;

use App\Exceptions\ZoneNodeAutomationBindingException;
use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Sensor;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Facades\DB;

/**
 * Fail-closed проверки перед UI-привязкой узла к зоне: дубли pH/EC телеметрии и дубли ролей полива/коррекции
 * ломают AE3 snapshot (см. ae3_snapshot_conflicting_config_values).
 */
class ZoneNodeAutomationBindingValidator
{
    /**
     * Роли инфраструктуры зоны из мастера привязки (полив + коррекция).
     *
     * @var array<string, array<int, string>>
     */
    private const WATER_AUTOMATION_ROLE_CHANNELS = [
        'pump_main' => ['pump_main'],
        'drain' => ['valve_drain', 'drain', 'drain_main', 'drain_valve'],
        'pump_acid' => ['pump_acid'],
        'pump_base' => ['pump_base'],
        'pump_a' => ['pump_a'],
        'pump_b' => ['pump_b'],
        'pump_c' => ['pump_c'],
        'pump_d' => ['pump_d'],
    ];

    /** @var array<string, string> */
    private const ROLE_LABEL_RU = [
        'pump_main' => 'основная помпа полива',
        'drain' => 'слив / дренаж',
        'pump_acid' => 'насос кислоты (коррекция pH)',
        'pump_base' => 'насос щёлочи (коррекция pH)',
        'pump_a' => 'насос EC (компонент A)',
        'pump_b' => 'насос EC (компонент B)',
        'pump_c' => 'насос EC (компонент C)',
        'pump_d' => 'насос EC (компонент D)',
    ];

    public function assertBindAllowed(DeviceNode $incomingNode, int $targetZoneId): void
    {
        $incomingId = (int) $incomingNode->id;

        $siblingIds = DeviceNode::query()
            ->where('id', '!=', $incomingId)
            ->where(function (Builder $q) use ($targetZoneId): void {
                $q->where('zone_id', $targetZoneId)
                    ->orWhere('pending_zone_id', $targetZoneId);
            })
            ->pluck('id')
            ->map(static fn ($id): int => (int) $id)
            ->all();

        if ($siblingIds === []) {
            return;
        }

        $this->assertNoDuplicatePhEcSources($targetZoneId, $incomingId, $siblingIds);
        $this->assertNoDuplicateWaterAutomationRoles($targetZoneId, $incomingId, $siblingIds);
    }

    /**
     * @param  array<int, int>  $siblingIds
     */
    private function assertNoDuplicatePhEcSources(int $targetZoneId, int $incomingId, array $siblingIds): void
    {
        $wantsPh = $this->nodeHasActiveSensorMetric($incomingId, ['PH']);
        $wantsEc = $this->nodeHasActiveSensorMetric($incomingId, ['EC', 'TDS']);

        if (! $wantsPh && ! $wantsEc) {
            return;
        }

        if ($wantsPh) {
            $blocker = $this->findSiblingBlockingPhTelemetry($targetZoneId, $siblingIds);
            if ($blocker !== null) {
                $uid = (string) ($blocker->uid ?? '');
                throw new ZoneNodeAutomationBindingException(
                    'В этой зоне уже есть источник телеметрии pH на узле '.$this->formatNodeRef($uid, (int) $blocker->id).'. '
                    .'Нельзя привязать второй узел с датчиком pH: для автоматики допустим только один активный pH на зону. '
                    .'Сначала отвяжите старый узел или выберите другую зону.'
                );
            }
        }

        if ($wantsEc) {
            $blocker = $this->findSiblingBlockingEcTelemetry($targetZoneId, $siblingIds);
            if ($blocker !== null) {
                $uid = (string) ($blocker->uid ?? '');
                throw new ZoneNodeAutomationBindingException(
                    'В этой зоне уже есть источник телеметрии EC на узле '.$this->formatNodeRef($uid, (int) $blocker->id).'. '
                    .'Нельзя привязать второй узел с датчиком EC/TDS: AE3 допускает только один активный EC на зону. '
                    .'Сначала отвяжите старый узел.'
                );
            }
        }
    }

    /**
     * @param  array<int, int>  $siblingIds
     */
    private function findSiblingBlockingPhTelemetry(int $targetZoneId, array $siblingIds): ?DeviceNode
    {
        foreach ($siblingIds as $siblingId) {
            if ($this->nodeHasActiveSensorMetric($siblingId, ['PH'])) {
                return DeviceNode::query()->select(['id', 'uid'])->find($siblingId);
            }
        }

        $nodeId = Sensor::query()
            ->where('zone_id', $targetZoneId)
            ->where('is_active', true)
            ->where('type', 'PH')
            ->whereIn('node_id', $siblingIds)
            ->orderBy('id')
            ->value('node_id');

        return $nodeId ? DeviceNode::query()->select(['id', 'uid'])->find((int) $nodeId) : null;
    }

    /**
     * @param  array<int, int>  $siblingIds
     */
    private function findSiblingBlockingEcTelemetry(int $targetZoneId, array $siblingIds): ?DeviceNode
    {
        foreach ($siblingIds as $siblingId) {
            if ($this->nodeHasActiveSensorMetric($siblingId, ['EC', 'TDS'])) {
                return DeviceNode::query()->select(['id', 'uid'])->find($siblingId);
            }
        }

        $nodeId = Sensor::query()
            ->where('zone_id', $targetZoneId)
            ->where('is_active', true)
            ->where('type', 'EC')
            ->whereIn('node_id', $siblingIds)
            ->orderBy('id')
            ->value('node_id');

        return $nodeId ? DeviceNode::query()->select(['id', 'uid'])->find((int) $nodeId) : null;
    }

    /**
     * @param  array<int, int>  $siblingIds
     */
    private function assertNoDuplicateWaterAutomationRoles(int $targetZoneId, int $incomingId, array $siblingIds): void
    {
        $incomingRoles = $this->waterAutomationRolesClaimedByChannels($incomingId);
        if ($incomingRoles === []) {
            return;
        }

        $bindings = ChannelBinding::query()
            ->select(['channel_bindings.role', 'nodes.id as bound_node_id', 'nodes.uid as bound_node_uid'])
            ->join('node_channels', 'node_channels.id', '=', 'channel_bindings.node_channel_id')
            ->join('nodes', 'nodes.id', '=', 'node_channels.node_id')
            ->join('infrastructure_instances', 'infrastructure_instances.id', '=', 'channel_bindings.infrastructure_instance_id')
            ->where('infrastructure_instances.owner_type', 'zone')
            ->where('infrastructure_instances.owner_id', $targetZoneId)
            ->whereIn('nodes.id', $siblingIds)
            ->whereIn('channel_bindings.role', array_keys(self::WATER_AUTOMATION_ROLE_CHANNELS))
            ->get();

        foreach ($bindings as $row) {
            $role = strtolower((string) ($row->role ?? ''));
            if ($role === '' || ! isset($incomingRoles[$role])) {
                continue;
            }

            $otherUid = (string) ($row->bound_node_uid ?? '');
            $otherId = (int) $row->bound_node_id;
            $label = self::ROLE_LABEL_RU[$role] ?? $role;

            throw new ZoneNodeAutomationBindingException(
                'Роль «'.$label.'» в этой зоне уже занята узлом '.$this->formatNodeRef($otherUid, $otherId).'. '
                .'Нельзя привязать второй узел с тем же исполнительным каналом. '
                .'Сначала отвяжите старый узел или снимите привязку канала в инфраструктуре зоны.'
            );
        }
    }

    /**
     * @return array<string, true>
     */
    private function waterAutomationRolesClaimedByChannels(int $nodeId): array
    {
        $channels = NodeChannel::query()
            ->where('node_id', $nodeId)
            ->where('is_active', true)
            ->whereRaw("lower(coalesce(type, '')) = 'actuator'")
            ->pluck('channel')
            ->all();

        $normalized = [];
        foreach ($channels as $ch) {
            $normalized[strtolower(trim((string) $ch))] = true;
        }

        $claimed = [];
        foreach (self::WATER_AUTOMATION_ROLE_CHANNELS as $role => $candidates) {
            foreach ($candidates as $candidate) {
                if (isset($normalized[strtolower($candidate)])) {
                    $claimed[$role] = true;
                    break;
                }
            }
        }

        return $claimed;
    }

    /**
     * @param  array<int, string>  $metricsUpper
     */
    private function nodeHasActiveSensorMetric(int $nodeId, array $metricsUpper): bool
    {
        return NodeChannel::query()
            ->where('node_id', $nodeId)
            ->where('is_active', true)
            ->whereRaw("lower(coalesce(type, '')) = 'sensor'")
            ->whereIn(DB::raw("upper(trim(coalesce(metric, '')))"), $metricsUpper)
            ->exists();
    }

    private function formatNodeRef(string $uid, int $id): string
    {
        if ($uid !== '') {
            return $uid.' (#'.$id.')';
        }

        return '#'.$id;
    }
}
