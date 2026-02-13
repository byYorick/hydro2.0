<template>
  <Modal
    :open="open"
    title="Редактирование автоматизации"
    size="large"
    @close="$emit('close')"
  >
    <div class="space-y-4">
      <div class="flex flex-wrap items-center gap-2">
        <button
          v-for="item in steps"
          :key="item.id"
          type="button"
          class="btn btn-outline h-9 px-3 text-xs"
          :class="item.id === step ? 'border-[color:var(--accent-green)] text-[color:var(--text-primary)]' : ''"
          @click="step = item.id"
        >
          {{ item.label }}
        </button>
      </div>

      <section
        v-if="step === 1"
        class="grid grid-cols-1 md:grid-cols-2 gap-3"
      >
        <label class="text-xs text-[color:var(--text-muted)]">
          Автоклимат
          <select
            v-model="draftClimateForm.enabled"
            class="input-select mt-1 w-full"
          >
            <option :value="true">Включен</option>
            <option :value="false">Выключен</option>
          </select>
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Температура день
          <input
            v-model.number="draftClimateForm.dayTemp"
            type="number"
            min="10"
            max="35"
            step="0.5"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Температура ночь
          <input
            v-model.number="draftClimateForm.nightTemp"
            type="number"
            min="10"
            max="35"
            step="0.5"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Влажность день
          <input
            v-model.number="draftClimateForm.dayHumidity"
            type="number"
            min="30"
            max="90"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Влажность ночь
          <input
            v-model.number="draftClimateForm.nightHumidity"
            type="number"
            min="30"
            max="90"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Интервал климата (мин)
          <input
            v-model.number="draftClimateForm.intervalMinutes"
            type="number"
            min="1"
            max="1440"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Min форточек (%)
          <input
            v-model.number="draftClimateForm.ventMinPercent"
            type="number"
            min="0"
            max="100"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Max форточек (%)
          <input
            v-model.number="draftClimateForm.ventMaxPercent"
            type="number"
            min="0"
            max="100"
            class="input-field mt-1 w-full"
          />
        </label>
      </section>

      <section
        v-else-if="step === 2"
        class="space-y-3"
      >
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <label class="text-xs text-[color:var(--text-muted)]">
            Тип системы
            <select
              v-model="draftWaterForm.systemType"
              class="input-select mt-1 w-full"
              :disabled="isSystemTypeLocked"
            >
              <option value="drip">drip</option>
              <option value="substrate_trays">substrate_trays</option>
              <option value="nft">nft</option>
            </select>
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            target pH
            <input
              v-model.number="draftWaterForm.targetPh"
              type="number"
              min="4"
              max="9"
              step="0.1"
              class="input-field mt-1 w-full"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            target EC
            <input
              v-model.number="draftWaterForm.targetEc"
              type="number"
              min="0.1"
              max="10"
              step="0.1"
              class="input-field mt-1 w-full"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Интервал полива (мин)
            <input
              v-model.number="draftWaterForm.intervalMinutes"
              type="number"
              min="5"
              max="1440"
              class="input-field mt-1 w-full"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Длительность (сек)
            <input
              v-model.number="draftWaterForm.durationSeconds"
              type="number"
              min="1"
              max="3600"
              class="input-field mt-1 w-full"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Баков
            <input
              v-model.number="draftWaterForm.tanksCount"
              type="number"
              min="2"
              max="3"
              class="input-field mt-1 w-full"
              :disabled="isSystemTypeLocked || draftWaterForm.systemType === 'drip'"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Диагностика
            <select
              v-model="draftWaterForm.diagnosticsEnabled"
              class="input-select mt-1 w-full"
            >
              <option :value="true">Включена</option>
              <option :value="false">Выключена</option>
            </select>
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Интервал диагностики (мин)
            <input
              v-model.number="draftWaterForm.diagnosticsIntervalMinutes"
              type="number"
              min="1"
              max="1440"
              class="input-field mt-1 w-full"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Workflow запуска
            <select
              v-model="draftWaterForm.cycleStartWorkflowEnabled"
              class="input-select mt-1 w-full"
            >
              <option :value="true">cycle_start</option>
              <option :value="false">diagnostics</option>
            </select>
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Порог полного бака (0..1)
            <input
              v-model.number="draftWaterForm.cleanTankFullThreshold"
              type="number"
              min="0.05"
              max="1"
              step="0.01"
              class="input-field mt-1 w-full"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Refill длительность (сек)
            <input
              v-model.number="draftWaterForm.refillDurationSeconds"
              type="number"
              min="1"
              max="3600"
              class="input-field mt-1 w-full"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Refill timeout (сек)
            <input
              v-model.number="draftWaterForm.refillTimeoutSeconds"
              type="number"
              min="30"
              max="86400"
              class="input-field mt-1 w-full"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)] md:col-span-2">
            Refill обязательные типы нод (CSV)
            <input
              v-model="draftWaterForm.refillRequiredNodeTypes"
              type="text"
              class="input-field mt-1 w-full"
              placeholder="irrig,climate,light"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Refill канал
            <input
              v-model="draftWaterForm.refillPreferredChannel"
              type="text"
              class="input-field mt-1 w-full"
              placeholder="fill_valve"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Смена раствора
            <select
              v-model="draftWaterForm.solutionChangeEnabled"
              class="input-select mt-1 w-full"
            >
              <option :value="true">Включена</option>
              <option :value="false">Выключена</option>
            </select>
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Интервал смены (мин)
            <input
              v-model.number="draftWaterForm.solutionChangeIntervalMinutes"
              type="number"
              min="1"
              max="1440"
              class="input-field mt-1 w-full"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Длительность смены (сек)
            <input
              v-model.number="draftWaterForm.solutionChangeDurationSeconds"
              type="number"
              min="1"
              max="86400"
              class="input-field mt-1 w-full"
            />
          </label>
        </div>
        <p
          v-if="isSystemTypeLocked"
          class="text-xs text-[color:var(--text-dim)]"
        >
          Тип системы нельзя менять в активном цикле. Он задаётся только при старте.
        </p>
      </section>

      <section
        v-else
        class="grid grid-cols-1 md:grid-cols-3 gap-3"
      >
        <label class="text-xs text-[color:var(--text-muted)]">
          Досветка
          <select
            v-model="draftLightingForm.enabled"
            class="input-select mt-1 w-full"
          >
            <option :value="true">Включена</option>
            <option :value="false">Выключена</option>
          </select>
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Lux day
          <input
            v-model.number="draftLightingForm.luxDay"
            type="number"
            min="0"
            max="120000"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Lux night
          <input
            v-model.number="draftLightingForm.luxNight"
            type="number"
            min="0"
            max="120000"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Часов света
          <input
            v-model.number="draftLightingForm.hoursOn"
            type="number"
            min="0"
            max="24"
            step="0.5"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Интервал досветки (мин)
          <input
            v-model.number="draftLightingForm.intervalMinutes"
            type="number"
            min="1"
            max="1440"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Начало
          <input
            v-model="draftLightingForm.scheduleStart"
            type="time"
            class="input-field mt-1 w-full"
          />
        </label>
        <label class="text-xs text-[color:var(--text-muted)]">
          Конец
          <input
            v-model="draftLightingForm.scheduleEnd"
            type="time"
            class="input-field mt-1 w-full"
          />
        </label>
      </section>
    </div>

    <template #footer>
      <Button
        type="button"
        variant="outline"
        @click="resetDraft"
      >
        Сбросить к рекомендуемым
      </Button>
      <Button
        v-if="step > 1"
        type="button"
        variant="secondary"
        @click="goPrevStep"
      >
        Назад
      </Button>
      <Button
        v-if="step < 3"
        type="button"
        @click="goNextStep"
      >
        Далее
      </Button>
      <Button
        v-else
        type="button"
        :disabled="isApplying"
        @click="emitApply"
      >
        {{ isApplying ? 'Отправка...' : 'Сохранить' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import { resetToRecommended as resetFormsToRecommended, syncSystemToTankLayout } from '@/composables/zoneAutomationFormLogic'
import type {
  ClimateFormState,
  LightingFormState,
  WaterFormState,
} from '@/composables/zoneAutomationTypes'

interface Props {
  open: boolean
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
  isApplying: boolean
  isSystemTypeLocked: boolean
}

interface ZoneAutomationWizardApplyPayload {
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
}

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'apply', payload: ZoneAutomationWizardApplyPayload): void
}>()

