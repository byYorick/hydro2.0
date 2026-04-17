<template>
  <div class="space-y-4">
    <PresetSelector
      :water-form="waterForm"
      :can-configure="true"
      :tanks-count="tanksCount"
      @update:water-form="Object.assign(waterForm, $event)"
      @preset-applied="$emit('preset-applied', $event)"
      @preset-cleared="$emit('preset-cleared')"
    />

    <div class="flex flex-wrap items-center gap-2">
      <button
        v-for="item in automationTabs"
        :key="item.id"
        type="button"
        class="btn btn-outline h-9 px-3 text-xs"
        :class="item.id === activeTab ? 'border-[color:var(--accent-green)] text-[color:var(--text-primary)]' : ''"
        @click="activeTab = item.id"
      >
        {{ item.label }}
      </button>
    </div>

    <section
      v-if="activeTab === 1"
      class="grid grid-cols-1 md:grid-cols-2 gap-3"
    >
      <label class="text-xs text-[color:var(--text-muted)]">
        Автоклимат
        <select
          v-model="climateForm.enabled"
          class="input-select mt-1 w-full"
        >
          <option :value="true">Включен</option>
          <option :value="false">Выключен</option>
        </select>
      </label>
      <label class="text-xs text-[color:var(--text-muted)]">
        Температура день
        <input
          v-model.number="climateForm.dayTemp"
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
          v-model.number="climateForm.nightTemp"
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
          v-model.number="climateForm.dayHumidity"
          type="number"
          min="30"
          max="90"
          class="input-field mt-1 w-full"
        />
      </label>
      <label class="text-xs text-[color:var(--text-muted)]">
        Влажность ночь
        <input
          v-model.number="climateForm.nightHumidity"
          type="number"
          min="30"
          max="90"
          class="input-field mt-1 w-full"
        />
      </label>
      <label class="text-xs text-[color:var(--text-muted)]">
        Интервал климата (мин)
        <input
          v-model.number="climateForm.intervalMinutes"
          type="number"
          min="1"
          max="1440"
          class="input-field mt-1 w-full"
        />
      </label>
      <label class="text-xs text-[color:var(--text-muted)]">
        Min форточек (%)
        <input
          v-model.number="climateForm.ventMinPercent"
          type="number"
          min="0"
          max="100"
          class="input-field mt-1 w-full"
        />
      </label>
      <label class="text-xs text-[color:var(--text-muted)]">
        Max форточек (%)
        <input
          v-model.number="climateForm.ventMaxPercent"
          type="number"
          min="0"
          max="100"
          class="input-field mt-1 w-full"
        />
      </label>
    </section>

    <section
      v-else-if="activeTab === 2"
      class="space-y-3"
    >
      <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-4 space-y-4">
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          Конфигурация водного контура
        </div>

        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-[10px] font-medium uppercase tracking-wide text-[color:var(--text-dim)]">Тип системы</div>
            <div class="mt-1 text-sm font-medium text-[color:var(--text-primary)]">{{ systemTypeLabel }}</div>
            <div class="mt-0.5 text-[10px] text-[color:var(--text-dim)]">Определяется рецептом</div>
          </div>

          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-[10px] font-medium uppercase tracking-wide text-[color:var(--text-dim)]">Режим полива</div>
            <div class="mt-1 text-sm font-medium text-[color:var(--text-primary)]">{{ irrigationStrategyLabel }}</div>
            <div class="mt-0.5 text-[10px] text-[color:var(--text-dim)]">{{ irrigationStrategyDescription }}</div>
          </div>

          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-[10px] font-medium uppercase tracking-wide text-[color:var(--text-dim)]">Цели из рецепта</div>
            <div class="mt-1 text-sm font-medium text-[color:var(--text-primary)]">pH {{ waterForm.targetPh }} · EC {{ waterForm.targetEc }}</div>
          </div>

          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-[10px] font-medium uppercase tracking-wide text-[color:var(--text-dim)]">Расписание полива</div>
            <div class="mt-1 text-sm font-medium text-[color:var(--text-primary)]">{{ irrigationScheduleSummary }}</div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs">
          <div class="text-[color:var(--text-muted)]">Баков</div>
          <div class="text-[color:var(--text-primary)]">{{ tanksCount }}</div>

          <div class="text-[color:var(--text-muted)]">Объём чистого бака</div>
          <div class="text-[color:var(--text-primary)]">{{ waterForm.cleanTankFillL }} л</div>

          <div class="text-[color:var(--text-muted)]">Объём бака раствора</div>
          <div class="text-[color:var(--text-primary)]">{{ waterForm.nutrientTankTargetL }} л</div>

          <div class="text-[color:var(--text-muted)]">Порция полива</div>
          <div class="text-[color:var(--text-primary)]">{{ waterForm.irrigationBatchL }} л</div>

          <div class="text-[color:var(--text-muted)]">Температура набора</div>
          <div class="text-[color:var(--text-primary)]">{{ waterForm.fillTemperatureC }} °C</div>

          <div class="text-[color:var(--text-muted)]">Окно набора воды</div>
          <div class="text-[color:var(--text-primary)]">{{ waterForm.fillWindowStart }} — {{ waterForm.fillWindowEnd }}</div>

          <div v-if="isSmartIrrigation" class="text-[color:var(--text-muted)]">Датчик влажности</div>
          <div v-if="isSmartIrrigation" class="text-[color:var(--text-primary)]">
            {{ soilMoistureBoundNodeChannelId ? `Привязан (ID: ${soilMoistureBoundNodeChannelId})` : 'Не привязан' }}
          </div>
        </div>

        <div class="text-[11px] text-[color:var(--text-dim)]">
          Параметры водного контура задаются в мастере настройки зоны или через профиль автоматики выше.
          При запуске цикла они передаются как override и не перезаписывают настройки зоны.
        </div>
      </div>
    </section>

    <section
      v-else
      class="grid grid-cols-1 md:grid-cols-3 gap-3"
    >
      <label class="text-xs text-[color:var(--text-muted)]">
        Досветка
        <select
          v-model="lightingForm.enabled"
          class="input-select mt-1 w-full"
        >
          <option :value="true">Включена</option>
          <option :value="false">Выключена</option>
        </select>
      </label>
      <label class="text-xs text-[color:var(--text-muted)]">
        Lux day
        <input
          v-model.number="lightingForm.luxDay"
          type="number"
          min="0"
          max="120000"
          class="input-field mt-1 w-full"
        />
      </label>
      <label class="text-xs text-[color:var(--text-muted)]">
        Lux night
        <input
          v-model.number="lightingForm.luxNight"
          type="number"
          min="0"
          max="120000"
          class="input-field mt-1 w-full"
        />
      </label>
      <label class="text-xs text-[color:var(--text-muted)]">
        Часов света
        <input
          v-model.number="lightingForm.hoursOn"
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
          v-model.number="lightingForm.intervalMinutes"
          type="number"
          min="1"
          max="1440"
          class="input-field mt-1 w-full"
        />
      </label>
      <label class="text-xs text-[color:var(--text-muted)]">
        Начало
        <input
          v-model="lightingForm.scheduleStart"
          type="time"
          class="input-field mt-1 w-full"
        />
      </label>
      <label class="text-xs text-[color:var(--text-muted)]">
        Конец
        <input
          v-model="lightingForm.scheduleEnd"
          type="time"
          class="input-field mt-1 w-full"
        />
      </label>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import PresetSelector from '@/Components/AutomationForms/PresetSelector.vue'
