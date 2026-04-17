<?php

namespace App\Http\Controllers;

use App\Models\Zone;
use App\Models\ZoneConfigChange;
use App\Services\ZoneConfigRevisionService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Validation\Rule;

class ZoneConfigModeController extends Controller
{
    public const MIN_TTL_SECONDS = 5 * 60;
    public const MAX_TTL_SECONDS = 7 * 24 * 60 * 60;

    public function __construct(
        private readonly ZoneConfigRevisionService $revisionService,
    ) {}

    public function show(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if ($user === null || ! $user->can('view', $zone)) {
            return response()->json([
                'status' => 'error',
                'code' => 'FORBIDDEN',
                'message' => 'Нет доступа к зоне.',
            ], 403);
        }

        return response()->json([
            'zone_id' => $zone->id,
            'config_mode' => $zone->config_mode ?? 'locked',
            'config_revision' => (int) ($zone->config_revision ?? 1),
            'live_until' => optional($zone->live_until)->toIso8601String(),
            'live_started_at' => optional($zone->live_started_at)->toIso8601String(),
            'config_mode_changed_at' => optional($zone->config_mode_changed_at)->toIso8601String(),
            'config_mode_changed_by' => $zone->config_mode_changed_by,
        ]);
    }

    public function update(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if ($user === null) {
            return response()->json(['status' => 'error', 'code' => 'UNAUTHENTICATED'], 401);
        }

        $validated = $request->validate([
            'mode' => ['required', 'string', Rule::in(['locked', 'live'])],
            'reason' => ['required', 'string', 'min:3', 'max:500'],
            'live_until' => ['required_if:mode,live', 'nullable', 'date'],
        ]);

        $targetMode = $validated['mode'];

        if ($targetMode === 'live') {
            if (! $user->can('setLive', $zone)) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'FORBIDDEN_SET_LIVE',
                    'message' => 'Роль не позволяет переключать зону в live.',
                ], 403);
            }

        } else {
            if (! $user->can('update', $zone)) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'FORBIDDEN',
                    'message' => 'Нет прав на изменение зоны.',
                ], 403);
            }
        }

        $loggedFrom = $zone->config_mode ?? 'locked';
        $loggedZoneId = $zone->id;

        $result = DB::transaction(function () use (
            $zone,
            $targetMode,
            $validated,
            $user,
            &$loggedFrom,
            &$loggedZoneId,
        ): JsonResponse {
            /** @var Zone|null $locked */
            $locked = Zone::lockForUpdate()->find($zone->id);
            if ($locked === null) {
                return response()->json(['status' => 'error', 'code' => 'NOT_FOUND'], 404);
            }

            $currentMode = $locked->config_mode ?? 'locked';
            $loggedFrom = $currentMode;
            $loggedZoneId = $locked->id;
            $now = Carbon::now();
            $updates = [
                'config_mode' => $targetMode,
                'config_mode_changed_at' => $now,
                'config_mode_changed_by' => $user->id,
            ];

            if ($targetMode === 'live') {
                $controlMode = strtolower(trim((string) ($locked->control_mode ?? 'auto')));
                if ($controlMode === 'auto') {
                    return response()->json([
                        'status' => 'error',
                        'code' => 'CONFIG_MODE_CONFLICT_WITH_AUTO',
                        'message' => 'Нельзя переключить зону в live, пока control_mode=auto.',
                        'details' => ['control_mode' => $controlMode],
                    ], 409);
                }

                $liveUntil = Carbon::parse($validated['live_until'])->utc();
                $deltaSec = $liveUntil->timestamp - $now->timestamp;
                if ($deltaSec < self::MIN_TTL_SECONDS || $deltaSec > self::MAX_TTL_SECONDS) {
                    return response()->json([
                        'status' => 'error',
                        'code' => 'TTL_OUT_OF_RANGE',
                        'message' => 'TTL должен быть от 5 минут до 7 дней.',
                        'details' => [
                            'min_sec' => self::MIN_TTL_SECONDS,
                            'max_sec' => self::MAX_TTL_SECONDS,
                            'actual_sec' => $deltaSec,
                        ],
                    ], 422);
                }

                $startedAt = $currentMode === 'live'
                    ? ($locked->live_started_at ?? $now)
                    : $now;
                $totalSec = $liveUntil->timestamp - Carbon::parse($startedAt)->timestamp;
                if ($totalSec > self::MAX_TTL_SECONDS) {
                    return response()->json([
                        'status' => 'error',
                        'code' => 'TTL_TOTAL_EXCEEDED',
                        'message' => 'Суммарное время live не может превышать 7 дней от первого включения.',
                        'details' => [
                            'max_total_sec' => self::MAX_TTL_SECONDS,
                            'actual_total_sec' => $totalSec,
                        ],
                    ], 422);
                }

                $updates['live_until'] = $liveUntil;
                if ($currentMode !== 'live') {
                    $updates['live_started_at'] = $now;
                }
            } else {
                $updates['live_until'] = null;
                $updates['live_started_at'] = null;
            }

            $locked->forceFill($updates)->save();

            // Phase 5 / audit 2026-04-17: каждая смена config_mode инкрементирует
            // `zones.config_revision` через `bumpAndAudit`. Без bump-а повторное
            // переключение (например live→locked→live в пределах одной сессии
            // tuning) ловилось unique constraint `zone_config_changes (zone_id,
            // revision)`. Дополнительный бонус: AE3 `_checkpoint` видит revision++
            // и корректно обновляет `ae3_zone_config_mode` gauge при любой смене.
            $revision = $this->revisionService->bumpAndAudit(
                scopeType: 'zone',
                scopeId: $locked->id,
                namespace: 'zone.config_mode',
                diff: [
                    'from' => $currentMode,
                    'to' => $targetMode,
                    'live_until' => optional($locked->live_until)->toIso8601String(),
                ],
                userId: $user->id,
                reason: $validated['reason'],
            );
            $locked->refresh();

            return response()->json([
                'status' => 'ok',
                'zone_id' => $locked->id,
                'config_mode' => $locked->config_mode,
                'config_revision' => (int) ($revision ?? $locked->config_revision),
                'live_until' => optional($locked->live_until)->toIso8601String(),
            ]);
        });

        Log::info('zone.config_mode.changed', [
            'zone_id' => $loggedZoneId,
            'from' => $loggedFrom,
            'to' => $targetMode,
            'user_id' => $user->id,
            'status' => $result->status(),
        ]);

        return $result;
    }

    public function extend(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if ($user === null || ! $user->can('setLive', $zone)) {
            return response()->json([
                'status' => 'error',
                'code' => 'FORBIDDEN_SET_LIVE',
                'message' => 'Роль не позволяет продлить live TTL.',
            ], 403);
        }

        $validated = $request->validate([
            'live_until' => ['required', 'date'],
        ]);

        $newLiveUntil = Carbon::parse($validated['live_until'])->utc();
        if ($newLiveUntil->timestamp <= Carbon::now()->timestamp) {
            return response()->json([
                'status' => 'error',
                'code' => 'TTL_IN_PAST',
                'message' => 'live_until должен быть в будущем.',
            ], 422);
        }

        // Phase 5 audit fix: lock row to avoid race with TTL revert cron.
        // Without the lock, cron could flip us to locked between the read
        // below and the save, leaving us with `config_mode=locked` +
        // non-null `live_until` → violates `zones_live_requires_until` CHECK.
        $result = DB::transaction(function () use ($zone, $newLiveUntil): JsonResponse {
            /** @var Zone $locked */
            $locked = Zone::lockForUpdate()->find($zone->id);
            if ($locked === null) {
                return response()->json(['status' => 'error', 'code' => 'NOT_FOUND'], 404);
            }
            if (($locked->config_mode ?? 'locked') !== 'live') {
                return response()->json([
                    'status' => 'error',
                    'code' => 'NOT_IN_LIVE_MODE',
                    'message' => 'Продление доступно только в live режиме.',
                ], 409);
            }
            $startedAt = $locked->live_started_at ?? Carbon::now();
            $totalSec = $newLiveUntil->timestamp - Carbon::parse($startedAt)->timestamp;
            if ($totalSec > self::MAX_TTL_SECONDS) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'TTL_TOTAL_EXCEEDED',
                    'message' => 'Суммарное время live не может превышать 7 дней от первого включения.',
                    'details' => ['max_total_sec' => self::MAX_TTL_SECONDS, 'actual_total_sec' => $totalSec],
                ], 422);
            }
            $locked->forceFill(['live_until' => $newLiveUntil])->save();
            return response()->json([
                'status' => 'ok',
                'zone_id' => $locked->id,
                'live_until' => $newLiveUntil->toIso8601String(),
            ]);
        });

        Log::info('zone.config_mode.extended', [
            'zone_id' => $zone->id,
            'live_until' => $newLiveUntil->toIso8601String(),
            'user_id' => $user->id,
            'status' => $result->status(),
        ]);

        return $result;
    }

    public function changes(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if ($user === null || ! $user->can('view', $zone)) {
            return response()->json(['status' => 'error', 'code' => 'FORBIDDEN'], 403);
        }

        $namespace = (string) $request->query('namespace', '');
        $limit = (int) $request->query('limit', 50);
        $limit = max(1, min(200, $limit));

        $query = ZoneConfigChange::where('zone_id', $zone->id)
            ->orderByDesc('created_at')
            ->limit($limit);
        if ($namespace !== '') {
            $query->where('namespace', $namespace);
        }

        return response()->json([
            'zone_id' => $zone->id,
            'changes' => $query->get()->map(function (ZoneConfigChange $row): array {
                return [
                    'id' => $row->id,
                    'revision' => $row->revision,
                    'namespace' => $row->namespace,
                    'diff' => $row->diff_json,
                    'user_id' => $row->user_id,
                    'reason' => $row->reason,
                    'created_at' => $row->created_at?->toIso8601String(),
                ];
            }),
        ]);
    }
}
