<template>
  <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
    <div class="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
      <div class="space-y-2 min-w-0">
        <p class="text-[11px] uppercase tracking-[0.22em] text-[color:var(--text-dim)]">workflow</p>
        <div class="flex flex-wrap items-center gap-2">
          <Badge :variant="stateBadgeVariant">
            {{ stateCode }}
          </Badge>
          <span class="text-sm text-[color:var(--text-primary)]">{{ stateLabel }}</span>
          <Badge
            v-if="isStale"
            variant="warning"
          >
            кэш{{ staleDuration ? ` · ${staleDuration}` : '' }}
          </Badge>
        </div>
      </div>
      <Badge
        v-if="isProcessActive"
        variant="info"
      >
        Выполняется
      </Badge>
    </div>

    <!-- Error banner -->
    <div
      v-if="hasFailed"
      class="rounded-xl border border-red-400/30 bg-red-500/10 px-3 py-2 text-sm space-y-0.5"
    >
      <p class="font-semibold text-red-400">Ошибка выполнения</p>
      <p
        v-if="errorCode"
        class="text-xs text-red-300/80 font-mono"
      >{{ errorCode }}</p>
      <p
        v-if="errorMessage"
        class="text-xs text-red-300/70 break-words"
      >{{ errorMessage }}</p>
    </div>

    <!-- Current stage -->
    <div
      v-if="currentStageLabel"
      class="text-xs text-[color:var(--text-muted)] flex items-center gap-1.5"
    >
      <span class="text-[color:var(--text-dim)]">Стадия:</span>
      <span>{{ currentStageLabel }}</span>
    </div>

    <!-- Data timestamp -->
    <div
      v-if="dataTimestamp"
      class="text-[11px] text-[color:var(--text-dim)]"
    >
      Данные: {{ dataTimestamp }}
    </div>

    <div
      v-if="hasProgress"
      class="space-y-1"
    >
      <div class="flex items-center justify-between text-xs text-[color:var(--text-muted)]">
        <span>Прогресс фазы</span>
        <span>{{ progressPercent }}%</span>
      </div>
      <div class="h-2 rounded-full bg-[color:var(--surface-muted)]/60 overflow-hidden">
        <div
          class="h-full bg-[color:var(--accent,#3b82f6)] transition-all duration-300"
          :style="{ width: `${progressPercent}%` }"
        />
      </div>
    </div>

    <div
      v-if="lastSnapshot?.irr_node_state"
      class="text-xs text-[color:var(--text-muted)] flex flex-wrap items-center gap-3"
    >
      <span>IRR node:</span>
      <span>pump={{ boolFlag(lastSnapshot.irr_node_state.pump_main) }}</span>
      <span>clean_max={{ boolFlag(lastSnapshot.irr_node_state.clean_level_max) }}</span>
      <span>solution_max={{ boolFlag(lastSnapshot.irr_node_state.solution_level_max) }}</span>
    </div>

    <div class="border-t border-[color:var(--border-muted)] pt-3">
      <button
        type="button"
        class="w-full rounded-xl px-3 py-2 text-left transition-colors hover:bg-[color:var(--surface-muted)]/40"
        @click="processExpanded = !processExpanded"
      >
        <div class="flex items-center justify-between gap-3">
          <span class="text-sm font-semibold text-[color:var(--text-primary)]">
            Процесс выполнения автоматизации
          </span>
          <svg
            class="w-5 h-5 text-[color:var(--text-dim)] transition-transform duration-200"
            :class="{ 'rotate-180': processExpanded }"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        </div>
      </button>

      <div
        v-show="processExpanded"
        class="pt-3"
      >
        <AutomationProcessPanel
          :zone-id="zoneId"
          :fallback-tanks-count="fallbackTanksCount"
          :fallback-system-type="fallbackSystemType"
          @state-change="handleStateChange"
          @state-snapshot="handleStateSnapshot"
        />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import AutomationProcessPanel from '@/Components/AutomationProcessPanel.vue'
