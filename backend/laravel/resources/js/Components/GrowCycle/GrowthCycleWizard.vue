<template>
  <Modal
    :open="show"
    :title="wizardTitle"
    size="large"
    data-testid="growth-cycle-wizard"
    @close="handleClose"
  >
    <ErrorBoundary>
      <div class="mb-6">
        <div class="flex items-center justify-center gap-1.5">
          <div
            v-for="(step, index) in steps"
            :key="step.key"
            class="w-2.5 h-2.5 rounded-full transition-colors"
            :class="[
              index < currentStep
                ? 'bg-[color:var(--accent-green)]'
                : index === currentStep
                  ? 'bg-[color:var(--accent-cyan)] ring-2 ring-[color:var(--accent-cyan)]/30'
                  : 'bg-[color:var(--border-muted)]',
            ]"
          ></div>
        </div>
        <p class="text-center text-sm text-[color:var(--text-muted)] mt-2">
          {{ steps[currentStep]?.label }} ({{ currentStep + 1 }} / {{ steps.length }})
        </p>
      </div>

      <div
        v-if="currentStep === 0"
        class="space-y-4"
      >
        <div v-if="zoneId">
          <div class="p-4 rounded-lg bg-[color:var(--badge-success-bg)] border border-[color:var(--badge-success-border)]">
            <div class="text-sm font-medium text-[color:var(--badge-success-text)]">
              Зона выбрана: {{ zoneName || `Зона #${zoneId}` }}
            </div>
          </div>
        </div>
        <div v-else>
          <label class="block text-sm font-medium mb-2">Выберите зону</label>
          <select
            v-model="form.zoneId"
            class="input-select w-full"
            @change="onZoneSelected"
          >
            <option :value="null">
              Выберите зону
            </option>
            <option
              v-for="zone in availableZones"
              :key="zone.id"
              :value="zone.id"
            >
              {{ zone.name }} ({{ zone.greenhouse?.name || "" }})
            </option>
          </select>
        </div>
      </div>

      <div
        v-if="currentStep === 1"
        class="space-y-4"
      >
        <div>
          <label class="block text-sm font-medium mb-2">Выберите растение</label>
          <select
            v-model="selectedPlantId"
            class="input-select w-full"
          >
            <option :value="null">
              Выберите растение
            </option>
            <option
              v-for="plant in availablePlants"
              :key="plant.id"
              :value="plant.id"
            >
              {{ plant.name }} {{ plant.variety ? `(${plant.variety})` : "" }}
            </option>
          </select>
        </div>
      </div>

      <WizardRecipeStep
        v-if="currentStep === 2"
        v-model:recipe-mode="recipeMode"
        v-model:selected-recipe-id="selectedRecipeId"
        v-model:selected-revision-id="selectedRevisionId"
        :available-recipes="availableRecipes"
        :selected-recipe="selectedRecipe"
        :available-revisions="availableRevisions"
        :selected-revision="selectedRevision"
        @recipe-selected="onRecipeSelected"
        @recipe-created="onRecipeCreated"
      />

      <div
        v-if="currentStep === 3"
        class="space-y-5"
      >
        <section class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] space-y-4">
          <h3 class="text-sm font-semibold">
            Период цикла
          </h3>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label class="text-sm">
              <span class="block font-medium mb-2">Дата начала</span>
              <input
                v-model="form.startedAt"
                type="datetime-local"
                class="input-field w-full"
                :min="minStartDate"
                required
              />
            </label>
            <label class="text-sm">
              <span class="block font-medium mb-2">Ожидаемая дата сбора (опционально)</span>
              <input
                v-model="form.expectedHarvestAt"
                type="date"
                class="input-field w-full"
                :min="form.startedAt ? form.startedAt.slice(0, 10) : undefined"
              />
            </label>
          </div>
        </section>
      </div>

      <WizardAutomationStep
        v-if="currentStep === 4"
        v-model:climate-form="climateForm"
        v-model:water-form="waterForm"
        v-model:lighting-form="lightingForm"
        v-model:soil-moisture-channel-id="soilMoistureSelectedNodeChannelId"
        v-model:active-tab="automationTab"
        :soil-moisture-channel-candidates="soilMoistureChannelCandidates"
        :soil-moisture-binding-loading="soilMoistureBindingLoading"
        :soil-moisture-binding-error="soilMoistureBindingError"
        :soil-moisture-binding-saved-at="soilMoistureBindingSavedAt"
        :soil-moisture-bound-node-channel-id="soilMoistureBoundNodeChannelId"
        :tanks-count="tanksCount"
        :format-date-time="formatDateTime"
        @save-soil-moisture-binding="saveSoilMoistureBinding"
      />

      <WizardCalibrationStep
        v-if="currentStep === 5"
        :zone-id="form.zoneId"
        :devices-loading="isZoneDevicesLoading"
        :devices-error="zoneDevicesError"
        :pump-channels-count="pumpChannels.length"
        :mapped-pump-components="mappedPumpComponents"
        :calibrated-channels="calibratedChannels"
        :missing-pump-components="missingPumpComponents"
        :loading-run="loadingPumpCalibrationRun"
        :loading-save="loadingPumpCalibrationSave"
        @open-modal="openPumpCalibrationModal"
        @refresh="refreshPumpCalibrationData(true)"
      />

      <WizardConfirmStep
        v-if="currentStep === 6"
        :zone-id="form.zoneId"
        :zone-name="zoneName"
        :readiness="zoneReadiness"
        :readiness-loading="zoneReadinessLoading"
        :recipe-name="selectedRecipe?.name"
        :recipe-phases="selectedRevision?.phases ?? []"
        :total-duration-days="totalDurationDays"
        :started-at="form.startedAt"
        :expected-harvest-at="form.expectedHarvestAt"
        :water-form="waterForm"
        :tanks-count="tanksCount"
        :is-smart-irrigation="isSmartIrrigation"
        :irrigation-strategy-label="irrigationStrategyLabel"
        :irrigation-schedule-summary="irrigationScheduleSummary"
        :soil-moisture-bound-node-channel-id="soilMoistureBoundNodeChannelId"
        :calibrated-count="calibratedChannels.length"
        :missing-pump-components="missingPumpComponents"
        :validation-errors="validationErrors"
        :format-date-time="formatDateTime"
        :format-date="formatDate"
      />

      <div
        v-if="error && validationErrors.length === 0"
        class="mt-4 p-3 rounded-lg bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)]"
      >
        <div class="text-sm text-[color:var(--badge-danger-text)]">
          {{ error }}
        </div>
        <ul
          v-if="errorDetails.length > 0"
          class="mt-2 text-xs text-[color:var(--badge-danger-text)] list-disc list-inside space-y-1"
        >
          <li
            v-for="detail in errorDetails"
            :key="detail"
          >
            {{ detail }}
          </li>
        </ul>
      </div>
    </ErrorBoundary>

    <template #footer>
      <div class="flex items-center justify-between w-full">
        <Button
          v-if="currentStep > 0"
          variant="secondary"
          :disabled="loading"
          @click="prevStep"
        >
          Назад
        </Button>
        <div v-else></div>

        <div class="flex gap-2">
          <Button
            variant="secondary"
            :disabled="loading"
            @click="handleClose"
          >
            Отмена
          </Button>
          <Button
            v-if="currentStep < steps.length - 1"
            data-testid="growth-cycle-wizard-next"
            :disabled="loading || !canProceed"
            @click="nextStep"
          >
            Далее
          </Button>
          <Button
            v-else
            data-testid="growth-cycle-wizard-submit"
            :disabled="!canSubmit || loading"
            @click="onSubmit"
          >
            {{ loading ? "Создание..." : "Запустить цикл" }}
          </Button>
        </div>
      </div>

      <div
        v-if="nextStepBlockedReason && currentStep < steps.length - 1"
        class="mt-2 text-xs text-[color:var(--badge-danger-text)]"
      >
        {{ nextStepBlockedReason }}
      </div>
    </template>
  </Modal>

  <PumpCalibrationModal
    v-if="showPumpCalibrationModal"
    :show="showPumpCalibrationModal"
    :zone-id="form.zoneId"
    :devices="zoneDevices"
    :loading-run="loadingPumpCalibrationRun"
    :loading-save="loadingPumpCalibrationSave"
    :save-success-seq="pumpCalibrationSaveSeq"
    :run-success-seq="pumpCalibrationRunSeq"
    :last-run-token="pumpCalibrationLastRunToken"
    @close="closePumpCalibrationModal"
    @start="startPumpCalibration"
    @save="savePumpCalibration"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useToast } from "@/composables/useToast";
