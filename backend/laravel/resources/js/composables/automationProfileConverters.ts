import type { AutomationProfile } from '@/schemas/automationProfile';
import { automationProfileDefaults } from '@/schemas/automationProfile';
import {
    createDefaultClimateForm,
    FALLBACK_AUTOMATION_DEFAULTS,
} from './useAutomationDefaults';
import { buildGrowthCycleConfigPayload } from './zoneAutomationProfilePayload';
import type { ZoneAutomationForms } from './zoneAutomationTypes';
import {
    normalizeZoneLogicProfilePayload,
    resolveZoneLogicProfileEntry,
    upsertZoneLogicProfilePayload,
    type ZoneAutomationLogicMode,
} from './zoneLogicProfileDocument';

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

function asStringList(value: unknown): string[] {
    if (!Array.isArray(value)) return [];
    return value
        .filter((item): item is string => typeof item === 'string')
        .map((item) => item.trim())
        .filter((item) => item.length > 0);
}

function asEnum<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
    if (typeof value === 'string' && (allowed as readonly string[]).includes(value)) {
        return value as T;
    }
    return fallback;
}

function firstDict(value: unknown): Dict {
    if (!Array.isArray(value)) return {};
    return asDict(value[0]);
}

function secondsToMinutes(value: unknown, fallback: number): number {
    const seconds = asNumber(value, Number.NaN);
    if (!Number.isFinite(seconds)) return fallback;
    return Math.max(0, Math.round(seconds / 60));
}

function asRatio(value: unknown, fallback: number): number {
    const number = asNumber(value, fallback);
    if (number > 1 && number <= 100) return number / 100;
    return number;
}

