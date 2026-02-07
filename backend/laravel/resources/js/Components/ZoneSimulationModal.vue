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
        <ZoneSimulationFormFields
          v-model:form="form"
          v-model:recipe-search="recipeSearch"
          v-model:drift-ph="driftPh"
          v-model:drift-ec="driftEc"
          v-model:drift-temp-air="driftTempAir"
          v-model:drift-temp-water="driftTempWater"
          v-model:drift-humidity="driftHumidity"
          v-model:drift-noise="driftNoise"
          :recipes="recipes"
          :recipes-loading="recipesLoading"
          :recipes-error="recipesError"
          @mark-drift-touched="markDriftTouched"
          @apply-aggressive-drift="applyAggressiveDrift"
          @reset-drift-values="resetDriftValues"
        />
        
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
            ref="simulationEventsListRef"
            class="mt-3 space-y-3 max-h-64 overflow-y-auto pr-1"
            @scroll="onSimulationEventsScroll"
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
                    <th class="py-1">
                      #
                    </th>
                    <th class="py-1">
                      Название
                    </th>
                    <th class="py-1">
                      Старт
                    </th>
                    <th class="py-1">
                      Финиш
                    </th>
                    <th class="py-1">
                      Статус
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="phase in reportPhaseEntries"
                    :key="`phase-${phase.phase_id || phase.phase_index}`"
                    class="border-t border-[color:var(--border-muted)]"
                  >
                    <td class="py-1 pr-2">
                      {{ phase.phase_index ?? '—' }}
                    </td>
                    <td class="py-1 pr-2">
                      {{ phase.name || '—' }}
                    </td>
                    <td class="py-1 pr-2">
                      {{ formatTimestamp(phase.started_at) }}
                    </td>
                    <td class="py-1 pr-2">
                      {{ formatTimestamp(phase.completed_at) }}
                    </td>
                    <td class="py-1">
                      {{ phase.status || '—' }}
                    </td>
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
import { ref, reactive, computed, toRef } from 'vue'
import { logger } from '@/utils/logger'
import Button from '@/Components/Button.vue'
import ChartBase from '@/Components/ChartBase.vue'
import ZoneSimulationFormFields from '@/Components/ZoneSimulationFormFields.vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useLoading } from '@/composables/useLoading'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { useTheme } from '@/composables/useTheme'
import {
  useSimulationPresentation,
  type SimulationReportPhase,
} from '@/composables/useSimulationPresentation'
import { useSimulationDrift } from '@/composables/useSimulationDrift'
import { useSimulationChart } from '@/composables/useSimulationChart'
import {
  useSimulationEventFeed,
} from '@/composables/useSimulationEventFeed'
import { useSimulationInitialTelemetry } from '@/composables/useSimulationInitialTelemetry'
import { useSimulationLifecycle } from '@/composables/useSimulationLifecycle'
import { useSimulationRuntimeState } from '@/composables/useSimulationRuntimeState'
import {
  useSimulationSubmit,
  type SimulationSubmitForm,
  type SimulationSubmitDrift,
} from '@/composables/useSimulationSubmit'
import { useSimulationRecipes } from '@/composables/useSimulationRecipes'
import { useSimulationPolling } from '@/composables/useSimulationPolling'
import {
  formatDateTime,
  formatPidValue,
  formatReportKey,
  formatReportValue,
  formatSimulationPayload,
  formatTimestamp,
  simulationLevelClass,
} from '@/utils/simulationFormatters'
import {
  normalizeSimulationResult,
  type SimulationResults,
} from '@/utils/simulationResultParser'

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
  activeSimulationId?: number | null
  activeSimulationStatus?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  mode: 'modal',
  defaultRecipeId: null,
  initialTelemetry: null,
  activeSimulationId: null,
  activeSimulationStatus: null,
})

defineEmits<{
  close: []
}>()

const { showToast } = useToast()
const { api } = useApi(showToast)
const { theme } = useTheme()
const { submitZoneSimulation } = useSimulationSubmit(api)

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

type SimulationForm = SimulationSubmitForm

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

const {
  driftPh,
  driftEc,
  driftTempAir,
  driftTempWater,
  driftHumidity,
  driftNoise,
  markDriftTouched,
  applyAutoDrift,
  applyAggressiveDrift,
  resetDriftValues,
} = useSimulationDrift(form.initial_state)

