<?php

namespace App\Services;

use App\Enums\NodeLifecycleState;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\Zone;
use Illuminate\Database\Eloquent\Collection;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;
use RuntimeException;

class SiteInfrastructureService
{
    public const SITE_GREENHOUSE_UID = 'site';

    public const SITE_WEATHER_ZONE_UID = 'wx';

    public function ensureSiteGreenhouse(): Greenhouse
    {
        $greenhouse = Greenhouse::query()->where('uid', self::SITE_GREENHOUSE_UID)->first();
        if ($greenhouse) {
            if (! $greenhouse->is_system) {
                $greenhouse->forceFill(['is_system' => true])->save();
            }

            return $greenhouse;
        }

        return Greenhouse::query()->create([
            'uid' => self::SITE_GREENHOUSE_UID,
            'name' => 'Site Infrastructure',
            'timezone' => 'UTC',
            'type' => 'system',
            'description' => 'Hidden system greenhouse for site-level devices (weather stations).',
            'provisioning_token' => 'gh_'.Str::random(32),
            'is_system' => true,
        ]);
    }

    public function ensureWeatherZone(): Zone
    {
        $site = $this->ensureSiteGreenhouse();
        $zone = Zone::query()->where('uid', self::SITE_WEATHER_ZONE_UID)->first();
        if ($zone) {
            if ((int) $zone->greenhouse_id !== (int) $site->id) {
                $zone->forceFill(['greenhouse_id' => $site->id])->save();
            }

            return $zone;
        }

        return Zone::query()->create([
            'uid' => self::SITE_WEATHER_ZONE_UID,
            'name' => 'Site Weather',
            'description' => 'MQTT transport anchor for site-level weather stations.',
            'status' => 'online',
            'greenhouse_id' => $site->id,
        ]);
    }

    /**
     * @return Collection<int, DeviceNode>
     */
    public function listWeatherStations(): Collection
    {
        $zone = $this->ensureWeatherZone();

        return DeviceNode::query()
            ->where('zone_id', $zone->id)
            ->with(['channels:id,node_id,channel,type,metric,unit'])
            ->orderBy('id')
            ->get(['id', 'uid', 'name', 'type', 'zone_id', 'status', 'lifecycle_state', 'fw_version', 'hardware_id', 'last_seen_at', 'created_at', 'updated_at']);
    }

    public function assignWeatherStation(DeviceNode $node): DeviceNode
    {
        if (strtolower((string) $node->type) !== 'climate') {
            throw new \DomainException('Site weather station must be nodes.type=climate.');
        }

        $zone = $this->ensureWeatherZone();

        if ($node->zone_id !== null && (int) $node->zone_id !== (int) $zone->id) {
            $currentZone = Zone::query()->find($node->zone_id);
            $currentGh = $currentZone?->greenhouse;
            if ($currentGh && ! $currentGh->is_system) {
                throw new \DomainException('Node is already assigned to a user greenhouse/zone. Detach it first.');
            }
        }

        return DB::transaction(function () use ($node, $zone) {
            $node->zone_id = $zone->id;
            $node->pending_zone_id = null;
            $node->lifecycle_state = NodeLifecycleState::ASSIGNED_TO_ZONE;
            $node->save();

            return $node->fresh(['channels:id,node_id,channel,type,metric,unit']);
        });
    }

    public function unassignWeatherStation(DeviceNode $node): DeviceNode
    {
        $zone = $this->ensureWeatherZone();
        if ((int) $node->zone_id !== (int) $zone->id) {
            throw new \DomainException('Node is not a site weather station.');
        }

        return DB::transaction(function () use ($node) {
            Greenhouse::query()
                ->where('shared_weather_station_node_id', $node->id)
                ->update(['shared_weather_station_node_id' => null]);

            $node->zone_id = null;
            $node->pending_zone_id = null;
            $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
            $node->save();

            return $node->fresh();
        });
    }

    public function assertSelectableWeatherStation(?int $nodeId): void
    {
        if ($nodeId === null) {
            return;
        }

        $zone = $this->ensureWeatherZone();
        $exists = DeviceNode::query()
            ->where('id', $nodeId)
            ->where('zone_id', $zone->id)
            ->whereRaw('lower(type) = ?', ['climate'])
            ->exists();

        if (! $exists) {
            throw new \DomainException('shared_weather_station_node_id must reference a site weather station (climate node in site/wx).');
        }
    }

    public function siteGreenhouseId(): int
    {
        $id = $this->ensureSiteGreenhouse()->id;
        if ($id === null) {
            throw new RuntimeException('Site greenhouse id missing.');
        }

        return (int) $id;
    }
}
