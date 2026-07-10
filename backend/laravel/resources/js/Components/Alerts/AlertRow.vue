<template>
  <div class="relative flex items-start gap-2">
    <span
      class="absolute left-0 top-0 h-full w-0.5 -ml-3 rounded-full"
      :class="severityRailClass(item)"
    ></span>
    <Badge
      :variant="alertBadgeVariant(item.status)"
      size="sm"
      class="shrink-0 mt-0.5"
    >
      {{ translateStatus(item.status) }}
    </Badge>
    <div class="flex-1 min-w-0">
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="text-xs font-semibold text-[color:var(--text-primary)] truncate">
          {{ getAlertTitle(item) }}
        </span>
        <span
          v-if="item.code"
          class="font-mono text-[11px] text-[color:var(--text-dim)]"
        >
          {{ item.code }}
        </span>
        <Badge
          v-if="processStoppingBadge"
          :variant="processStoppingBadge.variant"
          size="xs"
          class="font-semibold uppercase tracking-wide"
          data-testid="alert-process-stop-badge"
          :data-process-stopping-kind="processStoppingBadge.kind"
          :title="processStoppingBadge.title"
        >
          {{ processStoppingBadge.label }}
        </Badge>
        <span class="ml-auto shrink-0 text-[11px] text-[color:var(--text-dim)]">
          {{ formatAlertDate(item.created_at) }}
        </span>
      </div>
      <p
        v-if="getAlertMessage(item)"
        class="mt-0.5 text-xs leading-snug text-[color:var(--text-muted)] truncate"
      >
        {{ getAlertMessage(item) }}
      </p>
      <p
        v-if="normalizeAlertStatus(item.status) === 'RESOLVED'"
        class="mt-0.5 text-[11px] text-[color:var(--text-dim)]"
      >
        Решён: {{ formatAlertDate(item.resolved_at || item.updated_at) }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import { translateStatus } from '@/utils/i18n'
import type { Alert } from '@/types/Alert'
import {
  alertProcessStoppingKind,
  PROCESS_STOPPING_BADGE_LABEL,
  type ProcessStoppingKind,
} from '@/utils/automationBlock'
import {
  alertBadgeVariant,
  formatAlertDate,
  getAlertMessage,
  getAlertTitle,
  normalizeAlertStatus,
  severityRailClass,
} from '@/utils/alertMeta'

const props = defineProps<{
  item: Alert
}>()

const processStoppingKind = computed(() => alertProcessStoppingKind(props.item.code))

const processStoppingBadge = computed<{
  kind: ProcessStoppingKind
  label: string
  title: string
  variant: 'danger' | 'warning'
} | null>(() => {
  if (processStoppingKind.value === 'automation_block') {
    return {
      kind: 'automation_block',
      label: PROCESS_STOPPING_BADGE_LABEL.automation_block,
      title: 'Алерт блокирует автоматический процесс до ручного решения.',
      variant: 'danger',
    }
  }

  if (processStoppingKind.value === 'safety') {
    return {
      kind: 'safety',
      label: PROCESS_STOPPING_BADGE_LABEL.safety,
      title: 'Safety-critical алерт по железу или исполнительному каналу.',
      variant: 'danger',
    }
  }

  return null
})
</script>
