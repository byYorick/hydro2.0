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

        $roleOrderSql = "CASE cb.role
            WHEN 'ph_acid_pump' THEN 1
            WHEN 'ph_base_pump' THEN 2
            WHEN 'ec_npk_pump' THEN 3
            WHEN 'ec_calcium_pump' THEN 4
            WHEN 'ec_magnesium_pump' THEN 5
            WHEN 'ec_micro_pump' THEN 6
            ELSE 99
        END";

        $rows = DB::table('infrastructure_instances as ii')
            ->join('channel_bindings as cb', 'cb.infrastructure_instance_id', '=', 'ii.id')
            ->join('node_channels as nc', 'nc.id', '=', 'cb.node_channel_id')
            ->join('nodes as n', 'n.id', '=', 'nc.node_id')
            ->leftJoinSub($latestCalibrations, 'pc', function ($join): void {
                $join->on('pc.node_channel_id', '=', 'nc.id');
            })
            ->where('ii.owner_type', 'zone')
            ->where('ii.owner_id', $zone->id)
            ->where('cb.direction', 'actuator')
            ->whereIn('cb.role', PumpCalibrationCatalog::dosingRoles())
            ->selectRaw(
                "nc.id AS node_channel_id,
                 cb.role,
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
            return [
                'node_channel_id' => (int) $row->node_channel_id,
                'role' => (string) $row->role,
                'component' => (string) ($row->calibration_component ?: PumpCalibrationCatalog::componentForRole($row->role) ?: 'unknown'),
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
        })->values();

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
                'source' => 'manual',
                'valid_from' => $now,
                'is_active' => true,
                'created_at' => $now,
                'updated_at' => $now,
            ]);

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'PUMP_CALIBRATION_SAVED',
                'payload_json' => [
                    'node_channel_id' => $channelId,
                    'role' => $role,
                    'component' => $component,
                    'ml_per_sec' => (float) $data['ml_per_sec'],
                    'source' => 'manual',
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
}
