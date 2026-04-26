<template>
  <ShellCard title="Relay автотюнинг">
    <template #actions>
      <Button
        size="sm"
        :variant="selectedType === 'ph' ? 'primary' : 'secondary'"
        @click="selectedType = 'ph'"
      >
        pH
      </Button>
      <Button
        size="sm"
        :variant="selectedType === 'ec' ? 'primary' : 'secondary'"
        @click="selectedType = 'ec'"
      >
        EC
      </Button>
    </template>

    <div class="flex flex-col gap-2.5">
      <div class="text-xs">
        <div
          v-if="status?.status === 'running'"
          class="flex items-center gap-2 text-brand"
        >
          <span class="animate-pulse font-mono">●</span>
          <span>
            Выполняется:
            <span class="font-mono">{{ status.progress?.cycles_detected ?? 0 }}/{{ status.progress?.min_cycles ?? 3 }}</span>
            циклов
            <span class="text-[var(--text-dim)]">({{ formatElapsed(status.progress?.elapsed_sec) }})</span>
          </span>
        </div>

        <div
          v-else-if="status?.status === 'complete'"
          class="flex items-center gap-2 text-growth"
        >
          <span class="font-mono">✓</span>
          <span>
            Завершён:
            <span class="font-mono">Kp={{ tunedKp ?? '?' }}</span>,
            <span class="font-mono">Ki={{ tunedKi ?? '?' }}</span>,
            <span class="font-mono">Au={{ formatOptionalNumber(status.result?.oscillation_amplitude, 4) ?? '?' }}</span>,
            циклов <span class="font-mono">{{ status.result?.cycles_detected ?? 0 }}</span>
          </span>
        </div>

        <div
          v-else-if="status?.status === 'timeout'"
          class="flex items-center gap-2 text-warn"
        >
          <span class="font-mono">!</span>
          <span>Таймаут. Система не вошла в устойчивые колебания.</span>
        </div>

        <div
          v-else
          class="text-[var(--text-dim)]"
        >
          Не запускался
        </div>
      </div>

      <Hint :show="true">
        Relay-автотюнинг занимает 1-2 часа. Во время процедуры PID заменяется
        relay-режимом. После завершения коэффициенты сохраняются в конфиг PID.
      </Hint>

      <Button
        size="sm"
        variant="primary"
        :disabled="isRunning || starting"
        @click="startAutotune"
      >
        <span v-if="starting">Запуск...</span>
        <span
          v-else-if="isRunning"
        >Выполняется ({{ status?.progress?.cycles_detected ?? 0 }}/{{ status?.progress?.min_cycles ?? 3 }})</span>
        <span v-else>▶ Запустить автотюнинг {{ selectedType.toUpperCase() }}</span>
      </Button>
    </div>
  </ShellCard>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import ShellCard from '@/Components/Launch/Shell/ShellCard.vue'
import { Hint } from '@/Components/Shared/Primitives'
import { usePidConfig } from '@/composables/usePidConfig'
import type { RelayAutotuneStatus } from '@/types/PidConfig'

const props = defineProps<{ zoneId: number }>()

const selectedType = ref<'ph' | 'ec'>('ph')
const status = ref<RelayAutotuneStatus | null>(null)
const starting = ref(false)
let pollInterval: ReturnType<typeof setInterval> | null = null

const { getRelayAutotuneStatus, startRelayAutotune } = usePidConfig()

const isRunning = computed(() => status.value?.status === 'running')

const tunedKp = computed(() => {
  const result = status.value?.result
  if (!result?.ku) return null
  return formatOptionalNumber(0.45 * result.ku, 3)
})

const tunedKi = computed(() => {
  const result = status.value?.result
  if (!result?.ku || !result?.tu_sec || result.tu_sec <= 0) return null
  const kp = 0.45 * result.ku
  const ti = 0.83 * result.tu_sec
  return formatOptionalNumber(kp / ti, 5)
})

function formatOptionalNumber(value: number | undefined | null, digits: number): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return null
  }
  return Number(value).toFixed(digits)
}

function formatElapsed(sec?: number): string {
  if (!sec || sec <= 0) return '0 мин'
  return `${Math.round(sec / 60)} мин`
}

function stopPolling(): void {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

function syncPollingState(): void {
  if (isRunning.value && !pollInterval) {
    pollInterval = setInterval(() => {
      void loadStatus()
    }, 10_000)
    return
  }
  if (!isRunning.value) {
    stopPolling()
  }
}

async function loadStatus(): Promise<void> {
  status.value = await getRelayAutotuneStatus(props.zoneId, selectedType.value)
  syncPollingState()
}

async function startAutotune(): Promise<void> {
  if (starting.value || isRunning.value) return
  starting.value = true
  try {
    await startRelayAutotune(props.zoneId, selectedType.value)
    await loadStatus()
  } finally {
    starting.value = false
  }
}

watch(selectedType, () => {
  stopPolling()
  void loadStatus()
})

onMounted(() => {
  void loadStatus()
})

onUnmounted(() => {
  stopPolling()
})
</script>
