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
        <dd class="font-mono text-[11px]">{{ correctionStep }}</dd>
      </div>
    </dl>

    <div
      v-if="schedulerSummary"
      class="rounded-lg border border-[color:var(--border-muted)]/40 bg-[color:var(--surface-muted)]/20 px-3 py-2 text-xs text-[color:var(--text-muted)]"
    >
      <span class="text-[color:var(--text-primary)] font-medium">Планировщик:</span>
      {{ schedulerSummary }}
    </div>

    <div
      v-if="offlineNodes.length > 0"
      class="rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100"
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
        <p class="mt-1 font-mono text-[10px] opacity-70">
          {{ hint.code }}
        </p>
      </li>
    </ul>

    <p
      v-else-if="observability.runtime?.task_is_active"
      class="text-xs text-emerald-300/90"
    >
      Явных признаков зависания не обнаружено. Этап выполняется в пределах ожидаемых порогов.
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import type { AutomationObservability, AutomationState } from '@/types/Automation'
import {
  formatObservabilityDuration,
  observabilityHealthLabel,
  resolveObservability,
  stageDiagnosticLabel,
} from '@/utils/automationObservability'

interface Props {
  automationState: AutomationState | null
}

const props = defineProps<Props>()

const observability = computed<AutomationObservability | null>(() => resolveObservability(props.automationState))

const hangHints = computed(() => observability.value?.hang_hints ?? [])

const healthLabel = computed(() => observabilityHealthLabel(observability.value?.overall_health))

const healthBadgeVariant = computed<'neutral' | 'info' | 'warning' | 'danger' | 'success'>(() => {
  const health = observability.value?.overall_health
  if (health === 'critical') return 'danger'
  if (health === 'warning') return 'warning'
  if (health === 'active') return 'info'
  return 'neutral'
})

const stageLabel = computed(() => {
  const runtime = observability.value?.runtime
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

const stageElapsedLabel = computed(() => formatObservabilityDuration(observability.value?.runtime?.stage_elapsed_sec))

const deadlineLabel = computed(() => {
  const remaining = observability.value?.runtime?.stage_deadline_remaining_sec
  if (remaining === null || remaining === undefined) {
    return observability.value?.runtime?.stage_deadline_at ? 'задан' : '—'
  }
  if (remaining < 0) {
    return `просрочен на ${formatObservabilityDuration(Math.abs(remaining))}`
  }
  return `осталось ${formatObservabilityDuration(remaining)}`
})

const correctionStep = computed(() => observability.value?.runtime?.correction_step ?? null)

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

function hintClass(severity: string): string {
  if (severity === 'critical') {
    return 'border-red-400/35 bg-red-500/10 text-red-100'
  }
  return 'border-amber-400/35 bg-amber-500/10 text-amber-100'
}
</script>

<style scoped>
.diag-tile {
  border-radius: 0.65rem;
  border: 1px solid rgb(100 116 139 / 0.25);
  background: rgb(15 23 42 / 0.2);
  padding: 0.5rem 0.65rem;
}

.diag-tile dt {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
}

.diag-tile dd {
  margin-top: 0.15rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-word;
}
</style>
