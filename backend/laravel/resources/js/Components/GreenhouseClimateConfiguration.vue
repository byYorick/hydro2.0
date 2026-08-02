<template>
  <section class="greenhouse-climate-configuration surface-card overflow-hidden rounded-2xl border border-[color:var(--border-muted)]">
    <header class="flex flex-col gap-3 border-b border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/35 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between md:px-5">
      <div class="min-w-0 space-y-1">
        <div class="flex flex-wrap items-center gap-2">
          <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Климат теплицы
          </h4>
          <span
            class="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px]"
            :class="enabled
              ? 'border-[color:var(--accent-green)]/35 bg-[color:var(--accent-green)]/10 text-[color:var(--accent-green)]'
              : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)]'"
          >
            <span
              class="h-1.5 w-1.5 rounded-full"
              :class="enabled ? 'bg-[color:var(--accent-green)]' : 'bg-[color:var(--text-dim)]'"
            />
            {{ enabled ? 'Активен' : 'Выключен' }}
          </span>
          <span
            v-if="enabled"
            class="rounded-full border border-[color:var(--border-muted)] px-2 py-0.5 text-[11px] tabular-nums text-[color:var(--text-muted)]"
          >
            {{ selectedBindingsCount }} привязок
          </span>
        </div>
        <p class="text-xs text-[color:var(--text-muted)]">
          Датчики, форточки, погодные ограничения и runtime-параметры AE.
        </p>
      </div>
      <div
        class="shrink-0"
        :title="fieldHelp('climate.enabled')"
      >
        <ToggleField
          :model-value="enabled"
          label="Климат"
          inline
          data-testid="greenhouse-climate-enabled"
          :disabled="!canConfigure"
          @update:model-value="(v) => (enabled = v)"
        />
      </div>
    </header>

    <div
      v-if="!enabled"
      class="flex flex-col items-center justify-center px-6 py-12 text-center"
    >
      <div class="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-[color:var(--accent-cyan)]">
        <svg
          class="h-5 w-5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="1.8"
            d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z"
          />
        </svg>
      </div>
      <p class="text-sm font-medium text-[color:var(--text-primary)]">
        Профиль климата выключен
      </p>
      <p class="mt-1 max-w-md text-xs text-[color:var(--text-muted)]">
        Включите климат, чтобы настроить привязки нод, дневной/ночной профиль и ограничения вентиляции.
      </p>
    </div>

    <div
      v-else
      class="space-y-0"
    >
      <nav class="flex gap-1 overflow-x-auto border-b border-[color:var(--border-muted)] px-3 py-2 md:px-4">
        <button
          v-for="panel in panels"
          :key="panel.id"
          type="button"
          class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
          :class="activePanel === panel.id
            ? 'bg-[color:var(--accent-cyan)]/15 text-[color:var(--accent-cyan)]'
            : 'text-[color:var(--text-muted)] hover:bg-[color:var(--bg-elevated)] hover:text-[color:var(--text-primary)]'"
          @click="activePanel = panel.id"
        >
          {{ panel.label }}
          <span
            v-if="panel.id === 'bindings' && selectedBindingsCount > 0"
            class="ml-1 tabular-nums opacity-80"
          >{{ selectedBindingsCount }}</span>
        </button>
      </nav>

      <div class="space-y-4 p-4 md:p-5">
        <div
          v-if="activePanel === 'bindings'"
          class="space-y-4"
        >
          <div>
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">
              Привязка нод
            </div>
            <p class="mt-1 text-xs text-[color:var(--text-muted)]">
              Сначала выберите greenhouse climate nodes, затем сохраните профиль.
            </p>
          </div>

          <div class="grid gap-3 lg:grid-cols-2">
            <div
              v-for="group in bindingGroups"
              :key="group.key"
              class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/30 p-3"
            >
              <div class="mb-2.5 flex items-center justify-between gap-2">
                <div class="text-xs font-semibold uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
                  {{ group.label }}
                </div>
                <span class="rounded-full border border-[color:var(--border-muted)] px-2 py-0.5 text-[11px] tabular-nums text-[color:var(--text-muted)]">
                  {{ bindings[group.key].length }}/{{ group.candidates.length }}
                </span>
              </div>

              <div
                v-if="group.candidates.length > 0"
                class="space-y-1.5"
              >
                <label
                  v-for="node in group.candidates"
                  :key="`${group.key}-${node.id}`"
                  class="flex cursor-pointer items-center gap-2.5 rounded-lg border px-2.5 py-2 text-sm transition-colors"
                  :class="bindings[group.key].includes(node.id)
                    ? 'border-[color:var(--accent-cyan)]/40 bg-[color:var(--accent-cyan)]/8 text-[color:var(--text-primary)]'
                    : 'border-transparent bg-[color:var(--bg-surface)]/60 text-[color:var(--text-primary)] hover:border-[color:var(--border-muted)]'"
                >
                  <input
                    :checked="bindings[group.key].includes(node.id)"
                    type="checkbox"
                    class="rounded border-[color:var(--border-strong)]"
                    :disabled="!canConfigure"
                    @change="toggleSelection(group.key, node.id)"
                  >
                  <span class="min-w-0 truncate">{{ nodeLabel(node) }}</span>
                </label>
              </div>
              <p
                v-else
                class="rounded-lg border border-dashed border-[color:var(--border-muted)] px-3 py-4 text-center text-xs text-[color:var(--text-muted)]"
              >
                Нет подходящих нод
              </p>
            </div>
          </div>
        </div>

        <div
          v-else-if="activePanel === 'profile'"
          class="space-y-3"
        >
          <div>
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">
              Базовый профиль
            </div>
            <p class="mt-1 text-xs text-[color:var(--text-muted)]">
              Режим runtime, дневные/ночные цели и лимиты форточек.
            </p>
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.controlMode')"
            >
              Режим runtime
              <select
                v-model="climateForm.controlMode"
                class="input-select mt-1 w-full"
                :disabled="!canConfigure"
              >
                <option value="auto">
                  Auto
                </option>
                <option value="semi">
                  Semi
                </option>
                <option value="manual">
                  Manual
                </option>
              </select>
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.intervalMinutes')"
            >
              Интервал климата (мин)
              <input
                v-model.number="climateForm.intervalMinutes"
                data-testid="greenhouse-climate-interval"
                type="number"
                min="1"
                max="1440"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.overrideMinutes')"
            >
              Ручной override (мин)
              <input
                v-model.number="climateForm.overrideMinutes"
                type="number"
                min="5"
                max="120"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.useExternalTelemetry')"
            >
              Внешняя телеметрия
              <select
                v-model="climateForm.useExternalTelemetry"
                class="input-select mt-1 w-full"
                :disabled="!canConfigure"
              >
                <option :value="true">
                  Использовать
                </option>
                <option :value="false">
                  Игнорировать
                </option>
              </select>
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.dayTemp')"
            >
              Температура день
              <input
                v-model.number="climateForm.dayTemp"
                data-testid="greenhouse-climate-day-temp"
                type="number"
                min="10"
                max="35"
                step="0.5"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.nightTemp')"
            >
              Температура ночь
              <input
                v-model.number="climateForm.nightTemp"
                type="number"
                min="10"
                max="35"
                step="0.5"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.dayHumidity')"
            >
              Влажность день
              <input
                v-model.number="climateForm.dayHumidity"
                type="number"
                min="30"
                max="90"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.nightHumidity')"
            >
              Влажность ночь
              <input
                v-model.number="climateForm.nightHumidity"
                type="number"
                min="30"
                max="90"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.ventMinPercent')"
            >
              Min форточек (%)
              <input
                v-model.number="climateForm.ventMinPercent"
                type="number"
                min="0"
                max="100"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.ventMaxPercent')"
            >
              Max форточек (%)
              <input
                v-model.number="climateForm.ventMaxPercent"
                type="number"
                min="0"
                max="100"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.maxVentStepPct')"
            >
              Макс. шаг форточек за tick (%)
              <input
                v-model.number="climateForm.maxVentStepPct"
                data-testid="greenhouse-climate-max-step-pct"
                type="number"
                min="1"
                max="100"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.dayStart')"
            >
              День начинается
              <input
                v-model="climateForm.dayStart"
                type="time"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.nightStart')"
            >
              Ночь начинается
              <input
                v-model="climateForm.nightStart"
                type="time"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.outsideTempMin')"
            >
              Мин. внешняя t°C
              <input
                v-model.number="climateForm.outsideTempMin"
                type="number"
                min="-30"
                max="45"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.outsideTempMax')"
            >
              Макс. внешняя t°C
              <input
                v-model.number="climateForm.outsideTempMax"
                type="number"
                min="-30"
                max="45"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.outsideHumidityMax')"
            >
              Макс. внешняя влажность (%)
              <input
                v-model.number="climateForm.outsideHumidityMax"
                type="number"
                min="20"
                max="100"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)] md:col-span-2"
              :title="fieldHelp('climate.manualOverrideEnabled')"
            >
              Ручной override климата
              <select
                v-model="climateForm.manualOverrideEnabled"
                class="input-select mt-1 w-full"
                :disabled="!canConfigure"
              >
                <option :value="true">
                  Включен
                </option>
                <option :value="false">
                  Выключен
                </option>
              </select>
            </label>
          </div>
        </div>

        <div
          v-else-if="activePanel === 'runtime'"
          class="space-y-3"
        >
          <div>
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">
              Runtime и безопасность
            </div>
            <p class="mt-1 text-xs text-[color:var(--text-muted)]">
              Интервалы команд, deadband и аварийные позиции.
            </p>
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
            <label
              v-for="field in runtimeFields"
              :key="field.key"
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp(field.helpKey)"
            >
              {{ field.label }}
              <input
                :value="numberFieldValue(field.key, field.fallback)"
                type="number"
                :min="field.min"
                :max="field.max"
                :step="field.step ?? 1"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
                @input="setNumberField(field.key, $event)"
              >
            </label>
          </div>
        </div>

        <div
          v-else-if="activePanel === 'vents'"
          class="space-y-3"
        >
          <div>
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">
              Позиции форточек день/ночь
            </div>
            <p class="mt-1 text-xs text-[color:var(--text-muted)]">
              Базовые позиции, cold guard и пороги полного открытия.
            </p>
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
            <label
              v-for="field in ventPositionFields"
              :key="field.key"
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp(field.helpKey)"
            >
              {{ field.label }}
              <input
                :value="numberFieldValue(field.key, field.fallback)"
                type="number"
                :min="field.min"
                :max="field.max"
                :step="field.step ?? 1"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
                @input="setNumberField(field.key, $event)"
              >
            </label>
          </div>
        </div>

        <div
          v-else-if="activePanel === 'weather'"
          class="space-y-3"
        >
          <div>
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">
              Погодные ограничения
            </div>
            <p class="mt-1 text-xs text-[color:var(--text-muted)]">
              Ветер, дождь, перегрев и коэффициенты внешней среды.
            </p>
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
            <label
              v-for="field in weatherFields"
              :key="field.key"
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp(field.helpKey)"
            >
              {{ field.label }}
              <input
                :value="numberFieldValue(field.key, field.fallback)"
                type="number"
                :min="field.min"
                :max="field.max"
                :step="field.step ?? 1"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
                @input="setNumberField(field.key, $event)"
              >
            </label>
          </div>
        </div>

        <div
          v-else
          class="space-y-3"
        >
          <div>
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">
              Ориентация и target policy
            </div>
            <p class="mt-1 text-xs text-[color:var(--text-muted)]">
              Источник целей и геометрия кровли для windward/leeward.
            </p>
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.targetPolicy')"
            >
              Target policy
              <select
                v-model="climateForm.targetPolicy"
                class="input-select mt-1 w-full"
                :disabled="!canConfigure"
              >
                <option value="greenhouse_targets">
                  Greenhouse targets
                </option>
                <option value="primary_zone">
                  Primary zone
                </option>
                <option value="active_zones_strictest">
                  Active zones strictest
                </option>
              </select>
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.primaryZoneId')"
            >
              Primary zone ID
              <input
                :value="nullableNumberFieldValue('primaryZoneId')"
                type="number"
                min="1"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure || climateForm.targetPolicy !== 'primary_zone'"
                @input="setNullableNumberField('primaryZoneId', $event)"
              >
            </label>
            <label
              v-for="field in orientationFields"
              :key="field.key"
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp(field.helpKey)"
            >
              {{ field.label }}
              <input
                :value="nullableNumberFieldValue(field.key)"
                type="number"
                min="0"
                max="359.999"
                step="0.1"
                class="input-field mt-1 w-full"
                :disabled="!canConfigure"
                @input="setNullableNumberField(field.key, $event)"
              >
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="fieldHelp('climate.manualEmergencyOverrideEnabled')"
            >
              Emergency override
              <select
                v-model="climateForm.manualEmergencyOverrideEnabled"
                class="input-select mt-1 w-full"
                :disabled="!canConfigure"
              >
                <option :value="true">
                  Включен
                </option>
                <option :value="false">
                  Выключен
                </option>
              </select>
            </label>
          </div>
        </div>
      </div>

      <footer
        v-if="showApplyButton"
        class="flex flex-col gap-2 border-t border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/40 px-4 py-3 sm:flex-row sm:items-center sm:justify-between md:px-5"
      >
        <p class="text-xs text-[color:var(--text-muted)]">
          Сохраняются profile и bindings. Runtime dispatcher климата пока в разработке.
        </p>
        <button
          type="button"
          data-testid="greenhouse-climate-apply"
          class="btn btn-primary h-9 shrink-0 px-3 text-sm"
          :disabled="!canConfigure || applying"
          @click="$emit('apply')"
        >
          {{ applying ? 'Сохранение...' : applyLabel }}
        </button>
      </footer>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ToggleField } from '@/Components/Shared/Primitives'