function profileFromCanonicalSubsystems(subsystems: Dict): AutomationProfile {
    const d = automationProfileDefaults;
    const fb = FALLBACK_AUTOMATION_DEFAULTS;

    const irrigation = asDict(subsystems.irrigation);
    const irrigationExecution = asDict(irrigation.execution);
    const irrigationDecision = asDict(irrigation.decision);
    const irrigationDecisionConfig = asDict(irrigationDecision.config);
    const irrigationRecovery = asDict(irrigation.recovery);
    const irrigationSafety = asDict(irrigation.safety);
    const irrigationSchedule = firstDict(irrigationExecution.schedule);
    const drainControl = asDict(irrigationExecution.drain_control);

    const diagnostics = asDict(subsystems.diagnostics);
    const diagnosticsExecution = asDict(diagnostics.execution);
    const diagnosticsRefill = asDict(diagnosticsExecution.refill);
    const diagnosticsStartup = asDict(diagnosticsExecution.startup);
    const diagnosticsCorrection = asDict(diagnosticsExecution.correction);
    const diagnosticsRecovery = asDict(diagnosticsExecution.irrigation_recovery);
    const failSafeGuards = asDict(diagnosticsExecution.fail_safe_guards);

    const lighting = asDict(subsystems.lighting);
    const lightingExecution = asDict(lighting.execution);
    const lightingLux = asDict(lightingExecution.lux);
    const lightingPhotoperiod = asDict(lightingExecution.photoperiod);
    const lightingSchedule = firstDict(lightingExecution.schedule);

    const zoneClimate = asDict(subsystems.zone_climate ?? subsystems.climate);
    const solutionChange = asDict(subsystems.solution_change);
    const solutionChangeExecution = asDict(solutionChange.execution);

    const detectedTopology = asString(diagnosticsExecution.topology, '');
    const fallbackTanksCount = detectedTopology === 'three_tank_drip_substrate_trays' ? 3 : d.waterForm.tanksCount;
    const refillRequiredNodeTypes = asStringList(
        diagnosticsExecution.required_node_types ?? diagnosticsStartup.required_node_types,
    ).join(',');

    return {
        waterForm: {
            systemType: asEnum(
                irrigationExecution.system_type,
                ['drip', 'substrate_trays', 'nft'] as const,
                d.waterForm.systemType,
            ),
            tanksCount: (() => {
                const raw = asNumber(irrigationExecution.tanks_count, fallbackTanksCount);
                const rounded = Math.round(raw);
                return rounded >= 3 ? 3 : 2;
            })(),
            cleanTankFillL: asNumber(irrigationExecution.clean_tank_fill_l, d.waterForm.cleanTankFillL),
            nutrientTankTargetL: asNumber(irrigationExecution.nutrient_tank_target_l, d.waterForm.nutrientTankTargetL),
            irrigationBatchL: asNumber(irrigationExecution.irrigation_batch_l, d.waterForm.irrigationBatchL),
            intervalMinutes: asNumber(
                irrigationExecution.interval_minutes,
                secondsToMinutes(irrigationExecution.interval_sec, d.waterForm.intervalMinutes),
            ),
            durationSeconds: asNumber(
                irrigationExecution.duration_seconds,
                asNumber(irrigationExecution.duration_sec, d.waterForm.durationSeconds),
            ),
            fillTemperatureC: asNumber(irrigationExecution.fill_temperature_c, d.waterForm.fillTemperatureC),
            fillWindowStart: asString(irrigationSchedule.start, d.waterForm.fillWindowStart),
            fillWindowEnd: asString(irrigationSchedule.end, d.waterForm.fillWindowEnd),
            targetPh: d.waterForm.targetPh,
            targetEc: d.waterForm.targetEc,
            phPct: d.waterForm.phPct,
            ecPct: d.waterForm.ecPct,
            valveSwitching: asBool(irrigationExecution.valve_switching_enabled, d.waterForm.valveSwitching),
            correctionDuringIrrigation: asBool(
                irrigationExecution.correction_during_irrigation,
                d.waterForm.correctionDuringIrrigation,
            ),
            enableDrainControl: asBool(drainControl.enabled, d.waterForm.enableDrainControl),
            drainTargetPercent: asNumber(drainControl.target_percent, d.waterForm.drainTargetPercent),
            diagnosticsEnabled: asBool(diagnostics.enabled, d.waterForm.diagnosticsEnabled),
            diagnosticsIntervalMinutes: secondsToMinutes(
                diagnosticsExecution.interval_sec,
                d.waterForm.diagnosticsIntervalMinutes,
            ),
            diagnosticsWorkflow: asEnum(
                diagnosticsExecution.workflow,
                ['startup', 'cycle_start', 'diagnostics'] as const,
                'diagnostics',
            ),
            cleanTankFullThreshold: asRatio(
                diagnosticsExecution.clean_tank_full_threshold,
                d.waterForm.cleanTankFullThreshold,
            ),
            refillDurationSeconds: asNumber(
                diagnosticsRefill.duration_sec ?? diagnosticsExecution.refill_duration_sec,
                d.waterForm.refillDurationSeconds,
            ),
            refillTimeoutSeconds: asNumber(
                diagnosticsRefill.timeout_sec ?? diagnosticsExecution.refill_timeout_sec,
                d.waterForm.refillTimeoutSeconds,
            ),
            mainPumpFlowLpm: d.waterForm.mainPumpFlowLpm,
            cleanWaterFlowLpm: d.waterForm.cleanWaterFlowLpm,
            workingTankL: d.waterForm.workingTankL,
            startupCleanFillTimeoutSeconds: asNumber(
                diagnosticsStartup.clean_fill_timeout_sec,
                d.waterForm.refillTimeoutSeconds,
            ),
            startupSolutionFillTimeoutSeconds: asNumber(
                diagnosticsStartup.solution_fill_timeout_sec,
                d.waterForm.refillTimeoutSeconds,
            ),
            startupPrepareRecirculationTimeoutSeconds: asNumber(
                diagnosticsStartup.prepare_recirculation_timeout_sec,
                d.waterForm.refillTimeoutSeconds,
            ),
            startupCleanFillRetryCycles: asNumber(diagnosticsStartup.clean_fill_retry_cycles, 0),
            cleanFillMinCheckDelayMs: asNumber(failSafeGuards.clean_fill_min_check_delay_ms, fb.water_clean_fill_min_check_delay_ms),
            solutionFillCleanMinCheckDelayMs: asNumber(
                failSafeGuards.solution_fill_clean_min_check_delay_ms,
                fb.water_solution_fill_clean_min_check_delay_ms,
            ),
            solutionFillSolutionMinCheckDelayMs: asNumber(
                failSafeGuards.solution_fill_solution_min_check_delay_ms,
                fb.water_solution_fill_solution_min_check_delay_ms,
            ),
            recirculationStopOnSolutionMin: asBool(
                failSafeGuards.recirculation_stop_on_solution_min,
                fb.water_recirculation_stop_on_solution_min,
            ),
            estopDebounceMs: asNumber(failSafeGuards.estop_debounce_ms, fb.water_estop_debounce_ms),
            irrigationDecisionStrategy: asEnum(
                irrigationDecision.strategy,
                ['task', 'smart_soil_v1'] as const,
                'task',
            ),
            irrigationDecisionLookbackSeconds: asNumber(irrigationDecisionConfig.lookback_sec, 0),
            irrigationDecisionMinSamples: asNumber(irrigationDecisionConfig.min_samples, 0),
            irrigationDecisionStaleAfterSeconds: asNumber(irrigationDecisionConfig.stale_after_sec, 0),
            irrigationDecisionHysteresisPct: asNumber(irrigationDecisionConfig.hysteresis_pct, 0),
            irrigationDecisionSpreadAlertThresholdPct: asNumber(
                irrigationDecisionConfig.spread_alert_threshold_pct,
                0,
            ),
            irrigationRecoveryMaxContinueAttempts: asNumber(
                irrigationRecovery.max_continue_attempts ?? diagnosticsRecovery.max_continue_attempts,
                0,
            ),
            irrigationRecoveryTimeoutSeconds: asNumber(
                irrigationRecovery.timeout_sec ?? diagnosticsRecovery.timeout_sec,
                0,
            ),
            irrigationAutoReplayAfterSetup: asBool(irrigationRecovery.auto_replay_after_setup, false),
            irrigationMaxSetupReplays: asNumber(irrigationRecovery.max_setup_replays, 0),
            stopOnSolutionMin: asBool(
                irrigationSafety.stop_on_solution_min ?? failSafeGuards.irrigation_stop_on_solution_min,
                fb.water_irrigation_stop_on_solution_min,
            ),
            correctionMaxEcCorrectionAttempts: asNumber(diagnosticsCorrection.max_ec_correction_attempts, 0),
            correctionMaxPhCorrectionAttempts: asNumber(diagnosticsCorrection.max_ph_correction_attempts, 0),
            correctionPrepareRecirculationMaxAttempts: asNumber(
                diagnosticsCorrection.prepare_recirculation_max_attempts,
                0,
            ),
            correctionPrepareRecirculationMaxCorrectionAttempts: asNumber(
                diagnosticsCorrection.prepare_recirculation_max_correction_attempts,
                0,
            ),
            correctionStabilizationSec: asNumber(diagnosticsCorrection.stabilization_sec, 0),
            refillRequiredNodeTypes,
            refillPreferredChannel: asString(
                diagnosticsRefill.channel ?? diagnosticsExecution.preferred_channel,
                d.waterForm.refillPreferredChannel,
            ),
            solutionChangeEnabled: asBool(solutionChange.enabled, d.waterForm.solutionChangeEnabled),
            solutionChangeIntervalMinutes: secondsToMinutes(
                solutionChangeExecution.interval_sec,
                d.waterForm.solutionChangeIntervalMinutes,
            ),
            solutionChangeDurationSeconds: asNumber(
                solutionChangeExecution.duration_sec,
                d.waterForm.solutionChangeDurationSeconds,
            ),
            manualIrrigationSeconds: d.waterForm.manualIrrigationSeconds,
        },
        lightingForm: {
            enabled: asBool(lighting.enabled, d.lightingForm.enabled),
            luxDay: asNumber(lightingLux.day, d.lightingForm.luxDay),
            luxNight: asNumber(lightingLux.night, d.lightingForm.luxNight),
            hoursOn: asNumber(lightingPhotoperiod.hours_on, d.lightingForm.hoursOn),
            intervalMinutes: secondsToMinutes(lightingExecution.interval_sec, d.lightingForm.intervalMinutes),
            scheduleStart: asString(lightingSchedule.start, d.lightingForm.scheduleStart),
            scheduleEnd: asString(lightingSchedule.end, d.lightingForm.scheduleEnd),
            manualIntensity: d.lightingForm.manualIntensity,
            manualDurationHours: d.lightingForm.manualDurationHours,
        },
        zoneClimateForm: {
            enabled: asBool(zoneClimate.enabled, d.zoneClimateForm.enabled),
        },
        assignments: { ...d.assignments },
    };
}

