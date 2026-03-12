<template>
  <Card>
    <div class="space-y-3">
      <div class="flex items-center justify-between gap-3">
        <div class="text-sm font-semibold">Relay автотюнинг</div>
        <div class="flex gap-1">
          <Button
            size="sm"
            :variant="selectedType === 'ph' ? 'default' : 'outline'"
            @click="selectedType = 'ph'"
          >
            pH
          </Button>
          <Button
            size="sm"
            :variant="selectedType === 'ec' ? 'default' : 'outline'"
            @click="selectedType = 'ec'"
          >
            EC
          </Button>
        </div>
      </div>

      <div class="text-xs space-y-1">
        <div
          v-if="status?.status === 'running'"
          class="flex items-center gap-2 text-[color:var(--badge-info-text)]"
        >
          <span class="animate-pulse">●</span>
          <span>
            Выполняется: {{ status.progress?.cycles_detected ?? 0 }}/{{ status.progress?.min_cycles ?? 3 }} циклов
            ({{ formatElapsed(status.progress?.elapsed_sec) }})
          </span>
        </div>

        <div
          v-else-if="status?.status === 'complete'"
          class="text-[color:var(--badge-success-text)]"
        >
          Завершён: Kp={{ tunedKp ?? '?' }}, Ki={{ tunedKi ?? '?' }},
          Au={{ formatOptionalNumber(status.result?.oscillation_amplitude, 4) ?? '?' }},
          циклов={{ status.result?.cycles_detected ?? 0 }}
        </div>

        <div
          v-else-if="status?.status === 'timeout'"
          class="text-[color:var(--badge-warning-text)]"
        >
          Таймаут. Система не вошла в устойчивые колебания.
        </div>

        <div
          v-else
          class="text-[color:var(--text-dim)]"
        >
          Не запускался
        </div>
      </div>

      <div class="rounded-md bg-[color:var(--bg-elevated)] p-2 text-xs text-[color:var(--text-dim)]">
        Relay-автотюнинг занимает 1-2 часа. Во время процедуры PID заменяется relay-режимом.
        После завершения коэффициенты сохраняются в конфиг PID.
      </div>

      <Button
        size="sm"
        variant="outline"
        :disabled="isRunning || starting"
        @click="startAutotune"
      >
        <span v-if="starting">Запуск...</span>
        <span v-else-if="isRunning">Выполняется ({{ status?.progress?.cycles_detected ?? 0 }}/{{ status?.progress?.min_cycles ?? 3 }})</span>
        <span v-else>Запустить автотюнинг {{ selectedType.toUpperCase() }}</span>
      </Button>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
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
