import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import type { useApi } from "@/composables/useApi";
import type { useToast } from "@/composables/useToast";
import type { useZones } from "@/composables/useZones";
import { logger } from "@/utils/logger";
import { TOAST_TIMEOUT } from "@/constants/timeouts";
import { extractSetupWizardErrorDetails, extractSetupWizardErrorMessage } from "@/composables/setupWizardErrors";
import { buildGrowthCycleConfigPayload } from "@/composables/zoneAutomationPayloadBuilders";
import type { ClimateFormState, LightingFormState, WaterFormState } from "@/composables/zoneAutomationTypes";
import type { PumpCalibrationComponent } from "@/types/Calibration";
import type { DeviceChannel } from "@/types/Device";

const PUMP_ACTUATOR_TYPES = [
  "ph_acid_pump",
  "ph_base_pump",
  "ec_npk_pump",
  "ec_calcium_pump",
  "ec_magnesium_pump",
  "ec_micro_pump",
] as const;

const ACTUATOR_ALIAS_MAP: Record<string, typeof PUMP_ACTUATOR_TYPES[number]> = {
  ph_down: "ph_acid_pump",
  ph_up: "ph_base_pump",
};

const ACTUATOR_COMPONENT_MAP: Record<string, PumpCalibrationComponent> = {
  ph_acid_pump: "ph_down",
  ph_base_pump: "ph_up",
  ec_npk_pump: "npk",
  ec_calcium_pump: "calcium",
  ec_magnesium_pump: "magnesium",
  ec_micro_pump: "micro",
};

const PUMP_COMPONENT_TO_ACTUATOR_MAP: Record<string, typeof PUMP_ACTUATOR_TYPES[number]> = {
  ph_down: "ph_acid_pump",
  acid: "ph_acid_pump",
  ph_up: "ph_base_pump",
  base: "ph_base_pump",
  npk: "ec_npk_pump",
  calcium: "ec_calcium_pump",
  magnesium: "ec_magnesium_pump",
  micro: "ec_micro_pump",
};

const DEFAULT_ML_PER_SEC_BY_ACTUATOR: Record<string, number> = {
  ph_acid_pump: 0.5,
  ph_down: 0.5,
  ph_base_pump: 0.5,
  ph_up: 0.5,
  ec_npk_pump: 1,
  ec_calcium_pump: 1,
  ec_magnesium_pump: 0.8,
  ec_micro_pump: 0.8,
};

const LOGIC_RECIPE_FIELDS = [
  "ph_target",
  "ph_min",
  "ph_max",
  "ec_target",
  "ec_min",
  "ec_max",
  "systemType",
  "intervalMinutes",
  "durationSeconds",
  "dayTemp",
  "nightTemp",
  "dayHumidity",
  "nightHumidity",
  "hoursOn",
  "scheduleStart",
] as const;

type LogicRecipeField = typeof LOGIC_RECIPE_FIELDS[number];

type IrrigationSystem = "drip" | "substrate_trays" | "nft";

type WizardStepKey = "zone" | "plant" | "recipe" | "logic" | "calibration" | "confirm";

interface WizardStep {
  key: WizardStepKey;
  label: string;
}

interface WizardRecipePhase {
  ph_target?: number | null;
  ph_min?: number | null;
  ph_max?: number | null;
  ec_target?: number | null;
  ec_min?: number | null;
  ec_max?: number | null;
  irrigation_mode?: string | null;
  irrigation_interval_sec?: number | null;
  irrigation_duration_sec?: number | null;
  temp_air_target?: number | null;
  humidity_target?: number | null;
  lighting_photoperiod_hours?: number | null;
  lighting_start_time?: string | null;
}

interface WizardLogicForm {
  ph_target: number;
  ph_min: number;
  ph_max: number;
  ec_target: number;
  ec_min: number;
  ec_max: number;
  systemType: IrrigationSystem;
  tanksCount: number;
  intervalMinutes: number;
  durationSeconds: number;
  cleanTankFillL: number;
  nutrientTankTargetL: number;
  irrigationBatchL: number;
  climateEnabled: boolean;
  dayTemp: number;
  nightTemp: number;
  dayHumidity: number;
  nightHumidity: number;
  lightingEnabled: boolean;
  hoursOn: number;
  scheduleStart: string;
  scheduleEnd: string;
  _recipeLoaded: boolean;
}

interface WizardCalibrationEntry {
  node_channel_id: number;
  component: PumpCalibrationComponent;
  channel_label: string;
  ml_per_sec: number;
  skip: boolean;
}

interface WizardFormState {
  zoneId: number | null;
  startedAt: string;
  expectedHarvestAt: string;
  logic: WizardLogicForm;
  calibrations: WizardCalibrationEntry[];
  calibrationSkipped: boolean;
}

interface GrowthCycleSubmitPayload {
  zoneId: number;
  cycleId?: number;
  recipeId?: number;
  recipeRevisionId?: number;
  startedAt: string;
  expectedHarvestAt?: string;
}

export interface GrowthCycleWizardProps {
  show: boolean;
  zoneId?: number;
  zoneName?: string;
  currentPhaseTargets?: unknown;
  activeCycle?: unknown;
  initialData?: {
    recipeId?: number | null;
    recipeRevisionId?: number | null;
    plantId?: number | null;
    startedAt?: string | null;
    expectedHarvestAt?: string | null;
  } | null;
}

export type GrowthCycleWizardEmit = (event: "close" | "submit", payload?: GrowthCycleSubmitPayload) => void;

interface UseGrowthCycleWizardOptions {
  props: GrowthCycleWizardProps;
  emit: GrowthCycleWizardEmit;
  api: ReturnType<typeof useApi>["api"];
  showToast: ReturnType<typeof useToast>["showToast"];
  fetchZones: ReturnType<typeof useZones>["fetchZones"];
}

interface ZoneNodeResponse {
  id?: number;
  uid?: string;
  name?: string;
  channels?: DeviceChannel[];
}

function getNowLocalDatetimeValue(): string {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 16);
}

function createDefaultLogicForm(): WizardLogicForm {
  return {
    ph_target: 5.8,
    ph_min: 5.6,
    ph_max: 6,
    ec_target: 1.2,
    ec_min: 1,
    ec_max: 1.4,
    systemType: "drip",
    tanksCount: 2,
    intervalMinutes: 30,
    durationSeconds: 120,
    cleanTankFillL: 20,
    nutrientTankTargetL: 15,
    irrigationBatchL: 2,
    climateEnabled: false,
    dayTemp: 23,
    nightTemp: 20,
    dayHumidity: 65,
    nightHumidity: 70,
    lightingEnabled: false,
    hoursOn: 16,
    scheduleStart: "06:00",
    scheduleEnd: "22:00",
    _recipeLoaded: false,
  };
}

