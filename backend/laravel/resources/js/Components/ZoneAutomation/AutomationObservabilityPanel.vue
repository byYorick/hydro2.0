<template>
  <section
    class="rounded-xl border border-[color:var(--border-muted)]/60 bg-[color:var(--surface-card)]/50 p-3 space-y-3"
    data-testid="automation-observability-panel"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h4 class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-dim)]">
          Диагностика FSM
        </h4>
        <p class="text-xs text-[color:var(--text-muted)] mt-0.5">
          Точки риска зависания two-tank workflow и планировщика
        </p>
      </div>
      <Badge :variant="healthBadgeVariant">
        {{ healthLabel }}
      </Badge>
    </div>

    <dl class="grid grid-cols-2 gap-2 text-xs">
      <div class="diag-tile">
        <dt>Этап AE3</dt>
        <dd>{{ stageLabel }}</dd>
      </div>
      <div class="diag-tile">
        <dt>Статус задачи</dt>
        <dd>{{ taskStatusLabel }}</dd>
      </div>
      <div class="diag-tile">
        <dt>На этапе</dt>
        <dd>{{ stageElapsedLabel }}</dd>
      </div>
      <div class="diag-tile">
        <dt>Дедлайн этапа</dt>
        <dd>{{ deadlineLabel }}</dd>
      </div>
      <div
        v-if="correctionStep"
        class="diag-tile col-span-2"
      >
        <dt>Коррекция</dt>
        <dd class="font-mono text-[11px]">
          {{ correctionStep }}
        </dd>
        <p class="mt-1 text-[10px] text-[color:var(--text-dim)] leading-relaxed">
          Успех коррекции: <span class="font-medium">targets_in_tolerance</span> (±%);
          переход <span class="font-mono">*_stop_to_ready</span>:
          <span class="font-medium">workflow_ready</span> (explicit min/max).
        </p>
      </div>
      <div
        v-if="topologyLabel"
        class="diag-tile"
      >
        <dt>Топология</dt>
        <dd class="font-mono text-[11px]">
          {{ topologyLabel }}
        </dd>
      </div>
      <div
        v-if="pendingManualStepLabel"
        class="diag-tile col-span-2"
      >
        <dt>Ручной шаг</dt>
        <dd class="font-mono text-[11px]">
          {{ pendingManualStepLabel }}
        </dd>
      </div>
    </dl>

    <div
      v-if="correctionDosing"
      class="rounded-lg border px-3 py-2.5 text-xs space-y-1.5"
      :class="correctionDosingClass"
      data-testid="automation-correction-dosing"
    >
      <p class="font-semibold text-sm">
        Коррекция / дозирование
      </p>
      <p
        v-if="correctionDosing.reason"
        class="leading-relaxed"
      >
        {{ correctionDosing.reason }}
      </p>
      <p
        v-if="correctionDosing.detail"
        class="text-[10px] opacity-85 leading-relaxed"
      >
        {{ correctionDosing.detail }}
      </p>
      <dl class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-[10px]">
        <div v-if="correctionDosing.corrStepLabel">
          <dt class="uppercase tracking-wide opacity-70">
            Шаг AE3
          </dt>
          <dd class="mt-0.5 font-mono">
            {{ correctionDosing.corrStepLabel }}
          </dd>
        </div>
        <div v-if="correctionDosing.lastDoseSummary">
          <dt class="uppercase tracking-wide opacity-70">
            Последняя доза
          </dt>
          <dd class="mt-0.5">
            {{ correctionDosing.lastDoseSummary }}
          </dd>
        </div>
        <div v-if="correctionDosing.cooldownLabel">
          <dt class="uppercase tracking-wide opacity-70">
            Кулдаун / повтор
          </dt>
          <dd class="mt-0.5">
            через {{ correctionDosing.cooldownLabel }}
          </dd>
        </div>
        <div v-if="correctionDosing.targetsInTolerance !== null || correctionDosing.workflowReady !== null">
          <dt class="uppercase tracking-wide opacity-70">
            Готовность
          </dt>
          <dd class="mt-0.5">
            <span v-if="correctionDosing.targetsInTolerance !== null">
              ±%: {{ readinessBoolLabel(correctionDosing.targetsInTolerance) }}
            </span>
            <span
              v-if="correctionDosing.workflowReady !== null"
              :class="correctionDosing.targetsInTolerance !== null ? 'ml-2' : ''"
            >
              ready: {{ readinessBoolLabel(correctionDosing.workflowReady) }}
            </span>
          </dd>
        </div>
      </dl>
    </div>

    <div
      v-if="failureDiagnostics"
      class="rounded-lg border px-3 py-2.5 text-xs space-y-2"
      :class="failureDiagnostics.isActiveFailure
        ? 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)]'
        : 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]'"
      data-testid="automation-fsm-failure-details"
    >
      <p class="font-semibold text-sm">
        {{ failureDiagnostics.title }}
      </p>
      <p
        v-if="failureDiagnostics.summary"
        class="leading-relaxed"
      >
        {{ failureDiagnostics.summary }}
      </p>
      <dl class="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div v-if="failureDiagnostics.errorCode">
          <dt class="text-[10px] uppercase tracking-wide opacity-75">
            Код ошибки
          </dt>
          <dd class="mt-0.5 font-mono text-[11px] break-all">
            {{ failureDiagnostics.errorCode }}
          </dd>
        </div>
        <div v-if="failureDiagnostics.failedStageLabel">
          <dt class="text-[10px] uppercase tracking-wide opacity-75">
            Этап сбоя
          </dt>
          <dd class="mt-0.5 font-medium">
            {{ failureDiagnostics.failedStageLabel }}
            <span
              v-if="failureDiagnostics.failedStage"
              class="block font-mono text-[10px] opacity-80"
            >
              {{ failureDiagnostics.failedStage }}
            </span>
          </dd>
        </div>
        <div v-if="failureDiagnostics.taskId">
          <dt class="text-[10px] uppercase tracking-wide opacity-75">
            Задача
          </dt>
          <dd class="mt-0.5 font-mono text-[11px]">
            #{{ failureDiagnostics.taskId }}
          </dd>
        </div>
        <div v-if="failureDiagnostics.failedAt">
          <dt class="text-[10px] uppercase tracking-wide opacity-75">
            Время сбоя
          </dt>
          <dd class="mt-0.5">
            {{ formatFailureTimestamp(failureDiagnostics.failedAt) }}
          </dd>
        </div>
        <div v-if="failureDiagnostics.workflowPhase">
          <dt class="text-[10px] uppercase tracking-wide opacity-75">
            Фаза workflow
          </dt>
          <dd class="mt-0.5 font-mono text-[11px]">
            {{ failureDiagnostics.workflowPhase }}
          </dd>
        </div>
      </dl>
      <p
        v-if="failureDiagnostics.technicalMessage"
        class="font-mono text-[10px] leading-relaxed opacity-85 break-words"
      >
        {{ failureDiagnostics.technicalMessage }}
      </p>
      <p
        v-if="failureDiagnostics.isHistoricalFailure"
        class="text-[10px] opacity-80"
      >
        Активный policy-алерт подтверждён; ниже — данные последнего terminal failure из AE3/БД.
      </p>
    </div>

    <div
      v-if="taskIdLabel && !failureDiagnostics"
      class="diag-info-block"
    >
      <span class="font-medium text-[color:var(--text-primary)]">Task:</span>
      {{ taskIdLabel }}
    </div>

    <div
      v-if="schedulerSummary"
      class="diag-info-block"
    >
      <span class="font-medium text-[color:var(--text-primary)]">Планировщик:</span>
      {{ schedulerSummary }}
    </div>

    <div
      v-if="offlineNodes.length > 0"
      class="rounded-lg border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] px-3 py-2 text-xs text-[color:var(--badge-warning-text)]"
    >
      <p class="font-medium">
        Узлы offline / stale
      </p>
      <p class="mt-1 font-mono text-[11px] break-all">
        {{ offlineNodes.join(', ') }}
      </p>
    </div>

    <p
      v-if="dataSourceLabel"
      class="text-[10px] text-[color:var(--text-dim)]"
    >
      Источник: {{ dataSourceLabel }}
    </p>

    <SchedulerDispatchMetricsStrip />

    <ul
      v-if="hangHints.length > 0"
      class="space-y-2"
    >
      <li
        v-for="hint in hangHints"
        :key="hint.code"
        class="rounded-lg border px-3 py-2 text-xs"
        :class="hintClass(hint.severity)"
      >
        <p class="font-semibold">
          {{ hint.message }}
        </p>
        <p
          v-if="hint.recommendation"
          class="mt-1 opacity-90"
        >
          {{ hint.recommendation }}
        </p>
        <ul
          v-if="hintDetailLines(hint).length > 0"
          class="mt-1.5 space-y-0.5 font-mono text-[10px] opacity-80"
        >
          <li
            v-for="line in hintDetailLines(hint)"
            :key="line"
          >
            {{ line }}
          </li>
        </ul>
        <p class="mt-1 font-mono text-[10px] opacity-70">
          {{ hint.code }}
        </p>
      </li>
    </ul>

    <p
      v-else-if="observability?.runtime?.task_is_active"
      class="text-xs text-[color:var(--badge-success-text)]"
    >
      Явных признаков зависания не обнаружено. Этап выполняется в пределах ожидаемых порогов.
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import SchedulerDispatchMetricsStrip from '@/Components/ZoneAutomation/SchedulerDispatchMetricsStrip.vue'
import type { AutomationObservability, AutomationState } from '@/types/Automation'
import {
  formatObservabilityDuration,
  observabilityHealthLabel,
  resolveCorrectionDosingDiagnostics,
  resolveObservability,
  stageDiagnosticLabel,
} from '@/utils/automationObservability'
import { resolveAutomationFailureDiagnostics } from '@/utils/automationFailureDiagnostics'
import { formatDateTime } from '@/utils/simulationFormatters'