import { useZones } from "@/composables/useZones";
import Modal from "@/Components/Modal.vue";
import Button from "@/Components/Button.vue";
import ErrorBoundary from "@/Components/ErrorBoundary.vue";
import PumpCalibrationModal from "@/Components/PumpCalibrationModal.vue";
import WizardAutomationStep from "@/Components/GrowCycle/steps/WizardAutomationStep.vue";
import WizardCalibrationStep from "@/Components/GrowCycle/steps/WizardCalibrationStep.vue";
import WizardConfirmStep from "@/Components/GrowCycle/steps/WizardConfirmStep.vue";
import WizardRecipeStep from "@/Components/GrowCycle/steps/WizardRecipeStep.vue";
import { usePumpCalibration } from "@/composables/usePumpCalibration";
import { usePumpCalibrationActions } from "@/composables/usePumpCalibrationActions";
import { useGrowthCycleWizard, type GrowthCycleWizardProps, type GrowthCycleWizardEmit } from "@/composables/useGrowthCycleWizard";
import type { PumpCalibrationComponent, PumpCalibrationRunPayload, PumpCalibrationSavePayload } from "@/types/Calibration";

interface Props extends GrowthCycleWizardProps {
  show: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  zoneId: undefined,
  zoneName: "",
});

const emit = defineEmits<{
  close: [];
  submit: [
    data: {
      zoneId: number;
      cycleId?: number;
      recipeId?: number;
      recipeRevisionId?: number;
      startedAt: string;
      expectedHarvestAt?: string;
    },
  ];
}>();

