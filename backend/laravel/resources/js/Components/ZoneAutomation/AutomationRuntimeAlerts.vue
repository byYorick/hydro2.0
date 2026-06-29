<template>
  <div
    v-if="hasContent"
    class="space-y-2"
  >
    <div
      v-if="failed"
      class="rounded-xl border px-3 py-2.5 text-sm"
      :class="activeFailure
        ? 'border-red-400/35 bg-red-500/10'
        : 'border-amber-400/35 bg-amber-500/10'"
    >
      <p
        class="font-semibold"
        :class="activeFailure ? 'text-red-300' : 'text-amber-200'"
      >
        {{ activeFailure ? 'Сбой автоматики' : 'Последний сбой автоматики' }}
      </p>
      <p
        v-if="humanErrorMessage"
        class="mt-1 text-xs break-words"
        :class="activeFailure ? 'text-red-200/85' : 'text-amber-100/90'"
      >
        {{ humanErrorMessage }}
      </p>
      <p
        v-if="errorCode"
        class="mt-1 font-mono text-[11px]"
        :class="activeFailure ? 'text-red-300/70' : 'text-amber-200/70'"
      >
        {{ errorCode }}
      </p>
      <p
        v-if="historicalFailure"
        class="mt-1 text-[10px] opacity-75"
        :class="activeFailure ? 'text-red-200/70' : 'text-amber-100/80'"
      >
        Активный алерт подтверждён; показан последний terminal failure из БД.
      </p>
    </div>

    <p
      v-if="errorMessage"
      class="text-xs text-red-400"
    >
      {{ errorMessage }}
    </p>

    <p
      v-if="connectivityWarning"
      class="rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200"
    >
      {{ connectivityWarning }}
    </p>

    <div
      v-if="isStale"
      class="flex flex-wrap items-center gap-2 text-xs text-amber-300/90"
    >
      <span class="rounded-full border border-amber-400/40 bg-amber-500/15 px-2 py-0.5">
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
