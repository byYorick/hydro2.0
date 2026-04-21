import type { AutomationProfile } from '@/schemas/automationProfile';
import { automationProfileDefaults } from '@/schemas/automationProfile';

type Dict = Record<string, unknown>;

function asDict(value: unknown): Dict {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    return value as Dict;
}

function asNumber(value: unknown, fallback: number): number {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim() !== '') {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) return parsed;
    }
    return fallback;
}

function asBool(value: unknown, fallback: boolean): boolean {
    if (typeof value === 'boolean') return value;
    if (value === 'true' || value === 1 || value === '1') return true;
    if (value === 'false' || value === 0 || value === '0') return false;
    return fallback;
}

function asString(value: unknown, fallback: string): string {
    if (typeof value === 'string') return value;
    if (typeof value === 'number') return String(value);
    return fallback;
}

function asEnum<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
    if (typeof value === 'string' && (allowed as readonly string[]).includes(value)) {
        return value as T;
    }
    return fallback;
}

/**
 * Преобразует `zone.logic_profile` JSON payload в типизированные формы для
 * `<ZoneAutomationProfileSections>`. Неизвестные/отсутствующие поля → defaults.
 */
export function zoneLogicProfileToProfile(payload: unknown): AutomationProfile {
    const root = asDict(payload);
    const water = asDict(root.water);
    const lighting = asDict(root.lighting);
    const zoneClimate = asDict(root.zone_climate ?? root.climate);

    const irrigation = asDict(water.irrigation);
    const correction = asDict(water.correction);
    const fillWindow = asDict(water.fill_window);
    const diagnostics = asDict(water.diagnostics);
    const refill = asDict(water.refill);
    const pumps = asDict(water.pumps);
    const solutionChange = asDict(water.solution_change);
    const decision = asDict(water.irrigation_decision);
    const recovery = asDict(water.irrigation_recovery);
    const startup = asDict(water.startup);
    const correctionLimits = asDict(water.correction_limits);

    const d = automationProfileDefaults;

    return {
        waterForm: {
            systemType: asEnum(water.system_type, ['drip', 'substrate_trays', 'nft'] as const, d.waterForm.systemType),
            tanksCount: (() => {
                const raw = asNumber(water.tanks_count, d.waterForm.tanksCount);
                const rounded = Math.round(raw);
                if (rounded >= 3) return 3;
                return 2;
            })(),
            cleanTankFillL: asNumber(water.clean_tank_fill_l, d.waterForm.cleanTankFillL),
            nutrientTankTargetL: asNumber(water.nutrient_tank_target_l, d.waterForm.nutrientTankTargetL),
            irrigationBatchL: asNumber(water.irrigation_batch_l, d.waterForm.irrigationBatchL),
            intervalMinutes: asNumber(irrigation.interval_minutes ?? water.interval_minutes, d.waterForm.intervalMinutes),
            durationSeconds: asNumber(irrigation.duration_seconds ?? water.duration_seconds, d.waterForm.durationSeconds),
            fillTemperatureC: asNumber(water.fill_temperature_c, d.waterForm.fillTemperatureC),
            fillWindowStart: asString(fillWindow.start ?? water.fill_window_start, d.waterForm.fillWindowStart),
            fillWindowEnd: asString(fillWindow.end ?? water.fill_window_end, d.waterForm.fillWindowEnd),
            targetPh: asNumber(correction.target_ph ?? water.target_ph, d.waterForm.targetPh),
            targetEc: asNumber(correction.target_ec ?? water.target_ec, d.waterForm.targetEc),
            phPct: asNumber(correction.ph_pct ?? water.ph_pct, d.waterForm.phPct),
            ecPct: asNumber(correction.ec_pct ?? water.ec_pct, d.waterForm.ecPct),
            valveSwitching: asBool(water.valve_switching, d.waterForm.valveSwitching),
            correctionDuringIrrigation: asBool(water.correction_during_irrigation, d.waterForm.correctionDuringIrrigation),
            enableDrainControl: asBool(water.enable_drain_control, d.waterForm.enableDrainControl),
            drainTargetPercent: asNumber(water.drain_target_percent, d.waterForm.drainTargetPercent),
            diagnosticsEnabled: asBool(diagnostics.enabled ?? water.diagnostics_enabled, d.waterForm.diagnosticsEnabled),
            diagnosticsIntervalMinutes: asNumber(diagnostics.interval_minutes ?? water.diagnostics_interval_minutes, d.waterForm.diagnosticsIntervalMinutes),
            diagnosticsWorkflow: asEnum(
                diagnostics.workflow,
                ['startup', 'cycle_start', 'diagnostics'] as const,
                'diagnostics',
            ),
            cleanTankFullThreshold: asNumber(water.clean_tank_full_threshold, d.waterForm.cleanTankFullThreshold),
            refillDurationSeconds: asNumber(refill.duration_seconds ?? water.refill_duration_seconds, d.waterForm.refillDurationSeconds),
            refillTimeoutSeconds: asNumber(refill.timeout_seconds ?? water.refill_timeout_seconds, d.waterForm.refillTimeoutSeconds),
            mainPumpFlowLpm: asNumber(pumps.main_flow_lpm ?? water.main_pump_flow_lpm, d.waterForm.mainPumpFlowLpm),
            cleanWaterFlowLpm: asNumber(pumps.clean_water_flow_lpm ?? water.clean_water_flow_lpm, d.waterForm.cleanWaterFlowLpm),
            workingTankL: asNumber(water.working_tank_l, d.waterForm.workingTankL),
            startupCleanFillTimeoutSeconds: asNumber(startup.clean_fill_timeout_seconds, d.waterForm.refillTimeoutSeconds),
            startupSolutionFillTimeoutSeconds: asNumber(startup.solution_fill_timeout_seconds, d.waterForm.refillTimeoutSeconds),
            startupPrepareRecirculationTimeoutSeconds: asNumber(startup.prepare_recirculation_timeout_seconds, d.waterForm.refillTimeoutSeconds),
            startupCleanFillRetryCycles: asNumber(startup.clean_fill_retry_cycles, 0),
            cleanFillMinCheckDelayMs: asNumber(startup.clean_fill_min_check_delay_ms, 0),
            solutionFillCleanMinCheckDelayMs: asNumber(startup.solution_fill_clean_min_check_delay_ms, 0),
            solutionFillSolutionMinCheckDelayMs: asNumber(startup.solution_fill_solution_min_check_delay_ms, 0),
            recirculationStopOnSolutionMin: asBool(startup.recirculation_stop_on_solution_min, false),
            estopDebounceMs: asNumber(startup.estop_debounce_ms, 0),
            irrigationDecisionStrategy: asEnum(
                decision.strategy,
                ['task', 'smart_soil_v1'] as const,
                'task',
            ),
            irrigationDecisionLookbackSeconds: asNumber(decision.lookback_sec, 0),
            irrigationDecisionMinSamples: asNumber(decision.min_samples, 0),
            irrigationDecisionStaleAfterSeconds: asNumber(decision.stale_after_sec, 0),
            irrigationDecisionHysteresisPct: asNumber(decision.hysteresis_pct, 0),
            irrigationDecisionSpreadAlertThresholdPct: asNumber(decision.spread_alert_threshold_pct, 0),
            irrigationRecoveryMaxContinueAttempts: asNumber(recovery.max_continue_attempts, 0),
            irrigationRecoveryTimeoutSeconds: asNumber(recovery.timeout_seconds, 0),
            irrigationAutoReplayAfterSetup: asBool(recovery.auto_replay_after_setup, false),
            irrigationMaxSetupReplays: asNumber(recovery.max_setup_replays, 0),
            stopOnSolutionMin: asBool(water.stop_on_solution_min, false),
            correctionMaxEcCorrectionAttempts: asNumber(correctionLimits.max_ec_correction_attempts, 0),
            correctionMaxPhCorrectionAttempts: asNumber(correctionLimits.max_ph_correction_attempts, 0),
            correctionPrepareRecirculationMaxAttempts: asNumber(correctionLimits.prepare_recirculation_max_attempts, 0),
            correctionPrepareRecirculationMaxCorrectionAttempts: asNumber(correctionLimits.prepare_recirculation_max_correction_attempts, 0),
            correctionStabilizationSec: asNumber(correctionLimits.stabilization_sec, 0),
            refillRequiredNodeTypes: asString(refill.required_node_types, d.waterForm.refillRequiredNodeTypes),
            refillPreferredChannel: asString(refill.preferred_channel, d.waterForm.refillPreferredChannel),
            solutionChangeEnabled: asBool(solutionChange.enabled, d.waterForm.solutionChangeEnabled),
            solutionChangeIntervalMinutes: asNumber(solutionChange.interval_minutes, d.waterForm.solutionChangeIntervalMinutes),
            solutionChangeDurationSeconds: asNumber(solutionChange.duration_seconds, d.waterForm.solutionChangeDurationSeconds),
            manualIrrigationSeconds: asNumber(water.manual_irrigation_seconds, d.waterForm.manualIrrigationSeconds),
        },
        lightingForm: {
            enabled: asBool(lighting.enabled, d.lightingForm.enabled),
            luxDay: asNumber(lighting.lux_day, d.lightingForm.luxDay),
            luxNight: asNumber(lighting.lux_night, d.lightingForm.luxNight),
            hoursOn: asNumber(lighting.hours_on ?? lighting.photoperiod_hours, d.lightingForm.hoursOn),
            intervalMinutes: asNumber(lighting.interval_minutes, d.lightingForm.intervalMinutes),
            scheduleStart: asString(lighting.schedule_start ?? lighting.start_time, d.lightingForm.scheduleStart),
            scheduleEnd: asString(lighting.schedule_end ?? lighting.end_time, d.lightingForm.scheduleEnd),
            manualIntensity: asNumber(lighting.manual_intensity, d.lightingForm.manualIntensity),
            manualDurationHours: asNumber(lighting.manual_duration_hours, d.lightingForm.manualDurationHours),
        },
        zoneClimateForm: {
            enabled: asBool(zoneClimate.enabled, d.zoneClimateForm.enabled),
        },
        assignments: { ...d.assignments },
    };
}

