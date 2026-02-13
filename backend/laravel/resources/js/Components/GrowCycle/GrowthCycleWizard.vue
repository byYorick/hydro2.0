<template>
  <Modal
    :open="show"
    :title="wizardTitle"
    size="large"
    @close="handleClose"
  >
    <ErrorBoundary>
      <div class="mb-6">
        <div class="flex items-center justify-between">
          <div
            v-for="(step, index) in steps"
            :key="index"
            class="flex items-center flex-1"
          >
            <div class="flex items-center">
              <div :class="['w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold transition-all', currentStep > index ? 'bg-[color:var(--accent-green)] text-white' : currentStep === index ? 'bg-[color:var(--accent-cyan)] text-white ring-2 ring-[color:var(--accent-cyan)] ring-offset-2' : 'bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]']">
                <span v-if="currentStep > index">✓</span>
                <span v-else>{{ index + 1 }}</span>
              </div>
              <span :class="['ml-3 text-sm font-medium', currentStep >= index ? 'text-[color:var(--text-primary)]' : 'text-[color:var(--text-muted)]']">
                {{ step.title }}
              </span>
            </div>
            <div
              v-if="index < steps.length - 1"
              :class="['flex-1 h-0.5 mx-4 transition-colors', currentStep > index ? 'bg-[color:var(--accent-green)]' : 'bg-[color:var(--border-muted)]']"
            ></div>
          </div>
        </div>
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
        <div class="text-xs text-[color:var(--text-muted)]">
          💡 Подсказка: Убедитесь, что зона имеет привязанный рецепт и устройства
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
        <div class="text-xs text-[color:var(--text-muted)]">
          💡 Растение определяет контекст для подбора рецепта
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
                {{ recipe.name }} ({{ recipe.published_revisions?.[0]?.phases?.length || 0 }} фаз)
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
              Rev {{ revision.revision_number }} — {{ revision.description || "Без описания" }}
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
        <div class="text-xs text-[color:var(--text-muted)]">
          💡 Подсказка: Рецепт определяет фазы роста и целевые параметры для каждой фазы
        </div>
      </div>
      <div
        v-if="currentStep === 3"
        class="space-y-4"
      >
        <div>
          <h3 class="text-sm font-semibold mb-3">
            Параметры запуска цикла
          </h3>
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium mb-2">Дата начала</label>
              <input
                v-model="form.startedAt"
                type="datetime-local"
                class="input-field w-full"
                :min="minStartDate"
                required
              />
              <div class="text-xs text-[color:var(--text-muted)] mt-1">
                Цикл начнется с первой фазы выбранного рецепта
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium mb-2">Ожидаемая дата сбора (опционально)</label>
              <input
                v-model="form.expectedHarvestAt"
                type="date"
                class="input-field w-full"
                :min="form.startedAt ? form.startedAt.slice(0, 10) : undefined"
              />
              <div class="text-xs text-[color:var(--text-muted)] mt-1">
                Используется для планирования и аналитики
              </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 p-3 rounded-lg bg-[color:var(--bg-elevated)] border border-[color:var(--border-muted)]">
              <div class="md:col-span-2 text-sm font-medium">
                Параметры водного узла на старте
              </div>
              <div>
                <label class="block text-sm font-medium mb-2">Тип системы</label>
                <select
                  v-model="form.irrigation.systemType"
                  class="input-select w-full"
                >
                  <option value="drip">drip</option>
                  <option value="substrate_trays">substrate_trays</option>
                  <option value="nft">nft</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium mb-2">Интервал полива (мин)</label>
                <input
                  v-model.number="form.irrigation.intervalMinutes"
                  type="number"
                  min="5"
                  max="1440"
                  class="input-field w-full"
                />
              </div>
              <div>
                <label class="block text-sm font-medium mb-2">Длительность полива (сек)</label>
                <input
                  v-model.number="form.irrigation.durationSeconds"
                  type="number"
                  min="1"
                  max="3600"
                  class="input-field w-full"
                />
              </div>
              <div>
                <label class="block text-sm font-medium mb-2">Объём чистого бака (л)</label>
                <input
                  v-model.number="form.irrigation.cleanTankFillL"
                  type="number"
                  min="10"
                  max="5000"
                  class="input-field w-full"
                />
              </div>
              <div>
                <label class="block text-sm font-medium mb-2">Объём питательного бака (л)</label>
                <input
                  v-model.number="form.irrigation.nutrientTankTargetL"
                  type="number"
                  min="10"
                  max="5000"
                  class="input-field w-full"
                />
              </div>
            </div>
            <div
              v-if="selectedRecipe"
              class="p-3 rounded-lg bg-[color:var(--bg-elevated)] border border-[color:var(--border-muted)]"
            >
              <div class="text-xs font-medium mb-1">
                Предполагаемая длительность цикла:
              </div>
              <div class="text-sm">
                {{ Math.round(totalDurationDays) }} дней
                <span class="text-xs text-[color:var(--text-muted)]"> ({{ selectedRevision?.phases?.length || 0 }} фаз) </span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div
        v-if="currentStep === 4"
        class="space-y-4"
      >
        <div>
          <h3 class="text-sm font-semibold mb-3">
            Предпросмотр цикла выращивания
          </h3>
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
            </div>
            <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
              <div class="text-xs text-[color:var(--text-dim)] mb-1">
                Дата начала
              </div>
              <div class="text-sm font-medium">
                {{ formatDateTime(form.startedAt) }}
              </div>
            </div>
            <div class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]">
              <div class="text-xs text-[color:var(--text-dim)] mb-1">
                Параметры водного узла
              </div>
              <div class="text-sm font-medium">
                {{ form.irrigation.cleanTankFillL }} / {{ form.irrigation.nutrientTankTargetL }} л
              </div>
              <div class="text-xs text-[color:var(--text-muted)] mt-1">
                Полив: каждые {{ form.irrigation.intervalMinutes }} мин, {{ form.irrigation.durationSeconds }} сек · {{ form.irrigation.systemType }}
              </div>
            </div>
            <div
              v-if="form.expectedHarvestAt"
              class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
            >
              <div class="text-xs text-[color:var(--text-dim)] mb-1">
                Ожидаемая дата сбора
              </div>
              <div class="text-sm font-medium">
                {{ formatDate(form.expectedHarvestAt) }}
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
                  <span class="text-[color:var(--text-muted)]"> {{ phase.duration_days ?? (phase.duration_hours ? Math.round(phase.duration_hours / 24) : "-") }} дней </span>
                </div>
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
        v-if="error"
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
            :disabled="loading || !canProceed"
            @click="nextStep"
          >
            Далее
          </Button>
          <Button
            v-else
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
</template>
<script setup lang="ts">
import { useApi } from "@/composables/useApi";
import { useToast } from "@/composables/useToast";
import { useZones } from "@/composables/useZones";
import Modal from "@/Components/Modal.vue";
import Button from "@/Components/Button.vue";
import ErrorBoundary from "@/Components/ErrorBoundary.vue";
import RecipeCreateWizard from "@/Components/RecipeCreateWizard.vue";
import { useGrowthCycleWizard, type GrowthCycleWizardProps, type GrowthCycleWizardEmit } from "@/composables/useGrowthCycleWizard";

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
            recipeId?: number;
            recipeRevisionId?: number;
            startedAt: string;
            expectedHarvestAt?: string;
        },
    ];
}>();
const { api } = useApi();
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
    canSubmit,
    canProceed,
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
} = useGrowthCycleWizard({
    props,
    emit: wizardEmit,
    api,
    showToast,
    fetchZones,
});
</script>
