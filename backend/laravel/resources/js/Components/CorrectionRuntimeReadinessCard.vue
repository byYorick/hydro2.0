<template>
  <Card>
    <div class="space-y-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-sm font-semibold">Готовность correction runtime</div>
          <div class="mt-1 text-xs text-[color:var(--text-dim)]">
            Агрегированная проверка калибровки процесса и калибровок дозирующих насосов для in-flow correction.
          </div>
        </div>
        <Badge :variant="overallStatus.variant">
          {{ overallStatus.label }}
        </Badge>
      </div>

      <div
        v-if="loading"
        class="text-sm text-[color:var(--text-dim)]"
      >
        Загрузка...
      </div>

      <div
        v-else
        class="space-y-4"
      >
        <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs text-[color:var(--text-dim)]">
          <div class="font-medium text-[color:var(--text-primary)]">
            {{ overallStatus.title }}
          </div>
          <div class="mt-1">
            {{ overallStatus.description }}
          </div>
          <div
            v-if="showActions"
            class="mt-3 flex flex-wrap gap-2"
          >
            <button
              v-if="hasFailClosedPhases"
              type="button"
              class="btn btn-outline h-8 px-3 text-xs"
              data-testid="correction-readiness-process-btn"
              @click="emit('focus-process-calibration')"
            >
              Перейти к калибровке процесса
            </button>
            <button
              v-if="hasMissingPumpGroups"
              type="button"
              class="btn btn-outline h-8 px-3 text-xs"
              data-testid="correction-readiness-pump-btn"
              @click="emit('open-pump-calibration')"
            >
              Открыть калибровку насосов
            </button>
          </div>
        </div>

        <section
          v-if="latestIssues.length > 0"
          class="space-y-2"
        >
          <div class="text-xs font-medium uppercase tracking-[0.08em] text-[color:var(--text-muted)]">
            Последние runtime blockers
          </div>

          <div
            v-for="issue in latestIssues"
            :key="`${issue.kind}-${issue.id}`"
            class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-sm font-medium text-[color:var(--text-primary)]">
                  {{ issue.title }}
                </div>
                <div class="mt-1 text-xs text-[color:var(--text-dim)]">
                  {{ issue.message }}
                </div>
                <div
                  v-if="issue.meta"
                  class="mt-1 text-[11px] text-[color:var(--text-muted)]"
                >
                  {{ issue.meta }}
                </div>
              </div>
              <Badge :variant="issue.badgeVariant">
                {{ issue.badgeLabel }}
              </Badge>
            </div>
            <div class="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-[color:var(--text-muted)]">
              <span v-if="issue.occurredAt">
                {{ issue.occurredAt }}
              </span>
              <span v-if="issue.recommendation">
                {{ issue.recommendation }}
              </span>
            </div>
            <div
              v-if="issue.action"
              class="mt-2"
            >
              <button
                type="button"
                class="btn btn-outline h-8 px-3 text-xs"
                :data-testid="`correction-issue-action-${issue.id}`"
                @click="handleIssueAction(issue.action)"
              >
                {{ issue.actionLabel }}
              </button>
            </div>
          </div>
        </section>

        <div class="grid gap-4 xl:grid-cols-2">
          <section class="space-y-2">
            <div class="text-xs font-medium uppercase tracking-[0.08em] text-[color:var(--text-muted)]">
              Калибровка процесса
            </div>

            <div
              v-for="item in phaseCoverage"
              :key="item.mode"
              class="rounded-xl border border-[color:var(--border-muted)] p-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-[color:var(--text-primary)]">
                  {{ item.label }}
                </div>
                <Badge :variant="item.badgeVariant">
                  {{ item.badgeLabel }}
                </Badge>
              </div>
              <div class="mt-1 text-xs text-[color:var(--text-dim)]">
                {{ item.message }}
              </div>
            </div>
          </section>

          <section class="space-y-2">
            <div class="text-xs font-medium uppercase tracking-[0.08em] text-[color:var(--text-muted)]">
              Калибровка насосов
            </div>

            <div
              v-for="group in pumpGroups"
              :key="group.key"
              class="rounded-xl border border-[color:var(--border-muted)] p-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-[color:var(--text-primary)]">
                  {{ group.label }}
                </div>
                <Badge :variant="group.ready ? 'success' : 'warning'">
                  {{ group.ready ? 'Готово' : 'Нужна калибровка' }}
                </Badge>
              </div>
              <div class="mt-1 text-xs text-[color:var(--text-dim)]">
                <template v-if="group.ready">
                  Все обязательные насосы откалиброваны.
                </template>
                <template v-else>
                  {{ group.missingMessage }}
                </template>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Badge from '@/Components/Badge.vue'