function createDefaultForm(zoneId?: number): WizardFormState {
  return {
    zoneId: zoneId || null,
    startedAt: getNowLocalDatetimeValue(),
    expectedHarvestAt: "",
    logic: createDefaultLogicForm(),
    calibrations: [],
    calibrationSkipped: false,
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }

  return null;
}

function resolveNodeChannelId(channel: DeviceChannel): number | null {
  const directId = toFiniteNumber(channel.node_channel_id);
  if (directId && directId > 0) {
    return directId;
  }

  const fallbackId = toFiniteNumber(channel.id);
  if (fallbackId && fallbackId > 0) {
    return fallbackId;
  }

  return null;
}

function normalizeDatetimeLocal(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  const raw = value.trim();
  if (!raw) {
    return null;
  }

  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(raw)) {
    return raw;
  }

  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }

  return parsed.toISOString().slice(0, 16);
}

function normalizeSystemType(value: unknown, fallback: IrrigationSystem): IrrigationSystem {
  const raw = String(value || "").trim().toLowerCase();

  if (raw === "substrate" || raw === "substrate_trays") {
    return "substrate_trays";
  }

  if (raw === "recirc" || raw === "nft") {
    return "nft";
  }

  if (raw === "drip") {
    return "drip";
  }

  return fallback;
}

function isValidHHMM(value: string): boolean {
  if (!/^\d{2}:\d{2}$/.test(value)) {
    return false;
  }

  const [h, m] = value.split(":").map(Number);
  return Number.isFinite(h) && Number.isFinite(m) && h >= 0 && h <= 23 && m >= 0 && m <= 59;
}

function addHoursToTime(start: string, hours: number): string {
  const [h, m] = (isValidHHMM(start) ? start : "06:00").split(":").map(Number);
  const startMinutes = h * 60 + m;
  const delta = Math.round(clamp(hours, 0, 24) * 60);
  const totalMinutes = (startMinutes + delta) % (24 * 60);
  const endH = Math.floor(totalMinutes / 60)
    .toString()
    .padStart(2, "0");
  const endM = (totalMinutes % 60).toString().padStart(2, "0");
  return `${endH}:${endM}`;
}

function areValuesEqual(a: unknown, b: unknown): boolean {
  if (typeof a === "number" && typeof b === "number") {
    return Math.abs(a - b) < 0.000001;
  }

  return String(a) === String(b);
}

function normalizeErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}

function extractNodesFromResponse(raw: unknown): ZoneNodeResponse[] {
  if (Array.isArray(raw)) {
    return raw as ZoneNodeResponse[];
  }

  if (raw && typeof raw === "object") {
    const payload = raw as {
      data?: unknown;
    };

    if (Array.isArray(payload.data)) {
      return payload.data as ZoneNodeResponse[];
    }

    if (payload.data && typeof payload.data === "object") {
      const nested = payload.data as { data?: unknown };
      if (Array.isArray(nested.data)) {
        return nested.data as ZoneNodeResponse[];
      }
    }
  }

  return [];
}

function normalizeActuatorType(channel: DeviceChannel): string | null {
  const directType = String(channel.actuator_type || "").trim().toLowerCase();
  if (directType) {
    const normalizedDirectType = ACTUATOR_ALIAS_MAP[directType] || directType;
    if (PUMP_ACTUATOR_TYPES.includes(normalizedDirectType as typeof PUMP_ACTUATOR_TYPES[number])) {
      return normalizedDirectType;
    }
  }

  const config = channel.config && typeof channel.config === "object" ? channel.config : {};
  const bindingRoleRaw = String(
    channel.binding_role
      || (config as Record<string, unknown>).zone_role
      || (config as Record<string, unknown>).binding_role
      || "",
  )
    .trim()
    .toLowerCase();
  if (bindingRoleRaw) {
    const normalizedBindingRole = ACTUATOR_ALIAS_MAP[bindingRoleRaw] || bindingRoleRaw;
    if (PUMP_ACTUATOR_TYPES.includes(normalizedBindingRole as typeof PUMP_ACTUATOR_TYPES[number])) {
      return normalizedBindingRole;
    }
  }

  const cfgActuatorType = String((config as Record<string, unknown>).actuator_type || "")
    .trim()
    .toLowerCase();
  if (cfgActuatorType) {
    const normalizedCfgType = ACTUATOR_ALIAS_MAP[cfgActuatorType] || cfgActuatorType;
    if (PUMP_ACTUATOR_TYPES.includes(normalizedCfgType as typeof PUMP_ACTUATOR_TYPES[number])) {
      return normalizedCfgType;
    }
  }

  const pumpComponentRaw = String(channel.pump_component || channel.pump_calibration?.component || "")
    .trim()
    .toLowerCase();
  if (pumpComponentRaw && PUMP_COMPONENT_TO_ACTUATOR_MAP[pumpComponentRaw]) {
    return PUMP_COMPONENT_TO_ACTUATOR_MAP[pumpComponentRaw];
  }

  const cfgPumpCalibration = (config as Record<string, unknown>).pump_calibration;
  if (cfgPumpCalibration && typeof cfgPumpCalibration === "object") {
    const cfgPumpComponent = String((cfgPumpCalibration as Record<string, unknown>).component || "")
      .trim()
      .toLowerCase();
    if (cfgPumpComponent && PUMP_COMPONENT_TO_ACTUATOR_MAP[cfgPumpComponent]) {
      return PUMP_COMPONENT_TO_ACTUATOR_MAP[cfgPumpComponent];
    }
  }

  const channelName = String(channel.channel || "").toLowerCase();
  if (channelName.includes("acid") || channelName.includes("ph_down")) {
    return "ph_acid_pump";
  }
  if (channelName.includes("base") || channelName.includes("ph_up")) {
    return "ph_base_pump";
  }
  if (channelName.includes("npk") || channelName === "pump_a") {
    return "ec_npk_pump";
  }
  if (channelName.includes("calcium") || channelName === "pump_b") {
    return "ec_calcium_pump";
  }
  if (channelName.includes("magnesium") || channelName === "pump_c") {
    return "ec_magnesium_pump";
  }
  if (channelName.includes("micro") || channelName === "pump_d") {
    return "ec_micro_pump";
  }

  return null;
}

function resolvePumpComponent(actuatorType: string): PumpCalibrationComponent | null {
  return ACTUATOR_COMPONENT_MAP[actuatorType] || null;
}

function defaultMlPerSecFor(actuatorType: string): number {
  return DEFAULT_ML_PER_SEC_BY_ACTUATOR[actuatorType] || 1;
}