import type { ClimateFormState } from '@/composables/zoneAutomationTypes'
import type { AutomationNode as SetupWizardNode } from '@/types/AutomationNode'

interface GreenhouseClimateBindingsState {
  climate_sensors: number[]
  weather_station_sensors: number[]
  vent_actuators: number[]
  fan_actuators: number[]
}

type PanelId = 'bindings' | 'profile' | 'runtime' | 'vents' | 'weather' | 'orientation'

const props = withDefaults(defineProps<{
  availableNodes?: SetupWizardNode[]
  canConfigure?: boolean
  applying?: boolean
  showApplyButton?: boolean
  applyLabel?: string
}>(), {
  availableNodes: () => [],
  canConfigure: true,
  applying: false,
  showApplyButton: false,
  applyLabel: 'Сохранить климат теплицы',
})

const enabled = defineModel<boolean>('enabled', { required: true })
const climateForm = defineModel<ClimateFormState>('climateForm', { required: true })
const bindings = defineModel<GreenhouseClimateBindingsState>('bindings', { required: true })

defineEmits<{
  (e: 'apply'): void
}>()

const activePanel = ref<PanelId>('bindings')

const panels: Array<{ id: PanelId; label: string }> = [
  { id: 'bindings', label: 'Привязка' },
  { id: 'profile', label: 'Профиль' },
  { id: 'runtime', label: 'Runtime' },
  { id: 'vents', label: 'Форточки' },
  { id: 'weather', label: 'Погода' },
  { id: 'orientation', label: 'Ориентация' },
]