interface Props {
  automationState: AutomationState | null
}

const props = defineProps<Props>()

const observability = computed<AutomationObservability | null>(() => resolveObservability(props.automationState))

const failureDiagnostics = computed(() => resolveAutomationFailureDiagnostics(
  props.automationState,
  observability.value,
))

const hangHints = computed(() => observability.value?.hang_hints ?? [])

const correctionDosing = computed(() => resolveCorrectionDosingDiagnostics(
  props.automationState,
  observability.value,
))

const correctionDosingClass = computed(() => {
  const severity = correctionDosing.value?.severity ?? 'neutral'
  if (severity === 'danger') {
    return 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)]'
  }
  if (severity === 'warning') {
    return 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]'
  }
  if (severity === 'info') {
    return 'border-[color:var(--badge-info-border)] bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)]'
  }
  return 'border-[color:var(--border-muted)]/70 bg-[color:var(--bg-elevated)]/55 text-[color:var(--text-primary)]'
})

const healthLabel = computed(() => {
  if (failureDiagnostics.value) {
    return failureDiagnostics.value.isActiveFailure ? 'Сбой' : 'Последний сбой'
  }
  return observabilityHealthLabel(observability.value?.overall_health)
})

const healthBadgeVariant = computed<'neutral' | 'info' | 'warning' | 'danger' | 'success'>(() => {
  if (failureDiagnostics.value) {
    return failureDiagnostics.value.isActiveFailure ? 'danger' : 'warning'
  }
  const health = observability.value?.overall_health
  if (health === 'critical') return 'danger'
  if (health === 'warning') return 'warning'
  if (health === 'active') return 'info'
  return 'neutral'
})