import type {
  ClimateFormState,
  LightingFormState,
  WaterFormState,
} from '@/composables/zoneAutomationTypes'

interface SoilMoistureChannelOption {
  id: number
  label: string
}

defineProps<{
  soilMoistureChannelCandidates: SoilMoistureChannelOption[]
  soilMoistureBindingLoading: boolean
  soilMoistureBindingError: string | null
  soilMoistureBindingSavedAt: string | null
  soilMoistureBoundNodeChannelId: number | null
  tanksCount: number
  formatDateTime: (value: string | null | undefined) => string
}>()

const emit = defineEmits<{
  'save-soil-moisture-binding': []
  'preset-applied': [preset: { id: number; name: string }]
  'preset-cleared': []
}>()

const climateForm = defineModel<ClimateFormState>('climateForm', { required: true })
const waterForm = defineModel<WaterFormState>('waterForm', { required: true })
const lightingForm = defineModel<LightingFormState>('lightingForm', { required: true })
const soilMoistureChannelId = defineModel<number | null>('soilMoistureChannelId', { required: true })
const activeTab = defineModel<1 | 2 | 3>('activeTab', { default: 1 })

const automationTabs = [
  { id: 1 as const, label: 'Климат' },
  { id: 2 as const, label: 'Водный узел' },
  { id: 3 as const, label: 'Досветка' },
]

const systemTypeLabel = computed(() => {
  const labels: Record<string, string> = {
    drip: 'Капельный полив (Drip)',
    substrate_trays: 'DWC / Субстрат',
    nft: 'NFT (Nutrient Film)',
  }
  return labels[waterForm.value.systemType] ?? waterForm.value.systemType
})

const isTimedIrrigation = computed(() => waterForm.value.irrigationDecisionStrategy !== 'smart_soil_v1')
const isSmartIrrigation = computed(() => waterForm.value.irrigationDecisionStrategy === 'smart_soil_v1')

const irrigationStrategyLabel = computed(() =>
  isSmartIrrigation.value ? 'Умный полив по SOIL_MOISTURE' : 'Полив по расписанию'
)

const irrigationStrategyDescription = computed(() =>
  isSmartIrrigation.value
    ? 'Перед стартом оценивается влажность субстрата и качество телеметрии; без привязки датчика стратегия не сработает корректно.'
    : 'Полив стартует по временным окнам цикла без предварительной оценки влажности субстрата.'
)

const irrigationRecipeSummary = computed(() =>
  `Рецепт задаёт базовые launch-targets: pH ${waterForm.value.targetPh}, EC ${waterForm.value.targetEc}.`
)

const irrigationScheduleSummary = computed(() =>
  `Стартовая схема полива: каждые ${waterForm.value.intervalMinutes} мин на ${waterForm.value.durationSeconds} сек.`
)

const waterAdvancedSummary = computed(() => {
  const diagnosticsState = waterForm.value.diagnosticsEnabled ? 'диагностика включена' : 'диагностика выключена'
  const refillState = `${waterForm.value.refillDurationSeconds}с / timeout ${waterForm.value.refillTimeoutSeconds}с`
  const solutionChangeState = waterForm.value.solutionChangeEnabled
    ? `смена раствора каждые ${waterForm.value.solutionChangeIntervalMinutes} мин`
    : 'смена раствора отключена'

  return `${diagnosticsState}, refill ${refillState}, ${solutionChangeState}.`
})
</script>