function buildZoneAutomationForms(logic: WizardLogicForm, tanksCount: number): {
  climateForm: ClimateFormState;
  waterForm: WaterFormState;
  lightingForm: LightingFormState;
} {
  const safeHoursOn = clamp(logic.hoursOn, 1, 24);

  const climateForm: ClimateFormState = {
    enabled: logic.climateEnabled,
    dayTemp: clamp(logic.dayTemp, 10, 35),
    nightTemp: clamp(logic.nightTemp, 10, 35),
    dayHumidity: clamp(logic.dayHumidity, 30, 90),
    nightHumidity: clamp(logic.nightHumidity, 30, 90),
    intervalMinutes: 5,
    dayStart: "07:00",
    nightStart: "19:00",
    ventMinPercent: 15,
    ventMaxPercent: 85,
    useExternalTelemetry: true,
    outsideTempMin: 4,
    outsideTempMax: 34,
    outsideHumidityMax: 90,
    manualOverrideEnabled: true,
    overrideMinutes: 30,
  };

  const waterForm: WaterFormState = {
    systemType: logic.systemType,
    tanksCount,
    cleanTankFillL: clamp(logic.cleanTankFillL, 10, 5000),
    nutrientTankTargetL: clamp(logic.nutrientTankTargetL, 10, 5000),
    irrigationBatchL: clamp(logic.irrigationBatchL, 1, 500),
    intervalMinutes: clamp(Math.round(logic.intervalMinutes), 5, 1440),
    durationSeconds: clamp(Math.round(logic.durationSeconds), 1, 3600),
    fillTemperatureC: 20,
    fillWindowStart: "00:00",
    fillWindowEnd: "23:59",
    targetPh: clamp(logic.ph_target, 4, 9),
    targetEc: clamp(logic.ec_target, 0.1, 10),
    valveSwitching: true,
    correctionDuringIrrigation: true,
    enableDrainControl: false,
    drainTargetPercent: 20,
    diagnosticsEnabled: true,
    diagnosticsIntervalMinutes: 15,
    cycleStartWorkflowEnabled: true,
    cleanTankFullThreshold: 0.95,
    refillDurationSeconds: 120,
    refillTimeoutSeconds: 900,
    refillRequiredNodeTypes: "irrig",
    refillPreferredChannel: "",
    solutionChangeEnabled: false,
    solutionChangeIntervalMinutes: 720,
    solutionChangeDurationSeconds: 120,
    manualIrrigationSeconds: 120,
  };

  const lightingForm: LightingFormState = {
    enabled: logic.lightingEnabled,
    luxDay: 12000,
    luxNight: 0,
    hoursOn: safeHoursOn,
    intervalMinutes: 30,
    scheduleStart: isValidHHMM(logic.scheduleStart) ? logic.scheduleStart : "06:00",
    scheduleEnd: isValidHHMM(logic.scheduleEnd) ? logic.scheduleEnd : addHoursToTime(logic.scheduleStart, safeHoursOn),
    manualIntensity: 0,
    manualDurationHours: 1,
  };

  return {
    climateForm,
    waterForm,
    lightingForm,
  };
}

function buildLogicSubsystems(logic: WizardLogicForm, tanksCount: number): Record<string, unknown> {
  const isTwoTank = tanksCount === 2;
  const forms = buildZoneAutomationForms(logic, tanksCount);
  const basePayload = buildGrowthCycleConfigPayload(forms);
  const subsystems = (basePayload.subsystems || {}) as Record<string, any>;
  const diagnosticsExecution = (subsystems.diagnostics?.execution || {}) as Record<string, unknown>;
  const twoTankCommands = isTwoTank ? diagnosticsExecution.two_tank_commands : undefined;
  const startup = isTwoTank ? diagnosticsExecution.startup : undefined;

  return {
    ph: {
      enabled: true,
      execution: {},
    },
    ec: {
      enabled: true,
      execution: {},
    },
    irrigation: {
      enabled: true,
      execution: {
        interval_minutes: clamp(Math.round(logic.intervalMinutes), 5, 1440),
        interval_sec: clamp(Math.round(logic.intervalMinutes), 5, 1440) * 60,
        duration_seconds: clamp(Math.round(logic.durationSeconds), 10, 3600),
        duration_sec: clamp(Math.round(logic.durationSeconds), 10, 3600),
        system_type: logic.systemType,
        tanks_count: tanksCount,
        ...(isTwoTank
          ? {
              clean_tank_fill_l: clamp(Math.round(logic.cleanTankFillL), 10, 5000),
              nutrient_tank_target_l: clamp(Math.round(logic.nutrientTankTargetL), 10, 5000),
              irrigation_batch_l: clamp(Math.round(logic.irrigationBatchL), 1, 500),
            }
          : {}),
        valve_switching_enabled: true,
        correction_during_irrigation: true,
        correction_node: {
          target_ph: Number(logic.ph_target.toFixed(2)),
          target_ec: Number(logic.ec_target.toFixed(2)),
          sensors_location: "correction_node",
        },
        topology: isTwoTank ? "two_tank_drip_substrate_trays" : "three_tank_drip",
        ...(isTwoTank && twoTankCommands ? { two_tank_commands: twoTankCommands } : {}),
      },
    },
    diagnostics: {
      enabled: true,
      execution: {
        interval_sec: 900,
        workflow: "startup",
        target_ph: Number(logic.ph_target.toFixed(2)),
        target_ec: Number(logic.ec_target.toFixed(2)),
        topology: isTwoTank ? "two_tank_drip_substrate_trays" : "three_tank_drip",
        ...(startup ? { startup } : {}),
        ...(isTwoTank && twoTankCommands ? { two_tank_commands: twoTankCommands } : {}),
      },
    },
    climate: {
      enabled: logic.climateEnabled,
      execution: logic.climateEnabled
        ? {
            interval_sec: 300,
            temperature: {
              day: clamp(logic.dayTemp, 10, 35),
              night: clamp(logic.nightTemp, 10, 35),
            },
            humidity: {
              day: clamp(logic.dayHumidity, 30, 90),
              night: clamp(logic.nightHumidity, 30, 90),
            },
          }
        : {},
    },
    lighting: {
      enabled: logic.lightingEnabled,
      execution: logic.lightingEnabled
        ? {
            interval_sec: 1800,
            photoperiod: {
              hours_on: clamp(logic.hoursOn, 1, 24),
              hours_off: clamp(24 - logic.hoursOn, 0, 23),
            },
            schedule: [
              {
                start: isValidHHMM(logic.scheduleStart) ? logic.scheduleStart : "06:00",
                end: isValidHHMM(logic.scheduleEnd) ? logic.scheduleEnd : addHoursToTime(logic.scheduleStart, logic.hoursOn),
              },
            ],
          }
        : {},
    },
  };
}

