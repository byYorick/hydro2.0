<?php

namespace App\Support;

use Illuminate\Support\Facades\DB;

final class ZoneNodeChannelScope
{
    public static function belongsToZone(int $zoneId, int $channelId): bool
    {
        return DB::table('node_channels as nc')
            ->join('nodes as n', 'n.id', '=', 'nc.node_id')
            ->leftJoin('channel_bindings as cb', 'cb.node_channel_id', '=', 'nc.id')
            ->leftJoin('infrastructure_instances as ii', function ($join): void {
                $join->on('ii.id', '=', 'cb.infrastructure_instance_id')
                    ->where('ii.owner_type', '=', 'zone');
            })
            ->where('nc.id', $channelId)
            ->where(function ($query) use ($zoneId): void {
                $query->where('n.zone_id', $zoneId)
                    ->orWhere('n.pending_zone_id', $zoneId)
                    ->orWhere('ii.owner_id', $zoneId);
            })
            ->exists();
    }
}