const props = defineProps<Props>()

const steps = [
  { id: 1, label: 'Климат' },
  { id: 2, label: 'Водный узел' },
  { id: 3, label: 'Досветка' },
] as const

const step = ref<1 | 2 | 3>(1)
const draftClimateForm = reactive<ClimateFormState>({ ...props.climateForm })
const draftWaterForm = reactive<WaterFormState>({ ...props.waterForm })
const draftLightingForm = reactive<LightingFormState>({ ...props.lightingForm })

function syncDraftFromProps(): void {
  Object.assign(draftClimateForm, props.climateForm)
  Object.assign(draftWaterForm, props.waterForm)
  Object.assign(draftLightingForm, props.lightingForm)
}

function goPrevStep(): void {
  if (step.value === 3) {
    step.value = 2
    return
  }
  if (step.value === 2) {
    step.value = 1
  }
}

function goNextStep(): void {
  if (step.value === 1) {
    step.value = 2
    return
  }
  if (step.value === 2) {
    step.value = 3
  }
}

function resetDraft(): void {
  resetFormsToRecommended({
    climateForm: draftClimateForm,
    waterForm: draftWaterForm,
    lightingForm: draftLightingForm,
  })
}

function emitApply(): void {
  const waterFormForApply: WaterFormState = { ...draftWaterForm }
  if (waterFormForApply.systemType === 'drip') {
    waterFormForApply.tanksCount = 2
    waterFormForApply.enableDrainControl = false
  } else {
    waterFormForApply.tanksCount = waterFormForApply.tanksCount === 3 ? 3 : 2
    if (waterFormForApply.tanksCount === 2) {
      waterFormForApply.enableDrainControl = false
    }
  }

  emit('apply', {
    climateForm: { ...draftClimateForm },
    waterForm: waterFormForApply,
    lightingForm: { ...draftLightingForm },
  })
}

watch(
  () => draftWaterForm.systemType,
  (systemType) => {
    syncSystemToTankLayout(draftWaterForm, systemType)
  },
  { immediate: true },
)

watch(
  () => draftWaterForm.tanksCount,
  (tanksCount) => {
    const normalizedTanksCount = Math.round(Number(tanksCount)) === 3 ? 3 : 2

    if (draftWaterForm.systemType === 'drip') {
      if (draftWaterForm.tanksCount !== 2) {
        draftWaterForm.tanksCount = 2
      }
      draftWaterForm.enableDrainControl = false
      return
    }

    if (draftWaterForm.tanksCount !== normalizedTanksCount) {
      draftWaterForm.tanksCount = normalizedTanksCount
    }
    if (normalizedTanksCount === 2) {
      draftWaterForm.enableDrainControl = false
    }
  },
)

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      syncDraftFromProps()
      step.value = 1
    }
  },
)
</script>