const { showToast } = useToast();
const { fetchZones } = useZones();
const wizardEmit = emit as GrowthCycleWizardEmit;

const {
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
  canSubmit,
  canProceed,
  nextStepBlockedReason,
  zoneDevices,
  isZoneDevicesLoading,
  zoneDevicesError,
  zoneReadiness,
  zoneReadinessLoading,
  soilMoistureChannelCandidates,
  soilMoistureBindingLoading,
  soilMoistureBindingError,
  soilMoistureBindingSavedAt,
  soilMoistureSelectedNodeChannelId,
  soilMoistureBoundNodeChannelId,
  formatDateTime,
  formatDate,
  onZoneSelected,
  onRecipeSelected,
  onRecipeCreated,
  fetchZoneDevices,
  loadZoneReadiness,
  saveSoilMoistureBinding,
  nextStep,
  prevStep,
  onSubmit,
  handleClose,
} = useGrowthCycleWizard({
  props,
  emit: wizardEmit,
  showToast,
  fetchZones,
});

const automationTab = ref<1 | 2 | 3>(1);

const showPumpCalibrationModal = ref(false);
const pumpCalibrationActions = usePumpCalibrationActions({
  getZoneId: () => form.value.zoneId,
  showToast,
  runSuccessMessage: "Запуск калибровки отправлен. После прогона сохраните фактический объём.",
  saveSuccessMessage: "Калибровка насоса сохранена.",
  onSaveSuccess: async () => {
    await refreshPumpCalibrationData(true);
  },
})
const loadingPumpCalibrationRun = pumpCalibrationActions.loadingRun;
const loadingPumpCalibrationSave = pumpCalibrationActions.loadingSave;
const pumpCalibrationSaveSeq = pumpCalibrationActions.saveSeq;
const pumpCalibrationRunSeq = pumpCalibrationActions.runSeq;
const pumpCalibrationLastRunToken = pumpCalibrationActions.lastRunToken;

