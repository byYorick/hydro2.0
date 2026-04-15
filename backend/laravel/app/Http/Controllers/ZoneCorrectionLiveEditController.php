<?php

namespace App\Http\Controllers;

use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\ZoneConfigRevisionService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Arr;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Phase 6.2: full fine-tuning correction params на лету.
 *
 * Accepts flat dot-notation patches для:
 * - `zone.correction` (через `correction_patch`) — per-base или per-phase через `phase` ключ
 * - `zone.process_calibration.{phase}` (через `calibration_patch`) — требует `phase`
 *
 * Каждый путь в patch'ах проверяется против whitelist (`LIVE_EDITABLE_*_PATHS`).
 * Хот-свап AE3 подхватывает изменения на следующем handler checkpoint, если
 * zone в config_mode=live.
 */
class ZoneCorrectionLiveEditController extends Controller
{
    /**
     * Dot-notation paths для live-edit в zone.correction payload.
     *
     * Патч применяется к `base_config.*` (если `phase` не указан) или
     * `phase_overrides.{phase}.*`. `base_config` использует категориальную
     * структуру (retry / dosing / safety / timing / runtime / tolerance / controllers),
     * см. `ZoneCorrectionConfigCatalog::fieldCatalog`.
     */
    private const LIVE_EDITABLE_CORRECTION_PATHS = [
        // timing
        'timing.stabilization_sec',
        'timing.telemetry_max_age_sec',
        'timing.irr_state_max_age_sec',
        'timing.level_poll_interval_sec',
        'timing.sensor_mode_stabilization_time_sec',
        // retry / attempts / delays
        'retry.max_ec_correction_attempts',
        'retry.max_ph_correction_attempts',
        'retry.prepare_recirculation_max_attempts',
        'retry.prepare_recirculation_max_correction_attempts',
        'retry.prepare_recirculation_timeout_sec',
        'retry.prepare_recirculation_correction_slack_sec',
        'retry.telemetry_stale_retry_sec',
        'retry.decision_window_retry_sec',
        'retry.low_water_retry_sec',
        // dosing limits (caps)
        'dosing.max_ec_dose_ml',
        'dosing.max_ph_dose_ml',
        'dosing.solution_volume_l',
        // safety
        'safety.safe_mode_on_no_effect',
        'safety.block_on_active_no_effect_alert',
        // tolerance
        'tolerance.prepare_tolerance.ph_pct',
        'tolerance.prepare_tolerance.ec_pct',
        // PID per-controller (ph)
        'controllers.ph.kp', 'controllers.ph.ki', 'controllers.ph.kd',
        'controllers.ph.deadband',
        'controllers.ph.max_dose_ml', 'controllers.ph.min_interval_sec',
        'controllers.ph.max_integral', 'controllers.ph.derivative_filter_alpha',
        'controllers.ph.anti_windup.enabled',
        'controllers.ph.overshoot_guard.enabled',
        'controllers.ph.overshoot_guard.hard_min',
        'controllers.ph.overshoot_guard.hard_max',
        'controllers.ph.no_effect.enabled',
        'controllers.ph.no_effect.max_count',
        'controllers.ph.observe.telemetry_period_sec',
        'controllers.ph.observe.window_min_samples',
        'controllers.ph.observe.decision_window_sec',
        'controllers.ph.observe.observe_poll_sec',
        'controllers.ph.observe.min_effect_fraction',
        'controllers.ph.observe.stability_max_slope',
        'controllers.ph.observe.no_effect_consecutive_limit',
        // PID per-controller (ec) — симметрично
        'controllers.ec.kp', 'controllers.ec.ki', 'controllers.ec.kd',
        'controllers.ec.deadband',
        'controllers.ec.max_dose_ml', 'controllers.ec.min_interval_sec',
        'controllers.ec.max_integral', 'controllers.ec.derivative_filter_alpha',
        'controllers.ec.anti_windup.enabled',
        'controllers.ec.overshoot_guard.enabled',
        'controllers.ec.overshoot_guard.hard_min',
        'controllers.ec.overshoot_guard.hard_max',
        'controllers.ec.no_effect.enabled',
        'controllers.ec.no_effect.max_count',
        'controllers.ec.observe.telemetry_period_sec',
        'controllers.ec.observe.window_min_samples',
        'controllers.ec.observe.decision_window_sec',
        'controllers.ec.observe.observe_poll_sec',
        'controllers.ec.observe.min_effect_fraction',
        'controllers.ec.observe.stability_max_slope',
        'controllers.ec.observe.no_effect_consecutive_limit',
    ];

