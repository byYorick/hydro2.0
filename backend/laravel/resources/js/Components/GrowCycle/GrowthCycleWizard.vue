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

      <div
        v-if="currentStep === 2"
        class="space-y-4"
      >
        <div>
          <label class="block text-sm font-medium mb-2">Выберите рецепт</label>
          <div class="flex gap-2 mb-3">
            <Button
              size="sm"
              :variant="recipeMode === 'select' ? 'primary' : 'secondary'"
              @click="recipeMode = 'select'"
            >
              Выбрать существующий
            </Button>
            <Button
              size="sm"
              :variant="recipeMode === 'create' ? 'primary' : 'secondary'"
              @click="recipeMode = 'create'"
            >
              Создать новый
            </Button>
          </div>

          <div v-if="recipeMode === 'select'">
            <select
              v-model="selectedRecipeId"
              class="input-select w-full"
              @change="onRecipeSelected"
            >
              <option :value="null">
                Выберите рецепт
              </option>
              <option
                v-for="recipe in availableRecipes"
                :key="recipe.id"
                :value="recipe.id"
              >
                {{ recipe.name }} ({{ recipe.phases_count || 0 }} фаз)
              </option>
            </select>
          </div>
          <div v-else>
            <RecipeCreateWizard
              :show="recipeMode === 'create'"
              @close="recipeMode = 'select'"
              @created="onRecipeCreated"
            />
          </div>
        </div>

        <div
          v-if="selectedRecipe"
          class="space-y-2"
        >
          <label class="block text-sm font-medium mb-2">Ревизия</label>
          <select
            v-model="selectedRevisionId"
            class="input-select w-full"
          >
            <option :value="null">
              Выберите ревизию
            </option>
            <option
              v-for="revision in availableRevisions"
              :key="revision.id"
              :value="revision.id"
            >
              {{ revision.revision_number ? `Rev ${revision.revision_number}` : 'Актуальная опубликованная ревизия' }}
              — {{ revision.description || "Без описания" }}
            </option>
          </select>
        </div>

        <div
          v-if="selectedRevision"
          class="mt-4 p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
        >
          <div class="text-sm font-semibold mb-2">
            {{ selectedRecipe.name }}
          </div>
          <div
            v-if="selectedRecipe.description"
            class="text-xs text-[color:var(--text-muted)] mb-3"
          >
            {{ selectedRecipe.description }}
          </div>
          <div class="text-xs font-medium mb-2">
            Фазы рецепта:
          </div>
          <div class="space-y-2">
            <div
              v-for="(phase, index) in selectedRevision.phases"
              :key="index"
              class="flex items-center justify-between p-2 rounded bg-[color:var(--bg-surface-strong)]"
            >
              <div>
                <div class="text-xs font-medium">
                  {{ phase.name || `Фаза ${index + 1}` }}
                </div>
                <div class="text-xs text-[color:var(--text-dim)]">
                  {{ phase.duration_days ?? (phase.duration_hours ? Math.round(phase.duration_hours / 24) : "-") }} дней
                </div>
              </div>
              <div class="text-xs text-[color:var(--text-muted)]">
                pH: {{ phase.ph_min ?? "-" }}–{{ phase.ph_max ?? "-" }} EC: {{ phase.ec_min ?? "-" }}–{{ phase.ec_max ?? "-" }}
              </div>
            </div>
          </div>
        </div>
      </div>

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

      <div
        v-if="currentStep === 5"
        class="space-y-4"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-sm font-semibold">
              Калибровка насосов
            </h3>
            <p class="text-xs text-[color:var(--text-muted)] mt-1">
              Используется тот же calibration flow, что и в setup wizard. Сохранённые значения берутся только из backend `pump_calibrations`.
            </p>
          </div>
          <Button
            size="sm"
            variant="primary"
            :disabled="!form.zoneId || loadingPumpCalibrationRun || loadingPumpCalibrationSave"
            @click="openPumpCalibrationModal"
          >
            Открыть калибровку насосов
          </Button>
        </div>

        <div
          v-if="isZoneDevicesLoading"
          class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-sm text-[color:var(--text-muted)]"
        >
          Загружаю насосы зоны...
        </div>

        <div
          v-else-if="zoneDevicesError"
          class="p-4 rounded-lg bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)] text-sm text-[color:var(--badge-danger-text)] space-y-2"
        >
          <div>{{ zoneDevicesError }}</div>
          <Button
            size="sm"
            variant="secondary"
            @click="refreshPumpCalibrationData(true)"
          >
            Повторить
          </Button>
        </div>

        <div
          v-else-if="pumpChannels.length === 0"
          class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-sm text-[color:var(--text-muted)] space-y-2"
        >
          <div>В зоне не найдены дозирующие насосы для calibration flow.</div>
          <Button
            size="sm"
            variant="secondary"
            @click="refreshPumpCalibrationData(true)"
          >
            Обновить список
          </Button>
        </div>

        <div
          v-else
          class="space-y-3"
        >
          <div
            class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] space-y-3"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="text-sm font-medium">
                  Сохранено {{ calibratedChannels.length }} из {{ mappedPumpComponents.length }} ожидаемых pump calibration.
                </div>
                <div class="text-xs text-[color:var(--text-muted)] mt-1">
                  Launch wizard не записывает `ml/sec` локально. Сначала сохраните калибровки через общую модалку, затем readiness автоматически разрешит запуск.
                </div>
              </div>
              <Button
                size="sm"
                variant="secondary"
                :disabled="loadingPumpCalibrationRun || loadingPumpCalibrationSave"
                @click="refreshPumpCalibrationData(true)"
              >
                Обновить статус
              </Button>
            </div>

            <div class="flex flex-wrap gap-2">
              <span
                v-for="item in mappedPumpComponents"
                :key="item.component"
                class="inline-flex items-center rounded-full border px-2.5 py-1 text-xs"
                :class="item.calibrated
                  ? 'border-[color:var(--badge-success-border)] bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)]'
                  : 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]'"
              >
                {{ item.label }}: {{ item.calibrated ? 'готово' : 'не сохранено' }}
              </span>
            </div>
          </div>

          <div
            v-if="missingPumpComponents.length > 0"
            class="p-3 rounded-lg bg-[color:var(--badge-warning-bg)] border border-[color:var(--badge-warning-border)] text-sm text-[color:var(--badge-warning-text)]"
          >
            Для correction runtime ещё не сохранены: {{ missingPumpComponents.join(', ') }}.
          </div>

          <div
            v-if="calibratedChannels.length > 0"
            class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
          >
            <div class="text-xs text-[color:var(--text-dim)] mb-2">
              Уже сохранено
            </div>
            <div class="space-y-1">
              <div
                v-for="channel in calibratedChannels"
                :key="channel.id"
                class="text-sm text-[color:var(--text-primary)]"
              >
                {{ channel.label }}: {{ channel.calibration?.ml_per_sec ?? '-' }} мл/сек
              </div>
            </div>
          </div>
        </div>
      </div>

      <div
        v-if="currentStep === 6"
        class="space-y-4"
      >
        <h3 class="text-sm font-semibold mb-1">
          Предпросмотр запуска
        </h3>

        <ReadinessChecklist
          :zone-id="form.zoneId"
          :readiness="zoneReadiness"
          :loading="zoneReadinessLoading"
        />

        <div class="space-y-3">
          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">
              Зона
            </div>
            <div class="text-sm font-medium">
              {{ zoneName || `Зона #${form.zoneId}` }}
            </div>
          </div>

          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">
              Рецепт
            </div>
            <div class="text-sm font-medium">
              {{ selectedRecipe?.name || "Не выбран" }}
            </div>
            <div
              v-if="totalDurationDays > 0"
              class="text-xs text-[color:var(--text-muted)] mt-1"
            >
              Оценочная длительность: {{ Math.round(totalDurationDays) }} дней
            </div>
          </div>

          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">
              Период
            </div>
            <div class="text-sm font-medium">
              Старт: {{ formatDateTime(form.startedAt) }}
            </div>
            <div
              v-if="form.expectedHarvestAt"
              class="text-xs text-[color:var(--text-muted)] mt-1"
            >
              Сбор: {{ formatDate(form.expectedHarvestAt) }}
            </div>
          </div>

          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">
              Автоматика
            </div>
            <div class="text-sm font-medium">
              Автоматика: pH {{ waterForm.targetPh }}, EC {{ waterForm.targetEc }}, система {{ waterForm.systemType }}
            </div>
          </div>

          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">
              Полив
            </div>
            <div class="text-sm font-medium">
              {{ irrigationStrategyLabel }} · {{ waterForm.systemType }}
            </div>
            <div class="text-xs text-[color:var(--text-muted)] mt-1">
              {{ irrigationScheduleSummary }}
            </div>
            <div
              v-if="tanksCount === 2"
              class="text-xs text-[color:var(--text-muted)] mt-1"
            >
              Баки: {{ waterForm.cleanTankFillL }} / {{ waterForm.nutrientTankTargetL }} л, партия {{ waterForm.irrigationBatchL }} л
            </div>
            <div
              v-if="isSmartIrrigation"
              class="text-xs text-[color:var(--text-muted)] mt-1"
            >
              Датчик влажности: {{ soilMoistureBoundNodeChannelId ? `node_channel_id ${soilMoistureBoundNodeChannelId}` : 'не привязан' }}
            </div>
          </div>

          <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">
              Калибровка насосов
            </div>
            <div class="text-sm font-medium">
              {{ calibratedChannels.length }} сохранено, {{ missingPumpComponents.length }} требуют внимания
            </div>
          </div>

          <div
            v-if="selectedRevision"
            class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
          >
            <div class="text-xs text-[color:var(--text-dim)] mb-2">
              План фаз:
            </div>
            <div class="space-y-2">
              <div
                v-for="(phase, index) in selectedRevision.phases"
                :key="index"
                class="flex items-center justify-between text-xs"
              >
                <span class="font-medium">{{ phase.name || `Фаза ${index + 1}` }}</span>
                <span class="text-[color:var(--text-muted)]">{{ phase.duration_days ?? (phase.duration_hours ? Math.round(phase.duration_hours / 24) : "-") }} дней</span>
              </div>
            </div>
          </div>
        </div>

        <div
          v-if="validationErrors.length > 0"
          class="p-3 rounded-lg bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)]"
        >
          <div class="text-sm font-medium text-[color:var(--badge-danger-text)] mb-1">
            Ошибки валидации:
          </div>
          <ul class="text-xs text-[color:var(--badge-danger-text)] list-disc list-inside">
            <li
              v-for="validationError in validationErrors"
              :key="validationError"
            >
              {{ validationError }}
            </li>
          </ul>
        </div>
      </div>

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
import ReadinessChecklist from "@/Components/GrowCycle/ReadinessChecklist.vue";
import PumpCalibrationModal from "@/Components/PumpCalibrationModal.vue";
import RecipeCreateWizard from "@/Components/RecipeCreateWizard.vue";
import WizardAutomationStep from "@/Components/GrowCycle/steps/WizardAutomationStep.vue";
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
