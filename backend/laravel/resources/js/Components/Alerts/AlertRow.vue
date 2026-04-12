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