/**
 * Преобразует `zone.logic_profile` JSON payload в типизированные формы для
 * `<ZoneAutomationProfileSections>`. Неизвестные/отсутствующие поля → defaults.
 */
export function zoneLogicProfileToProfile(payload: unknown): AutomationProfile {
    const root = asDict(payload);
    const canonicalEntry = resolveZoneLogicProfileEntry(normalizeZoneLogicProfilePayload(root));
    if (canonicalEntry) {
        return profileFromCanonicalSubsystems(asDict(canonicalEntry.subsystems));
    }

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
    const fb = FALLBACK_AUTOMATION_DEFAULTS;

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
            cleanTankFullThreshold: asRatio(water.clean_tank_full_threshold, d.waterForm.cleanTankFullThreshold),
            refillDurationSeconds: asNumber(refill.duration_seconds ?? water.refill_duration_seconds, d.waterForm.refillDurationSeconds),
            refillTimeoutSeconds: asNumber(refill.timeout_seconds ?? water.refill_timeout_seconds, d.waterForm.refillTimeoutSeconds),
            mainPumpFlowLpm: asNumber(pumps.main_flow_lpm ?? water.main_pump_flow_lpm, d.waterForm.mainPumpFlowLpm),
            cleanWaterFlowLpm: asNumber(pumps.clean_water_flow_lpm ?? water.clean_water_flow_lpm, d.waterForm.cleanWaterFlowLpm),
            workingTankL: asNumber(water.working_tank_l, d.waterForm.workingTankL),
            startupCleanFillTimeoutSeconds: asNumber(startup.clean_fill_timeout_seconds, d.waterForm.refillTimeoutSeconds),
            startupSolutionFillTimeoutSeconds: asNumber(startup.solution_fill_timeout_seconds, d.waterForm.refillTimeoutSeconds),
            startupPrepareRecirculationTimeoutSeconds: asNumber(startup.prepare_recirculation_timeout_seconds, d.waterForm.refillTimeoutSeconds),
            startupCleanFillRetryCycles: asNumber(startup.clean_fill_retry_cycles, 0),
            cleanFillMinCheckDelayMs: asNumber(startup.clean_fill_min_check_delay_ms, fb.water_clean_fill_min_check_delay_ms),
            solutionFillCleanMinCheckDelayMs: asNumber(
                startup.solution_fill_clean_min_check_delay_ms,
                fb.water_solution_fill_clean_min_check_delay_ms,
            ),
            solutionFillSolutionMinCheckDelayMs: asNumber(
                startup.solution_fill_solution_min_check_delay_ms,
                fb.water_solution_fill_solution_min_check_delay_ms,
            ),
            recirculationStopOnSolutionMin: asBool(
                startup.recirculation_stop_on_solution_min,
                fb.water_recirculation_stop_on_solution_min,
            ),
            estopDebounceMs: asNumber(startup.estop_debounce_ms, fb.water_estop_debounce_ms),
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
            stopOnSolutionMin: asBool(water.stop_on_solution_min, fb.water_irrigation_stop_on_solution_min),
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

export function profileToZoneLogicSubsystems(profile: AutomationProfile): Dict {
    const forms: ZoneAutomationForms = {
        climateForm: createDefaultClimateForm(FALLBACK_AUTOMATION_DEFAULTS),
        waterForm: profile.waterForm,
        lightingForm: profile.lightingForm,
        zoneClimateForm: profile.zoneClimateForm,
    };

    const payload = buildGrowthCycleConfigPayload(forms, {
        includeClimateSubsystem: false,
        automationDefaults: FALLBACK_AUTOMATION_DEFAULTS,
    });

    return asDict(payload.subsystems);
}

/**
 * Преобразует `AutomationProfile` обратно в canonical `zone.logic_profile`.
 * Возвращаемое значение передаётся как payload в automation-configs API без
 * дополнительной обёртки `{ payload: ... }`.
 */
export function profileToZoneLogicProfile(
    profile: AutomationProfile,
    currentPayload: unknown = {},
    mode: ZoneAutomationLogicMode = 'working',
): Dict {
    return upsertZoneLogicProfilePayload(
        normalizeZoneLogicProfilePayload(currentPayload),
        mode,
        profileToZoneLogicSubsystems(profile),
        true,
    ) as unknown as Dict;
}

/**
 * Маппинг binding_role (от backend) → assignment_role (UI ключ).
 * Зеркало SetupWizardController::bindingSpecs() — один assignment_role
 * покрывает несколько binding_role на железе.
 */
const BINDING_ROLE_TO_ASSIGNMENT_ROLE: Record<string, keyof AutomationProfile['assignments']> = {
    pump_main: 'irrigation',
    drain: 'irrigation',
    pump_acid: 'ph_correction',
    pump_base: 'ph_correction',
    pump_a: 'ec_correction',
    pump_b: 'ec_correction',
    pump_c: 'ec_correction',
    pump_d: 'ec_correction',
    light_actuator: 'light',
    soil_moisture_sensor: 'soil_moisture_sensor',
    co2_sensor: 'co2_sensor',
    co2_actuator: 'co2_actuator',
    root_vent_actuator: 'root_vent_actuator',
};

/**
 * Из payload `data.channel_bindings` (ZoneController::show) извлекает
 * assignments для форм. Ожидаемый формат: array объектов
 * `{role, node_id, node_channel_id, ...}` — UI хранит node_id.
 *
 * Fallback: если в записях только `node_channel_id` (старый формат) — пропускаем,
 * т.к. UI работает с node_id; вызывающий должен использовать
 * deriveBindingsFromNodes() как альтернативу.
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
        const bindingRole = asString(rec.role, '');
        const nodeId = asNumber(rec.node_id, 0);
        if (nodeId <= 0) continue;
        const assignmentRole = BINDING_ROLE_TO_ASSIGNMENT_ROLE[bindingRole];
        if (!assignmentRole) continue;
        // Если уже задан этим же node_id — не перезаписываем, иначе ставим.
        const current = (out as Record<string, number | null>)[assignmentRole];
        if (current == null) {
            (out as Record<string, number | null>)[assignmentRole] = nodeId;
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
