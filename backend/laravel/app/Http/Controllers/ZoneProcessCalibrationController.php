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
use Illuminate\Database\QueryException;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;

class ZoneProcessCalibrationController extends Controller
{
    private const ALLOWED_MODES = [
        'generic',
        'solution_fill',
        'tank_filling',
        'tank_recirc',
        'prepare_recirculation',
        'irrigation',
        'irrigating',
        'irrig_recirc',
    ];

    public function index(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $latestIds = ZoneProcessCalibration::query()
            ->selectRaw('MAX(id) as id')
            ->where('zone_id', $zone->id)
            ->where('is_active', true)
            ->groupBy('mode');

        $rows = ZoneProcessCalibration::query()
            ->whereIn('id', $latestIds)
            ->orderByRaw("CASE WHEN mode = 'generic' THEN 1 ELSE 0 END")
            ->orderByDesc('valid_from')
            ->get()
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
        $current = $this->currentCalibration(zoneId: $zone->id, mode: $normalizedMode);
        $payload = $this->mergeCalibrationPayload(current: $current, validated: $validated, userId: $userId);

        if (! $this->hasPrimaryGain($payload)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Нужно задать хотя бы один primary gain: ec_gain_per_ml, ph_up_gain_per_ml или ph_down_gain_per_ml.',
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        try {
            $calibration = DB::transaction(function () use ($zone, $normalizedMode, $payload, $now, $current, $userId) {
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
                    'ec_gain_per_ml' => $payload['ec_gain_per_ml'],
                    'ph_up_gain_per_ml' => $payload['ph_up_gain_per_ml'],
                    'ph_down_gain_per_ml' => $payload['ph_down_gain_per_ml'],
                    'ph_per_ec_ml' => $payload['ph_per_ec_ml'],
                    'ec_per_ph_ml' => $payload['ec_per_ph_ml'],
                    'transport_delay_sec' => $payload['transport_delay_sec'],
                    'settle_sec' => $payload['settle_sec'],
                    'confidence' => $payload['confidence'],
                    'source' => $payload['source'],
                    'valid_from' => $now,
                    'valid_to' => null,
                    'is_active' => true,
                    'meta' => $payload['meta'],
                ]);

                ZoneEvent::create([
                    'zone_id' => $zone->id,
                    'type' => 'PROCESS_CALIBRATION_SAVED',
                    'payload_json' => $this->buildCalibrationEventPayload(
                        mode: $normalizedMode,
                        payload: $payload,
                        userId: $userId,
                        current: $current,
                    ),
                ]);

                return $created;
            });
        } catch (QueryException $e) {
            if ($this->isActiveCalibrationConflict($e)) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Для зоны уже есть активная calibration этого режима. Повторите запрос.',
                ], Response::HTTP_CONFLICT);
            }

            throw $e;
        }

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
        if (! in_array($normalized, self::ALLOWED_MODES, true)) {
            return null;
        }

        return match ($normalized) {
            'tank_filling' => 'solution_fill',
            'prepare_recirculation' => 'tank_recirc',
            'irrigating', 'irrig_recirc' => 'irrigation',
            default => $normalized,
        };
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
            'updated_at' => optional($calibration->updated_at)->toISOString(),
        ];
    }

    private function currentCalibration(int $zoneId, string $mode): ?ZoneProcessCalibration
    {
        return ZoneProcessCalibration::query()
            ->where('zone_id', $zoneId)
            ->where('mode', $mode)
            ->where('is_active', true)
            ->orderByDesc('valid_from')
            ->orderByDesc('id')
            ->first();
    }

    /**
     * @param  array<string, mixed>  $validated
     * @return array<string, mixed>
     */
    private function mergeCalibrationPayload(
        ?ZoneProcessCalibration $current,
        array $validated,
        ?int $userId,
    ): array {
        $currentMeta = is_array($current?->meta) ? $current->meta : [];
        $incomingMeta = is_array($validated['meta'] ?? null) ? $validated['meta'] : $currentMeta;

        return [
            'ec_gain_per_ml' => array_key_exists('ec_gain_per_ml', $validated) ? $validated['ec_gain_per_ml'] : $current?->ec_gain_per_ml,
            'ph_up_gain_per_ml' => array_key_exists('ph_up_gain_per_ml', $validated) ? $validated['ph_up_gain_per_ml'] : $current?->ph_up_gain_per_ml,
            'ph_down_gain_per_ml' => array_key_exists('ph_down_gain_per_ml', $validated) ? $validated['ph_down_gain_per_ml'] : $current?->ph_down_gain_per_ml,
            'ph_per_ec_ml' => array_key_exists('ph_per_ec_ml', $validated) ? $validated['ph_per_ec_ml'] : $current?->ph_per_ec_ml,
            'ec_per_ph_ml' => array_key_exists('ec_per_ph_ml', $validated) ? $validated['ec_per_ph_ml'] : $current?->ec_per_ph_ml,
            'transport_delay_sec' => array_key_exists('transport_delay_sec', $validated) ? $validated['transport_delay_sec'] : $current?->transport_delay_sec,
            'settle_sec' => array_key_exists('settle_sec', $validated) ? $validated['settle_sec'] : $current?->settle_sec,
            'confidence' => array_key_exists('confidence', $validated) ? $validated['confidence'] : $current?->confidence,
            'source' => array_key_exists('source', $validated) ? $validated['source'] : ($current?->source ?? 'manual'),
            'meta' => array_merge($incomingMeta, ['updated_by' => $userId]),
        ];
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function hasPrimaryGain(array $payload): bool
    {
        foreach (['ec_gain_per_ml', 'ph_up_gain_per_ml', 'ph_down_gain_per_ml'] as $key) {
            if (($payload[$key] ?? null) !== null) {
                return true;
            }
        }

        return false;
    }

    private function isActiveCalibrationConflict(QueryException $e): bool
    {
        $sqlState = $e->errorInfo[0] ?? null;
        $message = strtolower($e->getMessage());

        return $sqlState === '23505'
            && str_contains($message, 'zone_process_calibrations_one_active_mode_unique');
    }

    /**
     * @param  array<string, mixed>  $payload
     * @return array<string, mixed>
     */
    private function buildCalibrationEventPayload(
        string $mode,
        array $payload,
        ?int $userId,
        ?ZoneProcessCalibration $current,
    ): array {
        return [
            'mode' => $mode,
            'source' => $payload['source'],
            'confidence' => $payload['confidence'],
            'transport_delay_sec' => $payload['transport_delay_sec'],
            'settle_sec' => $payload['settle_sec'],
            'ec_gain_per_ml' => $payload['ec_gain_per_ml'],
            'ph_up_gain_per_ml' => $payload['ph_up_gain_per_ml'],
            'ph_down_gain_per_ml' => $payload['ph_down_gain_per_ml'],
            'ph_per_ec_ml' => $payload['ph_per_ec_ml'],
            'ec_per_ph_ml' => $payload['ec_per_ph_ml'],
            'updated_by' => $userId,
            'previous' => $current ? [
                'confidence' => $current->confidence,
                'transport_delay_sec' => $current->transport_delay_sec,
                'settle_sec' => $current->settle_sec,
                'ec_gain_per_ml' => $current->ec_gain_per_ml,
                'ph_up_gain_per_ml' => $current->ph_up_gain_per_ml,
                'ph_down_gain_per_ml' => $current->ph_down_gain_per_ml,
                'ph_per_ec_ml' => $current->ph_per_ec_ml,
                'ec_per_ph_ml' => $current->ec_per_ph_ml,
            ] : null,
        ];
    }
}
