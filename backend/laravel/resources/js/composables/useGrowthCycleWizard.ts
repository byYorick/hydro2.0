import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import type { useApi } from "@/composables/useApi";
import type { useToast } from "@/composables/useToast";
import type { useZones } from "@/composables/useZones";
import { logger } from "@/utils/logger";
import { TOAST_TIMEOUT } from "@/constants/timeouts";
import { extractSetupWizardErrorDetails, extractSetupWizardErrorMessage } from "@/composables/setupWizardErrors";

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

export type GrowthCycleWizardEmit = (event: "close" | "submit", payload?: {
  zoneId: number;
  recipeId?: number;
  recipeRevisionId?: number;
  startedAt: string;
  expectedHarvestAt?: string;
}) => void;

interface UseGrowthCycleWizardOptions {
  props: GrowthCycleWizardProps;
  emit: GrowthCycleWizardEmit;
  api: ReturnType<typeof useApi>["api"];
  showToast: ReturnType<typeof useToast>["showToast"];
  fetchZones: ReturnType<typeof useZones>["fetchZones"];
}

export function useGrowthCycleWizard({
  props,
  emit,
  api,
  showToast,
  fetchZones,
}: UseGrowthCycleWizardOptions) {
  function getNowLocalDatetimeValue(): string {
    const now = new Date();
    const offsetMs = now.getTimezoneOffset() * 60_000;
    return new Date(now.getTime() - offsetMs).toISOString().slice(0, 16);
  }

  const currentStep = ref(0);
  const recipeMode = ref<"select" | "create">("select");
  const loading = ref(false);
  const error = ref<string | null>(null);
  const errorDetails = ref<string[]>([]);
  const validationErrors = ref<string[]>([]);

  const form = ref({
    zoneId: props.zoneId || null,
    startedAt: getNowLocalDatetimeValue(),
    expectedHarvestAt: "",
    irrigation: {
      systemType: "drip" as "drip" | "substrate_trays" | "nft",
      intervalMinutes: 30,
      durationSeconds: 120,
      cleanTankFillL: 300,
      nutrientTankTargetL: 280,
    },
  });

  const availableZones = ref<any[]>([]);
  const availablePlants = ref<any[]>([]);
  const availableRecipes = ref<any[]>([]);
  const selectedRecipe = ref<any | null>(null);
  const selectedRecipeId = ref<number | null>(null);
  const selectedRevisionId = ref<number | null>(null);
  const selectedPlantId = ref<number | null>(null);

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

  const steps = [
    { title: "Зона", key: "zone" },
    { title: "Растение", key: "plant" },
    { title: "Рецепт", key: "recipe" },
    { title: "Параметры", key: "params" },
    { title: "Подтверждение", key: "confirm" },
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

  const canProceed = computed(() => {
    switch (currentStep.value) {
      case 0:
        return form.value.zoneId !== null;
      case 1:
        return selectedPlantId.value !== null;
      case 2:
        return selectedRevisionId.value !== null && selectedRecipe.value !== null;
      case 3:
        return form.value.startedAt !== "";
      default:
        return true;
    }
  });

  const canSubmit = computed(() => {
    return canProceed.value && validationErrors.value.length === 0;
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

      if (form.value.irrigation.intervalMinutes < 5 || form.value.irrigation.intervalMinutes > 1440) {
        return "Интервал полива должен быть в диапазоне 5-1440 минут.";
      }
      if (form.value.irrigation.durationSeconds < 1 || form.value.irrigation.durationSeconds > 3600) {
        return "Длительность полива должна быть в диапазоне 1-3600 секунд.";
      }
      if (form.value.irrigation.cleanTankFillL < 10 || form.value.irrigation.nutrientTankTargetL < 10) {
        return "Объёмы баков должны быть не меньше 10 л.";
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

  function onZoneSelected(): void {}

  function syncSelectedRecipe(): void {
    if (!selectedRecipeId.value) {
      selectedRecipe.value = null;
      selectedRevisionId.value = null;
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

        if (form.value.irrigation.intervalMinutes < 5 || form.value.irrigation.intervalMinutes > 1440) {
          validationErrors.value.push("Интервал полива должен быть в диапазоне 5-1440 минут");
          return false;
        }
        if (form.value.irrigation.durationSeconds < 1 || form.value.irrigation.durationSeconds > 3600) {
          validationErrors.value.push("Длительность полива должна быть в диапазоне 1-3600 секунд");
          return false;
        }
        if (form.value.irrigation.cleanTankFillL < 10 || form.value.irrigation.nutrientTankTargetL < 10) {
          validationErrors.value.push("Объёмы баков должны быть не меньше 10 л");
          return false;
        }
        break;
      }
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
      currentStep.value++;
      saveDraft();
    }
  }

  function prevStep(): void {
    if (currentStep.value > 0) {
      currentStep.value--;
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
        irrigation: form.value.irrigation,
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

      const draft = JSON.parse(draftStr);
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
        selectedRecipe.value = availableRecipes.value.find((recipe) => recipe.id === draft.recipeId) || null;
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
      if (draft.irrigation) {
        form.value.irrigation = {
          ...form.value.irrigation,
          ...draft.irrigation,
        };
      }
      if (draft.currentStep !== undefined) {
        currentStep.value = draft.currentStep;
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

    try {
      const plantingAt = form.value.startedAt ? new Date(form.value.startedAt).toISOString() : undefined;
      const response = await api.post(`/api/zones/${zoneId}/grow-cycles`, {
        recipe_revision_id: selectedRevisionId.value,
        plant_id: selectedPlantId.value,
        planting_at: plantingAt,
        start_immediately: true,
        irrigation: {
          system_type: form.value.irrigation.systemType,
          interval_minutes: form.value.irrigation.intervalMinutes,
          duration_seconds: form.value.irrigation.durationSeconds,
          clean_tank_fill_l: form.value.irrigation.cleanTankFillL,
          nutrient_tank_target_l: form.value.irrigation.nutrientTankTargetL,
        },
        settings: {
          expected_harvest_at: form.value.expectedHarvestAt || undefined,
        },
      });

      if (response.data?.status === "ok") {
        clearDraft();
        showToast("Цикл выращивания успешно запущен", "success", TOAST_TIMEOUT.NORMAL);
        emit("close");
        emit("submit", {
          zoneId,
          recipeId: selectedRecipeId.value || undefined,
          recipeRevisionId: selectedRevisionId.value || undefined,
          startedAt: form.value.startedAt,
          expectedHarvestAt: form.value.expectedHarvestAt || undefined,
        });
      } else {
        throw new Error(response.data?.message || "Не удалось создать цикл");
      }
    } catch (err: any) {
      const errorMessage = extractSetupWizardErrorMessage(err, "Ошибка при создании цикла");
      const details = extractSetupWizardErrorDetails(err);
      const normalizedErrorMessage = String(errorMessage || "").toLowerCase();
      const isActiveCycleConflict =
        normalizedErrorMessage.includes("zone already has an active cycle") ||
        normalizedErrorMessage.includes("в зоне уже активный цикл");

      error.value = isActiveCycleConflict
        ? "В зоне уже активный цикл. Остановите, завершите или прервите текущий цикл."
        : errorMessage;
      errorDetails.value = details;
      logger.error("[GrowthCycleWizard] Failed to submit", err);

      if (isActiveCycleConflict) {
        showToast("В зоне уже активный цикл. Обновляю данные зоны.", "warning", TOAST_TIMEOUT.NORMAL);
        emit("close");
        emit("submit", {
          zoneId,
          startedAt: form.value.startedAt,
        });
      } else {
        const primaryDetail = details.length > 0 ? ` ${details[0]}` : "";
        showToast(`${errorMessage}${primaryDetail}`, "error", TOAST_TIMEOUT.NORMAL);
      }
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
    error.value = null;
    errorDetails.value = [];
    validationErrors.value = [];
    form.value = {
      zoneId: props.zoneId || null,
      startedAt: getNowLocalDatetimeValue(),
      expectedHarvestAt: "",
      irrigation: {
        systemType: "drip",
        intervalMinutes: 30,
        durationSeconds: 120,
        cleanTankFillL: 300,
        nutrientTankTargetL: 280,
      },
    };
    selectedPlantId.value = null;
    selectedRecipeId.value = null;
    selectedRevisionId.value = null;
    selectedRecipe.value = null;
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

  watch(selectedRecipeId, () => {
    syncSelectedRecipe();
  });

  watch(selectedRevision, (revision) => {
    const firstPhase = revision?.phases?.[0];
    const intervalSec = Number(firstPhase?.irrigation_interval_sec);
    if (Number.isFinite(intervalSec) && intervalSec > 0) {
      form.value.irrigation.intervalMinutes = Math.max(5, Math.round(intervalSec / 60));
    }
  });

  watch(availableRecipes, () => {
    syncSelectedRecipe();
  });

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
    canProceed,
    canSubmit,
    nextStepBlockedReason,
    formatDateTime,
    formatDate,
    onZoneSelected,
    onRecipeSelected,
    onRecipeCreated,
    nextStep,
    prevStep,
    onSubmit,
    handleClose,
  };
}
