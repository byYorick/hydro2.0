<template>
  <section class="rounded-xl border border-[color:var(--border-muted)] p-4 space-y-4">
    <div class="flex items-center justify-between gap-3">
      <div>
        <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
          Климат теплицы
        </h4>
        <p class="text-xs text-[color:var(--text-dim)] mt-1">
          Автономная система климата теплицы. Runtime dispatcher пока в разработке, но профиль и bindings уже сохраняются.
        </p>
      </div>
      <label class="inline-flex items-center gap-2 text-xs text-[color:var(--text-muted)]">
        <input
          :checked="enabled"
          type="checkbox"
          :disabled="!canConfigure"
          @change="$emit('update:enabled', ($event.target as HTMLInputElement).checked)"
        />
        Управлять климатом
      </label>
    </div>

    <div
      v-if="enabled"
      class="space-y-4"
    >
      <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-4">
        <div>
          <div class="text-sm font-semibold text-[color:var(--text-primary)]">
            Привязка нод
          </div>
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            Сначала выбираются greenhouse climate nodes, затем сохраняется сам профиль.
          </div>
        </div>

        <div class="grid gap-4 lg:grid-cols-2">
          <div class="space-y-2">
            <div class="text-xs font-semibold text-[color:var(--text-muted)]">
              Climate sensors
            </div>
            <label
              v-for="node in climateSensorCandidates"
              :key="`climate-${node.id}`"
              class="flex items-center gap-2 text-sm text-[color:var(--text-primary)]"
            >
              <input
                :checked="bindings.climate_sensors.includes(node.id)"
                type="checkbox"
                :disabled="!canConfigure"
                @change="toggleSelection('climate_sensors', node.id)"
              />
              <span>{{ nodeLabel(node) }}</span>
            </label>
          </div>

          <div class="space-y-2">
            <div class="text-xs font-semibold text-[color:var(--text-muted)]">
              Weather station
            </div>
            <label
              v-for="node in weatherStationCandidates"
              :key="`weather-${node.id}`"
              class="flex items-center gap-2 text-sm text-[color:var(--text-primary)]"
            >
              <input
                :checked="bindings.weather_station_sensors.includes(node.id)"
                type="checkbox"
                :disabled="!canConfigure"
                @change="toggleSelection('weather_station_sensors', node.id)"
              />
              <span>{{ nodeLabel(node) }}</span>
            </label>
          </div>

          <div class="space-y-2">
            <div class="text-xs font-semibold text-[color:var(--text-muted)]">
              Vent actuators
            </div>
            <label
              v-for="node in ventActuatorCandidates"
              :key="`vent-${node.id}`"
              class="flex items-center gap-2 text-sm text-[color:var(--text-primary)]"
            >
              <input
                :checked="bindings.vent_actuators.includes(node.id)"
                type="checkbox"
                :disabled="!canConfigure"
                @change="toggleSelection('vent_actuators', node.id)"
              />
              <span>{{ nodeLabel(node) }}</span>
            </label>
          </div>

          <div class="space-y-2">
            <div class="text-xs font-semibold text-[color:var(--text-muted)]">
              Fan actuators
            </div>
            <label
              v-for="node in fanActuatorCandidates"
              :key="`fan-${node.id}`"
              class="flex items-center gap-2 text-sm text-[color:var(--text-primary)]"
            >
              <input
                :checked="bindings.fan_actuators.includes(node.id)"
                type="checkbox"
                :disabled="!canConfigure"
                @change="toggleSelection('fan_actuators', node.id)"
              />
              <span>{{ nodeLabel(node) }}</span>
            </label>
          </div>
        </div>
      </div>

      <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
        <div class="text-sm font-semibold text-[color:var(--text-primary)]">
          Профиль климата
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <label class="text-xs text-[color:var(--text-muted)]">
            Интервал климата (мин)
            <input
              v-model.number="climateForm.intervalMinutes"
              type="number"
              min="1"
              max="1440"
              class="input-field mt-1 w-full"
              :disabled="!canConfigure"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Ручной override (мин)
            <input
              v-model.number="climateForm.overrideMinutes"
              type="number"
              min="5"
              max="120"
              class="input-field mt-1 w-full"
              :disabled="!canConfigure"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Внешняя телеметрия
            <select
              v-model="climateForm.useExternalTelemetry"
              class="input-select mt-1 w-full"
              :disabled="!canConfigure"
            >
              <option :value="true">Использовать</option>
              <option :value="false">Игнорировать</option>
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
              :disabled="!canConfigure"
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
              :disabled="!canConfigure"
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
              :disabled="!canConfigure"
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
              :disabled="!canConfigure"
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
              :disabled="!canConfigure"
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
              :disabled="!canConfigure"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            День начинается
            <input
              v-model="climateForm.dayStart"
              type="time"
              class="input-field mt-1 w-full"
              :disabled="!canConfigure"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Ночь начинается
            <input
              v-model="climateForm.nightStart"
              type="time"
              class="input-field mt-1 w-full"
              :disabled="!canConfigure"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Мин. внешняя t°C
            <input
              v-model.number="climateForm.outsideTempMin"
              type="number"
              min="-30"
              max="45"
              class="input-field mt-1 w-full"
              :disabled="!canConfigure"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Макс. внешняя t°C
            <input
              v-model.number="climateForm.outsideTempMax"
              type="number"
              min="-30"
              max="45"
              class="input-field mt-1 w-full"
              :disabled="!canConfigure"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Макс. внешняя влажность (%)
            <input
              v-model.number="climateForm.outsideHumidityMax"
              type="number"
              min="20"
              max="100"
              class="input-field mt-1 w-full"
              :disabled="!canConfigure"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)] md:col-span-2">
            Ручной override климата
            <select
              v-model="climateForm.manualOverrideEnabled"
              class="input-select mt-1 w-full"
              :disabled="!canConfigure"
            >
              <option :value="true">Включен</option>
              <option :value="false">Выключен</option>
            </select>
          </label>
        </div>
      </div>

      <div
        v-if="showApplyButton"
        class="flex items-center gap-2"
      >
        <button
          type="button"
          class="btn btn-primary h-9 px-3 text-sm"
          :disabled="!canConfigure || applying"
          @click="$emit('apply')"
        >
          {{ applying ? 'Сохранение...' : applyLabel }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ClimateFormState } from '@/composables/zoneAutomationTypes'
import type { Node as SetupWizardNode } from '@/types/SetupWizard'

interface GreenhouseClimateBindingsState {
  climate_sensors: number[]
  weather_station_sensors: number[]
  vent_actuators: number[]
  fan_actuators: number[]
}

const props = withDefaults(defineProps<{
  enabled: boolean
  climateForm: ClimateFormState
  bindings: GreenhouseClimateBindingsState
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

const emit = defineEmits<{
  (e: 'update:enabled', value: boolean): void
  (e: 'apply'): void
}>()

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
  const current = props.bindings[key]
  const exists = current.includes(nodeId)
  if (exists) {
    props.bindings[key] = current.filter((item) => item !== nodeId)
    return
  }

  props.bindings[key] = [...current, nodeId]
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
</script>
