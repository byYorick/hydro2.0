<template>
  <div class="relative flex items-start gap-3 border-b border-[color:var(--border-muted)] pb-2">
    <span
      class="absolute left-0 top-0 h-full w-1 -ml-3"
      :class="severityRailClass(item)"
    />
    <Badge
      :variant="alertBadgeVariant(item.status)"
      class="text-xs shrink-0 mt-0.5"
    >
      {{ translateStatus(item.status) }}
    </Badge>
    <div class="flex-1 min-w-0 space-y-1">
      <div class="flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-dim)]">
        <span>{{ formatAlertDate(item.created_at) }}</span>
        <span class="font-semibold text-[color:var(--text-primary)]">
          {{ getAlertTitle(item) }}
        </span>
        <span
          v-if="item.code"
          class="font-mono text-[color:var(--text-dim)]"
        >
          {{ item.code }}
        </span>
      </div>
      <div class="text-sm text-[color:var(--text-primary)] break-words">
        {{ getAlertMessage(item) || 'Без сообщения' }}
      </div>
      <div class="text-xs text-[color:var(--text-dim)]">
        {{
          normalizeAlertStatus(item.status) === 'RESOLVED'
            ? `Решён: ${formatAlertDate(item.resolved_at || item.updated_at)}`
            : 'Нажмите, чтобы открыть детали и закрыть алерт'
        }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'
import { translateStatus } from '@/utils/i18n'
import type { Alert } from '@/types/Alert'
import {
  alertBadgeVariant,
  formatAlertDate,
  getAlertMessage,
  getAlertTitle,
  normalizeAlertStatus,
  severityRailClass,
} from '@/utils/alertMeta'

defineProps<{
  item: Alert
}>()
</script>

