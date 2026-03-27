import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import type { useApi } from "@/composables/useApi";
import { useAutomationConfig } from "@/composables/useAutomationConfig";
import type { useToast } from "@/composables/useToast";
import type { useZones } from "@/composables/useZones";
import { logger } from "@/utils/logger";
import { TOAST_TIMEOUT } from "@/constants/timeouts";
import { extractSetupWizardErrorDetails, extractSetupWizardErrorMessage } from "@/composables/setupWizardErrors";
import { useAutomationCommandTemplates } from "@/composables/useAutomationCommandTemplates";
import {
  createDefaultClimateForm as createAutomationDefaultClimateForm,
  createDefaultLightingForm as createAutomationDefaultLightingForm,
  createDefaultWaterForm as createAutomationDefaultWaterForm,
  useAutomationDefaults,
} from "@/composables/useAutomationDefaults";
import { applyAutomationFromRecipe, syncSystemToTankLayout, validateForms } from "@/composables/zoneAutomationFormLogic";
import {
  payloadFromZoneLogicDocument,
  resolveZoneLogicProfileEntry,
  upsertZoneLogicProfilePayload,
} from "@/composables/zoneLogicProfileDocument";
import { resolveRecipePhaseSystemType } from "@/composables/recipeSystemType";
import { buildGrowthCycleConfigPayload } from "@/composables/zoneAutomationProfilePayload";
import type { ClimateFormState, LightingFormState, WaterFormState } from "@/composables/zoneAutomationTypes";
import type { Device, DeviceChannel } from "@/types/Device";

type WizardStepKey = "zone" | "plant" | "recipe" | "logic" | "automation" | "calibration" | "confirm";

interface WizardStep {
  key: WizardStepKey;
  label: string;
}

interface WizardRecipePhase {
  phase_index?: number | null;
  name?: string | null;
  duration_hours?: number | null;
  duration_days?: number | null;
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
  extensions?: Record<string, unknown> | null;
}

interface WizardFormState {
  zoneId: number | null;
  startedAt: string;
  expectedHarvestAt: string;
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

interface RecipeListItem {
  id: number;
  name?: string;
  description?: string | null;
  phases_count?: number;
  latest_published_revision_id?: number | null;
  latest_draft_revision_id?: number | null;
}

interface RecipeRevisionData {
  id: number;
  revision_number?: number | null;
  description?: string | null;
  phases?: WizardRecipePhase[];
}

interface ZoneLaunchReadiness {
  ready: boolean;
  errors?: string[];
  checks?: Record<string, boolean>;
  warnings?: string[];
  blocking_alerts?: Array<Record<string, unknown>>;
  dispatch_enabled?: boolean;
}

interface ZoneHealthPayload {
  readiness?: ZoneLaunchReadiness | null;
}

interface PaginatedCollectionPayload<T> {
  items: T[];
  currentPage: number | null;
  lastPage: number | null;
}

function getNowLocalDatetimeValue(): string {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 16);
}