import Card from '@/Components/Card.vue'
import { useApi } from '@/composables/useApi'
import { usePidConfig } from '@/composables/usePidConfig'
import type { PumpCalibration } from '@/types/PidConfig'
import type { ProcessCalibrationMode, ZoneProcessCalibration } from '@/types/ProcessCalibration'

interface ApiResponse<T> {
  status: string
  data: T
}

interface PumpGroupStatus {
  key: 'ph' | 'ec'
  label: string
  ready: boolean
  missingMessage: string
}

interface PhaseCoverageItem {
  mode: Exclude<ProcessCalibrationMode, 'generic'>
  label: string
  badgeLabel: string
  badgeVariant: 'success' | 'warning' | 'danger'
  message: string
  failClosed: boolean
}

interface ZoneApiEvent {
  id?: number | string | null
  event_id?: number | string | null
  type?: string | null
  message?: string | null
  occurred_at?: string | null
  created_at?: string | null
  payload?: unknown
  details?: unknown
}

interface RuntimeIssueItem {
  id: number
  kind: string
  title: string
  message: string
  meta: string | null
  occurredAt: string | null
  badgeVariant: 'danger' | 'warning' | 'info'
  badgeLabel: string
  recommendation: string | null
  action: 'focus-process-calibration' | 'open-pump-calibration' | null
  actionLabel: string | null
}

const props = defineProps<{ zoneId: number }>()
const emit = defineEmits<{
  (e: 'focus-process-calibration'): void
  (e: 'open-pump-calibration'): void
}>()

const { api } = useApi()
const { getPumpCalibrations } = usePidConfig()

const loading = ref(true)
const processCalibrations = ref<ZoneProcessCalibration[]>([])
const pumpCalibrations = ref<PumpCalibration[]>([])
const runtimeEvents = ref<RuntimeIssueItem[]>([])

const phaseLabels: Record<Exclude<ProcessCalibrationMode, 'generic'>, string> = {
  solution_fill: 'Наполнение',
  tank_recirc: 'Рециркуляция',
  irrigation: 'Полив',
}

const roleLabels: Record<string, string> = {
  ph_acid_pump: 'насос pH кислоты',
  ph_base_pump: 'насос pH щёлочи',
  ec_npk_pump: 'насос EC NPK',
  ec_calcium_pump: 'насос EC Calcium',
  ec_magnesium_pump: 'насос EC Magnesium',
  ec_micro_pump: 'насос EC Micro',
}

const pumpGroups = computed<PumpGroupStatus[]>(() => {
  const calibratedRoles = new Set(
    pumpCalibrations.value
      .filter((item) => typeof item.ml_per_sec === 'number' && item.ml_per_sec > 0)
      .map((item) => item.role)
  )

  const groups: Array<{ key: 'ph' | 'ec'; label: string; roles: string[] }> = [
    { key: 'ph', label: 'Контур дозирования pH', roles: ['ph_acid_pump', 'ph_base_pump'] },
    { key: 'ec', label: 'Контур дозирования EC', roles: ['ec_npk_pump', 'ec_calcium_pump', 'ec_magnesium_pump', 'ec_micro_pump'] },
  ]

  return groups.map((group) => {
    const missing = group.roles.filter((role) => !calibratedRoles.has(role))

    return {
      key: group.key,
      label: group.label,
      ready: missing.length === 0,
      missingMessage: missing.length === 0
        ? ''
        : `Не хватает калибровки для: ${missing.map((role) => roleLabels[role] ?? role).join(', ')}.`,
    }
  })
})

const phaseCoverage = computed<PhaseCoverageItem[]>(() => {
  const byMode = new Map(processCalibrations.value.map((item) => [item.mode, item]))
  const generic = byMode.get('generic')
  const modes: Array<Exclude<ProcessCalibrationMode, 'generic'>> = ['solution_fill', 'tank_recirc', 'irrigation']

  return modes.map((mode) => {
    const specific = byMode.get(mode)
    if (specific) {
      return {
        mode,
        label: phaseLabels[mode],
        badgeLabel: 'Отдельная',
        badgeVariant: 'success',
        message: `Для фазы сохранена отдельная калибровка процесса. Confidence: ${formatConfidence(specific.confidence)}.`,
        failClosed: false,
      }
    }

    if (generic) {
      return {
        mode,
        label: phaseLabels[mode],
        badgeLabel: 'Через generic',
        badgeVariant: 'warning',
        message: `Для фазы отдельной калибровки нет, используется generic-профиль. Confidence: ${formatConfidence(generic.confidence)}.`,
        failClosed: false,
      }
    }

    return {
      mode,
      label: phaseLabels[mode],
      badgeLabel: 'Блокировано',
      badgeVariant: 'danger',
      message: 'Для этой фазы не заданы ни отдельная, ни generic-калибровка процесса, поэтому correction runtime не должен дозировать.',
      failClosed: true,
    }
  })
})