const FIELD_HELP: Record<string, string> = {
  'climate.enabled': 'Включает greenhouse-level climate profile и разрешает сохранять bindings климатических нод теплицы.',
  'climate.controlMode': 'Начальный режим runtime: auto управляет полностью, semi оставляет оператору подтверждение, manual не публикует команды.',
  'climate.intervalMinutes': 'Период обновления climate automation для теплицы. Чем меньше интервал, тем чаще пересчитываются климатические действия.',
  'climate.emergencyIntervalSeconds': 'Интервал ускоренного пересчёта при аварийных условиях.',
  'climate.minCommandIntervalSeconds': 'Минимальная пауза между командами actuator-ам.',
  'climate.overrideMinutes': 'Сколько минут действует ручной climate override, если оператор временно вмешался в управление.',
  'climate.useExternalTelemetry': 'Разрешает использовать внешнюю погодную телеметрию при принятии климатических решений.',
  'climate.dayTemp': 'Целевая температура воздуха в дневном режиме теплицы.',
  'climate.nightTemp': 'Целевая температура воздуха в ночном режиме теплицы.',
  'climate.dayHumidity': 'Целевая влажность воздуха в дневном режиме.',
  'climate.nightHumidity': 'Целевая влажность воздуха в ночном режиме.',
  'climate.ventMinPercent': 'Минимальный процент открытия форточек, ниже которого automation не будет опускаться.',
  'climate.ventMaxPercent': 'Верхний лимит открытия форточек для greenhouse climate control.',
  'climate.maxVentStepPct': 'Максимальное изменение положения форточек за один tick AE (`max_step_pct`), 1–100%.',
  'climate.positionDeadbandPercent': 'Мёртвая зона изменения позиции: команды меньше этого процента не отправляются.',
  'climate.minSafeOpenPercent': 'Минимально безопасное открытие, которое учитывается fallback-логикой.',
  'climate.fallbackOpenPercent': 'Положение форточек при stale/недостаточной внутренней телеметрии.',
  'climate.weatherStaleMaxOpenPercent': 'Максимум открытия при устаревшей погодной телеметрии.',
  'climate.emergencyOpenPercent': 'Целевое открытие при перегреве emergency.',
  'climate.dayStart': 'Время начала дневного климатического профиля.',
  'climate.nightStart': 'Время начала ночного климатического профиля.',
  'climate.daylightLuxThreshold': 'Порог освещённости для определения дневного режима.',
  'climate.nightBaseOpenPercent': 'Базовое открытие форточек ночью.',
  'climate.nightMinOpenPercent': 'Минимум открытия ночью.',
  'climate.nightMaxOpenPercent': 'Максимум открытия ночью.',
  'climate.dayBaseOpenPercent': 'Базовое открытие форточек днём.',
  'climate.dayMinOpenPercent': 'Минимум открытия днём.',
  'climate.dayMaxOpenPercent': 'Максимум открытия днём.',
  'climate.tempFullOpenDeltaC': 'Превышение температуры, при котором запрос вентиляции доходит до 100%.',
  'climate.rhFullOpenDeltaPercent': 'Превышение влажности, при котором запрос вентиляции доходит до 100%.',
  'climate.insideTempSpreadAlertC': 'Порог разброса температуры между внутренними датчиками.',
  'climate.insideRhSpreadAlertPercent': 'Порог разброса влажности между внутренними датчиками.',
  'climate.coldGuardMarginC': 'Запас cold guard относительно нижней границы температуры.',
  'climate.coldGuardMaxOpenPercent': 'Максимум открытия при активном cold guard.',
  'climate.outsideHotterGain': 'Коэффициент снижения вентиляции, когда снаружи горячее.',
  'climate.outsideWetterGain': 'Коэффициент снижения вентиляции, когда снаружи влажнее.',
  'climate.outsideTempMin': 'Нижний порог внешней температуры, ниже которого форточки и внешнее проветривание ограничиваются.',
  'climate.outsideTempMax': 'Верхний порог внешней температуры, выше которого climate automation считает наружный воздух слишком горячим.',
  'climate.outsideHumidityMax': 'Максимальная допустимая внешняя влажность для использования наружного воздуха.',
  'climate.windReduceThresholdMs': 'Скорость ветра, с которой начинается ограничение открытия.',
  'climate.windCloseThresholdMs': 'Скорость ветра для storm clamp.',
  'climate.windReduceWindwardMaxPercent': 'Максимум открытия наветренной стороны при сильном ветре.',
  'climate.windReduceLeewardMaxPercent': 'Максимум открытия подветренной стороны при сильном ветре.',
  'climate.windStormWindwardMaxPercent': 'Максимум наветренной стороны при storm clamp.',
  'climate.windStormLeewardMaxPercent': 'Максимум подветренной стороны при storm clamp.',
  'climate.rainWindwardPositionPercent': 'Позиция наветренной стороны при дожде.',
  'climate.rainLeewardPositionPercent': 'Позиция подветренной стороны при дожде.',
  'climate.rainUnknownDirectionMaxPercent': 'Максимум открытия при дожде без направления ветра.',
  'climate.overheatEmergencyTempC': 'Температура emergency-перегрева.',
  'climate.sensorFreshnessSeconds': 'Максимальный возраст telemetry sample для fresh-решений.',
  'climate.greenhouseOrientationDeg': 'Ориентация теплицы в градусах; пусто = неизвестно.',
  'climate.leftRoofNormalDeg': 'Нормаль левой стороны кровли; пусто = вычислять/игнорировать.',
  'climate.rightRoofNormalDeg': 'Нормаль правой стороны кровли; пусто = вычислять/игнорировать.',
  'climate.targetPolicy': 'Источник целевых temp/RH: greenhouse targets, primary zone или strictest по активным зонам.',
  'climate.primaryZoneId': 'ID основной зоны для target_policy=primary_zone.',
  'climate.manualOverrideEnabled': 'Разрешает оператору временно переводить greenhouse climate в ручной override без отключения профиля.',
  'climate.manualEmergencyOverrideEnabled': 'Разрешает аварийный manual override сверх обычного TTL.',
}

