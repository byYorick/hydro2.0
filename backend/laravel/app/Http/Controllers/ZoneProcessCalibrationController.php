<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Http\Requests\UpsertZoneProcessCalibrationRequest;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Models\ZoneProcessCalibration;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;

class ZoneProcessCalibrationController extends Controller
{
    private const ALLOWED_MODES = [
        'generic',
        'solution_fill',
        'tank_recirc',
        'irrigating',
        'irrig_recirc',
    ];

    public function index(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $rows = ZoneProcessCalibration::query()
            ->where('zone_id', $zone->id)
            ->where('is_active', true)
            ->orderByRaw("CASE WHEN mode = 'generic' THEN 1 ELSE 0 END")
            ->orderByDesc('valid_from')
            ->get()
            ->unique('mode')
            ->values()
            ->map(fn (ZoneProcessCalibration $item) => $this->serializeCalibration($item));

        return response()->json([
            'status' => 'ok',
            'data' => $rows,
        ]);
    }

    public function show(Request $request, Zone $zone, string $mode): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $normalizedMode = $this->normalizeMode($mode);
        if ($normalizedMode === null) {
            return response()->json([
                'status' => 'error',
                'message' => 'Invalid mode.',
            ], Response::HTTP_BAD_REQUEST);
        }

        $calibration = ZoneProcessCalibration::query()
            ->where('zone_id', $zone->id)
            ->where('mode', $normalizedMode)
            ->where('is_active', true)
            ->where('valid_from', '<=', now())
            ->where(function ($query): void {
                $query->whereNull('valid_to')->orWhere('valid_to', '>', now());
            })
            ->orderByDesc('valid_from')
            ->first();

        if (! $calibration) {
            return response()->json([
                'status' => 'ok',
                'data' => null,
            ]);
        }

        return response()->json([
            'status' => 'ok',
            'data' => $this->serializeCalibration($calibration),
        ]);
    }

    public function update(
        UpsertZoneProcessCalibrationRequest $request,
        Zone $zone,
        string $mode
    ): JsonResponse {
        $this->authorizeZoneAccess($request, $zone);

        $normalizedMode = $this->normalizeMode($mode);
        if ($normalizedMode === null) {
            return response()->json([
                'status' => 'error',
                'message' => 'Invalid mode.',
            ], Response::HTTP_BAD_REQUEST);
        }

        $validated = $request->validated();
        $now = now();
        $userId = Auth::id();

        $calibration = DB::transaction(function () use ($zone, $normalizedMode, $validated, $now, $userId) {
            ZoneProcessCalibration::query()
                ->where('zone_id', $zone->id)
                ->where('mode', $normalizedMode)
                ->where('is_active', true)
                ->update([
                    'is_active' => false,
                    'valid_to' => $now,
                    'updated_at' => $now,
                ]);

            $created = ZoneProcessCalibration::query()->create([
                'zone_id' => $zone->id,
                'mode' => $normalizedMode,
                'ec_gain_per_ml' => $validated['ec_gain_per_ml'] ?? null,
                'ph_up_gain_per_ml' => $validated['ph_up_gain_per_ml'] ?? null,
                'ph_down_gain_per_ml' => $validated['ph_down_gain_per_ml'] ?? null,
                'ph_per_ec_ml' => $validated['ph_per_ec_ml'] ?? null,
                'ec_per_ph_ml' => $validated['ec_per_ph_ml'] ?? null,
                'transport_delay_sec' => $validated['transport_delay_sec'] ?? null,
                'settle_sec' => $validated['settle_sec'] ?? null,
                'confidence' => $validated['confidence'] ?? null,
                'source' => $validated['source'] ?? 'manual',
                'valid_from' => $now,
                'valid_to' => null,
                'is_active' => true,
                'meta' => array_merge(
                    is_array($validated['meta'] ?? null) ? $validated['meta'] : [],
                    ['updated_by' => $userId]
                ),
            ]);

            ZoneEvent::create([
                'zone_id' => $zone->id,
                'type' => 'PROCESS_CALIBRATION_SAVED',
                'payload_json' => [
                    'mode' => $normalizedMode,
                    'confidence' => $validated['confidence'] ?? null,
                    'source' => $validated['source'] ?? 'manual',
                ],
            ]);

            return $created;
        });

        return response()->json([
            'status' => 'ok',
            'data' => $this->serializeCalibration($calibration),
        ]);
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

    private function normalizeMode(string $mode): ?string
    {
        $normalized = trim(strtolower($mode));
        return in_array($normalized, self::ALLOWED_MODES, true) ? $normalized : null;
    }

    /**
     * @return array<string, mixed>
     */
    private function serializeCalibration(ZoneProcessCalibration $calibration): array
    {
        return [
            'id' => $calibration->id,
            'zone_id' => $calibration->zone_id,
            'mode' => $calibration->mode,
            'ec_gain_per_ml' => $calibration->ec_gain_per_ml,
            'ph_up_gain_per_ml' => $calibration->ph_up_gain_per_ml,
            'ph_down_gain_per_ml' => $calibration->ph_down_gain_per_ml,
            'ph_per_ec_ml' => $calibration->ph_per_ec_ml,
            'ec_per_ph_ml' => $calibration->ec_per_ph_ml,
            'transport_delay_sec' => $calibration->transport_delay_sec,
            'settle_sec' => $calibration->settle_sec,
            'confidence' => $calibration->confidence,
            'source' => $calibration->source,
            'valid_from' => optional($calibration->valid_from)->toISOString(),
            'valid_to' => optional($calibration->valid_to)->toISOString(),
            'is_active' => $calibration->is_active,
            'meta' => $calibration->meta,
        ];
    }
}
