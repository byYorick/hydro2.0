import { z } from 'zod';

export const irrigationSystemSchema = z.enum(['drip', 'substrate_trays', 'nft']);

const timeStringSchema = z
    .string()
    .regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'HH:MM format expected');

export const waterFormSchema = z.object({
    systemType: irrigationSystemSchema,
    tanksCount: z.number().int().min(2).max(3),
    cleanTankFillL: z.number().min(0),
    nutrientTankTargetL: z.number().min(0),
    irrigationBatchL: z.number().min(0),
    intervalMinutes: z.number().int().min(1).max(1440),
    durationSeconds: z.number().int().min(1).max(3600),
    fillTemperatureC: z.number().min(0).max(60),
    fillWindowStart: timeStringSchema,
    fillWindowEnd: timeStringSchema,
    targetPh: z.number().min(3).max(9),
    targetEc: z.number().min(0).max(10),
    phPct: z.number().min(0).max(100),
    ecPct: z.number().min(0).max(100),
    valveSwitching: z.boolean(),
    correctionDuringIrrigation: z.boolean(),
    enableDrainControl: z.boolean(),
    drainTargetPercent: z.number().min(0).max(100),
    diagnosticsEnabled: z.boolean(),
    diagnosticsIntervalMinutes: z.number().int().min(0),
    diagnosticsWorkflow: z.enum(['startup', 'cycle_start', 'diagnostics']).optional(),
    cleanTankFullThreshold: z.number().min(0).max(100),
    refillDurationSeconds: z.number().int().min(0),
    refillTimeoutSeconds: z.number().int().min(0),
    mainPumpFlowLpm: z.number().min(0).max(500),
    cleanWaterFlowLpm: z.number().min(0).max(500),
    workingTankL: z.number().min(0),
    startupCleanFillTimeoutSeconds: z.number().int().min(0).optional(),
    startupSolutionFillTimeoutSeconds: z.number().int().min(0).optional(),
    startupPrepareRecirculationTimeoutSeconds: z.number().int().min(0).optional(),
    startupCleanFillRetryCycles: z.number().int().min(0).optional(),
    cleanFillMinCheckDelayMs: z.number().int().min(0).optional(),
    solutionFillCleanMinCheckDelayMs: z.number().int().min(0).optional(),
    solutionFillSolutionMinCheckDelayMs: z.number().int().min(0).optional(),
    recirculationStopOnSolutionMin: z.boolean().optional(),
    estopDebounceMs: z.number().int().min(0).optional(),
    irrigationDecisionStrategy: z.enum(['task', 'smart_soil_v1']).optional(),
    irrigationDecisionLookbackSeconds: z.number().int().min(0).optional(),
    irrigationDecisionMinSamples: z.number().int().min(0).optional(),
    irrigationDecisionStaleAfterSeconds: z.number().int().min(0).optional(),
    irrigationDecisionHysteresisPct: z.number().min(0).optional(),
    irrigationDecisionSpreadAlertThresholdPct: z.number().min(0).optional(),
    irrigationRecoveryMaxContinueAttempts: z.number().int().min(0).optional(),
    irrigationRecoveryTimeoutSeconds: z.number().int().min(0).optional(),
    irrigationAutoReplayAfterSetup: z.boolean().optional(),
    irrigationMaxSetupReplays: z.number().int().min(0).optional(),
    stopOnSolutionMin: z.boolean().optional(),
    correctionMaxEcCorrectionAttempts: z.number().int().min(0).optional(),
    correctionMaxPhCorrectionAttempts: z.number().int().min(0).optional(),
    correctionPrepareRecirculationMaxAttempts: z.number().int().min(0).optional(),
    correctionPrepareRecirculationMaxCorrectionAttempts: z.number().int().min(0).optional(),
    correctionStabilizationSec: z.number().int().min(0).optional(),
    refillRequiredNodeTypes: z.string(),
    refillPreferredChannel: z.string(),
    solutionChangeEnabled: z.boolean(),
    solutionChangeIntervalMinutes: z.number().int().min(0),
    solutionChangeDurationSeconds: z.number().int().min(0),
    manualIrrigationSeconds: z.number().int().min(0),
});