const overallStatus = computed(() => {
  const missingPumpGroups = pumpGroups.value.filter((group) => !group.ready)
  const failClosedPhases = phaseCoverage.value.filter((item) => item.failClosed)

  if (missingPumpGroups.length === 0 && failClosedPhases.length === 0) {
    const usesFallback = phaseCoverage.value.some((item) => item.badgeLabel === 'Через generic')

    return {
      variant: usesFallback ? 'info' as const : 'success' as const,
      label: usesFallback ? 'Готово с fallback' : 'Готово',
      title: usesFallback ? 'Correction runtime готов, но часть фаз работает через generic fallback.' : 'Correction runtime полностью готов к работе.',
      description: usesFallback
        ? 'Проверьте, нужны ли mode-specific process calibration для каждой фазы, чтобы не жить на generic-профиле постоянно.'
        : 'Все process calibration и обязательные pump calibration заданы для текущего correction path.',
    }
  }

  if (failClosedPhases.length > 0) {
    return {
      variant: 'danger' as const,
      label: 'Блокировано',
      title: 'Есть фазы, где runtime должен оставаться fail-closed.',
      description: `Проблемные фазы: ${failClosedPhases.map((item) => item.label).join(', ')}. Сначала задайте process calibration, затем проверяйте correction cycle.`,
    }
  }

  return {
    variant: 'warning' as const,
    label: 'Нужна калибровка',
    title: 'Калибровка процесса есть, но контур дозирования ещё не готов.',
    description: `Не хватает калибровки насосов для: ${missingPumpGroups.map((group) => group.label).join(', ')}.`,
  }
})

const hasMissingPumpGroups = computed(() => pumpGroups.value.some((group) => !group.ready))
const hasFailClosedPhases = computed(() => phaseCoverage.value.some((item) => item.failClosed))
const showActions = computed(() => hasMissingPumpGroups.value || hasFailClosedPhases.value)
const latestIssues = computed(() => runtimeEvents.value.slice(0, 3))

function formatConfidence(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return 'не задан'
  }

  return value.toFixed(2)
}

function toPayloadRecord(raw: unknown): Record<string, unknown> | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return null
  }

  return raw as Record<string, unknown>
}

function parseNumeric(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }

  return null
}

function formatOccurredAt(value: string | null | undefined): string | null {
  if (!value) {
    return null
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return null
  }

  return date.toLocaleString('ru-RU')
}

