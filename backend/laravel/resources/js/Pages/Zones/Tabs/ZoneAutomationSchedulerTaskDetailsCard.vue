<template>
  <article class="rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--surface-muted)]/40 p-3 space-y-3">
    <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
      <div class="text-sm">
        <span class="text-[color:var(--text-dim)]">task_id:</span>
        <span class="font-mono text-[color:var(--text-primary)] ml-1">{{ schedulerTaskStatus.task_id }}</span>
      </div>
      <Badge :variant="schedulerTaskStatusVariant(schedulerTaskStatus.status)">
        {{ schedulerTaskStatusLabel(schedulerTaskStatus.status) }}
      </Badge>
    </div>
    <dl class="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
      <div>
        <dt class="text-[color:var(--text-dim)]">Тип</dt>
        <dd class="text-[color:var(--text-primary)]">{{ schedulerTaskStatus.task_type || '-' }}</dd>
      </div>
      <div>
        <dt class="text-[color:var(--text-dim)]">Создана</dt>
        <dd class="text-[color:var(--text-primary)]">{{ formatDateTime(schedulerTaskStatus.created_at) }}</dd>
      </div>
      <div>
        <dt class="text-[color:var(--text-dim)]">Обновлена</dt>
        <dd class="text-[color:var(--text-primary)]">{{ formatDateTime(schedulerTaskStatus.updated_at) }}</dd>
      </div>
    </dl>
    <dl class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-2 text-xs">
      <div>
        <dt class="text-[color:var(--text-dim)]">Scheduled</dt>
        <dd class="text-[color:var(--text-primary)]">{{ formatDateTime(schedulerTaskStatus.scheduled_for) }}</dd>
      </div>
      <div>
        <dt class="text-[color:var(--text-dim)]">Due</dt>
        <dd class="text-[color:var(--text-primary)]">{{ formatDateTime(schedulerTaskStatus.due_at || null) }}</dd>
      </div>
      <div>
        <dt class="text-[color:var(--text-dim)]">Expires</dt>
        <dd class="text-[color:var(--text-primary)]">{{ formatDateTime(schedulerTaskStatus.expires_at || null) }}</dd>
      </div>
      <div>
        <dt class="text-[color:var(--text-dim)]">SLA-контроль</dt>
        <dd class="space-y-1">
          <Badge :variant="schedulerTaskSla.variant">{{ schedulerTaskSla.label }}</Badge>
          <p class="text-[color:var(--text-dim)]">{{ schedulerTaskSla.hint }}</p>
        </dd>
      </div>
    </dl>
    <dl class="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
      <div>
        <dt class="text-[color:var(--text-dim)]">Решение автоматики</dt>
        <dd class="text-[color:var(--text-primary)]">
          {{ schedulerTaskDecisionLabel(schedulerTaskStatus.decision) }}
          <span
            v-if="schedulerTaskStatus.action_required === false"
            class="text-[color:var(--text-dim)]"
          >
            (действие не требуется)
          </span>
        </dd>
      </div>
      <div>
        <dt class="text-[color:var(--text-dim)]">Причина</dt>
        <dd class="text-[color:var(--text-primary)]">
          {{ schedulerTaskReasonLabel(schedulerTaskStatus.reason_code, schedulerTaskStatus.reason) }}
        </dd>
      </div>
    </dl>
    <dl class="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
      <div>
        <dt class="text-[color:var(--text-dim)]">Подтверждение ноды DONE</dt>
        <dd class="space-y-1">
          <Badge :variant="schedulerTaskDone.variant">{{ schedulerTaskDone.label }}</Badge>
          <p class="text-[color:var(--text-dim)]">{{ schedulerTaskDone.hint }}</p>
        </dd>
      </div>
      <div>
        <dt class="text-[color:var(--text-dim)]">Командный итог</dt>
        <dd class="text-[color:var(--text-primary)]">
          {{ schedulerTaskStatus.commands_effect_confirmed ?? schedulerTaskStatus.result?.commands_effect_confirmed ?? '-' }}
          /
          {{ schedulerTaskStatus.commands_total ?? schedulerTaskStatus.result?.commands_total ?? '-' }}
          подтверждено DONE
        </dd>
      </div>
    </dl>
    <dl
      v-if="schedulerTaskStatus.error_code || schedulerTaskStatus.error"
      class="grid grid-cols-1 gap-2 text-xs"
    >
      <div>
        <dt class="text-[color:var(--text-dim)]">Ошибка</dt>
        <dd class="text-[color:var(--text-primary)]">
          {{ schedulerTaskErrorLabel(schedulerTaskStatus.error_code, schedulerTaskStatus.error) }}
        </dd>
      </div>
    </dl>

    <section
      v-if="schedulerTaskStatus.process_state || (schedulerTaskStatus.process_steps && schedulerTaskStatus.process_steps.length > 0)"
      class="rounded-xl border border-[color:var(--border-muted)]/50 bg-[color:var(--surface-card)]/40 p-3 space-y-2"
    >
      <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
        <div class="text-xs text-[color:var(--text-dim)]">Текущий этап автоматики</div>
        <Badge :variant="schedulerTaskProcessStatusVariant(schedulerTaskStatus.process_state?.status)">
          {{ schedulerTaskProcessStatusLabel(schedulerTaskStatus.process_state?.status, schedulerTaskStatus.process_state?.status_label) }}
        </Badge>
      </div>
      <p class="text-sm text-[color:var(--text-primary)]">
        {{ schedulerTaskStatus.process_state?.phase_label || 'Этап не определён' }}
      </p>
      <p
        v-if="schedulerTaskStatus.process_state?.current_action"
        class="text-xs text-[color:var(--text-dim)]"
      >
        {{
          schedulerTaskEventLabel(schedulerTaskStatus.process_state.current_action.event_type) +
          (schedulerTaskStatus.process_state.current_action.reason_code
            ? ` · ${schedulerTaskReasonLabel(schedulerTaskStatus.process_state.current_action.reason_code)}`
            : '')
        }}
        · {{ formatDateTime(schedulerTaskStatus.process_state.current_action.at || null) }}
      </p>
      <ul
        v-if="schedulerTaskStatus.process_steps && schedulerTaskStatus.process_steps.length > 0"
        class="space-y-1 text-xs"
      >
        <li
          v-for="step in schedulerTaskStatus.process_steps"
          :key="`${schedulerTaskStatus.task_id}-process-${step.phase}`"
          class="flex flex-col md:flex-row md:items-center md:justify-between gap-1 border-b border-[color:var(--border-muted)]/40 pb-1 last:border-0"
        >
          <div class="text-[color:var(--text-primary)]">{{ step.label }}</div>
          <div class="flex items-center gap-2">
            <Badge :variant="schedulerTaskProcessStatusVariant(step.status)">
              {{ schedulerTaskProcessStatusLabel(step.status, step.status_label || null) }}
            </Badge>
            <span class="text-[color:var(--text-dim)]">{{ formatDateTime(step.updated_at || step.started_at || null) }}</span>
          </div>
        </li>
      </ul>
    </section>

    <ul
      v-if="schedulerTaskTimeline.length > 0"
      class="space-y-1 text-xs"
    >
      <li
        v-for="(step, index) in schedulerTaskTimeline"
        :key="`${schedulerTaskStatus.task_id}-timeline-${step.event_id || index}`"
        class="flex flex-col gap-1 border-b border-[color:var(--border-muted)]/40 pb-2 last:border-0"
      >
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-1">
          <div class="text-[color:var(--text-primary)]">
            {{ schedulerTaskTimelineStepLabel(step) }}
            <span
              v-if="schedulerTaskTimelineStageLabel(step)"
              class="text-[color:var(--text-dim)]"
            >
              · {{ schedulerTaskTimelineStageLabel(step) }}
            </span>
            <span
              v-if="step.reason_code && !schedulerTaskTimelineStageLabel(step)"
              class="text-[color:var(--text-dim)]"
            >
              · {{ schedulerTaskReasonLabel(step.reason_code, step.reason) }}
            </span>
            <span
              v-if="step.error_code"
              class="text-red-500"
            >
              · {{ schedulerTaskErrorLabel(step.error_code) }}
            </span>
          </div>
          <div class="text-[color:var(--text-dim)]">
            {{ formatDateTime(step.at) }}
          </div>
        </div>

        <div
          v-if="step.decision || step.reason_code || step.error_code"
          class="text-[11px] text-[color:var(--text-dim)]"
        >
          <span v-if="step.decision">
            decision: {{ schedulerTaskDecisionLabel(step.decision) }}
            <span class="font-mono">({{ step.decision }})</span>
          </span>
          <span
            v-if="step.reason_code"
            class="ml-2"
          >
            reason: {{ schedulerTaskReasonLabel(step.reason_code, step.reason) }}
            <span class="font-mono">({{ step.reason_code }})</span>
          </span>
          <span
            v-if="step.error_code"
            class="ml-2"
          >
            error: {{ schedulerTaskErrorLabel(step.error_code) }}
            <span class="font-mono">({{ step.error_code }})</span>
          </span>
        </div>

        <div
          v-if="schedulerTaskTimelineExtraMeta(step).length > 0"
          class="flex flex-wrap gap-1"
        >
          <span
            v-for="meta in schedulerTaskTimelineExtraMeta(step)"
            :key="`${step.event_id}-meta-${meta}`"
            class="rounded-md border border-[color:var(--border-muted)]/50 bg-[color:var(--surface-card)] px-1.5 py-0.5 text-[10px] text-[color:var(--text-dim)] font-mono"
          >
            {{ meta }}
          </span>
        </div>

        <details
          v-if="formatSchedulerTimelineRawDetails(step)"
          class="rounded-lg border border-[color:var(--border-muted)]/50 bg-[color:var(--surface-card)]/40"
        >
          <summary class="cursor-pointer list-none px-2 py-1 text-[11px] text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)]">
            raw payload
          </summary>
          <pre
            v-if="formatSchedulerTimelineRawDetails(step)"
            class="max-h-52 overflow-auto border-t border-[color:var(--border-muted)]/40 px-2 py-2 text-[10px] leading-4 text-[color:var(--text-muted)]"
          >{{ formatSchedulerTimelineRawDetails(step) }}</pre>
        </details>
      </li>
    </ul>
    <p
      v-else
      class="text-xs text-[color:var(--text-dim)]"
    >
      Timeline событий недоступен: ожидается event-contract (`event_id`, `event_type`, `at`).
    </p>
  </article>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'
