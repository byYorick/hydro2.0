<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\NodeChannel;
use App\Models\SensorCalibration;
use App\Models\SystemAutomationSetting;
use App\Models\Zone;
use App\Services\SensorCalibrationCommandService;
use DomainException;
use Illuminate\Http\JsonResponse;
use Illuminate\Database\QueryException;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\DB;

class SensorCalibrationController extends Controller
{
    public function __construct(
        private readonly SensorCalibrationCommandService $commandService,
    ) {
    }

    public function index(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $limit = max(1, min(100, (int) $request->integer('limit', 20)));
        $query = SensorCalibration::query()
            ->with(['nodeChannel.node', 'user'])
            ->where('zone_id', $zone->id);

        $sensorType = $request->string('sensor_type')->toString();
        if (in_array($sensorType, ['ph', 'ec'], true)) {
            $query->where('sensor_type', $sensorType);
        }

        $nodeChannelId = $request->integer('node_channel_id');
        if ($nodeChannelId > 0) {
            $query->where('node_channel_id', $nodeChannelId);
        }

        $items = $query->orderByDesc('created_at')
            ->limit($limit)
            ->get()
            ->map(fn (SensorCalibration $calibration) => $this->serializeCalibration($calibration))
            ->values();

        return response()->json([
            'status' => 'ok',
            'data' => $items,
        ]);
    }

    public function status(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $settings = SystemAutomationSetting::forNamespace('sensor_calibration');
        $warningDays = (int) $settings['reminder_days'];
        $criticalDays = (int) $settings['critical_days'];

        $channels = $this->sensorChannelsQuery($zone)->get();

        $data = $channels->map(function ($row) use ($zone, $warningDays, $criticalDays) {
            $lastCompleted = SensorCalibration::query()
                ->where('zone_id', $zone->id)
                ->where('node_channel_id', $row->node_channel_id)
                ->where('status', SensorCalibration::STATUS_COMPLETED)
                ->orderByDesc('completed_at')
                ->first(['completed_at']);
            $lastCompletedAt = $lastCompleted?->completed_at;

            $activeCalibration = SensorCalibration::query()
                ->where('zone_id', $zone->id)
                ->where('node_channel_id', $row->node_channel_id)
                ->whereNotIn('status', SensorCalibration::TERMINAL_STATUSES)
                ->orderByDesc('id')
                ->first(['id']);
            $activeCalibrationId = $activeCalibration?->id;

            $daysSince = null;
            $status = 'never';
            if ($lastCompletedAt) {
                $daysSince = $lastCompletedAt->diffInDays(now());
                $status = $daysSince >= $criticalDays
                    ? 'critical'
                    : ($daysSince >= $warningDays ? 'warning' : 'ok');
            }

            return [
                'node_channel_id' => (int) $row->node_channel_id,
                'channel_uid' => (string) $row->channel,
                'sensor_type' => (string) $row->sensor_type,
                'node_uid' => (string) $row->node_uid,
                'last_calibrated_at' => $lastCompletedAt ? (string) $lastCompletedAt : null,
                'days_since_calibration' => $daysSince,
                'calibration_status' => $status,
                'has_active_session' => $activeCalibrationId !== null,
                'active_calibration_id' => $activeCalibrationId,
            ];
        })->values();

        return response()->json([
            'status' => 'ok',
            'data' => $data,
        ]);
    }