function toRuntimeIssue(raw: ZoneApiEvent): RuntimeIssueItem | null {
  const kind = typeof raw.type === 'string' ? raw.type : null
  const id = Number(raw.event_id ?? raw.id)
  if (!kind || !Number.isInteger(id) || id <= 0) {
    return null
  }

  const payload = toPayloadRecord(raw.payload ?? raw.details)
  const message = typeof raw.message === 'string' && raw.message.trim() !== '' ? raw.message : kind
  const occurredAt = formatOccurredAt(raw.occurred_at ?? raw.created_at ?? null)

  if (kind === 'CORRECTION_SKIPPED_FRESHNESS') {
    const scope = typeof payload?.sensor_scope === 'string' ? payload.sensor_scope : null
    const sensor = typeof payload?.sensor_type === 'string' ? payload.sensor_type.toUpperCase() : null
    const retrySec = parseNumeric(payload?.retry_after_sec)
    return {
      id,
      kind,
      title: 'Недостаточно свежих данных для correction',
      message,
      meta: [scope === 'observe_window' ? 'observe window' : scope === 'decision_window' ? 'decision window' : null, sensor].filter(Boolean).join(' • ') || null,
      occurredAt,
      badgeVariant: 'warning',
      badgeLabel: 'Freshness',
      recommendation: retrySec !== null ? `Проверьте поток и окно наблюдения; runtime повторит попытку через ${retrySec} с.` : 'Проверьте поток и окно наблюдения process calibration.',
      action: 'focus-process-calibration',
      actionLabel: 'Проверить Process Calibration',
    }
  }

  if (kind === 'CORRECTION_SKIPPED_WINDOW_NOT_READY') {
    const scope = typeof payload?.sensor_scope === 'string' ? payload.sensor_scope : null
    const sensor = typeof payload?.sensor_type === 'string' ? payload.sensor_type.toUpperCase() : null
    const retrySec = parseNumeric(payload?.retry_after_sec)
    const reason = typeof payload?.reason === 'string' ? payload.reason : null
    return {
      id,
      kind,
      title: 'Окно наблюдения correction ещё не готово',
      message,
      meta: [scope === 'observe_window' ? 'observe window' : scope === 'decision_window' ? 'decision window' : null, sensor, reason].filter(Boolean).join(' • ') || null,
      occurredAt,
      badgeVariant: 'warning',
      badgeLabel: 'Window',
      recommendation: retrySec !== null ? `Проверьте частоту telemetry и параметры observe-window; retry через ${retrySec} с.` : 'Проверьте telemetry cadence и параметры observe-window.',
      action: 'focus-process-calibration',
      actionLabel: 'Проверить Process Calibration',
    }
  }

  if (kind === 'CORRECTION_SKIPPED_DOSE_DISCARDED') {
    const durationMs = parseNumeric(payload?.computed_duration_ms)
    const minDoseMs = parseNumeric(payload?.min_dose_ms)
    const reason = typeof payload?.reason === 'string' ? payload.reason : null
    return {
      id,
      kind,
      title: 'Correction отбросил слишком малую дозу',
      message,
      meta: durationMs !== null && minDoseMs !== null ? `${durationMs}мс < ${minDoseMs}мс` : reason,
      occurredAt,
      badgeVariant: 'warning',
      badgeLabel: 'Dose',
      recommendation: 'Сверьте pump calibration, min_effective_ml и min_dose_ms для этого dosing path.',
      action: 'open-pump-calibration',
      actionLabel: 'Открыть Pump Calibration',
    }
  }

  if (kind === 'CORRECTION_SKIPPED_WATER_LEVEL') {
    const levelPct = parseNumeric(payload?.water_level_pct)
    const retrySec = parseNumeric(payload?.retry_after_sec)
    return {
      id,
      kind,
      title: 'Correction остановлен уровнем воды',
      message,
      meta: levelPct !== null ? `Уровень воды ${levelPct.toFixed(1)}%` : null,
      occurredAt,
      badgeVariant: 'warning',
      badgeLabel: 'Water level',
      recommendation: retrySec !== null ? `Нужно восстановить уровень раствора; повтор через ${retrySec} с.` : 'Нужно восстановить уровень раствора перед следующей коррекцией.',
      action: null,
      actionLabel: null,
    }
  }

  if (kind === 'CORRECTION_NO_EFFECT') {
    const pidType = typeof payload?.pid_type === 'string' ? payload.pid_type.toUpperCase() : null
    const actualEffect = parseNumeric(payload?.actual_effect)
    const thresholdEffect = parseNumeric(payload?.threshold_effect)
    return {
      id,
      kind,
      title: 'Correction не дал наблюдаемого эффекта',
      message,
      meta: pidType && actualEffect !== null && thresholdEffect !== null
        ? `${pidType}: ${actualEffect.toFixed(4)} < ${thresholdEffect.toFixed(4)}`
        : pidType,
      occurredAt,
      badgeVariant: 'danger',
      badgeLabel: 'No effect',
      recommendation: 'Проверьте pump calibration и реальный dosing path перед следующим cycle.',
      action: 'open-pump-calibration',
      actionLabel: 'Открыть Pump Calibration',
    }
  }

  if (kind === 'CORRECTION_EXHAUSTED') {
    const stage = typeof payload?.stage === 'string' ? payload.stage : null
    return {
      id,
      kind,
      title: 'Correction исчерпал попытки',
      message,
      meta: stage ? `Стадия ${stage}` : null,
      occurredAt,
      badgeVariant: 'danger',
      badgeLabel: 'Exhausted',
      recommendation: 'Проверьте process calibration, PID limits и калибровки насосов перед повторным запуском.',
      action: 'open-pump-calibration',
      actionLabel: 'Открыть Pump Calibration',
    }
  }

  return null
}

function handleIssueAction(action: RuntimeIssueItem['action']): void {
  if (action === 'focus-process-calibration') {
    emit('focus-process-calibration')
    return
  }

  if (action === 'open-pump-calibration') {
    emit('open-pump-calibration')
  }
}

async function load(): Promise<void> {
  loading.value = true

  try {
    const [processResponse, pumps, eventsResponse] = await Promise.all([
      api.get<ApiResponse<ZoneProcessCalibration[]>>(`/api/zones/${props.zoneId}/process-calibrations`),
      getPumpCalibrations(props.zoneId),
      api.get<ApiResponse<ZoneApiEvent[]>>(`/api/zones/${props.zoneId}/events`, {
        params: {
          limit: 80,
        },
      }),
    ])

    processCalibrations.value = Array.isArray(processResponse.data.data) ? processResponse.data.data : []
    pumpCalibrations.value = Array.isArray(pumps) ? pumps : []
    runtimeEvents.value = Array.isArray(eventsResponse.data.data)
      ? eventsResponse.data.data
        .map((item) => toRuntimeIssue(item))
        .filter((item): item is RuntimeIssueItem => item !== null)
        .sort((left, right) => right.id - left.id)
      : []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>