    /**
     * Dot-notation paths для zone.process_calibration.{phase} payload.
     * Эти параметры — physical properties pump/solution (transport delay,
     * settle time после дозирования). Накладываются на root документа.
     */
    private const LIVE_EDITABLE_CALIBRATION_PATHS = [
        'transport_delay_sec',
        'settle_sec',
        'confidence',
        'ec_gain_per_ml',
        'ph_up_gain_per_ml',
        'ph_down_gain_per_ml',
        'ph_per_ec_ml',
        'ec_per_ph_ml',
    ];

    private const ALLOWED_CALIBRATION_PHASES = [
        'generic' => AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_GENERIC,
        'solution_fill' => AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_SOLUTION_FILL,
        'tank_recirc' => AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_TANK_RECIRC,
        'irrigation' => AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_IRRIGATION,
    ];

    public function __construct(
        private readonly AutomationConfigDocumentService $documents,
        private readonly ZoneConfigRevisionService $revisionService,
    ) {}

    public function update(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if ($user === null) {
            return response()->json(['status' => 'error', 'code' => 'UNAUTHENTICATED'], 401);
        }
        if (! $user->can('setLive', $zone)) {
            return response()->json([
                'status' => 'error',
                'code' => 'FORBIDDEN_SET_LIVE',
                'message' => 'Роль не позволяет править correction.',
            ], 403);
        }
        if (($zone->config_mode ?? 'locked') !== 'live') {
            return response()->json([
                'status' => 'error',
                'code' => 'ZONE_NOT_IN_LIVE_MODE',
                'message' => 'Правка correction на лету доступна только в config_mode=live.',
            ], 409);
        }

        $validated = $request->validate([
            'reason' => ['required', 'string', 'min:3', 'max:500'],
            'phase' => ['nullable', 'string', 'max:64'],
            'correction_patch' => ['nullable', 'array'],
            'correction_patch.*' => ['nullable'],
            'calibration_patch' => ['nullable', 'array'],
            'calibration_patch.*' => ['nullable'],
        ]);

        $reason = $validated['reason'];
        $phase = (string) ($validated['phase'] ?? '');
        $correctionPatch = (array) ($validated['correction_patch'] ?? []);
        $calibrationPatch = (array) ($validated['calibration_patch'] ?? []);

        // Strip null values
        $correctionPatch = array_filter($correctionPatch, fn ($v) => $v !== null);
        $calibrationPatch = array_filter($calibrationPatch, fn ($v) => $v !== null);

        if (empty($correctionPatch) && empty($calibrationPatch)) {
            return response()->json([
                'status' => 'error',
                'code' => 'NO_FIELDS_PROVIDED',
                'message' => 'Передай хотя бы одно поле в correction_patch или calibration_patch.',
                'details' => [
                    'allowed_correction_paths' => self::LIVE_EDITABLE_CORRECTION_PATHS,
                    'allowed_calibration_paths' => self::LIVE_EDITABLE_CALIBRATION_PATHS,
                    'allowed_calibration_phases' => array_keys(self::ALLOWED_CALIBRATION_PHASES),
                ],
            ], 422);
        }

        // Whitelist validation
        foreach (array_keys($correctionPatch) as $path) {
            if (! in_array($path, self::LIVE_EDITABLE_CORRECTION_PATHS, true)) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'PATH_NOT_WHITELISTED',
                    'message' => "Correction path '{$path}' не в whitelist для live-edit.",
                    'details' => ['allowed' => self::LIVE_EDITABLE_CORRECTION_PATHS],
                ], 422);
            }
        }
        foreach (array_keys($calibrationPatch) as $path) {
            if (! in_array($path, self::LIVE_EDITABLE_CALIBRATION_PATHS, true)) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'PATH_NOT_WHITELISTED',
                    'message' => "Calibration path '{$path}' не в whitelist для live-edit.",
                    'details' => ['allowed' => self::LIVE_EDITABLE_CALIBRATION_PATHS],
                ], 422);
            }
        }

        if (! empty($calibrationPatch) && $phase === '') {
            return response()->json([
                'status' => 'error',
                'code' => 'CALIBRATION_PHASE_REQUIRED',
                'message' => 'calibration_patch требует указания phase (generic/solution_fill/tank_recirc/irrigation).',
            ], 422);
        }
        if (! empty($calibrationPatch) && ! isset(self::ALLOWED_CALIBRATION_PHASES[$phase])) {
            return response()->json([
                'status' => 'error',
                'code' => 'CALIBRATION_PHASE_UNKNOWN',
                'message' => "Неизвестная calibration phase '{$phase}'.",
                'details' => ['allowed' => array_keys(self::ALLOWED_CALIBRATION_PHASES)],
            ], 422);
        }

        $result = DB::transaction(function () use (
            $zone, $correctionPatch, $calibrationPatch, $phase, $reason, $user
        ): array {
            $affected = [];

            if (! empty($correctionPatch)) {
                $affected['correction'] = $this->applyCorrectionPatch(
                    zone: $zone,
                    patch: $correctionPatch,
                    phase: $phase,
                    userId: $user->id,
                );
            }
            if (! empty($calibrationPatch)) {
                $affected['calibration'] = $this->applyCalibrationPatch(
                    zone: $zone,
                    patch: $calibrationPatch,
                    phase: $phase,
                    userId: $user->id,
                );
            }

            $revision = $this->revisionService->bumpAndAudit(
                scopeType: 'zone',
                scopeId: $zone->id,
                namespace: 'zone.correction.live',
                diff: [
                    'phase' => $phase ?: null,
                    'correction' => $affected['correction'] ?? null,
                    'calibration' => $affected['calibration'] ?? null,
                ],
                userId: $user->id,
                reason: $reason,
            );

            return [
                'revision' => $revision,
                'affected' => $affected,
            ];
        });

        Log::info('zone.correction.live_edited', [
            'zone_id' => $zone->id,
            'user_id' => $user->id,
            'phase' => $phase ?: null,
            'correction_fields' => array_keys($correctionPatch),
            'calibration_fields' => array_keys($calibrationPatch),
            'new_revision' => $result['revision'],
        ]);

        return response()->json([
            'status' => 'ok',
            'zone_id' => $zone->id,
            'config_revision' => $result['revision'],
            'phase' => $phase ?: null,
            'affected_fields' => [
                'correction' => array_keys($correctionPatch),
                'calibration' => array_keys($calibrationPatch),
            ],
        ]);
    }

    /**
     * @param  array<string, mixed>  $patch  dot-notation keyed
     * @return array<string, array{before: mixed, after: mixed}>
     */
    private function applyCorrectionPatch(Zone $zone, array $patch, string $phase, ?int $userId): array
    {
        $doc = $this->documents->getDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            true,
        );
        if ($doc === null) {
            throw new \RuntimeException('zone.correction document не материализован');
        }
        $payload = is_array($doc->payload) ? $doc->payload : [];

        // Target: base_config.* (без phase) или phase_overrides.{phase}.* (с phase).
        // resolver пересобирает `resolved_config` при upsert — трогать его
        // напрямую бесполезно, изменения будут стёрты на next compile.
        $targetPrefix = $phase !== '' ? "phase_overrides.{$phase}" : 'base_config';

        // Make sure phase_overrides is a proper array, not PHP [] (stdClass).
        if ($phase !== '') {
            $existing = Arr::get($payload, 'phase_overrides');
            if (! is_array($existing)) {
                Arr::set($payload, 'phase_overrides', []);
            }
        }

        $diff = [];
        foreach ($patch as $path => $value) {
            $fullPath = "{$targetPrefix}.{$path}";
            $before = Arr::get($payload, $fullPath);
            Arr::set($payload, $fullPath, $value);
            $diff[$path] = ['before' => $before, 'after' => $value];
        }

        $this->documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            $payload,
            $userId,
            'live_edit',
        );

        return $diff;
    }

    /**
     * @param  array<string, mixed>  $patch
     * @return array<string, array{before: mixed, after: mixed}>
     */
    private function applyCalibrationPatch(Zone $zone, array $patch, string $phase, ?int $userId): array
    {
        $namespace = self::ALLOWED_CALIBRATION_PHASES[$phase];
        $doc = $this->documents->getDocument(
            $namespace,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            true,
        );
        $payload = is_array($doc?->payload) ? $doc->payload : [];

        $diff = [];
        foreach ($patch as $path => $value) {
            $before = Arr::get($payload, $path);
            Arr::set($payload, $path, $value);
            $diff[$path] = ['before' => $before, 'after' => $value];
        }

        $this->documents->upsertDocument(
            $namespace,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            $payload,
            $userId,
            'live_edit',
        );

        return $diff;
    }
}