function fieldHelp(key: string): string {
  return FIELD_HELP[key] ?? 'Параметр climate profile теплицы.'
}

function nodeLabel(node: SetupWizardNode): string {
  return node.name || node.uid || `Node #${node.id}`
}

function nodeChannels(node: SetupWizardNode): string[] {
  return Array.isArray(node.channels)
    ? node.channels
      .map((channel) => String(channel.channel ?? '').toLowerCase())
      .filter((channel) => channel.length > 0)
    : []
}

function matchesAnyChannel(node: SetupWizardNode, candidates: string[]): boolean {
  const channels = new Set(nodeChannels(node))
  return candidates.some((candidate) => channels.has(candidate))
}

function toggleSelection(key: keyof GreenhouseClimateBindingsState, nodeId: number): void {
  const current = bindings.value[key]
  const exists = current.includes(nodeId)
  if (exists) {
    bindings.value[key] = current.filter((item) => item !== nodeId)
    return
  }

  bindings.value[key] = [...current, nodeId]
}

interface NumericField {
  key: keyof ClimateFormState
  label: string
  helpKey: string
  fallback: number
  min: number
  max: number
  step?: number
}

const runtimeFields: NumericField[] = [
  { key: 'emergencyIntervalSeconds', label: 'Emergency interval (sec)', helpKey: 'climate.emergencyIntervalSeconds', fallback: 60, min: 10, max: 3600 },
  { key: 'minCommandIntervalSeconds', label: 'Min command interval (sec)', helpKey: 'climate.minCommandIntervalSeconds', fallback: 300, min: 0, max: 3600 },
  { key: 'positionDeadbandPercent', label: 'Deadband (%)', helpKey: 'climate.positionDeadbandPercent', fallback: 5, min: 0, max: 50 },
  { key: 'minSafeOpenPercent', label: 'Min safe open (%)', helpKey: 'climate.minSafeOpenPercent', fallback: 15, min: 0, max: 100 },
  { key: 'fallbackOpenPercent', label: 'Fallback open (%)', helpKey: 'climate.fallbackOpenPercent', fallback: 5, min: 0, max: 100 },
  { key: 'weatherStaleMaxOpenPercent', label: 'Weather stale cap (%)', helpKey: 'climate.weatherStaleMaxOpenPercent', fallback: 20, min: 0, max: 100 },
  { key: 'emergencyOpenPercent', label: 'Emergency open (%)', helpKey: 'climate.emergencyOpenPercent', fallback: 100, min: 0, max: 100 },
  { key: 'daylightLuxThreshold', label: 'Daylight threshold (lux)', helpKey: 'climate.daylightLuxThreshold', fallback: 15000, min: 0, max: 200000 },
  { key: 'sensorFreshnessSeconds', label: 'Sensor freshness (sec)', helpKey: 'climate.sensorFreshnessSeconds', fallback: 1200, min: 30, max: 86400 },
]