export function useGrowthCycleWizard({
  props,
  emit,
  api,
  showToast,
  fetchZones,
}: UseGrowthCycleWizardOptions) {
  const currentStep = ref(0);
  const recipeMode = ref<"select" | "create">("select");
  const loading = ref(false);
  const error = ref<string | null>(null);
  const errorDetails = ref<string[]>([]);
  const validationErrors = ref<string[]>([]);

  const form = ref<WizardFormState>(createDefaultForm(props.zoneId));

  const availableZones = ref<any[]>([]);
  const availablePlants = ref<any[]>([]);
  const availableRecipes = ref<any[]>([]);
  const selectedRecipe = ref<any | null>(null);
  const selectedRecipeId = ref<number | null>(null);
  const selectedRevisionId = ref<number | null>(null);
  const selectedPlantId = ref<number | null>(null);

  const zoneChannels = ref<DeviceChannel[]>([]);
  const isZoneChannelsLoading = ref(false);
  const zoneChannelsLoaded = ref(false);
  const zoneChannelsError = ref<string | null>(null);

  const recipeLogicSeed = ref<Partial<Record<LogicRecipeField, number | string>>>({});

  const availableRevisions = computed(() => {
    if (!selectedRecipe.value) {
      return [];
    }

    return selectedRecipe.value.published_revisions || [];
  });

  const selectedRevision = computed(() => {
    if (!selectedRevisionId.value) {
      return null;
    }

    return availableRevisions.value.find((revision: any) => revision.id === selectedRevisionId.value) || null;
  });

  const steps: WizardStep[] = [
    { key: "zone", label: "Зона" },
    { key: "plant", label: "Растение" },
    { key: "recipe", label: "Рецепт" },
    { key: "logic", label: "Логика" },
    { key: "calibration", label: "Насосы" },
    { key: "confirm", label: "Запуск" },
  ];

  const wizardTitle = computed(() => {
    return props.activeCycle ? "Корректировка цикла выращивания" : "Запуск нового цикла выращивания";
  });

  const minStartDate = computed(() => {
    return getNowLocalDatetimeValue();
  });

  const totalDurationDays = computed(() => {
    if (!selectedRevision.value?.phases) {
      return 0;
    }

    const totalHours = selectedRevision.value.phases.reduce((sum: number, phase: any) => {
      if (typeof phase.duration_hours === "number") {
        return sum + phase.duration_hours;
      }
      if (typeof phase.duration_days === "number") {
        return sum + phase.duration_days * 24;
      }
      return sum;
    }, 0);

    return totalHours / 24;
  });

  const tanksCount = computed(() => {
    return form.value.logic.systemType === "nft" ? 0 : 2;
  });

  const canProceed = computed(() => {
    switch (currentStep.value) {
      case 0:
        return form.value.zoneId !== null;
      case 1:
        return selectedPlantId.value !== null;
      case 2:
        return selectedRevisionId.value !== null && selectedRecipe.value !== null;
      case 3:
        if (!form.value.startedAt) {
          return false;
        }

        if (Number.isNaN(new Date(form.value.startedAt).getTime())) {
          return false;
        }

        return (
          form.value.logic.ph_target >= 4
          && form.value.logic.ph_target <= 9
          && form.value.logic.ph_min < form.value.logic.ph_max
          && form.value.logic.ec_target >= 0
          && form.value.logic.intervalMinutes >= 5
          && form.value.logic.durationSeconds >= 10
        );
      case 4:
        return true;
      default:
        return true;
    }
  });

  const canSubmit = computed(() => {
    return canProceed.value && validationErrors.value.length === 0;
  });

  const hasCalibrationChannels = computed(() => form.value.calibrations.length > 0);

  const nextStepBlockedReason = computed(() => {
    if (currentStep.value === 0 && !form.value.zoneId) {
      return "Выберите зону, чтобы продолжить.";
    }

    if (currentStep.value === 1 && !selectedPlantId.value) {
      return "Выберите растение, чтобы продолжить.";
    }

    if (currentStep.value === 2) {
      if (!selectedRecipeId.value) {
        return "Выберите рецепт.";
      }

      if (!selectedRevisionId.value) {
        return "Выберите ревизию рецепта.";
      }
    }

    if (currentStep.value === 3) {
      if (!form.value.startedAt) {
        return "Укажите дату начала цикла.";
      }

      const startDate = new Date(form.value.startedAt);
      if (Number.isNaN(startDate.getTime())) {
        return "Дата начала указана некорректно.";
      }

      const now = new Date();
      now.setSeconds(0, 0);
      if (startDate < now) {
        return "Дата начала не может быть в прошлом.";
      }

      if (form.value.logic.ph_target < 4 || form.value.logic.ph_target > 9) {
        return "target pH должен быть в диапазоне 4-9.";
      }

      if (form.value.logic.ph_min >= form.value.logic.ph_max) {
        return "Минимум pH должен быть меньше максимума.";
      }

      if (form.value.logic.ec_target < 0 || form.value.logic.ec_target > 30) {
        return "target EC должен быть в диапазоне 0-30.";
      }

      if (form.value.logic.intervalMinutes < 5 || form.value.logic.intervalMinutes > 1440) {
        return "Интервал полива должен быть в диапазоне 5-1440 минут.";
      }

      if (form.value.logic.durationSeconds < 10 || form.value.logic.durationSeconds > 3600) {
        return "Длительность полива должна быть в диапазоне 10-3600 секунд.";
      }

      if (tanksCount.value === 2 && (form.value.logic.cleanTankFillL <= 0 || form.value.logic.nutrientTankTargetL <= 0)) {
        return "Объёмы баков должны быть больше нуля.";
      }

      if (form.value.logic.climateEnabled && (form.value.logic.dayTemp < 10 || form.value.logic.dayTemp > 40)) {
        return "Дневная температура должна быть в диапазоне 10-40°C.";
      }

      if (form.value.logic.lightingEnabled) {
        if (form.value.logic.hoursOn < 1 || form.value.logic.hoursOn > 24) {
          return "Фотопериод должен быть в диапазоне 1-24 часа.";
        }

        if (!isValidHHMM(form.value.logic.scheduleStart) || !isValidHHMM(form.value.logic.scheduleEnd)) {
          return "Укажите корректное расписание света в формате HH:MM.";
        }
      }
    }

    return "";
  });

  function formatDateTime(dateString: string): string {
    if (!dateString) {
      return "";
    }

    try {
      const date = new Date(dateString);
      return date.toLocaleString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return dateString;
    }
  }

  function formatDate(dateString: string): string {
    if (!dateString) {
      return "";
    }

    try {
      const date = new Date(dateString);
      return date.toLocaleDateString("ru-RU");
    } catch {
      return dateString;
    }
  }

  function rememberRecipeLogicSeed(): void {
    const seed: Partial<Record<LogicRecipeField, number | string>> = {};
    LOGIC_RECIPE_FIELDS.forEach((field) => {
      seed[field] = form.value.logic[field] as number | string;
    });
    recipeLogicSeed.value = seed;
  }

  function isLogicFieldOverridden(field: LogicRecipeField): boolean {
    if (!form.value.logic._recipeLoaded || !(field in recipeLogicSeed.value)) {
      return false;
    }

    return !areValuesEqual(form.value.logic[field], recipeLogicSeed.value[field]);
  }

  function isLogicFieldFromRecipe(field: LogicRecipeField): boolean {
    if (!form.value.logic._recipeLoaded || !(field in recipeLogicSeed.value)) {
      return false;
    }

    return !isLogicFieldOverridden(field);
  }

  function fillLogicFromRecipePhase(phase: WizardRecipePhase): void {
    const phTarget = toFiniteNumber(phase.ph_target) ?? 5.8;
    const phMin = toFiniteNumber(phase.ph_min) ?? 5.6;
    const phMax = toFiniteNumber(phase.ph_max) ?? 6;
    const ecTarget = toFiniteNumber(phase.ec_target) ?? 1.2;
    const ecMin = toFiniteNumber(phase.ec_min) ?? 1;
    const ecMax = toFiniteNumber(phase.ec_max) ?? 1.4;
    const temperatureTarget = toFiniteNumber(phase.temp_air_target) ?? 23;
    const humidityTarget = toFiniteNumber(phase.humidity_target) ?? 62;
    const intervalSec = toFiniteNumber(phase.irrigation_interval_sec) ?? 1800;
    const durationSec = toFiniteNumber(phase.irrigation_duration_sec) ?? 120;
    const hoursOn = toFiniteNumber(phase.lighting_photoperiod_hours) ?? 16;
    const scheduleStart = isValidHHMM(String(phase.lighting_start_time || ""))
      ? String(phase.lighting_start_time)
      : "06:00";

    form.value.logic.ph_target = Number(phTarget.toFixed(2));
    form.value.logic.ph_min = Number(phMin.toFixed(2));
    form.value.logic.ph_max = Number(phMax.toFixed(2));
    form.value.logic.ec_target = Number(ecTarget.toFixed(2));
    form.value.logic.ec_min = Number(ecMin.toFixed(2));
    form.value.logic.ec_max = Number(ecMax.toFixed(2));
    form.value.logic.systemType = normalizeSystemType(phase.irrigation_mode, form.value.logic.systemType);
    form.value.logic.intervalMinutes = Math.max(5, Math.round(intervalSec / 60));
    form.value.logic.durationSeconds = Math.max(10, Math.round(durationSec));
    form.value.logic.dayTemp = Number(temperatureTarget.toFixed(1));
    form.value.logic.nightTemp = Number((temperatureTarget - 3).toFixed(1));
    form.value.logic.dayHumidity = Math.round(humidityTarget);
    form.value.logic.nightHumidity = Math.round(humidityTarget + 8);
    form.value.logic.hoursOn = clamp(Math.round(hoursOn), 1, 24);
    form.value.logic.scheduleStart = scheduleStart;
    form.value.logic.scheduleEnd = addHoursToTime(scheduleStart, form.value.logic.hoursOn);
    form.value.logic.climateEnabled = true;
    form.value.logic.lightingEnabled = true;
    form.value.logic._recipeLoaded = true;

    rememberRecipeLogicSeed();
  }

  function getCalibrationComponentLabel(component: PumpCalibrationComponent): string {
    const labels: Record<PumpCalibrationComponent, string> = {
      npk: "NPK",
      calcium: "Ca",
      magnesium: "Mg",
      micro: "Micro",
      ph_up: "pH+",
      ph_down: "pH-",
    };

    return labels[component];
  }

  async function loadZones(): Promise<void> {
    try {
      const zones = await fetchZones(true);
      availableZones.value = zones;
    } catch (err) {
      logger.error("[GrowthCycleWizard] Failed to load zones", err);
    }
  }

  async function loadWizardData(): Promise<void> {
    try {
      const response = await api.get("/grow-cycle-wizard/data");
      if (response.data?.status === "ok") {
        const data = response.data.data || {};
        availableRecipes.value = data.recipes || [];
        availablePlants.value = data.plants || [];
      }
    } catch (err) {
      logger.error("[GrowthCycleWizard] Failed to load wizard data", err);
      showToast("Не удалось загрузить данные визарда", "error", TOAST_TIMEOUT.NORMAL);
    }
  }

  function onZoneSelected(): void {
    zoneChannelsLoaded.value = false;
    zoneChannels.value = [];
    form.value.calibrations = [];
  }

  function syncSelectedRecipe(): void {
    if (!selectedRecipeId.value) {
      selectedRecipe.value = null;
      selectedRevisionId.value = null;
      form.value.logic._recipeLoaded = false;
      recipeLogicSeed.value = {};
      return;
    }

    selectedRecipe.value = availableRecipes.value.find((recipe) => recipe.id === selectedRecipeId.value) || null;
    const revisions = selectedRecipe.value?.published_revisions || [];
    if (!revisions.length) {
      selectedRevisionId.value = null;
      return;
    }

    const hasSelected = revisions.some((revision: any) => revision.id === selectedRevisionId.value);
    if (!hasSelected) {
      selectedRevisionId.value = revisions[0].id;
    }
  }

  function onRecipeSelected(): void {
    syncSelectedRecipe();
  }

  function onRecipeCreated(recipe: any): void {
    selectedRecipeId.value = recipe.id;
    selectedRecipe.value = recipe;
    selectedRevisionId.value = recipe.latest_published_revision_id || recipe.latest_draft_revision_id || null;
    recipeMode.value = "select";
    void loadWizardData();
  }

  function applyInitialData(): void {
    const initialData = props.initialData;
    if (!initialData) {
      return;
    }

    if (initialData.plantId) {
      selectedPlantId.value = initialData.plantId;
    }

    if (initialData.recipeId) {
      selectedRecipeId.value = initialData.recipeId;
      syncSelectedRecipe();
    }

    if (initialData.recipeRevisionId) {
      selectedRevisionId.value = initialData.recipeRevisionId;
    }

    const normalizedStart = normalizeDatetimeLocal(initialData.startedAt);
    if (normalizedStart) {
      form.value.startedAt = normalizedStart;
    }

    if (initialData.expectedHarvestAt) {
      form.value.expectedHarvestAt = initialData.expectedHarvestAt;
    }

    const hasContext = Boolean(form.value.zoneId && selectedPlantId.value && selectedRecipeId.value && selectedRevisionId.value);
    if (hasContext && currentStep.value < 3) {
      currentStep.value = 3;
    }
  }

  function validateStep(step: number): boolean {
    validationErrors.value = [];

    switch (step) {
      case 0:
        if (!form.value.zoneId) {
          validationErrors.value.push("Необходимо выбрать зону");
          return false;
        }
        break;
      case 1:
        if (!selectedPlantId.value) {
          validationErrors.value.push("Необходимо выбрать растение");
          return false;
        }
        break;
      case 2:
        if (!selectedRecipeId.value || !selectedRevisionId.value) {
          validationErrors.value.push("Необходимо выбрать рецепт и ревизию");
          return false;
        }

        if (!selectedRecipe.value) {
          validationErrors.value.push("Рецепт не загружен");
          return false;
        }

        if (!selectedRevision.value?.phases || selectedRevision.value.phases.length === 0) {
          validationErrors.value.push("Рецепт должен содержать хотя бы одну фазу");
          return false;
        }
        break;
      case 3: {
        if (!form.value.startedAt) {
          validationErrors.value.push("Необходимо указать дату начала");
          return false;
        }

        const startDate = new Date(form.value.startedAt);
        if (Number.isNaN(startDate.getTime())) {
          validationErrors.value.push("Дата начала указана некорректно");
          return false;
        }

        const now = new Date();
        now.setSeconds(0, 0);
        if (startDate < now) {
          validationErrors.value.push("Дата начала не может быть в прошлом");
          return false;
        }

        if (form.value.expectedHarvestAt) {
          const harvestDate = new Date(form.value.expectedHarvestAt);
          if (harvestDate <= startDate) {
            validationErrors.value.push("Дата сбора должна быть позже даты начала");
            return false;
          }
        }

        if (form.value.logic.ph_target < 4 || form.value.logic.ph_target > 9) {
          validationErrors.value.push("target pH должен быть в диапазоне 4-9");
          return false;
        }

        if (form.value.logic.ph_min >= form.value.logic.ph_max) {
          validationErrors.value.push("Минимум pH должен быть меньше максимума");
          return false;
        }

        if (form.value.logic.ec_target < 0 || form.value.logic.ec_target > 30) {
          validationErrors.value.push("target EC должен быть в диапазоне 0-30");
          return false;
        }

        if (form.value.logic.intervalMinutes < 5 || form.value.logic.intervalMinutes > 1440) {
          validationErrors.value.push("Интервал полива должен быть в диапазоне 5-1440 минут");
          return false;
        }

        if (form.value.logic.durationSeconds < 10 || form.value.logic.durationSeconds > 3600) {
          validationErrors.value.push("Длительность полива должна быть в диапазоне 10-3600 секунд");
          return false;
        }

        if (tanksCount.value === 2) {
          if (form.value.logic.cleanTankFillL <= 0 || form.value.logic.nutrientTankTargetL <= 0) {
            validationErrors.value.push("Объёмы баков должны быть больше 0");
            return false;
          }

          if (form.value.logic.irrigationBatchL <= 0) {
            validationErrors.value.push("Объём партии полива должен быть больше 0");
            return false;
          }
        }

        if (form.value.logic.climateEnabled) {
          if (form.value.logic.dayTemp < 10 || form.value.logic.dayTemp > 40) {
            validationErrors.value.push("Дневная температура должна быть в диапазоне 10-40°C");
            return false;
          }
        }

        if (form.value.logic.lightingEnabled) {
          if (form.value.logic.hoursOn < 1 || form.value.logic.hoursOn > 24) {
            validationErrors.value.push("Фотопериод должен быть в диапазоне 1-24");
            return false;
          }

          if (!isValidHHMM(form.value.logic.scheduleStart) || !isValidHHMM(form.value.logic.scheduleEnd)) {
            validationErrors.value.push("Укажите корректное время включения/выключения света (HH:MM)");
            return false;
          }
        }

        break;
      }
      case 4:
      case 5:
      default:
        break;
    }

    return validationErrors.value.length === 0;
  }

  function nextStep(): void {
    if (!validateStep(currentStep.value)) {
      if (validationErrors.value.length > 0) {
        showToast(validationErrors.value[0], "error", TOAST_TIMEOUT.NORMAL);
      }
      return;
    }

    if (currentStep.value < steps.length - 1) {
      currentStep.value += 1;
      saveDraft();
    }
  }

  function prevStep(): void {
    if (currentStep.value > 0) {
      currentStep.value -= 1;
    }
  }

  function getDraftStorageKey(): string {
    const scope = props.zoneId ? `zone-${props.zoneId}` : "global";
    return `growthCycleWizardDraft:${scope}`;
  }

  function saveDraft(): void {
    try {
      const draft = {
        zoneId: form.value.zoneId,
        plantId: selectedPlantId.value,
        recipeId: selectedRecipeId.value,
        recipeRevisionId: selectedRevisionId.value,
        startedAt: form.value.startedAt,
        expectedHarvestAt: form.value.expectedHarvestAt,
        logic: form.value.logic,
        calibrationSkipped: form.value.calibrationSkipped,
        currentStep: currentStep.value,
      };

      localStorage.setItem(getDraftStorageKey(), JSON.stringify(draft));
    } catch (err) {
      logger.warn("[GrowthCycleWizard] Failed to save draft", err);
    }
  }

  function loadDraft(): void {
    try {
      const draftStr = localStorage.getItem(getDraftStorageKey());
      if (!draftStr) {
        return;
      }

      const draft = JSON.parse(draftStr) as Partial<{
        zoneId: number;
        plantId: number;
        recipeId: number;
        recipeRevisionId: number;
        startedAt: string;
        expectedHarvestAt: string;
        logic: Partial<WizardLogicForm>;
        calibrationSkipped: boolean;
        currentStep: number;
      }>;

      if (!props.zoneId && draft.zoneId) {
        form.value.zoneId = draft.zoneId;
      } else if (props.zoneId) {
        form.value.zoneId = props.zoneId;
      }

      if (draft.plantId) {
        selectedPlantId.value = draft.plantId;
      }

      if (draft.recipeId) {
        selectedRecipeId.value = draft.recipeId;
      }

      if (draft.recipeRevisionId) {
        selectedRevisionId.value = draft.recipeRevisionId;
      }

      if (draft.startedAt) {
        form.value.startedAt = draft.startedAt;
      }

      if (draft.expectedHarvestAt) {
        form.value.expectedHarvestAt = draft.expectedHarvestAt;
      }

      if (draft.logic) {
        form.value.logic = {
          ...form.value.logic,
          ...draft.logic,
        };
      }

      if (typeof draft.calibrationSkipped === "boolean") {
        form.value.calibrationSkipped = draft.calibrationSkipped;
      }

      if (typeof draft.currentStep === "number") {
        currentStep.value = clamp(Math.round(draft.currentStep), 0, steps.length - 1);
      }
    } catch (err) {
      logger.warn("[GrowthCycleWizard] Failed to load draft", err);
    }
  }

  function clearDraft(): void {
    try {
      localStorage.removeItem(getDraftStorageKey());
    } catch (err) {
      logger.warn("[GrowthCycleWizard] Failed to clear draft", err);
    }
  }

  async function requestZoneNodes(zoneId: number): Promise<ZoneNodeResponse[]> {
    const fallbackResponse = await api.get(`/api/nodes?zone_id=${zoneId}`);
    return extractNodesFromResponse(fallbackResponse.data);
  }

  function buildCalibrationEntries(channels: DeviceChannel[]): void {
    const currentByChannelId = new Map<number, WizardCalibrationEntry>(
      form.value.calibrations.map((entry) => [entry.node_channel_id, entry]),
    );

    const entries: WizardCalibrationEntry[] = [];

    channels.forEach((channel) => {
      const channelId = resolveNodeChannelId(channel);
      if (!channelId) {
        return;
      }

      const actuatorType = normalizeActuatorType(channel);
      if (!actuatorType || !PUMP_ACTUATOR_TYPES.includes(actuatorType as typeof PUMP_ACTUATOR_TYPES[number])) {
        return;
      }

      const component = resolvePumpComponent(actuatorType);
      if (!component) {
        return;
      }

      const existing = currentByChannelId.get(channelId);
      const calibratedMl = toFiniteNumber(channel.pump_calibration?.ml_per_sec);
      const mlPerSec = existing?.ml_per_sec
        ?? (calibratedMl !== null && calibratedMl > 0 ? calibratedMl : defaultMlPerSecFor(actuatorType));

      entries.push({
        node_channel_id: channelId,
        component,
        channel_label: existing?.channel_label || String((channel as any).__label || channel.channel || `Channel #${channelId}`),
        ml_per_sec: Number(mlPerSec.toFixed(2)),
        skip: existing?.skip ?? false,
      });
    });

    const componentOrder: PumpCalibrationComponent[] = ["ph_down", "ph_up", "npk", "calcium", "magnesium", "micro"];
    entries.sort((a, b) => {
      const left = componentOrder.indexOf(a.component);
      const right = componentOrder.indexOf(b.component);
      if (left !== right) {
        return left - right;
      }

      return a.channel_label.localeCompare(b.channel_label, "ru");
    });

    form.value.calibrations = entries;
  }

  async function fetchZoneChannels(force = false): Promise<void> {
    const zoneId = form.value.zoneId;
    if (!zoneId) {
      zoneChannels.value = [];
      form.value.calibrations = [];
      return;
    }

    if (zoneChannelsLoaded.value && !force) {
      return;
    }

    isZoneChannelsLoading.value = true;
    zoneChannelsError.value = null;

    try {
      const nodes = await requestZoneNodes(zoneId);
      const channels: DeviceChannel[] = [];

      nodes.forEach((node) => {
        const nodeLabel = node.uid || node.name || (node.id ? `Node #${node.id}` : "Node");
        (node.channels || []).forEach((channel) => {
          const channelType = String(channel.type || "").toUpperCase();
          if (channelType !== "ACTUATOR") {
            return;
          }

          const actuatorType = normalizeActuatorType(channel);
          if (!actuatorType || !PUMP_ACTUATOR_TYPES.includes(actuatorType as typeof PUMP_ACTUATOR_TYPES[number])) {
            return;
          }

          channels.push({
            ...channel,
            actuator_type: actuatorType,
            // Внутреннее поле только для UI-лейбла в wizard.
            ...( { __label: `${nodeLabel} / ${channel.channel}` } as any ),
          });
        });
      });

      zoneChannels.value = channels;
      buildCalibrationEntries(channels);
      zoneChannelsLoaded.value = true;
    } catch (err) {
      logger.error("[GrowthCycleWizard] Failed to fetch zone channels", err);
      zoneChannelsError.value = "Не удалось загрузить каналы насосов";
      zoneChannelsLoaded.value = false;
      zoneChannels.value = [];
      form.value.calibrations = [];
    } finally {
      isZoneChannelsLoading.value = false;
    }
  }

  async function saveAutomationProfile(zoneId: number, subsystems: Record<string, unknown>): Promise<void> {
    const payload = {
      mode: "setup",
      activate: true,
      subsystems,
    };

    try {
      await api.post(`/api/zones/${zoneId}/automation-logic-profiles`, payload);
      return;
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status !== 404) {
        throw err;
      }
    }

    await api.post(`/api/zones/${zoneId}/automation-logic-profile`, payload);
  }

  async function savePumpCalibrations(zoneId: number): Promise<string[]> {
    if (form.value.calibrationSkipped) {
      return [];
    }

    const activeCalibrations = form.value.calibrations.filter((entry) => !entry.skip && entry.ml_per_sec > 0);
    if (activeCalibrations.length === 0) {
      return [];
    }

    const failedChannels: string[] = [];

    await Promise.allSettled(
      activeCalibrations.map(async (entry) => {
        try {
          await api.post(`/api/zones/${zoneId}/calibrate-pump`, {
            node_channel_id: entry.node_channel_id,
            component: entry.component,
            actual_ml: entry.ml_per_sec,
            duration_sec: 1,
            skip_run: true,
          });
        } catch {
          failedChannels.push(entry.channel_label);
        }
      }),
    );

    return failedChannels;
  }

  async function onSubmit(): Promise<void> {
    if (!validateStep(currentStep.value)) {
      return;
    }

    if (!form.value.zoneId || !selectedRevisionId.value || !selectedPlantId.value || !form.value.startedAt) {
      error.value = "Заполните все обязательные поля";
      return;
    }

    const zoneId = form.value.zoneId;
    loading.value = true;
    error.value = null;
    errorDetails.value = [];

    let cycleId: number | null = null;

    try {
      const plantingAt = form.value.startedAt ? new Date(form.value.startedAt).toISOString() : undefined;
      const cycleResponse = await api.post(`/api/zones/${zoneId}/grow-cycles`, {
        recipe_revision_id: selectedRevisionId.value,
        plant_id: selectedPlantId.value,
        planting_at: plantingAt,
        start_immediately: true,
        irrigation: {
          system_type: form.value.logic.systemType,
          interval_minutes: form.value.logic.intervalMinutes,
          duration_seconds: form.value.logic.durationSeconds,
          clean_tank_fill_l: tanksCount.value === 2 ? form.value.logic.cleanTankFillL : undefined,
          nutrient_tank_target_l: tanksCount.value === 2 ? form.value.logic.nutrientTankTargetL : undefined,
          irrigation_batch_l: tanksCount.value === 2 ? form.value.logic.irrigationBatchL : undefined,
        },
        phase_overrides: {
          ph_target: form.value.logic.ph_target,
          ph_min: form.value.logic.ph_min,
          ph_max: form.value.logic.ph_max,
          ec_target: form.value.logic.ec_target,
          ec_min: form.value.logic.ec_min,
          ec_max: form.value.logic.ec_max,
        },
        settings: {
          expected_harvest_at: form.value.expectedHarvestAt || undefined,
        },
      });

      if (cycleResponse.data?.status !== "ok") {
        throw new Error(cycleResponse.data?.message || "Не удалось создать цикл");
      }

      const createdCycleId = toFiniteNumber(cycleResponse.data?.data?.id);
      cycleId = createdCycleId ? Math.round(createdCycleId) : null;

      const subsystems = buildLogicSubsystems(form.value.logic, tanksCount.value);
      await saveAutomationProfile(zoneId, subsystems);
    } catch (err: unknown) {
      if (cycleId !== null) {
        error.value = "Цикл создан, но не удалось сохранить профиль автоматики. Настройте его в разделе автоматики зоны.";
        errorDetails.value = [];
        showToast(error.value, "warning", TOAST_TIMEOUT.LONG);
      } else {
        const errorMessage = extractSetupWizardErrorMessage(err, "Ошибка при создании цикла");
        const details = extractSetupWizardErrorDetails(err);
        error.value = errorMessage;
        errorDetails.value = details;
        showToast(`${errorMessage}${details[0] ? ` ${details[0]}` : ""}`, "error", TOAST_TIMEOUT.NORMAL);
      }

      logger.error("[GrowthCycleWizard] Failed to submit", err);
      loading.value = false;
      return;
    }

    try {
      const failedCalibrations = await savePumpCalibrations(zoneId);
      if (failedCalibrations.length > 0) {
        showToast(
          `Цикл запущен, но не удалось сохранить калибровки: ${failedCalibrations.join(", ")}`,
          "warning",
          TOAST_TIMEOUT.LONG,
        );
      }

      clearDraft();
      showToast("Цикл выращивания успешно запущен", "success", TOAST_TIMEOUT.NORMAL);
      emit("close");
      emit("submit", {
        zoneId,
        cycleId: cycleId || undefined,
        recipeId: selectedRecipeId.value || undefined,
        recipeRevisionId: selectedRevisionId.value || undefined,
        startedAt: form.value.startedAt,
        expectedHarvestAt: form.value.expectedHarvestAt || undefined,
      });
    } catch (err: unknown) {
      const message = normalizeErrorMessage(err, "Цикл создан, но произошла ошибка при финализации");
      error.value = message;
      errorDetails.value = [];
      logger.error("[GrowthCycleWizard] Failed on final submit stage", err);
      showToast(message, "warning", TOAST_TIMEOUT.LONG);
    } finally {
      loading.value = false;
    }
  }

  function handleClose(): void {
    if (!loading.value) {
      emit("close");
    }
  }

  function reset(): void {
    currentStep.value = 0;
    recipeMode.value = "select";
    loading.value = false;
    error.value = null;
    errorDetails.value = [];
    validationErrors.value = [];
    form.value = createDefaultForm(props.zoneId);

    selectedPlantId.value = null;
    selectedRecipeId.value = null;
    selectedRevisionId.value = null;
    selectedRecipe.value = null;

    zoneChannels.value = [];
    isZoneChannelsLoading.value = false;
    zoneChannelsLoaded.value = false;
    zoneChannelsError.value = null;

    recipeLogicSeed.value = {};
  }

  async function initializeWizardState(): Promise<void> {
    if (!props.zoneId) {
      await loadZones();
    }

    await loadWizardData();
    loadDraft();
    applyInitialData();
  }

  watch(
    () => props.show,
    (show) => {
      if (show) {
        reset();
        void initializeWizardState();
      } else {
        clearDraft();
      }
    },
  );

  watch(
    () => props.zoneId,
    (newZoneId) => {
      if (newZoneId) {
        form.value.zoneId = newZoneId;
      }
    },
  );

  watch(tanksCount, (value) => {
    form.value.logic.tanksCount = value;
  }, { immediate: true });

  watch(selectedRecipeId, () => {
    syncSelectedRecipe();
  });

  watch(selectedRevision, (revision) => {
    const firstPhase = (revision?.phases?.[0] || null) as WizardRecipePhase | null;
    if (firstPhase) {
      fillLogicFromRecipePhase(firstPhase);
    }
  });

  watch(availableRecipes, () => {
    syncSelectedRecipe();
  });

  watch(
    () => currentStep.value,
    (step) => {
      if (steps[step]?.key === "calibration") {
        void fetchZoneChannels(true);
      }
    },
  );

  watch(
    () => [form.value.logic.scheduleStart, form.value.logic.hoursOn] as const,
    ([start, hours], [prevStart, prevHours]) => {
      if (!form.value.logic.lightingEnabled) {
        return;
      }

      const currentEnd = form.value.logic.scheduleEnd;
      const previousAutoEnd = addHoursToTime(prevStart || "06:00", Number(prevHours || 0));
      if (currentEnd === previousAutoEnd) {
        form.value.logic.scheduleEnd = addHoursToTime(start || "06:00", Number(hours || 0));
      }
    },
  );

  onMounted(() => {
    if (props.show) {
      void initializeWizardState();
    }
  });

  onUnmounted(() => {
    if (props.show) {
      saveDraft();
    }
  });

  return {
    currentStep,
    recipeMode,
    loading,
    error,
    errorDetails,
    validationErrors,
    form,
    availableZones,
    availablePlants,
    availableRecipes,
    selectedRecipe,
    selectedRecipeId,
    selectedRevisionId,
    selectedPlantId,
    availableRevisions,
    selectedRevision,
    steps,
    wizardTitle,
    minStartDate,
    totalDurationDays,
    tanksCount,
    canProceed,
    canSubmit,
    nextStepBlockedReason,
    zoneChannels,
    isZoneChannelsLoading,
    zoneChannelsLoaded,
    zoneChannelsError,
    hasCalibrationChannels,
    getCalibrationComponentLabel,
    isLogicFieldOverridden,
    isLogicFieldFromRecipe,
    formatDateTime,
    formatDate,
    onZoneSelected,
    onRecipeSelected,
    onRecipeCreated,
    fetchZoneChannels,
    nextStep,
    prevStep,
    onSubmit,
    handleClose,
  };
}
