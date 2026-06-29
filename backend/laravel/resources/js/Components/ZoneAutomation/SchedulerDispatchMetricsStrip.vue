<template>
  <div
    v-if="hasContent"
    class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 px-3 py-2 text-xs"
    data-testid="scheduler-dispatch-metrics-strip"
  >
    <p class="font-medium text-[color:var(--text-primary)]">
      Метрики Laravel scheduler (глобально)
    </p>
    <p
      v-if="loading && !metrics"
      class="mt-1 text-[color:var(--text-muted)]"
    >
      Загрузка…
    </p>
    <p
      v-else-if="error"
      class="mt-1 text-[color:var(--badge-warning-text)]"
    >
      {{ error }}
    </p>
    <ul
      v-else-if="metrics"
      class="mt-1.5 space-y-0.5 font-mono text-[10px] text-[color:var(--text-primary)]"
    >
      <li v-if="metrics.pendingIntents != null">
        pending_intents={{ metrics.pendingIntents }}
      </li>
      <li v-if="metrics.oldestPendingAgeSec != null">
        oldest_pending_age_sec={{ Math.round(metrics.oldestPendingAgeSec) }}
      </li>
      <li v-if="metrics.dispatchCycleOverrunSec != null">
        cycle_overrun_sec={{ metrics.dispatchCycleOverrunSec.toFixed(1) }}
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSchedulerDispatchMetrics } from '@/composables/useSchedulerDispatchMetrics'

const { metrics, loading, error } = useSchedulerDispatchMetrics()

const hasContent = computed(() =>
  loading.value
  || error.value !== null
  || metrics.value !== null,
)
</script>