    public function show(Request $request, Zone $zone, SensorCalibration $calibration): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);
        $this->ensureCalibrationBelongsToZone($zone, $calibration);

        $calibration->loadMissing(['nodeChannel.node', 'user']);

        return response()->json([
            'status' => 'ok',
            'data' => $this->serializeCalibration($calibration),
        ]);
    }

    public function create(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $data = $request->validate([
            'node_channel_id' => ['required', 'integer', 'exists:node_channels,id'],
            'sensor_type' => ['required', 'string', 'in:ph,ec'],
        ]);

        $channel = $this->resolveSensorChannel($zone, (int) $data['node_channel_id'], (string) $data['sensor_type']);
        try {
            $calibration = DB::transaction(function () use ($request, $zone, $channel, $data) {
                NodeChannel::query()
                    ->whereKey($channel->id)
                    ->lockForUpdate()
                    ->firstOrFail();

                $hasActive = SensorCalibration::query()
                    ->where('zone_id', $zone->id)
                    ->where('node_channel_id', $channel->id)
                    ->whereNotIn('status', SensorCalibration::TERMINAL_STATUSES)
                    ->lockForUpdate()
                    ->exists();
                if ($hasActive) {
                    throw new DomainException('An active sensor calibration session already exists for this channel.');
                }

                return SensorCalibration::query()->create([
                    'zone_id' => $zone->id,
                    'node_channel_id' => $channel->id,
                    'sensor_type' => $data['sensor_type'],
                    'status' => SensorCalibration::STATUS_STARTED,
                    'calibrated_by' => $request->user()?->id,
                    'meta' => [],
                ]);
            }, 3);
        } catch (DomainException $exception) {
            return $this->unprocessableCalibrationResponse($exception->getMessage());
        } catch (QueryException $exception) {
            if ($this->isActiveCalibrationConstraintViolation($exception)) {
                return $this->unprocessableCalibrationResponse('An active sensor calibration session already exists for this channel.');
            }

            throw $exception;
        }

        $calibration->loadMissing(['nodeChannel.node', 'user']);
        $defaults = $this->referenceDefaults((string) $data['sensor_type']);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'calibration' => $this->serializeCalibration($calibration),
                'defaults' => $defaults,
            ],
        ], Response::HTTP_CREATED);
    }

    public function point(Request $request, Zone $zone, SensorCalibration $calibration): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);
        $this->ensureCalibrationBelongsToZone($zone, $calibration);

        $data = $request->validate([
            'stage' => ['required', 'integer', 'in:1,2'],
            'reference_value' => ['required', 'numeric'],
        ]);

        $settings = SystemAutomationSetting::forNamespace('sensor_calibration');
        $stage = (int) $data['stage'];
        $referenceValue = (float) $data['reference_value'];
        try {
            $updated = DB::transaction(function () use ($zone, $calibration, $stage, $referenceValue, $settings) {
                /** @var SensorCalibration $lockedCalibration */
                $lockedCalibration = SensorCalibration::query()
                    ->with(['nodeChannel.node'])
                    ->whereKey($calibration->id)
                    ->lockForUpdate()
                    ->firstOrFail();

                $this->ensureCalibrationBelongsToZone($zone, $lockedCalibration);
                $this->assertPointSubmissionAllowed($lockedCalibration, $stage);
                $this->validateReferenceValue(
                    sensorType: $lockedCalibration->sensor_type,
                    referenceValue: $referenceValue,
                    settings: $settings,
                );

                $channel = $lockedCalibration->nodeChannel;
                if (! $channel) {
                    abort(422, 'Sensor calibration channel not found');
                }

                return $this->commandService->submitPoint(
                    calibration: $lockedCalibration,
                    channel: $channel,
                    zone: $zone,
                    stage: $stage,
                    referenceValue: $referenceValue,
                );
            }, 3);
        } catch (DomainException $exception) {
            return $this->unprocessableCalibrationResponse($exception->getMessage());
        }

        return response()->json([
            'status' => 'ok',
            'data' => $this->serializeCalibration($updated),
        ]);
    }

    public function cancel(Request $request, Zone $zone, SensorCalibration $calibration): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);
        $this->ensureCalibrationBelongsToZone($zone, $calibration);

        if (! $calibration->isTerminal()) {
            $calibration->fill([
                'status' => SensorCalibration::STATUS_CANCELLED,
                'completed_at' => now(),
            ])->save();
        }

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

    private function ensureCalibrationBelongsToZone(Zone $zone, SensorCalibration $calibration): void
    {
        if ((int) $calibration->zone_id !== (int) $zone->id) {
            abort(404, 'Sensor calibration not found in this zone');
        }
    }

    private function resolveSensorChannel(Zone $zone, int $channelId, string $sensorType): NodeChannel
    {
        $channel = NodeChannel::query()
            ->with('node')
            ->where('id', $channelId)
            ->whereHas('node', fn ($query) => $query->where('zone_id', $zone->id))
            ->firstOrFail();

        $resolvedType = $this->detectSensorType($channel);
        if ($resolvedType !== $sensorType) {
            abort(422, 'node_channel_id does not match the requested sensor_type');
        }

        return $channel;
    }

    private function sensorChannelsQuery(Zone $zone)
    {
        return DB::table('node_channels as nc')
            ->join('nodes as n', 'n.id', '=', 'nc.node_id')
            ->where('n.zone_id', $zone->id)
            ->where(function ($query): void {
                $query->whereIn(DB::raw('LOWER(COALESCE(nc.channel, \'\'))'), ['ph', 'ph_sensor', 'ec', 'ec_sensor'])
                    ->orWhereIn(DB::raw('UPPER(COALESCE(nc.metric, \'\'))'), ['PH', 'EC']);
            })
            ->selectRaw(
                "nc.id as node_channel_id,
                 nc.channel as channel,
                 n.uid as node_uid,
                 CASE
                     WHEN LOWER(COALESCE(nc.channel, '')) IN ('ph', 'ph_sensor') OR UPPER(COALESCE(nc.metric, '')) = 'PH' THEN 'ph'
                     WHEN LOWER(COALESCE(nc.channel, '')) IN ('ec', 'ec_sensor') OR UPPER(COALESCE(nc.metric, '')) = 'EC' THEN 'ec'
                     ELSE NULL
                 END as sensor_type"
            )
            ->orderBy('nc.id');
    }

    private function detectSensorType(NodeChannel $channel): ?string
    {
        $channelName = strtolower((string) $channel->channel);
        $metric = strtoupper((string) ($channel->metric ?? ''));

        return match (true) {
            in_array($channelName, ['ph', 'ph_sensor'], true), $metric === 'PH' => 'ph',
            in_array($channelName, ['ec', 'ec_sensor'], true), $metric === 'EC' => 'ec',
            default => null,
        };
    }

    private function referenceDefaults(string $sensorType): array
    {
        $settings = SystemAutomationSetting::forNamespace('sensor_calibration');

        return $sensorType === 'ph'
            ? [
                'point_1_value' => (float) $settings['ph_point_1_value'],
                'point_2_value' => (float) $settings['ph_point_2_value'],
            ]
            : [
                'point_1_value' => (int) $settings['ec_point_1_tds'],
                'point_2_value' => (int) $settings['ec_point_2_tds'],
            ];
    }

    private function validateReferenceValue(string $sensorType, float $referenceValue, array $settings): void
    {
        if ($sensorType === 'ph') {
            $min = (float) $settings['ph_reference_min'];
            $max = (float) $settings['ph_reference_max'];
            if ($referenceValue < $min || $referenceValue > $max) {
                abort(422, "reference_value must be within [{$min}, {$max}]");
            }

            return;
        }

        $max = (int) $settings['ec_tds_reference_max'];
        if ($referenceValue <= 0 || $referenceValue > $max) {
            abort(422, "reference_value must be within (0, {$max}]");
        }
    }

    private function assertPointSubmissionAllowed(SensorCalibration $calibration, int $stage): void
    {
        if ($calibration->isTerminal()) {
            throw new DomainException('Calibration session is already terminal.');
        }
        if ($stage === 1 && $calibration->status !== SensorCalibration::STATUS_STARTED) {
            throw new DomainException('Point 1 can only be submitted from started status.');
        }
        if ($stage === 2 && $calibration->status !== SensorCalibration::STATUS_POINT_1_DONE) {
            throw new DomainException('Point 2 can only be submitted after point 1 is completed.');
        }
    }

    private function isActiveCalibrationConstraintViolation(QueryException $exception): bool
    {
        $message = implode(' ', array_filter([
            $exception->getMessage(),
            $exception->errorInfo[2] ?? null,
        ]));

        return str_contains($message, 'uniq_sensor_cal_active_channel');
    }

    private function unprocessableCalibrationResponse(string $message): JsonResponse
    {
        return response()->json([
            'status' => 'error',
            'message' => $message,
        ], Response::HTTP_UNPROCESSABLE_ENTITY);
    }

    private function serializeCalibration(SensorCalibration $calibration): array
    {
        return [
            'id' => $calibration->id,
            'zone_id' => $calibration->zone_id,
            'node_channel_id' => $calibration->node_channel_id,
            'sensor_type' => $calibration->sensor_type,
            'status' => $calibration->status,
            'point_1_reference' => $calibration->point_1_reference,
            'point_1_command_id' => $calibration->point_1_command_id,
            'point_1_sent_at' => optional($calibration->point_1_sent_at)->toISOString(),
            'point_1_result' => $calibration->point_1_result,
            'point_1_error' => $calibration->point_1_error,
            'point_2_reference' => $calibration->point_2_reference,
            'point_2_command_id' => $calibration->point_2_command_id,
            'point_2_sent_at' => optional($calibration->point_2_sent_at)->toISOString(),
            'point_2_result' => $calibration->point_2_result,
            'point_2_error' => $calibration->point_2_error,
            'completed_at' => optional($calibration->completed_at)->toISOString(),
            'calibrated_by' => $calibration->calibrated_by,
            'calibrated_by_name' => $calibration->user?->name,
            'notes' => $calibration->notes,
            'meta' => $calibration->meta ?? [],
            'node_channel' => $calibration->nodeChannel ? [
                'id' => $calibration->nodeChannel->id,
                'channel' => $calibration->nodeChannel->channel,
                'node_uid' => $calibration->nodeChannel->node?->uid,
            ] : null,
            'created_at' => optional($calibration->created_at)->toISOString(),
            'updated_at' => optional($calibration->updated_at)->toISOString(),
        ];
    }
}