/**
 * Преобразует `AutomationProfile` обратно в `zone.logic_profile` JSON payload
 * (PUT /api/automation-configs/zone/{id}/zone.logic_profile).
 */
export function profileToZoneLogicProfile(profile: AutomationProfile): Dict {
    const w = profile.waterForm;
    const l = profile.lightingForm;
    const z = profile.zoneClimateForm;

    return {
        water: {
            system_type: w.systemType,
            tanks_count: w.tanksCount,
            clean_tank_fill_l: w.cleanTankFillL,
            nutrient_tank_target_l: w.nutrientTankTargetL,
            irrigation_batch_l: w.irrigationBatchL,
            irrigation: {
                interval_minutes: w.intervalMinutes,
                duration_seconds: w.durationSeconds,
            },
            fill_temperature_c: w.fillTemperatureC,
            fill_window: {
                start: w.fillWindowStart,
                end: w.fillWindowEnd,
            },
            correction: {
                target_ph: w.targetPh,
                target_ec: w.targetEc,
                ph_pct: w.phPct,
                ec_pct: w.ecPct,
            },
            valve_switching: w.valveSwitching,
            correction_during_irrigation: w.correctionDuringIrrigation,
            enable_drain_control: w.enableDrainControl,
            drain_target_percent: w.drainTargetPercent,
            diagnostics: {
                enabled: w.diagnosticsEnabled,
                interval_minutes: w.diagnosticsIntervalMinutes,
                workflow: w.diagnosticsWorkflow,
            },
            clean_tank_full_threshold: w.cleanTankFullThreshold,
            refill: {
                duration_seconds: w.refillDurationSeconds,
                timeout_seconds: w.refillTimeoutSeconds,
                required_node_types: w.refillRequiredNodeTypes,
                preferred_channel: w.refillPreferredChannel,
            },
            pumps: {
                main_flow_lpm: w.mainPumpFlowLpm,
                clean_water_flow_lpm: w.cleanWaterFlowLpm,
            },
            working_tank_l: w.workingTankL,
            startup: {
                clean_fill_timeout_seconds: w.startupCleanFillTimeoutSeconds,
                solution_fill_timeout_seconds: w.startupSolutionFillTimeoutSeconds,
                prepare_recirculation_timeout_seconds: w.startupPrepareRecirculationTimeoutSeconds,
                clean_fill_retry_cycles: w.startupCleanFillRetryCycles,
                clean_fill_min_check_delay_ms: w.cleanFillMinCheckDelayMs,
                solution_fill_clean_min_check_delay_ms: w.solutionFillCleanMinCheckDelayMs,
                solution_fill_solution_min_check_delay_ms: w.solutionFillSolutionMinCheckDelayMs,
                recirculation_stop_on_solution_min: w.recirculationStopOnSolutionMin,
                estop_debounce_ms: w.estopDebounceMs,
            },
            irrigation_decision: {
                strategy: w.irrigationDecisionStrategy,
                lookback_sec: w.irrigationDecisionLookbackSeconds,
                min_samples: w.irrigationDecisionMinSamples,
                stale_after_sec: w.irrigationDecisionStaleAfterSeconds,
                hysteresis_pct: w.irrigationDecisionHysteresisPct,
                spread_alert_threshold_pct: w.irrigationDecisionSpreadAlertThresholdPct,
            },
            irrigation_recovery: {
                max_continue_attempts: w.irrigationRecoveryMaxContinueAttempts,
                timeout_seconds: w.irrigationRecoveryTimeoutSeconds,
                auto_replay_after_setup: w.irrigationAutoReplayAfterSetup,
                max_setup_replays: w.irrigationMaxSetupReplays,
            },
            stop_on_solution_min: w.stopOnSolutionMin,
            correction_limits: {
                max_ec_correction_attempts: w.correctionMaxEcCorrectionAttempts,
                max_ph_correction_attempts: w.correctionMaxPhCorrectionAttempts,
                prepare_recirculation_max_attempts: w.correctionPrepareRecirculationMaxAttempts,
                prepare_recirculation_max_correction_attempts: w.correctionPrepareRecirculationMaxCorrectionAttempts,
                stabilization_sec: w.correctionStabilizationSec,
            },
            solution_change: {
                enabled: w.solutionChangeEnabled,
                interval_minutes: w.solutionChangeIntervalMinutes,
                duration_seconds: w.solutionChangeDurationSeconds,
            },
            manual_irrigation_seconds: w.manualIrrigationSeconds,
        },
        lighting: {
            enabled: l.enabled,
            lux_day: l.luxDay,
            lux_night: l.luxNight,
            hours_on: l.hoursOn,
            interval_minutes: l.intervalMinutes,
            schedule_start: l.scheduleStart,
            schedule_end: l.scheduleEnd,
            manual_intensity: l.manualIntensity,
            manual_duration_hours: l.manualDurationHours,
        },
        zone_climate: {
            enabled: z.enabled,
        },
    };
}

