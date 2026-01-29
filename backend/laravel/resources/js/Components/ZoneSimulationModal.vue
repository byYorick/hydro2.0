<template>
  <div
    v-if="isVisible"
    :class="rootClass"
  >
    <div
      v-if="isModal"
      class="absolute inset-0 bg-[color:var(--bg-main)] opacity-80"
      @click="$emit('close')"
    ></div>
    <div
      :class="panelClass"
      @click.stop="isModal"
    >
      <h2 class="text-lg font-semibold mb-4">
        Симуляция цифрового двойника
      </h2>
      
      <form
        class="space-y-4"
        @submit.prevent="onSubmit"
        @click.stop
      >
        <div>
          <label
            for="simulation-duration-hours"
            class="block text-sm font-medium mb-1"
          >Длительность (часы)</label>
          <p class="text-xs text-[color:var(--text-muted)] mb-1">
            Сколько часов моделировать. Дольше = более долгий прогноз.
          </p>
          <input
            id="simulation-duration-hours"
            v-model.number="form.duration_hours"
            name="duration_hours"
            type="number"
            min="1"
            max="720"
            class="input-field h-9 w-full"
            required
          />
        </div>
        
        <div>
          <label
            for="simulation-step-minutes"
            class="block text-sm font-medium mb-1"
          >Шаг (минуты)</label>
          <p class="text-xs text-[color:var(--text-muted)] mb-1">
            Меньше шаг — выше детализация, но расчет дольше.
          </p>
          <input
            id="simulation-step-minutes"
            v-model.number="form.step_minutes"
            name="step_minutes"
            type="number"
            min="1"
            max="60"
            class="input-field h-9 w-full"
            required
          />
        </div>

        <div>
          <label
            for="simulation-real-duration-minutes"
            class="block text-sm font-medium mb-1"
          >Длительность прогона (минуты)</label>
          <p class="text-xs text-[color:var(--text-muted)] mb-1">
            Опционально: сколько минут длится весь прогон в реальном времени.
          </p>
          <input
            id="simulation-real-duration-minutes"
            v-model.number="form.sim_duration_minutes"
            name="sim_duration_minutes"
            type="number"
            min="1"
            max="10080"
            class="input-field h-9 w-full"
          />
        </div>

        <div class="flex items-start gap-2">
          <input
            id="simulation-full-mode"
            v-model="form.full_simulation"
            name="full_simulation"
            type="checkbox"
            :disabled="form.sim_duration_minutes === null"
            class="mt-1 h-4 w-4 rounded border-[color:var(--border-muted)] bg-transparent text-[color:var(--accent-cyan)] disabled:opacity-40"
          />
          <label
            for="simulation-full-mode"
            class="text-xs text-[color:var(--text-muted)]"
          >
            Полный прогон: создать зону, растение, рецепт и дополнительную ноду, пройти все фазы до отчета.
          </label>
        </div>
        
        <div>
          <label
            for="simulation-recipe-search"
            class="block text-sm font-medium mb-1"
          >Рецепт (необязательно)</label>
          <p class="text-xs text-[color:var(--text-muted)] mb-1">
            Выберите рецепт из базы или оставьте "по умолчанию", чтобы взять рецепт зоны.
          </p>
          <input
            id="simulation-recipe-search"
            v-model="recipeSearch"
            name="recipe_search"
            type="text"
            placeholder="Поиск по названию..."
            class="input-field h-9 w-full mb-2"
          />
          <select
            id="simulation-recipe-select"
            v-model="form.recipe_id"
            name="recipe_id"
            class="input-field h-9 w-full"
          >
            <option :value="null">
              Рецепт зоны (по умолчанию)
            </option>
            <option
              v-for="recipe in recipes"
              :key="recipe.id"
              :value="recipe.id"
            >
              {{ recipe.name }}
            </option>
          </select>
          <div
            v-if="recipesLoading"
            class="text-xs text-[color:var(--text-muted)] mt-1"
          >
            Загрузка рецептов...
          </div>
          <div
            v-else-if="recipesError"
            class="text-xs text-[color:var(--accent-red)] mt-1"
          >
            {{ recipesError }}
          </div>
        </div>
        
        <div class="border-t border-[color:var(--border-muted)] pt-4">
          <div class="text-sm font-medium mb-2">
            Начальные условия (необязательно)
          </div>
          <p class="text-xs text-[color:var(--text-muted)] mb-2">
            Заполните только то, что хотите переопределить. Пустые поля возьмутся из текущих данных.
          </p>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label
                for="simulation-initial-ph"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >pH</label>
              <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
                Обычно 5.5–6.5 для гидропоники.
              </p>
              <input
                id="simulation-initial-ph"
                v-model.number="form.initial_state.ph"
                name="initial_state_ph"
                type="number"
                step="0.0001"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label
                for="simulation-initial-ec"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >EC</label>
              <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
                Электропроводность раствора (мСм/см).
              </p>
              <input
                id="simulation-initial-ec"
                v-model.number="form.initial_state.ec"
                name="initial_state_ec"
                type="number"
                step="0.0001"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label
                for="simulation-initial-temp-air"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >Температура воздуха (°C)</label>
              <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
                Стартовая температура воздуха в зоне.
              </p>
              <input
                id="simulation-initial-temp-air"
                v-model.number="form.initial_state.temp_air"
                name="initial_state_temp_air"
                type="number"
                step="0.0001"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label
                for="simulation-initial-temp-water"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >Температура воды (°C)</label>
              <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
                Температура питательного раствора.
              </p>
              <input
                id="simulation-initial-temp-water"
                v-model.number="form.initial_state.temp_water"
                name="initial_state_temp_water"
                type="number"
                step="0.0001"
                class="input-field h-8 w-full"
              />
            </div>
            <div class="col-span-2">
              <label
                for="simulation-initial-humidity"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >Влажность (%)</label>
              <p class="text-[11px] text-[color:var(--text-dim)] mb-1">
                Относительная влажность воздуха.
              </p>
              <input
                id="simulation-initial-humidity"
                v-model.number="form.initial_state.humidity_air"
                name="initial_state_humidity_air"
                type="number"
                step="0.0001"
                class="input-field h-8 w-full"
              />
            </div>
          </div>
        </div>

        <div class="border-t border-[color:var(--border-muted)] pt-4">
          <div class="text-sm font-medium mb-2">
            Дрифт параметров (node-sim)
          </div>
          <p class="text-xs text-[color:var(--text-muted)] mb-2">
            Задайте скорость изменения в единицах за минуту. Отрицательные значения допустимы.
          </p>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label
                for="simulation-drift-ph"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >Дрифт pH (ед/мин)</label>
              <input
                id="simulation-drift-ph"
                v-model.number="driftPh"
                @input="driftTouched.ph = true"
                name="node_sim_drift_ph"
                type="number"
                step="0.0001"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label
                for="simulation-drift-ec"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >Дрифт EC (мСм/см/мин)</label>
              <input
                id="simulation-drift-ec"
                v-model.number="driftEc"
                @input="driftTouched.ec = true"
                name="node_sim_drift_ec"
                type="number"
                step="0.0001"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label
                for="simulation-drift-temp-air"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >Дрифт температуры воздуха (°C/мин)</label>
              <input
                id="simulation-drift-temp-air"
                v-model.number="driftTempAir"
                @input="driftTouched.temp_air = true"
                name="node_sim_drift_temp_air"
                type="number"
                step="0.0001"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label
                for="simulation-drift-temp-water"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >Дрифт температуры воды (°C/мин)</label>
              <input
                id="simulation-drift-temp-water"
                v-model.number="driftTempWater"
                @input="driftTouched.temp_water = true"
                name="node_sim_drift_temp_water"
                type="number"
                step="0.0001"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label
                for="simulation-drift-humidity"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >Дрифт влажности (%/мин)</label>
              <input
                id="simulation-drift-humidity"
                v-model.number="driftHumidity"
                @input="driftTouched.humidity_air = true"
                name="node_sim_drift_humidity_air"
                type="number"
                step="0.0001"
                class="input-field h-8 w-full"
              />
            </div>
            <div>
              <label
                for="simulation-drift-noise"
                class="block text-xs text-[color:var(--text-muted)] mb-1"
              >Шум дрейфа (ед/мин)</label>
              <input
                id="simulation-drift-noise"
                v-model.number="driftNoise"
                @input="driftTouched.noise = true"
                name="node_sim_drift_noise"
                type="number"
                step="0.0001"
                class="input-field h-8 w-full"
              />
            </div>
          </div>
        </div>
        
        <div
          v-if="isSimulating"
          class="space-y-2"
        >
          <div class="text-xs text-[color:var(--text-muted)]">
            Статус: {{ simulationStatusLabel }}
          </div>
          <div
            v-if="simulationEngineLabel"
            class="text-xs text-[color:var(--text-muted)]"
          >
            Движок: {{ simulationEngineLabel }}
          </div>
          <div
            v-if="simulationCurrentPhaseLabel"
            class="text-xs text-[color:var(--text-muted)]"
          >
            Фаза: {{ simulationCurrentPhaseLabel }}
          </div>
          <div
            v-if="simulationProgressSourceLabel"
            class="text-xs text-[color:var(--text-muted)]"
          >
            Источник прогресса: {{ simulationProgressSourceLabel }}
          </div>
          <div
            v-if="simulationProgressDetails"
            class="text-xs text-[color:var(--text-muted)]"
          >
            {{ simulationProgressDetails }}
          </div>
          <div
            v-if="simulationSimTimeLabel"
            class="text-xs text-[color:var(--text-muted)]"
          >
            {{ simulationSimTimeLabel }}
          </div>
          <div class="relative w-full h-2 bg-[color:var(--border-muted)] rounded-full overflow-hidden">
            <div
              class="relative h-2 bg-[linear-gradient(90deg,var(--accent-cyan),var(--accent-green))] transition-all duration-500"
              :style="{ width: `${simulationProgress}%` }"
            >
              <div class="absolute inset-0 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.2),transparent)] simulation-shimmer"></div>
            </div>
          </div>
          <div
            v-if="simulationActions.length"
            class="rounded-lg border border-[color:var(--border-muted)] p-3"
          >
            <div class="text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
              Последние действия
            </div>
            <ul class="mt-2 space-y-1">
              <li
                v-for="action in simulationActions"
                :key="`${action.kind}-${action.id}`"
                class="flex items-start justify-between gap-3 text-xs text-[color:var(--text-muted)]"
              >
                <span class="flex-1 truncate">
                  {{ action.summary || action.event_type || action.cmd || 'Событие' }}
                </span>
                <span class="whitespace-nowrap text-[11px] text-[color:var(--text-dim)]">
                  {{ formatTimestamp(action.created_at) }}
                </span>
              </li>
            </ul>
          </div>
          <div
            v-if="simulationPidStatuses.length"
            class="rounded-lg border border-[color:var(--border-muted)] p-3"
          >
            <div class="text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
              PID статусы
            </div>
            <div class="mt-2 grid grid-cols-2 gap-3 text-xs text-[color:var(--text-muted)]">
              <div
                v-for="pid in simulationPidStatuses"
                :key="pid.type"
                class="rounded-md bg-[color:var(--bg-surface)] px-2 py-2"
              >
                <div class="text-xs font-semibold text-[color:var(--text-primary)]">
                  {{ pid.type.toUpperCase() }}
                </div>
                <div class="text-[11px] text-[color:var(--text-dim)]">
                  Текущее: {{ formatPidValue(pid.current) }} / Цель: {{ formatPidValue(pid.target) }}
                </div>
                <div class="text-[11px] text-[color:var(--text-dim)]">
                  Выход: {{ formatPidValue(pid.output, 3) }}
                </div>
                <div
                  v-if="pid.zone_state"
                  class="text-[11px] text-[color:var(--text-dim)]"
                >
                  Состояние: {{ pid.zone_state }}
                </div>
                <div
                  v-if="pid.error"
                  class="text-[11px] text-[color:var(--accent-red)]"
                >
                  Ошибка: {{ pid.error }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div
          v-if="simulationDbId"
          class="rounded-lg border border-[color:var(--border-muted)] p-3"
        >
          <div class="flex items-center justify-between gap-2 text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
            <span>Процесс симуляции</span>
            <span
              v-if="simulationEventsLoading"
              class="text-[10px] text-[color:var(--text-dim)]"
            >загрузка…</span>
          </div>
          <div
            v-if="simulationEventsError"
            class="mt-2 text-xs text-[color:var(--accent-red)]"
          >
            {{ simulationEventsError }}
          </div>
          <div
            v-else-if="!simulationEvents.length"
            class="mt-2 text-xs text-[color:var(--text-muted)]"
          >
            Событий пока нет.
          </div>
          <ul
            v-else
            class="mt-3 space-y-3 max-h-64 overflow-y-auto pr-1"
          >
            <li
              v-for="event in simulationEvents"
              :key="event.id"
              class="flex items-start gap-3 text-xs text-[color:var(--text-muted)]"
            >
              <span :class="`mt-1 h-2 w-2 rounded-full ${simulationLevelClass(event.level)}`"></span>
              <div class="flex-1 space-y-1">
                <div class="flex flex-wrap items-center gap-2 text-[11px] text-[color:var(--text-dim)]">
                  <span class="rounded-full border border-[color:var(--border-muted)] px-2 py-0.5">
                    {{ event.service }}
                  </span>
                  <span class="rounded-full border border-[color:var(--border-muted)] px-2 py-0.5">
                    {{ event.stage }}
                  </span>
                  <span class="rounded-full border border-[color:var(--border-muted)] px-2 py-0.5">
                    {{ event.status }}
                  </span>
                </div>
                <div class="text-xs text-[color:var(--text-primary)]">
                  {{ event.message || 'Событие симуляции' }}
                </div>
                <div
                  v-if="formatSimulationPayload(event.payload)"
                  class="text-[11px] text-[color:var(--text-dim)]"
                >
                  {{ formatSimulationPayload(event.payload) }}
                </div>
              </div>
              <span class="whitespace-nowrap text-[11px] text-[color:var(--text-dim)]">
                {{ formatTimestamp(event.occurred_at || event.created_at) }}
              </span>
            </li>
          </ul>
        </div>

        <div
          v-if="simulationReport"
          class="rounded-lg border border-[color:var(--border-muted)] p-3"
        >
          <div class="flex items-center justify-between gap-2 text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
            <span>Отчет симуляции</span>
            <span class="text-[10px] text-[color:var(--text-dim)]">
              {{ simulationReport.status }}
            </span>
          </div>
          <div class="mt-2 grid grid-cols-2 gap-2 text-xs text-[color:var(--text-muted)]">
            <div>Старт: {{ formatDateTime(simulationReport.started_at) }}</div>
            <div>Финиш: {{ formatDateTime(simulationReport.finished_at) }}</div>
          </div>

          <div
            v-if="reportSummaryEntries.length"
            class="mt-3"
          >
            <div class="text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
              Сводка
            </div>
            <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 text-xs text-[color:var(--text-muted)]">
              <div
                v-for="item in reportSummaryEntries"
                :key="`summary-${item.key}`"
                class="rounded-md bg-[color:var(--bg-surface)] px-2 py-2"
              >
                <div class="text-[11px] text-[color:var(--text-dim)]">
                  {{ formatReportKey(item.key) }}
                </div>
                <div class="text-xs text-[color:var(--text-primary)]">
                  {{ formatReportValue(item.value) }}
                </div>
              </div>
            </div>
          </div>

          <div
            v-if="reportPhaseEntries.length"
            class="mt-3"
          >
            <div class="text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
              Фазы
            </div>
            <div class="mt-2 max-h-48 overflow-auto">
              <table class="w-full text-xs text-[color:var(--text-muted)]">
                <thead class="text-[11px] uppercase text-[color:var(--text-dim)]">
                  <tr class="text-left">
                    <th class="py-1">#</th>
                    <th class="py-1">Название</th>
                    <th class="py-1">Старт</th>
                    <th class="py-1">Финиш</th>
                    <th class="py-1">Статус</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="phase in reportPhaseEntries"
                    :key="`phase-${phase.phase_id || phase.phase_index}`"
                    class="border-t border-[color:var(--border-muted)]"
                  >
                    <td class="py-1 pr-2">{{ phase.phase_index ?? '—' }}</td>
                    <td class="py-1 pr-2">{{ phase.name || '—' }}</td>
                    <td class="py-1 pr-2">{{ formatTimestamp(phase.started_at) }}</td>
                    <td class="py-1 pr-2">{{ formatTimestamp(phase.completed_at) }}</td>
                    <td class="py-1">{{ phase.status || '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div
            v-if="reportMetricsEntries.length"
            class="mt-3"
          >
            <div class="text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
              Метрики
            </div>
            <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 text-xs text-[color:var(--text-muted)]">
              <div
                v-for="item in reportMetricsEntries"
                :key="`metric-${item.key}`"
                class="rounded-md bg-[color:var(--bg-surface)] px-2 py-2"
              >
                <div class="text-[11px] text-[color:var(--text-dim)]">
                  {{ formatReportKey(item.key) }}
                </div>
                <div class="text-xs text-[color:var(--text-primary)]">
                  {{ formatReportValue(item.value) }}
                </div>
              </div>
            </div>
          </div>

          <div
            v-if="reportErrors.length"
            class="mt-3 text-xs text-[color:var(--accent-red)]"
          >
            Ошибки отчета: {{ formatReportValue(reportErrors) }}
          </div>
        </div>
        
        <div
          v-if="error"
          class="text-sm text-[color:var(--accent-red)]"
        >
          {{ error }}
        </div>
        
        <div class="flex justify-end gap-2 pt-4 border-t border-[color:var(--border-muted)]">
          <Button
            v-if="isModal"
            type="button"
            variant="secondary"
            @click="$emit('close')"
          >
            Отмена
          </Button>
          <Button
            type="submit"
            :disabled="loading"
          >
            {{ loading ? 'Запуск...' : 'Запустить' }}
          </Button>
        </div>
      </form>
      
      <div
        v-if="results"
        class="mt-6 border-t border-[color:var(--border-muted)] pt-4"
        @click.stop
      >
        <div class="text-sm font-medium mb-3">
          Результаты симуляции
        </div>
        <div class="text-xs text-[color:var(--text-muted)] mb-2">
          Длительность: {{ resultDurationHours }} ч, шаг: {{ resultStepMinutes }} мин
        </div>
        <div class="h-64">
          <ChartBase
            v-if="chartOption"
            :option="chartOption"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onUnmounted } from 'vue'
import { logger } from '@/utils/logger'
import Button from '@/Components/Button.vue'
import ChartBase from '@/Components/ChartBase.vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useLoading } from '@/composables/useLoading'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { useTheme } from '@/composables/useTheme'
import type { EChartsOption } from 'echarts'

interface Props {
  show?: boolean
  mode?: 'modal' | 'page'
  zoneId: number
  defaultRecipeId?: number | null
  initialTelemetry?: {
    ph?: number | null
    ec?: number | null
    temperature?: number | null
    humidity?: number | null
  } | null
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  mode: 'modal',
  defaultRecipeId: null,
  initialTelemetry: null,
})

defineEmits<{
  close: []
}>()

const { showToast } = useToast()
const { api } = useApi(showToast)
const { theme } = useTheme()

const isModal = computed(() => props.mode === 'modal')
const isVisible = computed(() => props.mode === 'page' || props.show)
const rootClass = computed(() => {
  if (isModal.value) {
    return 'fixed inset-0 z-50 flex items-center justify-center'
  }
  return 'w-full'
})
const panelClass = computed(() => {
  if (isModal.value) {
    return 'relative w-full max-w-2xl rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-6 max-h-[90vh] overflow-y-auto'
  }
  return 'w-full rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-6'
})

interface SimulationForm {
  duration_hours: number
  step_minutes: number
  sim_duration_minutes: number | null
  full_simulation: boolean
  recipe_id: number | null
  initial_state: {
    ph: number | null
    ec: number | null
    temp_air: number | null
    temp_water: number | null
    humidity_air: number | null
  }
}

interface SimulationPoint {
  t: number
  ph: number
  ec: number
  temp_air: number
}

interface SimulationResults {
  duration_hours?: number
  step_minutes?: number
  points: SimulationPoint[]
}

interface SimulationAction {
  kind: 'command' | 'event'
  id: number
  summary?: string | null
  cmd?: string | null
  event_type?: string | null
  created_at?: string | null
}

interface SimulationPidStatus {
  type: string
  current?: number | null
  target?: number | null
  output?: number | null
  zone_state?: string | null
  error?: string | null
  updated_at?: string | null
}

interface SimulationEvent {
  id: number
  simulation_id?: number | null
  zone_id?: number | null
  service: string
  stage: string
  status: string
  level?: string | null
  message?: string | null
  payload?: unknown
  occurred_at?: string | null
  created_at?: string | null
}

interface SimulationReport {
  id: number
  simulation_id: number
  zone_id: number
  status: string
  started_at?: string | null
  finished_at?: string | null
  summary_json?: Record<string, unknown> | null
  phases_json?: SimulationReportPhase[] | null
  metrics_json?: Record<string, unknown> | null
  errors_json?: unknown
}

interface SimulationReportPhase {
  phase_id?: number | null
  phase_index?: number | null
  name?: string | null
  started_at?: string | null
  completed_at?: string | null
  status?: string | null
}

interface RecipeOption {
  id: number
  name: string
}

interface RecipeDefaults {
  ph?: number | null
  ec?: number | null
  temp_air?: number | null
  temp_water?: number | null
  humidity_air?: number | null
}

const form = reactive<SimulationForm>({
  duration_hours: 72,
  step_minutes: 10,
  sim_duration_minutes: null,
  full_simulation: true,
  recipe_id: props.defaultRecipeId || null,
  initial_state: {
    ph: null,
    ec: null,
    temp_air: null,
    temp_water: null,
    humidity_air: null,
  },
})

const driftPh = ref<number | null>(null)
const driftEc = ref<number | null>(null)
const driftTempAir = ref<number | null>(null)
const driftTempWater = ref<number | null>(null)
const driftHumidity = ref<number | null>(null)
const driftNoise = ref<number | null>(null)

const { loading, startLoading, stopLoading } = useLoading<boolean>(false)
const error = ref<string | null>(null)
const results = ref<SimulationResults | null>(null)
const recipes = ref<RecipeOption[]>([])
const recipesLoading = ref(false)
const recipesError = ref<string | null>(null)
const recipeSearch = ref('')
let recipeSearchTimer: ReturnType<typeof setTimeout> | null = null
const lastDefaultsRecipeId = ref<number | null>(null)
const recipeDefaultsCache = new Map<number, RecipeDefaults>()
const simulationJobId = ref<string | null>(null)
const simulationStatus = ref<'idle' | 'queued' | 'processing' | 'completed' | 'failed'>('idle')
const simulationProgressValue = ref<number | null>(null)
const simulationElapsedMinutes = ref<number | null>(null)
const simulationRealDurationMinutes = ref<number | null>(null)
const simulationSimNow = ref<string | null>(null)
const simulationEngine = ref<string | null>(null)
const simulationMode = ref<string | null>(null)
const simulationProgressSource = ref<string | null>(null)
const simulationActions = ref<SimulationAction[]>([])
const simulationPidStatuses = ref<SimulationPidStatus[]>([])
const simulationCurrentPhase = ref<string | null>(null)
const simulationDbId = ref<number | null>(null)
const simulationReport = ref<SimulationReport | null>(null)
const simulationEvents = ref<SimulationEvent[]>([])
const simulationEventsLoading = ref(false)
const simulationEventsError = ref<string | null>(null)
const simulationEventsLastId = ref(0)
let simulationEventsSource: EventSource | null = null
let simulationPollTimer: ReturnType<typeof setInterval> | null = null

const driftTouched = reactive({
  ph: false,
  ec: false,
  temp_air: false,
  temp_water: false,
  humidity_air: false,
  noise: false,
})

const DRIFT_RELATIVE_RATES = {
  ph: 0.01,
  ec: 0.01,
  temp_air: 0.002,
  temp_water: 0.002,
  humidity_air: 0.002,
} as const

const roundDrift = (value: number, precision = 3): number => {
  const factor = 10 ** precision
  return Math.round(value * factor) / factor
}

const applyAutoDrift = () => {
  const state = form.initial_state
  const driftMap = {
    ph: driftPh,
    ec: driftEc,
    temp_air: driftTempAir,
    temp_water: driftTempWater,
    humidity_air: driftHumidity,
  } as const

  (Object.keys(DRIFT_RELATIVE_RATES) as Array<keyof typeof DRIFT_RELATIVE_RATES>).forEach((key) => {
    if (driftTouched[key]) return
    const baseValue = state[key]
    if (baseValue === null || baseValue === undefined) {
      driftMap[key].value = null
      return
    }
    driftMap[key].value = roundDrift(baseValue * DRIFT_RELATIVE_RATES[key])
  })

  if (!driftTouched.noise && driftNoise.value === null) {
    const values = Object.values(driftMap)
      .map((refValue) => refValue.value)
      .filter((value): value is number => typeof value === 'number' && !Number.isNaN(value))
    if (values.length) {
      const maxAbs = Math.max(...values.map((value) => Math.abs(value)))
      if (maxAbs > 0) {
        driftNoise.value = roundDrift(maxAbs * 0.1)
      }
    }
  }
}

const applyInitialTelemetry = (telemetry: Props['initialTelemetry']) => {
  if (!telemetry) return
  if (form.initial_state.ph === null && telemetry.ph != null) {
    form.initial_state.ph = telemetry.ph
  }
  if (form.initial_state.ec === null && telemetry.ec != null) {
    form.initial_state.ec = telemetry.ec
  }
  if (form.initial_state.temp_air === null && telemetry.temperature != null) {
    form.initial_state.temp_air = telemetry.temperature
  }
  if (form.initial_state.humidity_air === null && telemetry.humidity != null) {
    form.initial_state.humidity_air = telemetry.humidity
  }
  applyAutoDrift()
}

watch(
  () => props.initialTelemetry,
  (telemetry) => {
    applyInitialTelemetry(telemetry)
  },
  { immediate: true }
)

watch(
  () => form.initial_state,
  () => {
    applyAutoDrift()
  },
  { deep: true }
)

watch(
  () => props.defaultRecipeId,
  (recipeId) => {
    if (recipeId && form.recipe_id === null) {
      form.recipe_id = recipeId
    }
  }
)

const resolveCssColor = (variable: string, fallback: string): string => {
  if (typeof window === 'undefined') {
    return fallback
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

const chartPalette = computed(() => {
  theme.value
  return {
    text: resolveCssColor('--text-muted', '#9ca3af'),
    textStrong: resolveCssColor('--text-primary', '#e5e7eb'),
    grid: resolveCssColor('--border-muted', '#374151'),
    ph: resolveCssColor('--accent-cyan', '#3b82f6'),
    ec: resolveCssColor('--accent-green', '#10b981'),
    temp: resolveCssColor('--accent-amber', '#f59e0b'),
  }
})

const chartOption = computed<EChartsOption | null>(() => {
  if (!results.value?.points) return null
  
  const points = results.value.points
  const phData = points.map(p => [p.t, p.ph])
  const ecData = points.map(p => [p.t, p.ec])
  const tempData = points.map(p => [p.t, p.temp_air])
  
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    legend: {
      data: ['pH', 'EC', 'Температура воздуха'],
      textStyle: { color: chartPalette.value.textStrong },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true,
    },
    xAxis: {
      type: 'value',
      name: 'Время (ч)',
      nameTextStyle: { color: chartPalette.value.text },
      axisLabel: { color: chartPalette.value.text },
      splitLine: { lineStyle: { color: chartPalette.value.grid } },
    },
    yAxis: [
      {
        type: 'value',
        name: 'pH / EC',
        nameTextStyle: { color: chartPalette.value.text },
        axisLabel: { color: chartPalette.value.text },
        splitLine: { lineStyle: { color: chartPalette.value.grid } },
      },
      {
        type: 'value',
        name: 'Температура (°C)',
        nameTextStyle: { color: chartPalette.value.text },
        axisLabel: { color: chartPalette.value.text },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'pH',
        type: 'line',
        data: phData,
        smooth: true,
        lineStyle: { color: chartPalette.value.ph },
        itemStyle: { color: chartPalette.value.ph },
      },
      {
        name: 'EC',
        type: 'line',
        data: ecData,
        smooth: true,
        lineStyle: { color: chartPalette.value.ec },
        itemStyle: { color: chartPalette.value.ec },
      },
      {
        name: 'Температура воздуха',
        type: 'line',
        yAxisIndex: 1,
        data: tempData,
        smooth: true,
        lineStyle: { color: chartPalette.value.temp },
        itemStyle: { color: chartPalette.value.temp },
      },
    ],
  }
})

const simulationProgress = computed(() => {
  if (simulationProgressValue.value !== null) {
    return Math.round(simulationProgressValue.value * 100)
  }
  switch (simulationStatus.value) {
    case 'queued':
      return 20
    case 'processing':
      return 60
    case 'completed':
      return 100
    case 'failed':
      return 100
    default:
      return 0
  }
})

const simulationProgressDetails = computed(() => {
  if (simulationProgressValue.value === null) return null
  const percent = Math.round(simulationProgressValue.value * 100)
  if (simulationElapsedMinutes.value !== null && simulationRealDurationMinutes.value !== null) {
    const remaining = Math.max(
      0,
      Math.round((simulationRealDurationMinutes.value - simulationElapsedMinutes.value) * 100) / 100
    )
    return `Прогресс: ${percent}% (${simulationElapsedMinutes.value} / ${simulationRealDurationMinutes.value} мин, осталось ${remaining} мин)`
  }
  return `Прогресс: ${percent}%`
})

const simulationEngineLabel = computed(() => {
  if (!simulationEngine.value && !simulationMode.value) return null
  const engine = simulationEngine.value ? simulationEngine.value.replace('_', ' ') : 'unknown'
  return simulationMode.value ? `${engine} (${simulationMode.value})` : engine
})

const simulationProgressSourceLabel = computed(() => {
  if (!simulationProgressSource.value) return null
  if (simulationProgressSource.value === 'actions') return 'действия'
  if (simulationProgressSource.value === 'timer') return 'таймер'
  return simulationProgressSource.value
})

const simulationCurrentPhaseLabel = computed(() => {
  if (!simulationCurrentPhase.value) return null
  return String(simulationCurrentPhase.value)
})

const simulationSimTimeLabel = computed(() => {
  if (!simulationSimNow.value) return null
  const parsed = new Date(simulationSimNow.value)
  if (Number.isNaN(parsed.getTime())) {
    return `Сим-время: ${simulationSimNow.value}`
  }
  return `Сим-время: ${parsed.toLocaleString()}`
})

const simulationStatusLabel = computed(() => {
  switch (simulationStatus.value) {
    case 'queued':
      return 'В очереди'
    case 'processing':
      return 'Выполняется'
    case 'completed':
      return 'Завершено'
    case 'failed':
      return 'Ошибка'
    default:
      return ''
  }
})

const reportSummaryEntries = computed(() => {
  const summary = simulationReport.value?.summary_json
  if (!summary || typeof summary !== 'object') return []
  return Object.entries(summary)
    .map(([key, value]) => ({ key, value }))
    .filter((entry) => entry.value !== null && entry.value !== undefined && entry.value !== '')
})

const reportPhaseEntries = computed<SimulationReportPhase[]>(() => {
  const phases = simulationReport.value?.phases_json
  if (!Array.isArray(phases)) return []
  return phases as SimulationReportPhase[]
})

const reportMetricsEntries = computed(() => {
  const metrics = simulationReport.value?.metrics_json
  if (!metrics || typeof metrics !== 'object') return []
  return Object.entries(metrics)
    .map(([key, value]) => ({ key, value }))
    .filter((entry) => entry.value !== null && entry.value !== undefined && entry.value !== '')
})

const reportErrors = computed(() => {
  const errors = simulationReport.value?.errors_json
  if (!errors) return []
  if (Array.isArray(errors)) return errors
  return [errors]
})

const isSimulating = computed(() => {
  return simulationStatus.value === 'queued' || simulationStatus.value === 'processing' || loading.value
})

const resultDurationHours = computed(() => {
  return results.value?.duration_hours ?? form.duration_hours
})

const resultStepMinutes = computed(() => {
  return results.value?.step_minutes ?? form.step_minutes
})

function toNumberOrNull(value: unknown): number | null {
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

function extractRecipeDefaults(recipe: any): RecipeDefaults | null {
  const phases = Array.isArray(recipe?.phases) ? recipe.phases : []
  if (phases.length === 0) return null
  const sorted = [...phases].sort((a, b) => (a.phase_index ?? 0) - (b.phase_index ?? 0))
  const phase = sorted[0]

  return {
    ph: toNumberOrNull(
      phase?.ph_target ?? phase?.ph_min ?? phase?.ph_max ?? phase?.targets?.ph?.min ?? phase?.targets?.ph?.max
    ),
    ec: toNumberOrNull(
      phase?.ec_target ?? phase?.ec_min ?? phase?.ec_max ?? phase?.targets?.ec?.min ?? phase?.targets?.ec?.max
    ),
    temp_air: toNumberOrNull(
      phase?.temp_air_target ?? phase?.targets?.climate?.temperature?.target ?? phase?.targets?.climate?.temperature
    ),
    temp_water: toNumberOrNull(
      phase?.temp_water_target ?? phase?.extensions?.temp_water_target ?? phase?.extensions?.temp_water
    ),
    humidity_air: toNumberOrNull(
      phase?.humidity_target ?? phase?.targets?.climate?.humidity?.target ?? phase?.targets?.climate?.humidity
    ),
  }
}

function applyRecipeDefaults(defaults: RecipeDefaults | null): void {
  if (!defaults) return
  if (form.initial_state.ph === null && defaults.ph !== null && defaults.ph !== undefined) {
    form.initial_state.ph = defaults.ph
  }
  if (form.initial_state.ec === null && defaults.ec !== null && defaults.ec !== undefined) {
    form.initial_state.ec = defaults.ec
  }
  if (form.initial_state.temp_air === null && defaults.temp_air !== null && defaults.temp_air !== undefined) {
    form.initial_state.temp_air = defaults.temp_air
  }
  if (form.initial_state.temp_water === null && defaults.temp_water !== null && defaults.temp_water !== undefined) {
    form.initial_state.temp_water = defaults.temp_water
  }
  if (form.initial_state.humidity_air === null && defaults.humidity_air !== null && defaults.humidity_air !== undefined) {
    form.initial_state.humidity_air = defaults.humidity_air
  }
}

function addRecipeIfMissing(recipe: RecipeOption): void {
  if (!recipes.value.find((item) => item.id === recipe.id)) {
    recipes.value.push(recipe)
  }
}

async function ensureDefaultRecipe(): Promise<void> {
  if (!props.defaultRecipeId) return
  if (recipes.value.find((item) => item.id === props.defaultRecipeId)) return

  try {
    const response = await api.get<{ status: string; data?: { id: number; name: string } }>(
      `/recipes/${props.defaultRecipeId}`
    )
    const data = response.data?.data
    if (data?.id && data?.name) {
      addRecipeIfMissing({ id: data.id, name: data.name })
    }
  } catch (err) {
    logger.debug('[ZoneSimulationModal] Failed to load default recipe', err)
  }
}

async function loadRecipes(search?: string): Promise<void> {
  recipesLoading.value = true
  recipesError.value = null
  try {
    const response = await api.get<{ status: string; data?: { data?: RecipeOption[] } }>(
      '/recipes',
      {
        params: search ? { search } : {},
      }
    )
    const items = response.data?.data?.data || []
    recipes.value = items.map((item) => ({
      id: item.id,
      name: item.name,
    }))
    await ensureDefaultRecipe()
  } catch (err) {
    logger.error('[ZoneSimulationModal] Failed to load recipes', err)
    recipesError.value = 'Не удалось загрузить список рецептов'
  } finally {
    recipesLoading.value = false
  }
}

async function loadRecipeDefaults(recipeId: number): Promise<void> {
  if (recipeDefaultsCache.has(recipeId)) {
    applyRecipeDefaults(recipeDefaultsCache.get(recipeId) || null)
    return
  }

  try {
    const response = await api.get<{ status: string; data?: any }>(`/recipes/${recipeId}`)
    const data = response.data?.data
    const defaults = extractRecipeDefaults(data)
    if (defaults) {
      recipeDefaultsCache.set(recipeId, defaults)
    }
    applyRecipeDefaults(defaults)
  } catch (err) {
    logger.debug('[ZoneSimulationModal] Failed to load recipe defaults', err)
  }
}

const effectiveRecipeId = computed(() => form.recipe_id ?? props.defaultRecipeId ?? null)

function normalizeSimulationResult(payload: any): SimulationResults | null {
  if (!payload || typeof payload !== 'object') return null
  if (Array.isArray(payload.points)) {
    return payload as SimulationResults
  }
  if (payload.data && Array.isArray(payload.data.points)) {
    return payload.data as SimulationResults
  }
  if (payload.result && Array.isArray(payload.result.points)) {
    return payload.result as SimulationResults
  }
  if (payload.result?.data && Array.isArray(payload.result.data.points)) {
    return payload.result.data as SimulationResults
  }
  return null
}

function clearSimulationPolling(): void {
  if (simulationPollTimer) {
    clearInterval(simulationPollTimer)
    simulationPollTimer = null
  }
}

function clampProgress(value: number): number {
  if (value < 0) return 0
  if (value > 1) return 1
  return value
}

function formatTimestamp(value?: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleTimeString()
}

function formatDateTime(value?: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString()
}

function formatPidValue(value?: number | null, decimals = 2): string {
  if (value === null || value === undefined) return '—'
  return Number(value).toFixed(decimals)
}

function formatSimulationPayload(payload: unknown): string | null {
  if (!payload) return null
  if (typeof payload === 'string') {
    return payload.length > 160 ? `${payload.slice(0, 160)}…` : payload
  }
  try {
    const serialized = JSON.stringify(payload)
    return serialized.length > 160 ? `${serialized.slice(0, 160)}…` : serialized
  } catch {
    return null
  }
}

function formatReportKey(key: string): string {
  return key.replace(/_/g, ' ')
}

function formatReportValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return String(value)
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function simulationLevelClass(level?: string | null): string {
  switch (level) {
    case 'error':
      return 'bg-[color:var(--accent-red)]'
    case 'warning':
      return 'bg-[color:var(--accent-amber)]'
    default:
      return 'bg-[color:var(--accent-green)]'
  }
}

function resetSimulationEvents(): void {
  simulationDbId.value = null
  simulationEvents.value = []
  simulationEventsError.value = null
  simulationEventsLoading.value = false
  simulationEventsLastId.value = 0
  stopSimulationEventStream()
}

function stopSimulationEventStream(): void {
  if (simulationEventsSource) {
    simulationEventsSource.close()
    simulationEventsSource = null
  }
}

function appendSimulationEvent(event: SimulationEvent): void {
  if (simulationEvents.value.some((item) => item.id === event.id)) {
    return
  }
  simulationEvents.value.push(event)
  simulationEvents.value.sort((a, b) => {
    const aTime = a.occurred_at || a.created_at || ''
    const bTime = b.occurred_at || b.created_at || ''
    if (aTime === bTime) {
      return a.id - b.id
    }
    return aTime < bTime ? -1 : 1
  })
  simulationEventsLastId.value = Math.max(simulationEventsLastId.value, event.id)
  if (simulationEvents.value.length > 200) {
    simulationEvents.value = simulationEvents.value.slice(-200)
  }
}

async function loadSimulationEvents(simulationId: number): Promise<void> {
  simulationEventsLoading.value = true
  simulationEventsError.value = null
  try {
    const response = await api.get<{ status: string; data?: SimulationEvent[]; meta?: any }>(
      `/simulations/${simulationId}/events`,
      { params: { order: 'asc', limit: 200 } }
    )
    const items = Array.isArray(response.data?.data) ? response.data?.data : []
    simulationEvents.value = items
    const lastId = response.data?.meta?.last_id
    if (typeof lastId === 'number') {
      simulationEventsLastId.value = lastId
    } else if (items.length) {
      simulationEventsLastId.value = Math.max(...items.map((item) => item.id))
    }
  } catch (err) {
    logger.debug('[ZoneSimulationModal] Failed to load simulation events', err)
    simulationEventsError.value = 'Не удалось загрузить события симуляции'
  } finally {
    simulationEventsLoading.value = false
  }
}

function startSimulationEventStream(simulationId: number): void {
  stopSimulationEventStream()
  if (typeof window === 'undefined') return

  const params = new URLSearchParams()
  if (simulationEventsLastId.value > 0) {
    params.set('last_id', String(simulationEventsLastId.value))
  }
  const url = `/api/simulations/${simulationId}/events/stream?${params.toString()}`
  const source = new EventSource(url)
  simulationEventsSource = source

  source.addEventListener('simulation_event', (event) => {
    try {
      const data = JSON.parse((event as MessageEvent).data)
      if (data && typeof data.id === 'number') {
        appendSimulationEvent(data as SimulationEvent)
      }
    } catch (err) {
      logger.debug('[ZoneSimulationModal] Failed to parse simulation event', err)
    }
  })

  source.addEventListener('close', () => {
    stopSimulationEventStream()
  })

  source.addEventListener('error', () => {
    stopSimulationEventStream()
  })
}

async function pollSimulationStatus(jobId: string): Promise<void> {
  try {
    const response = await api.get<{ status: string; data?: any }>(`/simulations/${jobId}`)
    const data = response.data?.data
    if (!data) return

    const status = data.status as typeof simulationStatus.value | undefined
    if (status) {
      simulationStatus.value = status
    }

    const parsedSimId = Number(data.simulation_id)
    if (Number.isFinite(parsedSimId) && parsedSimId > 0) {
      if (simulationDbId.value !== parsedSimId) {
        simulationDbId.value = parsedSimId
        simulationEventsLastId.value = 0
        loadSimulationEvents(parsedSimId)
        startSimulationEventStream(parsedSimId)
      } else if (!simulationEvents.value.length && !simulationEventsLoading.value) {
        loadSimulationEvents(parsedSimId)
      }
    }

    if (data.simulation && typeof data.simulation === 'object') {
      simulationEngine.value = data.simulation.engine ?? null
      simulationMode.value = data.simulation.mode ?? null
    }
    simulationProgressSource.value = typeof data.progress_source === 'string' ? data.progress_source : null
    simulationActions.value = Array.isArray(data.actions) ? data.actions : []
    simulationPidStatuses.value = Array.isArray(data.pid_statuses) ? data.pid_statuses : []
    simulationCurrentPhase.value = data.current_phase ? String(data.current_phase) : null
    if (data.report && typeof data.report === 'object') {
      simulationReport.value = data.report as SimulationReport
    } else {
      simulationReport.value = null
    }

    if (typeof data.progress === 'number' && Number.isFinite(data.progress)) {
      simulationProgressValue.value = clampProgress(data.progress)
    } else {
      simulationProgressValue.value = null
    }
    if (typeof data.elapsed_minutes === 'number' && Number.isFinite(data.elapsed_minutes)) {
      simulationElapsedMinutes.value = Math.round(data.elapsed_minutes * 100) / 100
    } else {
      simulationElapsedMinutes.value = null
    }
    if (typeof data.real_duration_minutes === 'number' && Number.isFinite(data.real_duration_minutes)) {
      simulationRealDurationMinutes.value = Math.round(data.real_duration_minutes * 100) / 100
    } else {
      simulationRealDurationMinutes.value = null
    }
    if (typeof data.sim_now === 'string') {
      simulationSimNow.value = data.sim_now
    } else {
      simulationSimNow.value = null
    }

    if (status === 'completed') {
      const parsed = normalizeSimulationResult(data.result)
      if (parsed) {
        results.value = parsed
      }
      stopLoading()
      stopSimulationEventStream()
      clearSimulationPolling()
      return
    }

    if (status === 'failed') {
      error.value = data.error || 'Симуляция завершилась с ошибкой'
      stopLoading()
      stopSimulationEventStream()
      clearSimulationPolling()
    }
  } catch (err) {
    logger.debug('[ZoneSimulationModal] Simulation status poll failed', err)
  }
}

function startSimulationPolling(jobId: string): void {
  clearSimulationPolling()
  pollSimulationStatus(jobId)
  simulationPollTimer = setInterval(() => {
    pollSimulationStatus(jobId)
  }, 2000)
}

watch(
  () => props.show,
  (isOpen) => {
    if (isOpen) {
      loadRecipes(recipeSearch.value.trim())
      if (effectiveRecipeId.value) {
        loadRecipeDefaults(effectiveRecipeId.value)
      }
      driftPh.value = null
      driftEc.value = null
      driftTempAir.value = null
      driftTempWater.value = null
      driftHumidity.value = null
      driftNoise.value = null
      driftTouched.ph = false
      driftTouched.ec = false
      driftTouched.temp_air = false
      driftTouched.temp_water = false
      driftTouched.humidity_air = false
      driftTouched.noise = false
      applyAutoDrift()
    } else {
      clearSimulationPolling()
      simulationProgressValue.value = null
      simulationElapsedMinutes.value = null
      simulationRealDurationMinutes.value = null
      simulationSimNow.value = null
      simulationEngine.value = null
      simulationMode.value = null
      simulationProgressSource.value = null
      simulationActions.value = []
      simulationPidStatuses.value = []
      simulationCurrentPhase.value = null
      simulationReport.value = null
      resetSimulationEvents()
    }
  }
)

watch(recipeSearch, (value) => {
  if (!props.show) return
  if (recipeSearchTimer) {
    clearTimeout(recipeSearchTimer)
  }
  recipeSearchTimer = setTimeout(() => {
    loadRecipes(value.trim())
  }, 300)
})

watch(
  () => [props.show, effectiveRecipeId.value] as const,
  ([isOpen, recipeId]) => {
    if (!isOpen || !recipeId) return
    if (lastDefaultsRecipeId.value === recipeId) return
    lastDefaultsRecipeId.value = recipeId
    loadRecipeDefaults(recipeId)
  }
)

onUnmounted(() => {
  clearSimulationPolling()
  simulationProgressValue.value = null
  simulationElapsedMinutes.value = null
  simulationRealDurationMinutes.value = null
  simulationSimNow.value = null
  simulationEngine.value = null
  simulationMode.value = null
  simulationProgressSource.value = null
  simulationActions.value = []
  simulationPidStatuses.value = []
  simulationCurrentPhase.value = null
  simulationReport.value = null
  resetSimulationEvents()
})

async function onSubmit(): Promise<void> {
  startLoading()
  error.value = null
  results.value = null
  simulationJobId.value = null
  simulationStatus.value = 'queued'
  simulationProgressValue.value = null
  simulationElapsedMinutes.value = null
  simulationRealDurationMinutes.value = null
  simulationSimNow.value = null
  simulationEngine.value = null
  simulationMode.value = null
  simulationProgressSource.value = null
  simulationActions.value = []
  simulationPidStatuses.value = []
  simulationCurrentPhase.value = null
  simulationReport.value = null
  resetSimulationEvents()
  
  try {
    interface SimulationPayload {
      duration_hours: number
      step_minutes: number
      sim_duration_minutes?: number
      full_simulation?: boolean
      recipe_id?: number
      initial_state?: Partial<SimulationForm['initial_state']>
      node_sim?: {
        drift_per_minute?: Record<string, number>
        drift_noise_per_minute?: number
      }
    }
    
    const payload: SimulationPayload = {
      duration_hours: form.duration_hours,
      step_minutes: form.step_minutes,
    }

    if (form.sim_duration_minutes !== null) {
      payload.sim_duration_minutes = form.sim_duration_minutes
    }

    if (form.full_simulation && form.sim_duration_minutes !== null) {
      payload.full_simulation = true
    }
    
    if (form.recipe_id) {
      payload.recipe_id = form.recipe_id
    }
    
    // Фильтруем initial_state, убирая null значения
    const initialState: Partial<SimulationForm['initial_state']> = {}
    if (form.initial_state.ph !== null) initialState.ph = form.initial_state.ph
    if (form.initial_state.ec !== null) initialState.ec = form.initial_state.ec
    if (form.initial_state.temp_air !== null) initialState.temp_air = form.initial_state.temp_air
    if (form.initial_state.temp_water !== null) initialState.temp_water = form.initial_state.temp_water
    if (form.initial_state.humidity_air !== null) initialState.humidity_air = form.initial_state.humidity_air
    
    if (Object.keys(initialState).length > 0) {
      payload.initial_state = initialState
    }

    const driftPerMinute: Record<string, number> = {}
    if (driftPh.value !== null) driftPerMinute.ph = driftPh.value
    if (driftEc.value !== null) driftPerMinute.ec = driftEc.value
    if (driftTempAir.value !== null) driftPerMinute.temp_air = driftTempAir.value
    if (driftTempWater.value !== null) driftPerMinute.temp_water = driftTempWater.value
    if (driftHumidity.value !== null) driftPerMinute.humidity_air = driftHumidity.value

    const nodeSimPayload: SimulationPayload['node_sim'] = {}
    if (Object.keys(driftPerMinute).length > 0) {
      nodeSimPayload.drift_per_minute = driftPerMinute
    }
    if (driftNoise.value !== null) {
      nodeSimPayload.drift_noise_per_minute = driftNoise.value
    }
    if (Object.keys(nodeSimPayload).length > 0) {
      payload.node_sim = nodeSimPayload
    }
    
    const response = await api.post<{ status: string; data?: any }>(
      `/zones/${props.zoneId}/simulate`,
      payload
    )
    
    const responseData = response.data?.data
    if (response.data?.status === 'ok' && responseData) {
      if (responseData.job_id) {
        simulationJobId.value = responseData.job_id
        simulationStatus.value = responseData.status || 'queued'
        startSimulationPolling(responseData.job_id)
        showToast('Симуляция поставлена в очередь', 'info', TOAST_TIMEOUT.NORMAL)
        return
      }

      const parsed = normalizeSimulationResult(responseData)
      if (parsed) {
        results.value = parsed
        simulationStatus.value = 'completed'
        showToast('Симуляция успешно завершена', 'success', TOAST_TIMEOUT.NORMAL)
      } else {
        error.value = 'Неожиданный формат ответа'
        simulationStatus.value = 'failed'
      }
    } else {
      error.value = 'Неожиданный формат ответа'
      simulationStatus.value = 'failed'
    }
  } catch (err) {
    logger.error('[ZoneSimulationModal] Simulation error:', err)
    const errorMsg = err instanceof Error ? err.message : 'Не удалось запустить симуляцию'
    error.value = errorMsg
    simulationStatus.value = 'failed'
  } finally {
    if (simulationStatus.value !== 'queued' && simulationStatus.value !== 'processing') {
      stopLoading()
    }
  }
}
</script>

<style scoped>
@keyframes simulation-shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

.simulation-shimmer {
  animation: simulation-shimmer 1.6s infinite;
}
</style>