import Badge from '@/Components/Badge.vue'
import type { IrrigationSystem } from '@/composables/zoneAutomationTypes'
import type { AutomationState, AutomationStateType } from '@/types/Automation'

interface Props {
  zoneId: number | null
  fallbackTanksCount?: number
  fallbackSystemType?: IrrigationSystem
}

const props = withDefaults(defineProps<Props>(), {
  fallbackTanksCount: 2,
  fallbackSystemType: 'drip',
})

const emit = defineEmits<{
  (e: 'state-change', state: AutomationStateType): void
  (e: 'state-snapshot', snapshot: AutomationState): void
}>()

const processExpanded = ref(false)
const processState = ref<AutomationStateType>('IDLE')
const lastSnapshot = ref<AutomationState | null>(null)
const nowMs = ref(Date.now())
let staleTimer: ReturnType<typeof setInterval> | null = null

const stateCode = computed(() => lastSnapshot.value?.state ?? processState.value)
const stateLabel = computed(() => lastSnapshot.value?.state_label || 'Ожидание данных')
const isProcessActive = computed(() => stateCode.value !== 'IDLE' && stateCode.value !== 'READY')
const isStale = computed(() => Boolean(lastSnapshot.value?.state_meta?.is_stale))
const hasProgress = computed(() => {
  const progress = Number(lastSnapshot.value?.state_details.progress_percent ?? 0)
  const eta = Number(lastSnapshot.value?.estimated_completion_sec ?? 0)
  return progress > 0 || eta > 0
})
const progressPercent = computed(() => {
  const raw = Number(lastSnapshot.value?.state_details.progress_percent ?? 0)
  if (!Number.isFinite(raw)) return 0
  return Math.max(0, Math.min(100, Math.round(raw)))
})
const stateBadgeVariant = computed<'neutral' | 'info' | 'warning' | 'success'>(() => {
  const map: Record<AutomationStateType, 'neutral' | 'info' | 'warning' | 'success'> = {
    IDLE: 'neutral',
    TANK_FILLING: 'info',
    TANK_RECIRC: 'warning',
    READY: 'success',
    IRRIGATING: 'info',
    IRRIG_RECIRC: 'warning',
  }
  return map[stateCode.value]
})

const hasFailed = computed(() => Boolean(lastSnapshot.value?.state_details?.failed))
const errorCode = computed(() => lastSnapshot.value?.state_details?.error_code ?? null)
const errorMessage = computed(() => lastSnapshot.value?.state_details?.error_message ?? null)
const currentStageLabel = computed(
  () => lastSnapshot.value?.current_stage_label ?? lastSnapshot.value?.current_stage ?? null
)
const dataTimestamp = computed(() => {
  const servedAt = lastSnapshot.value?.state_meta?.served_at
  if (!servedAt) return null
  try {
    return new Date(servedAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return servedAt
  }
})

const staleDuration = computed(() => {
  if (!isStale.value) return null
  const servedAt = lastSnapshot.value?.state_meta?.served_at
  if (!servedAt) return null
  const servedAtMs = Date.parse(servedAt)
  if (!Number.isFinite(servedAtMs)) return null
  const elapsedSec = Math.max(0, Math.floor((nowMs.value - servedAtMs) / 1000))
  const mm = Math.floor(elapsedSec / 60)
  const ss = elapsedSec % 60
  return `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
})

function handleStateChange(state: AutomationStateType): void {
  processState.value = state
  emit('state-change', state)
}

function handleStateSnapshot(snapshot: AutomationState): void {
  lastSnapshot.value = snapshot
  emit('state-snapshot', snapshot)
}

function boolFlag(value: boolean | null | undefined): string {
  if (value === true) return 'on'
  if (value === false) return 'off'
  return 'n/a'
}

onMounted(() => {
  staleTimer = setInterval(() => {
    nowMs.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  if (staleTimer) {
    clearInterval(staleTimer)
    staleTimer = null
  }
})

const zoneId = computed(() => props.zoneId)
const fallbackTanksCount = computed(() => props.fallbackTanksCount)
const fallbackSystemType = computed(() => props.fallbackSystemType)
</script>