export const lightingFormSchema = z.object({
    enabled: z.boolean(),
    luxDay: z.number().min(0),
    luxNight: z.number().min(0),
    hoursOn: z.number().min(0).max(24),
    intervalMinutes: z.number().int().min(1).max(1440),
    scheduleStart: timeStringSchema,
    scheduleEnd: timeStringSchema,
    manualIntensity: z.number().min(0).max(100),
    manualDurationHours: z.number().min(0).max(24),
});

export const zoneClimateFormSchema = z.object({
    enabled: z.boolean(),
});

const nullableId = z
    .union([z.number().int().positive(), z.null()])
    .transform((v) => v);

export const assignmentsSchema = z.object({
    irrigation: nullableId,
    ph_correction: nullableId,
    ec_correction: nullableId,
    light: nullableId,
    soil_moisture_sensor: nullableId,
    co2_sensor: nullableId,
    co2_actuator: nullableId,
    root_vent_actuator: nullableId,
});

export interface AssignmentsShape {
    irrigation: number | null;
    ph_correction: number | null;
    ec_correction: number | null;
    light: number | null;
    soil_moisture_sensor: number | null;
    co2_sensor: number | null;
    co2_actuator: number | null;
    root_vent_actuator: number | null;
}

export const automationProfileSchema = z.object({
    waterForm: waterFormSchema,
    lightingForm: lightingFormSchema,
    zoneClimateForm: zoneClimateFormSchema,
    assignments: assignmentsSchema,
});

export type WaterFormSchemaShape = z.infer<typeof waterFormSchema>;
export type LightingFormSchemaShape = z.infer<typeof lightingFormSchema>;
export type ZoneClimateFormSchemaShape = z.infer<typeof zoneClimateFormSchema>;
export type AssignmentsSchemaShape = AssignmentsShape;

export interface AutomationProfile {
    waterForm: WaterFormSchemaShape;
    lightingForm: LightingFormSchemaShape;
    zoneClimateForm: ZoneClimateFormSchemaShape;
    assignments: AssignmentsShape;
}

export const automationProfileDefaults: AutomationProfile = {
    waterForm: {
        systemType: 'drip',
        tanksCount: 2,
        cleanTankFillL: 100,
        nutrientTankTargetL: 100,
        irrigationBatchL: 10,
        intervalMinutes: 30,
        durationSeconds: 120,
        fillTemperatureC: 22,
        fillWindowStart: '08:00',
        fillWindowEnd: '09:30',
        targetPh: 6.0,
        targetEc: 1.6,
        phPct: 5,
        ecPct: 5,
        valveSwitching: false,
        correctionDuringIrrigation: false,
        enableDrainControl: false,
        drainTargetPercent: 20,
        diagnosticsEnabled: true,
        diagnosticsIntervalMinutes: 60,
        cleanTankFullThreshold: 95,
        refillDurationSeconds: 60,
        refillTimeoutSeconds: 300,
        mainPumpFlowLpm: 10,
        cleanWaterFlowLpm: 15,
        workingTankL: 50,
        refillRequiredNodeTypes: '',
        refillPreferredChannel: '',
        solutionChangeEnabled: false,
        solutionChangeIntervalMinutes: 10080,
        solutionChangeDurationSeconds: 120,
        manualIrrigationSeconds: 60,
    },
    lightingForm: {
        enabled: false,
        luxDay: 30000,
        luxNight: 0,
        hoursOn: 12,
        intervalMinutes: 60,
        scheduleStart: '06:00',
        scheduleEnd: '18:00',
        manualIntensity: 70,
        manualDurationHours: 1,
    },
    zoneClimateForm: {
        enabled: false,
    },
    assignments: {
        irrigation: null,
        ph_correction: null,
        ec_correction: null,
        light: null,
        soil_moisture_sensor: null,
        co2_sensor: null,
        co2_actuator: null,
        root_vent_actuator: null,
    },
};
