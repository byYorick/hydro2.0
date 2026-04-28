<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Services\AutomationConfigDocumentService;
use App\Support\PumpCalibrationCatalog;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class ZonePumpCalibrationsController extends Controller
{
    public function index(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);
        $settings = app(AutomationConfigDocumentService::class)->getSystemPayloadByLegacyNamespace('pump_calibration', true);
        $this->ensureAutoBindingsForDosingChannels($zone);

        $latestCalibrations = DB::table('pump_calibrations as p')
            ->select(
                'p.node_channel_id',
                'p.component',
                'p.ml_per_sec',
                'p.k_ms_per_ml_l',
                'p.source',
                'p.valid_from',
                'p.is_active'
            )
            ->where('p.is_active', true)
            ->whereRaw(
                'p.valid_from = (
                    SELECT MAX(p2.valid_from)
                    FROM pump_calibrations p2
                    WHERE p2.node_channel_id = p.node_channel_id
                      AND p2.is_active = TRUE
                )'
            );

        $roleOrderSql = "CASE zb.role
            WHEN 'pump_acid' THEN 1
            WHEN 'pump_base' THEN 2
            WHEN 'pump_a' THEN 3
            WHEN 'pump_b' THEN 4
            WHEN 'pump_c' THEN 5
            WHEN 'pump_d' THEN 6
            ELSE 99
        END";

        $zoneBindings = DB::table('channel_bindings as cb')
            ->join('infrastructure_instances as ii', 'ii.id', '=', 'cb.infrastructure_instance_id')
            ->where('ii.owner_type', 'zone')
            ->where('ii.owner_id', $zone->id)
            ->where('cb.direction', 'actuator')
            ->selectRaw('cb.node_channel_id, MIN(cb.role) as role')
            ->groupBy('cb.node_channel_id');

        $rows = DB::table('node_channels as nc')
            ->join('nodes as n', 'n.id', '=', 'nc.node_id')
            ->leftJoinSub($zoneBindings, 'zb', function ($join): void {
                $join->on('zb.node_channel_id', '=', 'nc.id');
            })
            ->leftJoinSub($latestCalibrations, 'pc', function ($join): void {
                $join->on('pc.node_channel_id', '=', 'nc.id');
            })
            ->where(function ($query) use ($zone): void {
                $query->where('n.zone_id', $zone->id)
                    ->orWhere('n.pending_zone_id', $zone->id)
                    ->orWhereNotNull('zb.node_channel_id');
            })
            ->where(function ($query): void {
                $query->whereIn('zb.role', PumpCalibrationCatalog::dosingRoles())
                    ->orWhereIn('pc.component', PumpCalibrationCatalog::dosingComponents());
            })
            ->selectRaw(
                "nc.id AS node_channel_id,
                 zb.role,
                 n.uid AS node_uid,
                 nc.channel,
                 COALESCE(nc.config->>'label', nc.channel) AS channel_label,
                 pc.ml_per_sec,
                 pc.component AS calibration_component,
                 pc.k_ms_per_ml_l,
                 pc.source,
                 pc.valid_from,
                 COALESCE(pc.is_active, FALSE) AS is_active,
                 CASE
                    WHEN pc.valid_from IS NULL THEN NULL
                    ELSE GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (NOW() - pc.valid_from)) / 86400))::int
                 END AS calibration_age_days"
            )
            ->orderByRaw($roleOrderSql)
            ->orderBy('nc.id')
            ->get();

        $result = $rows->map(function ($row) {
            $resolvedRole = $row->role
                ?: PumpCalibrationCatalog::roleForComponent($row->calibration_component)
                ?: 'unbound_pump';

            $resolvedComponent = $row->calibration_component
                ?: PumpCalibrationCatalog::componentForRole($resolvedRole);

            if (! PumpCalibrationCatalog::isDosingRole($resolvedRole) && ! PumpCalibrationCatalog::isDosingComponent($resolvedComponent)) {
                return null;
            }

            return [
                'node_channel_id' => (int) $row->node_channel_id,
                'role' => (string) $resolvedRole,
                'component' => (string) ($resolvedComponent ?: 'unknown'),
                'channel_label' => (string) ($row->channel_label ?? $row->channel),
                'node_uid' => (string) $row->node_uid,
                'channel' => (string) $row->channel,
                'ml_per_sec' => $row->ml_per_sec !== null ? (float) $row->ml_per_sec : null,
                'k_ms_per_ml_l' => $row->k_ms_per_ml_l !== null ? (float) $row->k_ms_per_ml_l : null,
                'source' => $row->source !== null ? (string) $row->source : null,
                'valid_from' => $row->valid_from !== null ? (string) $row->valid_from : null,
                'is_active' => (bool) $row->is_active,
                'calibration_age_days' => $row->calibration_age_days !== null ? (int) $row->calibration_age_days : null,
            ];
        })->filter()->values();

        return response()->json([
            'status' => 'ok',
            'data' => $result,
            'meta' => [
                'settings' => $settings,
            ],
        ]);
    }

    public function update(Request $request, Zone $zone, int $channelId): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);
        $settings = app(AutomationConfigDocumentService::class)->getSystemPayloadByLegacyNamespace('pump_calibration', true);

        $data = $request->validate([
            'ml_per_sec' => ['required', 'numeric', 'min:'.$settings['ml_per_sec_min'], 'max:'.$settings['ml_per_sec_max']],
            'k_ms_per_ml_l' => ['nullable', 'numeric', 'min:0'],
        ]);

        $binding = DB::table('channel_bindings as cb')
            ->join('infrastructure_instances as ii', 'ii.id', '=', 'cb.infrastructure_instance_id')
            ->where('ii.owner_type', 'zone')
            ->where('ii.owner_id', $zone->id)
            ->where('cb.direction', 'actuator')
            ->whereIn('cb.role', PumpCalibrationCatalog::dosingRoles())
            ->where('cb.node_channel_id', $channelId)
            ->select('cb.role')
            ->first();

        if (! $binding) {
            $fallbackRole = $this->resolveDosingRoleForZoneChannel($zone, $channelId);
            if ($fallbackRole !== null) {
                $this->ensureBindingForRole($zone, $channelId, $fallbackRole);
                $binding = (object) ['role' => $fallbackRole];
            }
        }

        if (! $binding) {
            return response()->json([
                'status' => 'error',
                'message' => 'Channel not bound to this zone',
            ], 404);
        }

        $role = (string) $binding->role;
        $component = PumpCalibrationCatalog::componentForRole($role) ?? 'unknown';

        $now = now();

        DB::transaction(function () use ($channelId, $data, $component, $now, $zone, $role): void {
            DB::table('pump_calibrations')
                ->where('node_channel_id', $channelId)
                ->where('is_active', true)
                ->update([
                    'is_active' => false,
                    'valid_to' => $now,
                    'updated_at' => $now,
                ]);

            DB::table('pump_calibrations')->insert([
                'node_channel_id' => $channelId,
                'component' => $component,
                'ml_per_sec' => (float) $data['ml_per_sec'],
                'k_ms_per_ml_l' => array_key_exists('k_ms_per_ml_l', $data) ? $data['k_ms_per_ml_l'] : null,
                'source' => 'manual_calibration',
                'valid_from' => $now,
                'is_active' => true,
                'created_at' => $now,
                'updated_at' => $now,
            ]);

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'PUMP_CALIBRATION_FINISHED',
                'payload_json' => [
                    'node_channel_id' => $channelId,
                    'role' => $role,
                    'component' => $component,
                    'ml_per_sec' => (float) $data['ml_per_sec'],
                    'source' => 'manual_calibration',
                ],
            ]);
        });

        return response()->json(['status' => 'ok']);
    }

    private function authorizeZoneAccess(Request $request, Zone $zone): void
    {
        $user = $request->user();
        if (! $user) {
            abort(401, 'Unauthorized');
        }

        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            abort(403, 'Forbidden: Access denied to this zone');
        }
    }

    private function ensureAutoBindingsForDosingChannels(Zone $zone): void
    {
        $channels = DB::table('node_channels as nc')
            ->join('nodes as n', 'n.id', '=', 'nc.node_id')
            ->leftJoin('channel_bindings as cb', 'cb.node_channel_id', '=', 'nc.id')
            ->where(function ($query) use ($zone): void {
                $query->where('n.zone_id', $zone->id)
                    ->orWhere('n.pending_zone_id', $zone->id);
            })
            ->whereRaw("LOWER(COALESCE(nc.type, '')) = 'actuator'")
            ->select(
                'nc.id',
                'nc.channel',
                DB::raw("LOWER(COALESCE(nc.config->>'actuator_type', '')) as actuator_type"),
                DB::raw('MIN(cb.role) as bound_role')
            )
            ->groupBy('nc.id', 'nc.channel', DB::raw("LOWER(COALESCE(nc.config->>'actuator_type', ''))"))
            ->orderBy('nc.id')
            ->get();

        foreach ($channels as $channel) {
            if (is_string($channel->bound_role) && $channel->bound_role !== '') {
                continue;
            }

            $role = $this->resolveDosingRole((string) ($channel->channel ?? ''), (string) ($channel->actuator_type ?? ''));
            if (! $role) {
                continue;
            }

            $this->ensureBindingForRole($zone, (int) $channel->id, $role);
        }
    }

    private function resolveDosingRoleForZoneChannel(Zone $zone, int $channelId): ?string
    {
        $channel = DB::table('node_channels as nc')
            ->join('nodes as n', 'n.id', '=', 'nc.node_id')
            ->where('nc.id', $channelId)
            ->where(function ($query) use ($zone): void {
                $query->where('n.zone_id', $zone->id)
                    ->orWhere('n.pending_zone_id', $zone->id);
            })
            ->whereRaw("LOWER(COALESCE(nc.type, '')) = 'actuator'")
            ->select(
                'nc.channel',
                DB::raw("LOWER(COALESCE(nc.config->>'actuator_type', '')) as actuator_type")
            )
            ->first();

        if (! $channel) {
            return null;
        }

        return $this->resolveDosingRole(
            (string) ($channel->channel ?? ''),
            (string) ($channel->actuator_type ?? '')
        );
    }

    private function resolveDosingRole(string $channelName, string $actuatorType): ?string
    {
        $normalizedActuatorType = strtolower(trim($actuatorType));
        if (PumpCalibrationCatalog::isDosingRole($normalizedActuatorType)) {
            return $normalizedActuatorType;
        }

        $normalizedChannel = strtolower(trim($channelName));
        if (PumpCalibrationCatalog::isDosingRole($normalizedChannel)) {
            return $normalizedChannel;
        }

        return null;
    }

    private function ensureBindingForRole(Zone $zone, int $nodeChannelId, string $role): void
    {
        if (! PumpCalibrationCatalog::isDosingRole($role)) {
            return;
        }

        $existingRoleBinding = DB::table('channel_bindings as cb')
            ->join('infrastructure_instances as ii', 'ii.id', '=', 'cb.infrastructure_instance_id')
            ->where('ii.owner_type', 'zone')
            ->where('ii.owner_id', $zone->id)
            ->where('cb.role', $role)
            ->exists();

        if ($existingRoleBinding) {
            return;
        }

        $alreadyBound = DB::table('channel_bindings')
            ->where('node_channel_id', $nodeChannelId)
            ->exists();
        if ($alreadyBound) {
            return;
        }

        $instanceId = DB::table('infrastructure_instances')
            ->where('owner_type', 'zone')
            ->where('owner_id', $zone->id)
            ->where('label', $this->autoBindingLabelForRole($role))
            ->value('id');

        if (! $instanceId) {
            $instanceId = DB::table('infrastructure_instances')->insertGetId([
                'owner_type' => 'zone',
                'owner_id' => $zone->id,
                'asset_type' => 'PUMP',
                'label' => $this->autoBindingLabelForRole($role),
                'required' => in_array($role, ['pump_acid', 'pump_base', 'pump_a'], true),
                'created_at' => now(),
                'updated_at' => now(),
            ]);
        }

        DB::table('channel_bindings')->insert([
            'infrastructure_instance_id' => $instanceId,
            'node_channel_id' => $nodeChannelId,
            'direction' => 'actuator',
            'role' => $role,
            'created_at' => now(),
            'updated_at' => now(),
        ]);
    }

    private function autoBindingLabelForRole(string $role): string
    {
        return match ($role) {
            'pump_a' => 'Auto EC NPK Pump',
            'pump_b' => 'Auto EC Calcium Pump',
            'pump_c' => 'Auto EC Magnesium Pump',
            'pump_d' => 'Auto EC Micro Pump',
            'pump_base' => 'Auto pH Up Pump',
            'pump_acid' => 'Auto pH Down Pump',
            default => 'Auto Dosing Pump',
        };
    }
}