const ventPositionFields: NumericField[] = [
  { key: 'nightBaseOpenPercent', label: 'Night base (%)', helpKey: 'climate.nightBaseOpenPercent', fallback: 15, min: 0, max: 100 },
  { key: 'nightMinOpenPercent', label: 'Night min (%)', helpKey: 'climate.nightMinOpenPercent', fallback: 15, min: 0, max: 100 },
  { key: 'nightMaxOpenPercent', label: 'Night max (%)', helpKey: 'climate.nightMaxOpenPercent', fallback: 20, min: 0, max: 100 },
  { key: 'dayBaseOpenPercent', label: 'Day base (%)', helpKey: 'climate.dayBaseOpenPercent', fallback: 10, min: 0, max: 100 },
  { key: 'dayMinOpenPercent', label: 'Day min (%)', helpKey: 'climate.dayMinOpenPercent', fallback: 15, min: 0, max: 100 },
  { key: 'dayMaxOpenPercent', label: 'Day max (%)', helpKey: 'climate.dayMaxOpenPercent', fallback: 85, min: 0, max: 100 },
  { key: 'tempFullOpenDeltaC', label: 'Temp full-open delta (°C)', helpKey: 'climate.tempFullOpenDeltaC', fallback: 6, min: 0.1, max: 30, step: 0.1 },
  { key: 'rhFullOpenDeltaPercent', label: 'RH full-open delta (%)', helpKey: 'climate.rhFullOpenDeltaPercent', fallback: 20, min: 1, max: 100 },
  { key: 'insideTempSpreadAlertC', label: 'Inside temp spread alert (°C)', helpKey: 'climate.insideTempSpreadAlertC', fallback: 4, min: 0, max: 30, step: 0.1 },
  { key: 'insideRhSpreadAlertPercent', label: 'Inside RH spread alert (%)', helpKey: 'climate.insideRhSpreadAlertPercent', fallback: 15, min: 0, max: 100 },
  { key: 'coldGuardMarginC', label: 'Cold guard margin (°C)', helpKey: 'climate.coldGuardMarginC', fallback: 1, min: 0, max: 20, step: 0.1 },
  { key: 'coldGuardMaxOpenPercent', label: 'Cold guard max (%)', helpKey: 'climate.coldGuardMaxOpenPercent', fallback: 10, min: 0, max: 100 },
]