const stageLabel = computed(() => {
  const runtime = observability.value?.runtime
  if (runtime?.task_status === 'failed' && !runtime?.task_is_active) {
    const failedStage = runtime.failed_stage
      ?? props.automationState?.current_stage
      ?? null
    if (failedStage) {
      return `${stageDiagnosticLabel(failedStage)} (сбой)`
    }
    return '—'
  }
  return stageDiagnosticLabel(
    runtime?.current_stage
    ?? props.automationState?.current_stage_label
    ?? props.automationState?.current_stage,
  )
})

const taskStatusLabel = computed(() => {
  const runtime = observability.value?.runtime
  if (!runtime?.task_status) {
    return runtime?.task_is_active ? 'активна' : 'нет активной задачи'
  }
  if (runtime.waiting_command) {
    return `${runtime.task_status} (ожидание команды)`
  }
  return runtime.task_status
})

const stageElapsedLabel = computed(() => {
  const runtime = observability.value?.runtime
  if (runtime?.task_status === 'failed' || props.automationState?.state_details?.failed === true) {
    const elapsed = runtime?.stage_elapsed_sec
    return elapsed != null && elapsed > 0 ? formatObservabilityDuration(elapsed) : '—'
  }
  return formatObservabilityDuration(runtime?.stage_elapsed_sec)
})

const deadlineLabel = computed(() => {
  const runtime = observability.value?.runtime
  if (runtime?.task_status === 'failed' || props.automationState?.state_details?.failed === true) {
    return '—'
  }
  const remaining = runtime?.stage_deadline_remaining_sec
  if (remaining === null || remaining === undefined) {
    return runtime?.stage_deadline_at ? 'задан' : '—'
  }
  if (remaining < 0) {
    return `просрочен на ${formatObservabilityDuration(Math.abs(remaining))}`
  }
  return `осталось ${formatObservabilityDuration(remaining)}`
})

const correctionStep = computed(() => {
  if (observability.value?.runtime?.task_status === 'failed') {
    return null
  }
  return observability.value?.runtime?.correction_step ?? null
})