import type {
  SchedulerTaskDoneMeta,
  SchedulerTaskSlaMeta,
  SchedulerTaskStatus,
  SchedulerTaskTimelineItem,
} from '@/composables/zoneAutomationTypes'

interface SchedulerTaskDetailsCardProps {
  schedulerTaskStatus: SchedulerTaskStatus
  schedulerTaskSla: SchedulerTaskSlaMeta
  schedulerTaskDone: SchedulerTaskDoneMeta
  schedulerTaskTimeline: SchedulerTaskTimelineItem[]
  formatDateTime: (value: string | null | undefined) => string
  schedulerTaskStatusVariant: (status: string | null | undefined) => string
  schedulerTaskStatusLabel: (status: string | null | undefined) => string
  schedulerTaskDecisionLabel: (decision: string | null | undefined) => string
  schedulerTaskReasonLabel: (reasonCode?: string | null, reason?: string | null) => string
  schedulerTaskErrorLabel: (errorCode?: string | null, error?: string | null) => string
  schedulerTaskProcessStatusVariant: (status?: string | null) => string
  schedulerTaskProcessStatusLabel: (status?: string | null, statusLabel?: string | null) => string
  schedulerTaskEventLabel: (eventType?: string | null) => string
  schedulerTaskTimelineStepLabel: (step: SchedulerTaskTimelineItem) => string
  schedulerTaskTimelineStageLabel: (step: SchedulerTaskTimelineItem) => string | null
}