const weatherFields: NumericField[] = [
  { key: 'outsideHotterGain', label: 'Outside hotter gain', helpKey: 'climate.outsideHotterGain', fallback: 1, min: 0, max: 10, step: 0.1 },
  { key: 'outsideWetterGain', label: 'Outside wetter gain', helpKey: 'climate.outsideWetterGain', fallback: 1, min: 0, max: 10, step: 0.1 },
  { key: 'windReduceThresholdMs', label: 'Wind reduce (m/s)', helpKey: 'climate.windReduceThresholdMs', fallback: 8, min: 0, max: 100, step: 0.1 },
  { key: 'windCloseThresholdMs', label: 'Wind close (m/s)', helpKey: 'climate.windCloseThresholdMs', fallback: 12, min: 0, max: 100, step: 0.1 },
  { key: 'windReduceWindwardMaxPercent', label: 'Windward reduce max (%)', helpKey: 'climate.windReduceWindwardMaxPercent', fallback: 25, min: 0, max: 100 },
  { key: 'windReduceLeewardMaxPercent', label: 'Leeward reduce max (%)', helpKey: 'climate.windReduceLeewardMaxPercent', fallback: 50, min: 0, max: 100 },
  { key: 'windStormWindwardMaxPercent', label: 'Windward storm max (%)', helpKey: 'climate.windStormWindwardMaxPercent', fallback: 0, min: 0, max: 100 },
  { key: 'windStormLeewardMaxPercent', label: 'Leeward storm max (%)', helpKey: 'climate.windStormLeewardMaxPercent', fallback: 10, min: 0, max: 100 },
  { key: 'rainWindwardPositionPercent', label: 'Rain windward (%)', helpKey: 'climate.rainWindwardPositionPercent', fallback: 0, min: 0, max: 100 },
  { key: 'rainLeewardPositionPercent', label: 'Rain leeward (%)', helpKey: 'climate.rainLeewardPositionPercent', fallback: 10, min: 0, max: 100 },
  { key: 'rainUnknownDirectionMaxPercent', label: 'Rain unknown cap (%)', helpKey: 'climate.rainUnknownDirectionMaxPercent', fallback: 5, min: 0, max: 100 },
  { key: 'overheatEmergencyTempC', label: 'Overheat emergency (°C)', helpKey: 'climate.overheatEmergencyTempC', fallback: 38, min: 20, max: 80, step: 0.1 },
]