const topologyLabel = computed(() => {
  const topology = observability.value?.runtime?.topology
  if (typeof topology !== 'string' || topology.trim() === '') {
    return null
  }
  return topology.trim()
})

const pendingManualStepLabel = computed(() => {
  const step = observability.value?.runtime?.pending_manual_step
  if (typeof step !== 'string' || step.trim() === '') {
    return null
  }
  return step.trim()
})

const taskIdLabel = computed(() => {
  const taskId = observability.value?.runtime?.task_id
  if (taskId === null || taskId === undefined) {
    return null
  }
  return `#${taskId}`
})

const offlineNodes = computed(() => observability.value?.nodes?.offline_required ?? [])

const dataSourceLabel = computed(() => {
  if (props.automationState?.state_meta?.is_stale) {
    return 'кэш Laravel (AE3 недоступен)'
  }
  const source = observability.value?.runtime?.source
  if (source === 'laravel_db_fallback') {
    return 'БД Laravel (fallback)'
  }
  if (source === 'client_fallback') {
    return 'локальная оценка UI'
  }
  return 'AE3 live'
})

const schedulerSummary = computed(() => {
  const scheduler = observability.value?.scheduler
  if (!scheduler) {
    return null
  }
  const pending = scheduler.pending_count ?? 0
  const active = scheduler.active_count ?? 0
  const latest = scheduler.latest_intent
  if (active === 0 && pending === 0) {
    return 'нет активных intent'
  }
  const parts = [`активных intent: ${active}`, `pending: ${pending}`]
  if (latest?.intent_type) {
    parts.push(`последний: ${latest.intent_type} (${latest.status ?? 'unknown'})`)
  }
  if (latest?.age_sec != null) {
    parts.push(`возраст ${formatObservabilityDuration(latest.age_sec)}`)
  }
  return parts.join(' · ')
})

function formatFailureTimestamp(value: string): string {
  return formatDateTime(value)
}

function readinessBoolLabel(value: boolean): string {
  return value ? 'да' : 'нет'
}

function hintClass(severity: string): string {
  if (severity === 'critical') {
    return 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)]'
  }
  return 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]'
}

function hintDetailLines(hint: { details?: Record<string, unknown> }): string[] {
  const details = hint.details
  if (!details || typeof details !== 'object') {
    return []
  }

  const lines: string[] = []
  if (details.intent_id != null) {
    lines.push(`intent_id=${String(details.intent_id)}`)
  }
  if (typeof details.intent_type === 'string' && details.intent_type !== '') {
    lines.push(`intent_type=${details.intent_type}`)
  }
  if (details.age_sec != null) {
    lines.push(`age_sec=${String(details.age_sec)}`)
  }
  if (details.waiting_elapsed_sec != null) {
    lines.push(`waiting_elapsed_sec=${String(details.waiting_elapsed_sec)}`)
  }
  if (typeof details.current_stage === 'string' && details.current_stage !== '') {
    lines.push(`stage=${details.current_stage}`)
  }
  if (details.overdue_sec != null) {
    lines.push(`overdue_sec=${String(details.overdue_sec)}`)
  }
  if (typeof details.task_status === 'string' && details.task_status !== '') {
    lines.push(`task_status=${details.task_status}`)
  }
  if (typeof details.intent_status === 'string' && details.intent_status !== '') {
    lines.push(`intent_status=${details.intent_status}`)
  }
  if (typeof details.idempotency_key === 'string' && details.idempotency_key !== '') {
    lines.push(`idempotency_key=${details.idempotency_key}`)
  }
  if (Array.isArray(details.nodes) && details.nodes.length > 0) {
    lines.push(`nodes=${details.nodes.map((n) => String(n)).join(',')}`)
  }

  return lines
}
</script>

<style scoped>
.diag-tile {
  border-radius: 0.65rem;
  border: 1px solid color-mix(in srgb, var(--border-muted) 85%, transparent);
  background: color-mix(in srgb, var(--bg-elevated) 78%, transparent);
  padding: 0.5rem 0.65rem;
}

.diag-tile dt {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.diag-tile dd {
  margin-top: 0.15rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-word;
}

.diag-info-block {
  border-radius: 0.65rem;
  border: 1px solid color-mix(in srgb, var(--border-muted) 85%, transparent);
  background: color-mix(in srgb, var(--bg-elevated) 65%, transparent);
  padding: 0.5rem 0.75rem;
  font-size: 0.75rem;
  line-height: 1.4;
  color: var(--text-primary);
}
</style>
