<template>
  <div
    v-if="hasContent"
    class="space-y-2"
  >
    <div
      v-if="failed"
      class="rounded-xl border px-3 py-2.5 text-sm"
      :class="activeFailure
        ? 'border-status-critical bg-status-critical-soft'
        : 'border-status-warning bg-status-warning-soft'"
    >
      <p
        class="font-semibold"
        :class="activeFailure ? 'text-status-critical' : 'text-status-warning'"
      >
        {{ activeFailure ? 'Сбой автоматики' : 'Последний сбой автоматики' }}
      </p>
      <p
        v-if="humanErrorMessage"
        class="mt-1 text-xs break-words"
        :class="activeFailure ? 'text-status-critical' : 'text-status-warning'"
      >
        {{ humanErrorMessage }}
      </p>
      <p
        v-if="errorCode"
        class="mt-1 font-mono text-[11px]"
        :class="activeFailure ? 'text-status-critical' : 'text-status-warning'"
      >
        {{ errorCode }}
      </p>
      <p
        v-if="historicalFailure"
        class="mt-1 text-[10px] opacity-75"
        :class="activeFailure ? 'text-status-critical' : 'text-status-warning'"
      >
        Активный алерт подтверждён; показан последний terminal failure из БД.
      </p>
    </div>

    <p
      v-if="errorMessage"
      class="text-xs text-status-critical"
    >
      {{ errorMessage }}
    </p>

    <p
      v-if="connectivityWarning"
      class="rounded-lg border border-status-warning bg-status-warning-soft px-3 py-2 text-xs text-status-warning"
    >
      {{ connectivityWarning }}
    </p>

    <div
      v-if="isStale"
      class="flex flex-wrap items-center gap-2 text-xs text-status-warning"
    >
      <span class="rounded-full border border-status-warning bg-status-warning-soft px-2 py-0.5">
        Данные из кэша
      </span>
      <span
        v-if="staleDuration"
        class="text-[color:var(--text-muted)]"
      >
        устарели {{ staleDuration }} назад
      </span>
      <span
        v-if="dataTimestamp"
        class="text-[color:var(--text-dim)]"
      >
        снимок {{ dataTimestamp }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  failed?: boolean
  activeFailure?: boolean
  historicalFailure?: boolean
  humanErrorMessage?: string | null
  errorCode?: string | null
  errorMessage?: string | null
  connectivityWarning?: string | null
  isStale?: boolean
  staleDuration?: string | null
  dataTimestamp?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  failed: false,
  activeFailure: false,
  historicalFailure: false,
  humanErrorMessage: null,
  errorCode: null,
  errorMessage: null,
  connectivityWarning: null,
  isStale: false,
  staleDuration: null,
  dataTimestamp: null,
})

const hasContent = computed(() =>
  props.failed
  || Boolean(props.errorMessage)
  || Boolean(props.connectivityWarning)
  || props.isStale,
)
</script>