const componentLabels: Record<PumpCalibrationComponent, string> = {
  npk: "NPK",
  calcium: "Calcium",
  magnesium: "Magnesium",
  micro: "Micro",
  ph_up: "pH Up",
  ph_down: "pH Down",
};

const {
  componentOptions,
  pumpChannels,
  calibratedChannels,
  autoComponentMap,
  channelById,
  refreshDbCalibrations,
} = usePumpCalibration({
  get show() {
    return showPumpCalibrationModal.value;
  },
  get zoneId() {
    return form.value.zoneId;
  },
  get devices() {
    return zoneDevices.value;
  },
  get saveSuccessSeq() {
    return pumpCalibrationSaveSeq.value;
  },
  get runSuccessSeq() {
    return pumpCalibrationRunSeq.value;
  },
  get lastRunToken() {
    return pumpCalibrationLastRunToken.value;
  },
});

const mappedPumpComponents = computed(() => {
  return componentOptions
    .map((option) => {
      const channelId = autoComponentMap.value[option.value];
      const channel = channelId ? channelById.value.get(channelId) || null : null;
      const calibrated = Number(channel?.calibration?.ml_per_sec ?? 0) > 0;

      return {
        component: option.value,
        label: componentLabels[option.value],
        calibrated,
      };
    })
    .filter((item) => Boolean(autoComponentMap.value[item.component]));
});

const missingPumpComponents = computed(() => {
  return mappedPumpComponents.value
    .filter((item) => !item.calibrated)
    .map((item) => item.label);
});

// Step 4 computeds (isTimedIrrigation / waterAdvancedSummary / irrigationStrategyDescription /
// irrigationRecipeSummary) вынесены в WizardAutomationStep.vue. Здесь оставлены только
// значения, нужные родителю для confirm-превью (step 6).
const isSmartIrrigation = computed(() => waterForm.value.irrigationDecisionStrategy === "smart_soil_v1");
const irrigationStrategyLabel = computed(() =>
  isSmartIrrigation.value ? "Умный полив по SOIL_MOISTURE" : "Полив по расписанию"
);
const irrigationScheduleSummary = computed(() =>
  `Стартовая схема полива: каждые ${waterForm.value.intervalMinutes} мин на ${waterForm.value.durationSeconds} сек.`
);

async function refreshPumpCalibrationData(force = false): Promise<void> {
  await fetchZoneDevices(force);
  await refreshDbCalibrations();
  if (form.value.zoneId) {
    await loadZoneReadiness(form.value.zoneId);
  }
}

function openPumpCalibrationModal(): void {
  if (!form.value.zoneId) {
    showToast("Сначала выберите зону.", "warning");
    return;
  }

  showPumpCalibrationModal.value = true;
}

function closePumpCalibrationModal(): void {
  showPumpCalibrationModal.value = false;
}

async function startPumpCalibration(payload: PumpCalibrationRunPayload): Promise<void> {
  await pumpCalibrationActions.startPumpCalibration(payload);
}

async function savePumpCalibration(payload: PumpCalibrationSavePayload): Promise<void> {
  await pumpCalibrationActions.savePumpCalibration(payload);
}

watch(
  () => [props.show, currentStep.value, form.value.zoneId],
  ([isOpen, step, zoneId]) => {
    if (!isOpen || !zoneId || (step !== 5 && step !== 6)) {
      return;
    }

    void refreshPumpCalibrationData(step === 6);
  },
  { immediate: true },
);
</script>