const { loading, startLoading, stopLoading } = useLoading<boolean>(false)
const error = ref<string | null>(null)
const results = ref<SimulationResults | null>(null)
const {
  recipes,
  recipesLoading,
  recipesError,
  recipeSearch,
  handleOpen: handleRecipesOpen,
} = useSimulationRecipes({
  api,
  isOpen: isVisible,
  defaultRecipeId: toRef(props, 'defaultRecipeId'),
  selectedRecipeId: toRef(form, 'recipe_id'),
  initialState: form.initial_state,
})
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
const simulationReport = ref<SimulationReport | null>(null)
const {
  simulationDbId,
  simulationEvents,
  simulationEventsLoading,
  simulationEventsError,
  simulationEventsListRef,
  onSimulationEventsScroll,
  loadSimulationEvents,
  attachSimulation,
  resetSimulationEvents,
} = useSimulationEventFeed(api)

const { resetSimulationRuntimeState } = useSimulationRuntimeState<
  SimulationReport,
  SimulationAction,
  SimulationPidStatus
>({
  simulationProgressValue,
  simulationElapsedMinutes,
  simulationRealDurationMinutes,
  simulationSimNow,
  simulationEngine,
  simulationMode,
  simulationProgressSource,
  simulationActions,
  simulationPidStatuses,
  simulationCurrentPhase,
  simulationReport,
})

useSimulationInitialTelemetry({
  initialTelemetry: toRef(props, 'initialTelemetry'),
  initialState: form.initial_state,
  applyAutoDrift,
})

const { chartOption } = useSimulationChart({
  theme,
  results,
})

const {
  simulationProgress,
  simulationProgressDetails,
  simulationEngineLabel,
  simulationProgressSourceLabel,
  simulationCurrentPhaseLabel,
  simulationSimTimeLabel,
  simulationStatusLabel,
  reportSummaryEntries,
  reportPhaseEntries,
  reportMetricsEntries,
  reportErrors,
  isSimulating,
  resultDurationHours,
  resultStepMinutes,
} = useSimulationPresentation({
  simulationProgressValue,
  simulationStatus,
  simulationElapsedMinutes,
  simulationRealDurationMinutes,
  simulationEngine,
  simulationMode,
  simulationProgressSource,
  simulationCurrentPhase,
  simulationSimNow,
  simulationReport,
  loading,
  results,
  form,
})

const { clearSimulationPolling, startSimulationPolling } = useSimulationPolling<
  SimulationResults,
  SimulationReport,
  SimulationAction,
  SimulationPidStatus
>({
  api,
  simulationJobId,
  simulationStatus,
  simulationProgressValue,
  simulationElapsedMinutes,
  simulationRealDurationMinutes,
  simulationSimNow,
  simulationEngine,
  simulationMode,
  simulationProgressSource,
  simulationActions,
  simulationPidStatuses,
  simulationCurrentPhase,
  simulationReport,
  simulationDbId,
  simulationEvents,
  simulationEventsLoading,
  attachSimulation,
  loadSimulationEvents,
  normalizeSimulationResult,
  results,
  error,
  stopLoading,
  activeSimulationId: toRef(props, 'activeSimulationId'),
  activeSimulationStatus: toRef(props, 'activeSimulationStatus'),
  isVisible,
  loading,
})

const { resetSimulationLifecycleState } = useSimulationLifecycle({
  isVisible,
  handleOpen: handleRecipesOpen,
  resetDriftValues,
  clearSimulationPolling,
  resetSimulationRuntimeState,
  resetSimulationEvents,
})

async function onSubmit(): Promise<void> {
  startLoading()
  error.value = null
  results.value = null
  simulationJobId.value = null
  simulationStatus.value = 'queued'
  resetSimulationLifecycleState()
  
  try {
    const drift: SimulationSubmitDrift = {
      ph: driftPh.value,
      ec: driftEc.value,
      temp_air: driftTempAir.value,
      temp_water: driftTempWater.value,
      humidity_air: driftHumidity.value,
      noise: driftNoise.value,
    }

    const submitOutcome = await submitZoneSimulation(props.zoneId, form, drift)

    if (submitOutcome.kind === 'queued') {
      simulationJobId.value = submitOutcome.jobId
      simulationStatus.value = submitOutcome.status
      startSimulationPolling(submitOutcome.jobId)
      showToast('Симуляция поставлена в очередь', 'info', TOAST_TIMEOUT.NORMAL)
      return
    }

    if (submitOutcome.kind === 'completed') {
      const parsed = normalizeSimulationResult(submitOutcome.payload)
      if (parsed) {
        results.value = parsed
        simulationStatus.value = 'completed'
        showToast('Симуляция успешно завершена', 'success', TOAST_TIMEOUT.NORMAL)
      } else {
        error.value = 'Неожиданный формат ответа'
        simulationStatus.value = 'failed'
      }
    } else {
      error.value = submitOutcome.message
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