function createDefaultForm(zoneId?: number): WizardFormState {
  return {
    zoneId: zoneId || null,
    startedAt: getNowLocalDatetimeValue(),
    expectedHarvestAt: "",
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

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  return value as Record<string, unknown>;
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

function extractCollectionItems<T>(raw: unknown): T[] {
  return extractPaginatedCollection<T>(raw).items;
}

function extractPaginatedCollection<T>(raw: unknown): PaginatedCollectionPayload<T> {
  if (Array.isArray(raw)) {
    return {
      items: raw as T[],
      currentPage: null,
      lastPage: null,
    };
  }

  if (!raw || typeof raw !== "object") {
    return {
      items: [],
      currentPage: null,
      lastPage: null,
    };
  }

  const payload = raw as { data?: unknown };
  if (Array.isArray(payload.data)) {
    return {
      items: payload.data as T[],
      currentPage: null,
      lastPage: null,
    };
  }

  if (payload.data && typeof payload.data === "object") {
    const nested = payload.data as {
      data?: unknown;
      current_page?: unknown;
      last_page?: unknown;
    };
    if (Array.isArray(nested.data)) {
      return {
        items: nested.data as T[],
        currentPage: toFiniteNumber(nested.current_page),
        lastPage: toFiniteNumber(nested.last_page),
      };
    }
  }

  return {
    items: [],
    currentPage: null,
    lastPage: null,
  };
}

export function useGrowthCycleWizard({
  props,
  emit,
  api,
  showToast,
  fetchZones,
}: UseGrowthCycleWizardOptions) {
  const automationConfig = useAutomationConfig(showToast);
  const automationDefaults = useAutomationDefaults();
  const automationCommandTemplates = useAutomationCommandTemplates();
  const currentStep = ref(0);
  const recipeMode = ref<"select" | "create">("select");
  const loading = ref(false);
  const error = ref<string | null>(null);
  const errorDetails = ref<string[]>([]);
  const validationErrors = ref<string[]>([]);

  const form = ref<WizardFormState>(createDefaultForm(props.zoneId));

  const climateForm = ref<ClimateFormState>(createAutomationDefaultClimateForm(automationDefaults.value));
  const waterForm = ref<WaterFormState>(createAutomationDefaultWaterForm(automationDefaults.value));
  const lightingForm = ref<LightingFormState>(createAutomationDefaultLightingForm(automationDefaults.value));
  const draftWasLoaded = ref(false);
  const draftFormsHydrated = ref(false);
  const isInitializingWizard = ref(false);
  const automationProfileLoadedZoneId = ref<number | null>(null);

  const availableZones = ref<any[]>([]);
  const availablePlants = ref<any[]>([]);
  const availableRecipes = ref<RecipeListItem[]>([]);
  const selectedRecipe = ref<RecipeListItem | null>(null);
  const selectedRecipeId = ref<number | null>(null);
  const selectedRevisionId = ref<number | null>(null);
  const selectedRevisionData = ref<RecipeRevisionData | null>(null);
  const selectedRevisionRequestId = ref(0);
  const selectedPlantId = ref<number | null>(null);

  const zoneDevices = ref<Device[]>([]);
  const isZoneDevicesLoading = ref(false);
  const zoneDevicesLoaded = ref(false);
  const zoneDevicesError = ref<string | null>(null);
  const zoneReadiness = ref<ZoneLaunchReadiness | null>(null);
  const zoneReadinessLoading = ref(false);

  const availableRevisions = computed(() => {
    if (!selectedRecipe.value || !selectedRevisionId.value) {
      return [];
    }

    if (selectedRevisionData.value && selectedRevisionData.value.id === selectedRevisionId.value) {
      return [selectedRevisionData.value];
    }

    return [{
      id: selectedRevisionId.value,
      revision_number: null,
      description: null,
      phases: [],
    }];
  });

  const selectedRevision = computed(() => {
    if (!selectedRevisionId.value || !selectedRevisionData.value) {
      return null;
    }

    return selectedRevisionData.value.id === selectedRevisionId.value
      ? selectedRevisionData.value
      : null;
  });

  const selectedLaunchPhase = computed<WizardRecipePhase | null>(() => {
    const phases = selectedRevision.value?.phases;
    if (!Array.isArray(phases) || phases.length === 0) {
      return null;
    }

    const sortedPhases = phases
      .filter((phase): phase is WizardRecipePhase => Boolean(phase) && typeof phase === "object")
      .slice()
      .sort((left, right) => {
        const leftIndex = toFiniteNumber(left.phase_index) ?? 0;
        const rightIndex = toFiniteNumber(right.phase_index) ?? 0;
        return leftIndex - rightIndex;
      });

    return sortedPhases[0] ?? null;
  });

  const steps: WizardStep[] = [
    { key: "zone", label: "Зона" },
    { key: "plant", label: "Растение" },
    { key: "recipe", label: "Рецепт" },
    { key: "logic", label: "Период" },
    { key: "automation", label: "Автоматика" },
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

  const tanksCount = computed(() => waterForm.value.tanksCount);

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

        return true;
      case 4:
        return true;
      case 5:
        return true;
      default:
        return true;
    }
  });

  const canSubmit = computed(() => {
    if (currentStep.value === 6) {
      return validationErrors.value.length === 0
        && zoneReadinessLoading.value === false
        && zoneReadiness.value?.ready === true;
    }

    return canProceed.value && validationErrors.value.length === 0;
  });

  const zoneReadinessErrors = computed(() => {
    return Array.isArray(zoneReadiness.value?.errors) ? zoneReadiness.value?.errors ?? [] : [];
  });

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

  function getPhaseLabel(phase: WizardRecipePhase): string {
    const name = typeof phase.name === "string" ? phase.name.trim() : "";
    if (name) {
      return name;
    }

    const phaseIndex = toFiniteNumber(phase.phase_index);
    if (phaseIndex !== null) {
      return `Фаза ${Math.max(1, Math.round(phaseIndex) + 1)}`;
    }

    return "Первая фаза";
  }

  function validateWindowedTarget(
    label: string,
    target: number | null,
    min: number | null,
    max: number | null,
  ): string | null {
    if (target === null || min === null || max === null) {
      return `${label}: target/min/max должны быть числовыми значениями.`;
    }

    if (min > max) {
      return `${label}: min не может быть больше max.`;
    }

    if (target < min || target > max) {
      return `${label}: target=${target} должен быть в диапазоне min=${min}..max=${max}.`;
    }

    return null;
  }

  function validateSelectedRecipeTargets(): string | null {
    const phase = selectedLaunchPhase.value;
    if (!phase) {
      return "Рецепт должен содержать хотя бы одну фазу.";
    }

    const phaseLabel = getPhaseLabel(phase);

    const phError = validateWindowedTarget(
      "pH",
      toFiniteNumber(phase.ph_target),
      toFiniteNumber(phase.ph_min),
      toFiniteNumber(phase.ph_max),
    );
    if (phError) {
      return `${phError} (${phaseLabel})`;
    }

    const ecError = validateWindowedTarget(
      "EC",
      toFiniteNumber(phase.ec_target),
      toFiniteNumber(phase.ec_min),
      toFiniteNumber(phase.ec_max),
    );
    if (ecError) {
      return `${ecError} (${phaseLabel})`;
    }

    return null;
  }

  function syncFormsFromRecipePhase(phase: WizardRecipePhase): void {
    const systemType = resolveRecipePhaseSystemType(phase, waterForm.value.systemType);
    waterForm.value.systemType = systemType;
    waterForm.value.tanksCount = systemType === "nft" ? 0 : 2;

    const phTarget = toFiniteNumber(phase.ph_target);
    const ecTarget = toFiniteNumber(phase.ec_target);
    const tempAirTarget = toFiniteNumber(phase.temp_air_target);
    const humidityTarget = toFiniteNumber(phase.humidity_target);
    const intervalSec = toFiniteNumber(phase.irrigation_interval_sec);
    const durationSec = toFiniteNumber(phase.irrigation_duration_sec);
    const hoursOn = toFiniteNumber(phase.lighting_photoperiod_hours);
    const scheduleStart = isValidHHMM(String(phase.lighting_start_time || ""))
      ? String(phase.lighting_start_time)
      : "06:00";

    if (phTarget !== null) waterForm.value.targetPh = Number(phTarget.toFixed(2));
    if (ecTarget !== null) waterForm.value.targetEc = Number(ecTarget.toFixed(2));
    if (tempAirTarget !== null) climateForm.value.dayTemp = Number(tempAirTarget.toFixed(1));
    if (humidityTarget !== null) climateForm.value.dayHumidity = Math.round(humidityTarget);
    if (hoursOn !== null) {
      lightingForm.value.hoursOn = clamp(Math.round(hoursOn), 1, 24);
      lightingForm.value.scheduleStart = scheduleStart;
      lightingForm.value.scheduleEnd = addHoursToTime(scheduleStart, lightingForm.value.hoursOn);
    }
    if (intervalSec !== null && intervalSec > 0) {
      waterForm.value.intervalMinutes = Math.max(5, Math.round(intervalSec / 60));
    }
    if (durationSec !== null && durationSec > 0) {
      waterForm.value.durationSeconds = Math.max(10, Math.round(durationSec));
    }

    climateForm.value.enabled = true;
    lightingForm.value.enabled = true;
  }

  function syncRecipeLaunchTargetsFromPhase(phase: WizardRecipePhase): void {
    const phTarget = toFiniteNumber(phase.ph_target);
    const ecTarget = toFiniteNumber(phase.ec_target);

    if (phTarget !== null) {
      waterForm.value.targetPh = Number(phTarget.toFixed(2));
    }
    if (ecTarget !== null) {
      waterForm.value.targetEc = Number(ecTarget.toFixed(2));
    }
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
      const [plantsResponse, recipes] = await Promise.all([
        api.get("/plants"),
        loadAllRecipes(),
      ]);

      availablePlants.value = extractCollectionItems<any>(plantsResponse.data);
      availableRecipes.value = recipes
        .filter((recipe) => {
          const publishedId = toFiniteNumber(recipe.latest_published_revision_id);
          return publishedId !== null && publishedId > 0;
        });
    } catch (err) {
      logger.error("[GrowthCycleWizard] Failed to load wizard data", err);
      showToast("Не удалось загрузить данные визарда", "error", TOAST_TIMEOUT.NORMAL);
    }
  }

  async function loadAutomationProfile(zoneId: number): Promise<void> {
    loading.value = true;
    try {
      const document = await automationConfig.getDocument<Record<string, unknown>>("zone", zoneId, "zone.logic_profile");
      const profile = resolveZoneLogicProfileEntry(payloadFromZoneLogicDocument(document), "setup");
      const subsystems = profile?.subsystems ?? null;
      if (!subsystems) {
        logger.warn("[GrowthCycleWizard] Automation profile payload has no subsystems", { zoneId });
        return;
      }

      applyAutomationFromRecipe(
        {
          extensions: {
            subsystems,
          },
        },
        {
          climateForm: climateForm.value,
          waterForm: waterForm.value,
          lightingForm: lightingForm.value,
        },
      );

      const launchPhase = selectedLaunchPhase.value;
      // Для запуска цикла рецепт является единственным источником истины.
      // Зонный automation profile может заполнять соседние поля, но launch-targets
      // сразу возвращаем к значениям ревизии рецепта.
      if (launchPhase) {
        syncFormsFromRecipePhase(launchPhase);
      }

      automationProfileLoadedZoneId.value = zoneId;
    } catch (err) {
      logger.warn("[GrowthCycleWizard] Failed to load automation profile", { zoneId, err });
    } finally {
      loading.value = false;
    }
  }

  function getPreferredRevisionId(recipe: RecipeListItem | null): number | null {
    if (!recipe) {
      return null;
    }

    const publishedId = toFiniteNumber(recipe.latest_published_revision_id);
    if (publishedId && publishedId > 0) {
      return Math.round(publishedId);
    }

    const draftId = toFiniteNumber(recipe.latest_draft_revision_id);
    if (draftId && draftId > 0) {
      return Math.round(draftId);
    }

    return null;
  }

  async function loadSelectedRevision(revisionId: number): Promise<void> {
    const requestId = selectedRevisionRequestId.value + 1;
    selectedRevisionRequestId.value = requestId;

    try {
      const response = await api.get(`/recipe-revisions/${revisionId}`);
      const revision = response.data?.data || null;
      if (selectedRevisionRequestId.value !== requestId) {
        return;
      }

      if (revision && typeof revision === "object") {
        selectedRevisionData.value = revision as RecipeRevisionData;
        return;
      }

      selectedRevisionData.value = null;
    } catch (err) {
      if (selectedRevisionRequestId.value !== requestId) {
        return;
      }

      selectedRevisionData.value = null;
      logger.warn("[GrowthCycleWizard] Failed to load recipe revision", { revisionId, err });
      showToast("Не удалось загрузить ревизию рецепта", "warning", TOAST_TIMEOUT.NORMAL);
    }
  }

  async function loadAllRecipes(): Promise<RecipeListItem[]> {
    const perPage = 100;
    const collected = new Map<number, RecipeListItem>();
    let page = 1;
    let lastPage = 1;

    while (page <= lastPage) {
      const response = await api.get("/recipes", {
        params: {
          per_page: perPage,
          page,
        },
      });

      const payload = extractPaginatedCollection<RecipeListItem>(response.data);
      payload.items.forEach((recipe) => {
        if (typeof recipe?.id === "number" && recipe.id > 0) {
          collected.set(recipe.id, recipe);
        }
      });

      const reportedLastPage = payload.lastPage && payload.lastPage > 0
        ? Math.round(payload.lastPage)
        : page;

      if (payload.items.length === 0 || page >= reportedLastPage) {
        break;
      }

      lastPage = reportedLastPage;
      page += 1;
    }

    return Array.from(collected.values());
  }

  function onZoneSelected(): void {
    zoneDevicesLoaded.value = false;
    zoneDevices.value = [];
    zoneDevicesError.value = null;
    zoneReadiness.value = null;
  }

  function syncSelectedRecipe(): void {
    if (!selectedRecipeId.value) {
      selectedRecipe.value = null;
      selectedRevisionId.value = null;
      selectedRevisionData.value = null;
      return;
    }

    selectedRecipe.value = availableRecipes.value.find((recipe) => recipe.id === selectedRecipeId.value) || null;
    const preferredRevisionId = getPreferredRevisionId(selectedRecipe.value);
    if (!preferredRevisionId) {
      selectedRevisionId.value = null;
      selectedRevisionData.value = null;
      return;
    }

    if (selectedRevisionId.value !== preferredRevisionId) {
      selectedRevisionId.value = preferredRevisionId;
    }
  }

  function onRecipeSelected(): void {
    syncSelectedRecipe();
  }

  function onRecipeCreated(recipe: any): void {
    selectedRecipeId.value = recipe.id;
    selectedRecipe.value = null;
    selectedRevisionData.value = null;
    selectedRevisionId.value = null;
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

        break;
      }
      case 4:
      {
        const automationValidationError = validateForms({
          climateForm: climateForm.value,
          waterForm: waterForm.value,
        });
        if (automationValidationError) {
          validationErrors.value.push(automationValidationError);
          return false;
        }

        const recipeTargetValidationError = validateSelectedRecipeTargets();
        if (recipeTargetValidationError) {
          validationErrors.value.push(recipeTargetValidationError);
          return false;
        }
        break;
      }
      case 5:
      case 6:
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
        climateForm: climateForm.value,
        waterForm: waterForm.value,
        lightingForm: lightingForm.value,
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
        climateForm: Partial<ClimateFormState>;
        waterForm: Partial<WaterFormState>;
        lightingForm: Partial<LightingFormState>;
        currentStep: number;
      }>;
      let hasLoadedForms = false;

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

      if (draft.climateForm) {
        climateForm.value = { ...createAutomationDefaultClimateForm(automationDefaults.value), ...draft.climateForm };
        hasLoadedForms = true;
      }

      if (draft.waterForm) {
        waterForm.value = { ...createAutomationDefaultWaterForm(automationDefaults.value), ...draft.waterForm };
        hasLoadedForms = true;
      }

      if (draft.lightingForm) {
        lightingForm.value = { ...createAutomationDefaultLightingForm(automationDefaults.value), ...draft.lightingForm };
        hasLoadedForms = true;
      }

      if (hasLoadedForms) {
        draftWasLoaded.value = true;
        draftFormsHydrated.value = true;
      }

      if (typeof draft.currentStep === "number") {
        const restoredStep = clamp(Math.round(draft.currentStep), 0, steps.length - 1);
        currentStep.value = restoredStep >= 6 ? 5 : restoredStep;
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

  async function fetchZoneDevices(force = false): Promise<void> {
    const zoneId = form.value.zoneId;
    if (!zoneId) {
      zoneDevices.value = [];
      return;
    }

    if (zoneDevicesLoaded.value && !force) {
      return;
    }

    isZoneDevicesLoading.value = true;
    zoneDevicesError.value = null;

    try {
      const nodes = await requestZoneNodes(zoneId);
      zoneDevices.value = nodes
        .filter((node) => typeof node.id === "number" && Number.isInteger(node.id))
        .map((node) => ({
          id: node.id as number,
          uid: node.uid || `node-${node.id}`,
          name: node.name,
          type: "unknown",
          status: "unknown",
          channels: Array.isArray(node.channels) ? node.channels.map((channel) => ({ ...channel })) as DeviceChannel[] : [],
        }));
      zoneDevicesLoaded.value = true;
    } catch (err) {
      logger.error("[GrowthCycleWizard] Failed to fetch zone devices", err);
      zoneDevicesError.value = "Не удалось загрузить насосы зоны";
      zoneDevicesLoaded.value = false;
      zoneDevices.value = [];
    } finally {
      isZoneDevicesLoading.value = false;
    }
  }

  async function loadZoneReadiness(zoneId: number): Promise<void> {
    zoneReadinessLoading.value = true;

    try {
      const response = await api.get(`/api/zones/${zoneId}/health`);
      const payload = (response.data?.data || null) as ZoneHealthPayload | ZoneLaunchReadiness | null;
      const readinessPayload = payload && typeof payload === "object" && "readiness" in payload
        ? (payload as ZoneHealthPayload).readiness ?? null
        : (payload as ZoneLaunchReadiness | null);
      zoneReadiness.value = readinessPayload;
    } catch (err) {
      logger.warn("[GrowthCycleWizard] Failed to load zone readiness", { zoneId, err });
      zoneReadiness.value = null;
    } finally {
      zoneReadinessLoading.value = false;
    }
  }

  async function saveAutomationProfile(zoneId: number, subsystems: Record<string, unknown>): Promise<void> {
    const currentDocument = await automationConfig.getDocument<Record<string, unknown>>("zone", zoneId, "zone.logic_profile");
    const nextPayload = upsertZoneLogicProfilePayload(
      payloadFromZoneLogicDocument(currentDocument),
      "setup",
      subsystems,
      true,
    );

    await automationConfig.updateDocument("zone", zoneId, "zone.logic_profile", nextPayload as unknown as Record<string, unknown>);
  }

  async function persistLaunchPrerequisites(zoneId: number): Promise<void> {
    const configPayload = buildGrowthCycleConfigPayload({
      climateForm: climateForm.value,
      waterForm: waterForm.value,
      lightingForm: lightingForm.value,
    }, {
      automationDefaults: automationDefaults.value,
      automationCommandTemplates: automationCommandTemplates.value,
    });

    await saveAutomationProfile(zoneId, (configPayload.subsystems || {}) as Record<string, unknown>);
  }

  async function onSubmit(): Promise<void> {
    if (!validateStep(currentStep.value)) {
      return;
    }

    if (!form.value.zoneId || !selectedRevisionId.value || !selectedPlantId.value || !form.value.startedAt) {
      error.value = "Заполните все обязательные поля";
      return;
    }

    const recipeTargetValidationError = validateSelectedRecipeTargets();
    if (recipeTargetValidationError) {
      validationErrors.value = [recipeTargetValidationError];
      error.value = recipeTargetValidationError;
      errorDetails.value = [recipeTargetValidationError];
      showToast(recipeTargetValidationError, "error", TOAST_TIMEOUT.NORMAL);
      return;
    }

    const zoneId = form.value.zoneId;
    loading.value = true;
    error.value = null;
    errorDetails.value = [];

    try {
      await persistLaunchPrerequisites(zoneId);
      await loadZoneReadiness(zoneId);
      if (zoneReadiness.value?.ready !== true) {
        const readinessErrors = zoneReadinessErrors.value;
        const firstError = readinessErrors[0] || "Зона не готова к запуску цикла";
        validationErrors.value = readinessErrors;
        error.value = firstError;
        errorDetails.value = readinessErrors;
        showToast(firstError, "error", TOAST_TIMEOUT.NORMAL);
        return;
      }

      const plantingAt = form.value.startedAt ? new Date(form.value.startedAt).toISOString() : undefined;
      const cycleResponse = await api.post(`/api/zones/${zoneId}/grow-cycles`, {
        recipe_revision_id: selectedRevisionId.value,
        plant_id: selectedPlantId.value,
        planting_at: plantingAt,
        start_immediately: true,
        irrigation: {
          system_type: waterForm.value.systemType,
          interval_minutes: waterForm.value.intervalMinutes,
          duration_seconds: waterForm.value.durationSeconds,
          clean_tank_fill_l: tanksCount.value === 2 ? waterForm.value.cleanTankFillL : undefined,
          nutrient_tank_target_l: tanksCount.value === 2 ? waterForm.value.nutrientTankTargetL : undefined,
          irrigation_batch_l: tanksCount.value === 2 ? waterForm.value.irrigationBatchL : undefined,
        },
        settings: {
          expected_harvest_at: form.value.expectedHarvestAt || undefined,
        },
      });

      if (cycleResponse.data?.status !== "ok") {
        throw new Error(cycleResponse.data?.message || "Не удалось создать цикл");
      }

      const createdCycleId = toFiniteNumber(cycleResponse.data?.data?.id);
      const cycleId = createdCycleId ? Math.round(createdCycleId) : null;

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
      const errorMessage = extractSetupWizardErrorMessage(err, "Ошибка при запуске цикла");
      const details = extractSetupWizardErrorDetails(err);
      error.value = errorMessage;
      errorDetails.value = details;
      logger.error("[GrowthCycleWizard] Failed to submit", err);
      showToast(`${errorMessage}${details[0] ? ` ${details[0]}` : ""}`, "error", TOAST_TIMEOUT.NORMAL);
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

    climateForm.value = createAutomationDefaultClimateForm(automationDefaults.value);
    waterForm.value = createAutomationDefaultWaterForm(automationDefaults.value);
    lightingForm.value = createAutomationDefaultLightingForm(automationDefaults.value);
    draftWasLoaded.value = false;
    draftFormsHydrated.value = false;
    isInitializingWizard.value = false;
    automationProfileLoadedZoneId.value = null;

    selectedPlantId.value = null;
    selectedRecipeId.value = null;
    selectedRevisionId.value = null;
    selectedRecipe.value = null;
    selectedRevisionData.value = null;
    selectedRevisionRequestId.value = 0;

    zoneDevices.value = [];
    isZoneDevicesLoading.value = false;
    zoneDevicesLoaded.value = false;
    zoneDevicesError.value = null;
    zoneReadiness.value = null;
    zoneReadinessLoading.value = false;
  }

  async function initializeWizardState(): Promise<void> {
    isInitializingWizard.value = true;
    try {
      if (!props.zoneId) {
        await loadZones();
      }

      await loadWizardData();
      if (props.zoneId) {
        await loadAutomationProfile(props.zoneId);
        await loadZoneReadiness(props.zoneId);
      }
      loadDraft();
      applyInitialData();
    } finally {
      isInitializingWizard.value = false;
    }
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
        if (props.show && !draftFormsHydrated.value && automationProfileLoadedZoneId.value !== newZoneId) {
          void loadAutomationProfile(newZoneId);
        }
        if (props.show) {
          void fetchZoneDevices(true);
          void loadZoneReadiness(newZoneId);
        }
      }
    },
  );

  watch(
    () => form.value.zoneId,
    (zoneId, previousZoneId) => {
      if (!props.show || zoneId === previousZoneId) {
        return;
      }

      if (!zoneId) {
        zoneDevices.value = [];
        zoneDevicesLoaded.value = false;
        zoneDevicesError.value = null;
        zoneReadiness.value = null;
        zoneReadinessLoading.value = false;
        return;
      }

      void fetchZoneDevices(true);
      void loadZoneReadiness(zoneId);
    },
  );

  watch(selectedRecipeId, () => {
    syncSelectedRecipe();
  });

  watch(selectedRevisionId, (revisionId) => {
    if (!revisionId) {
      selectedRevisionData.value = null;
      return;
    }

    if (selectedRevisionData.value?.id === revisionId) {
      return;
    }

    void loadSelectedRevision(revisionId);
  });

  watch(selectedRevision, (revision) => {
    const firstPhase = selectedLaunchPhase.value;
    if (firstPhase) {
      if (draftWasLoaded.value) {
        syncRecipeLaunchTargetsFromPhase(firstPhase);
        draftWasLoaded.value = false;
        return;
      }

      syncFormsFromRecipePhase(firstPhase);
    }
  });

  watch(availableRecipes, () => {
    syncSelectedRecipe();
  });

  watch(
    () => waterForm.value.systemType,
    (systemType) => {
      syncSystemToTankLayout(waterForm.value, systemType);
    },
    { immediate: true },
  );

  watch(
    () => waterForm.value.tanksCount,
    (tanksCount) => {
      const normalizedTanksCount = Math.round(Number(tanksCount)) === 3 ? 3 : 2;

      if (waterForm.value.systemType === "drip") {
        if (waterForm.value.tanksCount !== 2) {
          waterForm.value.tanksCount = 2;
        }
        waterForm.value.enableDrainControl = false;
        if (waterForm.value.diagnosticsWorkflow === "cycle_start") {
          waterForm.value.diagnosticsWorkflow = "startup";
        }
        return;
      }

      if (waterForm.value.tanksCount !== normalizedTanksCount) {
        waterForm.value.tanksCount = normalizedTanksCount;
      }
      if (normalizedTanksCount === 2) {
        waterForm.value.enableDrainControl = false;
        if (waterForm.value.diagnosticsWorkflow === "cycle_start") {
          waterForm.value.diagnosticsWorkflow = "startup";
        }
      } else if (waterForm.value.diagnosticsWorkflow === "startup") {
        waterForm.value.diagnosticsWorkflow = "cycle_start";
      }
    },
  );

  watch(
    () => form.value.zoneId,
    (zoneId, previousZoneId) => {
      if (!props.show || props.zoneId || isInitializingWizard.value) {
        return;
      }

      if (!zoneId || previousZoneId !== null || draftFormsHydrated.value) {
        return;
      }

      if (automationProfileLoadedZoneId.value === zoneId) {
        return;
      }

      void fetchZoneDevices(true);
      void loadAutomationProfile(zoneId);
      void loadZoneReadiness(zoneId);
    },
  );

  watch(
    () => currentStep.value,
    (step) => {
      const stepKey = steps[step]?.key;
      if (stepKey === "calibration" || stepKey === "confirm") {
        void fetchZoneDevices(stepKey === "confirm");
      }
      if (stepKey === "confirm" && form.value.zoneId) {
        void loadZoneReadiness(form.value.zoneId);
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
    climateForm,
    waterForm,
    lightingForm,
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
    zoneDevices,
    isZoneDevicesLoading,
    zoneDevicesLoaded,
    zoneDevicesError,
    zoneReadiness,
    zoneReadinessLoading,
    zoneReadinessErrors,
    formatDateTime,
    formatDate,
    onZoneSelected,
    onRecipeSelected,
    onRecipeCreated,
    fetchZoneDevices,
    loadZoneReadiness,
    nextStep,
    prevStep,
    onSubmit,
    handleClose,
  };
}