const {
  formatDateTime,
  schedulerTaskDecisionLabel,
  schedulerTaskDone,
  schedulerTaskErrorLabel,
  schedulerTaskEventLabel,
  schedulerTaskProcessStatusLabel,
  schedulerTaskProcessStatusVariant,
  schedulerTaskReasonLabel,
  schedulerTaskSla,
  schedulerTaskStatus,
  schedulerTaskStatusLabel,
  schedulerTaskStatusVariant,
  schedulerTaskTimeline,
  schedulerTaskTimelineStageLabel,
  schedulerTaskTimelineStepLabel,
} = defineProps<SchedulerTaskDetailsCardProps>()

function normalizeSchedulerText(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  return normalized !== '' ? normalized : null
}

function formatSchedulerBool(value: boolean | null | undefined): string | null {
  if (value === true) return 'yes'
  if (value === false) return 'no'
  return null
}

function formatSchedulerTimelineRawDetails(step: SchedulerTaskTimelineItem): string {
  if (!step.details || typeof step.details !== 'object') return ''
  try {
    return JSON.stringify(step.details, null, 2)
  } catch {
    return ''
  }
}

function schedulerTaskTimelineExtraMeta(step: SchedulerTaskTimelineItem): string[] {
  const items: string[] = []
  const nodeUid = normalizeSchedulerText(step.node_uid)
  const channel = normalizeSchedulerText(step.channel)
  const cmd = normalizeSchedulerText(step.cmd)
  const runMode = normalizeSchedulerText(step.run_mode)
  const terminalStatus = normalizeSchedulerText(step.terminal_status)
  const source = normalizeSchedulerText(step.source)
  const eventSeq = typeof step.event_seq === 'number' ? String(step.event_seq) : null
  const retryAttempt = typeof step.retry_attempt === 'number' ? step.retry_attempt : null
  const retryMaxAttempts = typeof step.retry_max_attempts === 'number' ? step.retry_max_attempts : null
  const retryBackoff = typeof step.retry_backoff_sec === 'number' ? `${step.retry_backoff_sec}s` : null
  const commandSubmitted = formatSchedulerBool(step.command_submitted)
  const commandEffectConfirmed = formatSchedulerBool(step.command_effect_confirmed)
  const nextDueAt = normalizeSchedulerText(step.next_due_at)

  if (eventSeq) items.push(`seq: ${eventSeq}`)
  if (nodeUid) items.push(`node: ${nodeUid}`)
  if (channel) items.push(`channel: ${channel}`)
  if (cmd) items.push(`cmd: ${cmd}`)
  if (runMode) items.push(`mode: ${runMode}`)
  if (terminalStatus) items.push(`terminal: ${terminalStatus}`)
  if (commandSubmitted) items.push(`submitted: ${commandSubmitted}`)
  if (commandEffectConfirmed) items.push(`effect_confirmed: ${commandEffectConfirmed}`)
  if (retryAttempt !== null) {
    const retryMeta = retryMaxAttempts !== null ? `${retryAttempt}/${retryMaxAttempts}` : String(retryAttempt)
    items.push(`retry: ${retryMeta}`)
  }
  if (retryBackoff) items.push(`backoff: ${retryBackoff}`)
  if (nextDueAt) items.push(`next_due_at: ${formatDateTime(nextDueAt)}`)
  if (source) items.push(`source: ${source}`)

  return items
}
</script>