/**
 * Из ответа `GET /api/zones/{id}/channel-bindings` извлекает assignments для форм.
 * Ожидаемый формат: array объектов `{role, node_channel_id}` или `{role, channel_id}`.
 */
export function bindingsResponseToAssignments(raw: unknown): AutomationProfile['assignments'] {
    const out = { ...automationProfileDefaults.assignments };
    const list = Array.isArray(raw)
        ? raw
        : Array.isArray((raw as { data?: unknown })?.data)
          ? ((raw as { data?: unknown }).data as unknown[])
          : [];
    for (const entry of list) {
        if (!entry || typeof entry !== 'object') continue;
        const rec = entry as Dict;
        const role = asString(rec.role, '');
        const id = asNumber(rec.node_channel_id ?? rec.channel_id ?? rec.id, 0);
        if (role in out && id > 0) {
            (out as Record<string, number | null>)[role] = id;
        }
    }
    return out;
}

export type AssignmentApplyPayload = {
    zone_id: number;
    assignments: Record<string, number>;
};

/**
 * Готовит payload для `POST /api/setup-wizard/apply-device-bindings`.
 * Значения assignments — node IDs, backend сам маппит node → все каналы по asset_type.
 */
export function assignmentsToApplyPayload(
    zoneId: number,
    assignments: AutomationProfile['assignments'],
): AssignmentApplyPayload {
    const out: Record<string, number> = {};
    for (const [role, id] of Object.entries(assignments)) {
        if (typeof id === 'number' && id > 0) {
            out[role] = id;
        }
    }
    return { zone_id: zoneId, assignments: out };
}