const orientationFields: NumericField[] = [
  { key: 'greenhouseOrientationDeg', label: 'Greenhouse orientation (deg)', helpKey: 'climate.greenhouseOrientationDeg', fallback: 0, min: 0, max: 359.999, step: 0.1 },
  { key: 'leftRoofNormalDeg', label: 'Left roof normal (deg)', helpKey: 'climate.leftRoofNormalDeg', fallback: 0, min: 0, max: 359.999, step: 0.1 },
  { key: 'rightRoofNormalDeg', label: 'Right roof normal (deg)', helpKey: 'climate.rightRoofNormalDeg', fallback: 0, min: 0, max: 359.999, step: 0.1 },
]

function numberFieldValue(key: keyof ClimateFormState, fallback: number): number {
  const value = climateForm.value[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function setNumberField(key: keyof ClimateFormState, event: Event): void {
  const input = event.target as HTMLInputElement
  const next = Number(input.value)
  if (!Number.isFinite(next)) {
    return
  }

  (climateForm.value as unknown as Record<string, unknown>)[key] = next
}

function nullableNumberFieldValue(key: keyof ClimateFormState): string {
  const value = climateForm.value[key]
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : ''
}

function setNullableNumberField(key: keyof ClimateFormState, event: Event): void {
  const input = event.target as HTMLInputElement
  const raw = input.value.trim()
  ;(climateForm.value as unknown as Record<string, unknown>)[key] = raw === '' ? null : Number(raw)
}

const climateSensorCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'climate' || matchesAnyChannel(node, ['temp_air', 'humidity_air', 'co2_ppm'])
  })
})

const weatherStationCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'weather' || matchesAnyChannel(node, ['outdoor_temp', 'outdoor_humidity', 'wind_speed', 'rain', 'pressure'])
  })
})

const ventActuatorCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'climate' || matchesAnyChannel(node, ['vent_drive', 'vent_window_pct'])
  })
})

const fanActuatorCandidates = computed(() => {
  return props.availableNodes.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'climate' || matchesAnyChannel(node, ['fan_air'])
  })
})

const bindingGroups = computed(() => [
  { key: 'climate_sensors' as const, label: 'Датчики климата', candidates: climateSensorCandidates.value },
  { key: 'weather_station_sensors' as const, label: 'Метеостанция', candidates: weatherStationCandidates.value },
  { key: 'vent_actuators' as const, label: 'Форточки', candidates: ventActuatorCandidates.value },
  { key: 'fan_actuators' as const, label: 'Вентиляторы', candidates: fanActuatorCandidates.value },
])

const selectedBindingsCount = computed(() => {
  return bindings.value.climate_sensors.length
    + bindings.value.weather_station_sensors.length
    + bindings.value.vent_actuators.length
    + bindings.value.fan_actuators.length
})
</script>

<style scoped>
.greenhouse-climate-configuration :deep(label.text-xs) {
  display: grid;
  gap: 0.32rem;
  line-height: 1.35;
}

.greenhouse-climate-configuration :deep(.input-field),
.greenhouse-climate-configuration :deep(.input-select) {
  height: 2.2rem;
  padding: 0 0.7rem;
  font-size: 0.78rem;
  border-radius: 0.72rem;
}
</style>
