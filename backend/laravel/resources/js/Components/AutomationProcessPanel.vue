<template>
  <section class="automation-process-panel surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 md:p-5">
    <header class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div class="space-y-1">
        <p class="text-[11px] uppercase tracking-[0.22em] text-[color:var(--text-dim)]">автоматизация</p>
        <h3 class="text-base md:text-lg font-semibold text-[color:var(--text-primary)]">
          {{ stateLabel }}
        </h3>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <StatusIndicator
          :status="stateCode"
          :variant="stateVariant"
          :pulse="isProcessActive"
          :show-label="true"
        />
        <div class="text-sm text-[color:var(--text-muted)]">
          {{ progressSummary }}
        </div>
      </div>
    </header>

    <p
      v-if="errorMessage"
      class="mt-3 text-xs text-red-500"
    >
      {{ errorMessage }}
    </p>

    <div class="mt-4 overflow-x-auto">
      <svg
        class="process-svg min-w-[760px]"
        viewBox="0 0 840 430"
        role="img"
        aria-label="Схема процесса автоматизации зоны"
      >
        <defs>
          <linearGradient id="automation-clean-water-gradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="rgba(93,214,255,0.88)" />
            <stop offset="100%" stop-color="rgba(93,214,255,0.34)" />
          </linearGradient>
          <linearGradient id="automation-nutrient-gradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="rgba(73,224,138,0.9)" />
            <stop offset="100%" stop-color="rgba(73,224,138,0.36)" />
          </linearGradient>
          <linearGradient id="automation-buffer-gradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="rgba(240,178,104,0.88)" />
            <stop offset="100%" stop-color="rgba(240,178,104,0.34)" />
          </linearGradient>
        </defs>

        <g
          class="tank-group"
          @mouseenter="handleHover('clean', $event)"
          @mouseleave="handleLeave"
        >
          <rect class="tank-shell" x="70" y="70" width="150" height="250" rx="14" />
          <rect
            class="tank-fill"
            x="70"
            :y="tankFillY(cleanTankLevel)"
            width="150"
            :height="tankFillHeight(cleanTankLevel)"
            rx="14"
            fill="url(#automation-clean-water-gradient)"
          />
          <text class="tank-level" x="145" y="195">{{ Math.round(cleanTankLevel) }}%</text>
          <text class="tank-title" x="145" y="347">Чистая вода</text>
        </g>

        <g
          class="tank-group"
          @mouseenter="handleHover('nutrient', $event)"
          @mouseleave="handleLeave"
        >
          <rect class="tank-shell" x="350" y="70" width="150" height="250" rx="14" />
          <rect
            class="tank-fill"
            x="350"
            :y="tankFillY(nutrientTankLevel)"
            width="150"
            :height="tankFillHeight(nutrientTankLevel)"
            rx="14"
            fill="url(#automation-nutrient-gradient)"
          />
          <text class="tank-level" x="425" y="195">{{ Math.round(nutrientTankLevel) }}%</text>
          <text class="tank-title" x="425" y="347">Раствор NPK</text>
        </g>

        <g
          v-if="tanksCount === 3"
          class="tank-group"
          @mouseenter="handleHover('buffer', $event)"
          @mouseleave="handleLeave"
        >
          <rect class="tank-shell" x="630" y="70" width="150" height="250" rx="14" />
          <rect
            class="tank-fill"
            x="630"
            :y="tankFillY(bufferTankLevel)"
            width="150"
            :height="tankFillHeight(bufferTankLevel)"
            rx="14"
            fill="url(#automation-buffer-gradient)"
          />
          <text class="tank-level" x="705" y="195">{{ Math.round(bufferTankLevel) }}%</text>
          <text class="tank-title" x="705" y="347">Буфер / дренаж</text>
        </g>

        <g
          id="pipes"
          @mouseenter="handleHover('pipes', $event)"
          @mouseleave="handleLeave"
        >
          <line
            x1="220"
            y1="210"
            x2="350"
            y2="210"
            class="pipe-line"
            :class="{ 'pipe-line--active': isPumpInActive }"
          />
          <circle
            v-if="isPumpInActive"
            class="flow-dot"
            r="5"
            :cx="flowDotForwardX"
            cy="210"
          />

          <line
            x1="350"
            y1="250"
            x2="220"
            y2="250"
            class="pipe-line"
            :class="{ 'pipe-line--active': isCirculationActive }"
          />
          <circle
            v-if="isCirculationActive"
            class="flow-dot flow-dot--reverse"
            r="5"
            :cx="flowDotReverseX"
            cy="250"
          />

          <line
            v-if="tanksCount === 3"
            x1="500"
            y1="210"
            x2="630"
            y2="210"
            class="pipe-line"
            :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }"
          />
        </g>

        <g
          transform="translate(548, 118)"
          @mouseenter="handleHover('correction', $event)"
          @mouseleave="handleLeave"
        >
          <circle
            cx="0"
            cy="0"
            r="22"
            class="correction-indicator"
            :class="{ 'correction-indicator--active': isPhCorrectionActive }"
          />
          <text x="0" y="5" class="correction-text">pH</text>

          <circle
            cx="55"
            cy="0"
            r="22"
            class="correction-indicator correction-indicator--ec"
            :class="{ 'correction-indicator--active': isEcCorrectionActive }"
          />
          <text x="55" y="5" class="correction-text">EC</text>
        </g>

        <g
          class="correction-node-group"
          @mouseenter="handleHover('correction_node', $event)"
          @mouseleave="handleLeave"
        >
          <line
            x1="500"
            y1="210"
            x2="560"
            y2="210"
            class="pipe-line"
            :class="{ 'pipe-line--active': isCorrectionNodeActive }"
          />
          <circle
            v-if="isCorrectionNodeActive"
            class="flow-dot flow-dot--correction"
            r="4"
            :cx="correctionFlowX"
            cy="210"
          />

          <rect
            x="560"
            y="172"
            width="190"
            height="96"
            rx="12"
            class="correction-unit"
            :class="{ 'correction-unit--active': isCorrectionNodeActive }"
          />
          <text x="655" y="192" class="correction-unit-title">Узел коррекции</text>

          <g
            @mouseenter="handleHover('valve_in', $event)"
            @mouseleave="handleLeave"
          >
            <circle
              cx="585"
              cy="221"
              r="13"
              class="valve-icon"
              :class="{ 'valve-icon--open': isInletValveOpen }"
            />
            <text x="585" y="225" class="valve-label">V1</text>
          </g>

          <g
            @mouseenter="handleHover('pump_correction', $event)"
            @mouseleave="handleLeave"
          >
            <rect
              x="636"
              y="201"
              width="38"
              height="38"
              rx="8"
              class="pump-icon"
              :class="{ 'pump-icon--active pump-icon--correction': isCorrectionPumpActive }"
            />
            <text x="655" y="226" class="pump-text">P3</text>
          </g>

          <g
            @mouseenter="handleHover('valve_out', $event)"
            @mouseleave="handleLeave"
          >
            <circle
              cx="725"
              cy="221"
              r="13"
              class="valve-icon"
              :class="{ 'valve-icon--open': isOutletValveOpen }"
            />
            <text x="725" y="225" class="valve-label">V2</text>
          </g>
        </g>

        <g
          transform="translate(288, 192)"
          @mouseenter="handleHover('pump_in', $event)"
          @mouseleave="handleLeave"
        >
          <rect class="pump-icon" :class="{ 'pump-icon--active': isPumpInActive }" width="42" height="42" rx="9" />
          <text x="21" y="26" class="pump-text">P1</text>
        </g>
        <g
          transform="translate(288, 232)"
          @mouseenter="handleHover('circulation', $event)"
          @mouseleave="handleLeave"
        >
          <rect class="pump-icon" :class="{ 'pump-icon--active': isCirculationActive }" width="42" height="42" rx="9" />
          <text x="21" y="26" class="pump-text">P2</text>
        </g>
      </svg>
    </div>

    <div
      v-if="hoveredElement"
      class="details-tooltip"
      :style="tooltipStyle"
    >
      <div class="tooltip-title">{{ hoveredElement.title }}</div>
      <div class="tooltip-grid">
        <div
          v-for="(value, key) in hoveredElement.data"
          :key="key"
          class="tooltip-row"
        >
          <span class="tooltip-label">{{ key }}</span>
          <span class="tooltip-value">{{ value }}</span>
        </div>
      </div>
    </div>

    <div class="mt-4 border-t border-[color:var(--border-muted)] pt-3">
      <h4 class="text-xs uppercase tracking-[0.18em] text-[color:var(--text-dim)] mb-2">Timeline</h4>
      <ul class="space-y-2 max-h-44 overflow-y-auto pr-1">
        <li
          v-for="event in timelineEvents"
          :key="`${event.event}-${event.timestamp}`"
          class="timeline-item"
          :class="{ 'timeline-item--active': event.active }"
        >
          <span class="timeline-dot"></span>
          <span class="timeline-label">{{ event.label || event.event }}</span>
          <span class="timeline-time">{{ formatTime(event.timestamp) }}</span>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import StatusIndicator from '@/Components/StatusIndicator.vue'
import type { AutomationState, AutomationStateType, AutomationTimelineEvent, HoveredElement } from '@/types/Automation'
import type { IrrigationSystem } from '@/composables/zoneAutomationTypes'
import { readBooleanEnv } from '@/utils/env'
import { getEchoInstance, onWsStateChange } from '@/utils/echoClient'
import { logger } from '@/utils/logger'
import type { EchoChannelLike, WsEventPayload } from '@/ws/subscriptionTypes'

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
}>()

const automationState = ref<AutomationState | null>(null)
const errorMessage = ref<string | null>(null)
const hoveredElement = ref<HoveredElement | null>(null)
const flowOffset = ref(0)

const WS_ZONE_EVENT_NAMES = [
  '.telemetry.batch.updated',
  '.App\\Events\\TelemetryBatchUpdated',
  '.node.telemetry.updated',
  '.App\\Events\\NodeTelemetryUpdated',
  '.GrowCycleUpdated',
  '.App\\Events\\GrowCycleUpdated',
  '.ZoneUpdated',
  '.App\\Events\\ZoneUpdated',
] as const

const WS_COMMAND_EVENT_NAMES = [
  '.CommandStatusUpdated',
  '.App\\Events\\CommandStatusUpdated',
  '.CommandFailed',
  '.App\\Events\\CommandFailed',
] as const

const WS_MIN_REFRESH_INTERVAL_MS = 1200
const FALLBACK_POLL_INTERVAL_MS = 30000
const FLOW_TICK_INTERVAL_MS = 80
const wsEnabled = readBooleanEnv('VITE_ENABLE_WS', true)

let fetchInFlight = false
let fetchQueued = false

function clampPercent(value: unknown): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 0
  return Math.max(0, Math.min(100, parsed))
}

function normalizeState(raw: unknown): AutomationState {
  const source = (raw && typeof raw === 'object' ? raw : {}) as Partial<AutomationState>
  const state = String(source.state || 'IDLE') as AutomationStateType
  const tanksRaw = Number(source.system_config?.tanks_count ?? props.fallbackTanksCount)
  const tanksCount: 2 | 3 = tanksRaw === 3 ? 3 : 2

  return {
    zone_id: Number(source.zone_id ?? props.zoneId ?? 0),
    state,
    state_label: String(source.state_label || ''),
    state_details: {
      started_at: source.state_details?.started_at ?? null,
      elapsed_sec: Number(source.state_details?.elapsed_sec ?? 0),
      progress_percent: clampPercent(source.state_details?.progress_percent ?? 0),
    },
    system_config: {
      tanks_count: tanksCount,
      system_type: (source.system_config?.system_type as IrrigationSystem) || props.fallbackSystemType,
      clean_tank_capacity_l: source.system_config?.clean_tank_capacity_l ?? null,
      nutrient_tank_capacity_l: source.system_config?.nutrient_tank_capacity_l ?? null,
    },
    current_levels: {
      clean_tank_level_percent: clampPercent(source.current_levels?.clean_tank_level_percent ?? 0),
      nutrient_tank_level_percent: clampPercent(source.current_levels?.nutrient_tank_level_percent ?? 0),
      buffer_tank_level_percent: source.current_levels?.buffer_tank_level_percent ?? null,
      ph: source.current_levels?.ph ?? null,
      ec: source.current_levels?.ec ?? null,
    },
    active_processes: {
      pump_in: Boolean(source.active_processes?.pump_in),
      circulation_pump: Boolean(source.active_processes?.circulation_pump),
      ph_correction: Boolean(source.active_processes?.ph_correction),
      ec_correction: Boolean(source.active_processes?.ec_correction),
    },
    timeline: Array.isArray(source.timeline) ? source.timeline : [],
    next_state: source.next_state ?? null,
    estimated_completion_sec: source.estimated_completion_sec ?? null,
  }
}

async function fetchAutomationState(): Promise<void> {
  if (!props.zoneId) {
    return
  }

  if (fetchInFlight) {
    fetchQueued = true
    return
  }

  fetchInFlight = true

  try {
    const response = await fetch(`/api/zones/${props.zoneId}/automation-state`, {
      headers: { Accept: 'application/json' },
    })

    if (!response.ok) {
      throw new Error(`http_${response.status}`)
    }

    const payload = await response.json()
    const normalized = normalizeState(payload)
    automationState.value = normalized
    emit('state-change', normalized.state)
    errorMessage.value = null
  } catch (error) {
    const message = error instanceof Error ? error.message : 'unknown_error'
    errorMessage.value = `Не удалось получить состояние автоматизации (${message}).`
  } finally {
    fetchInFlight = false
    if (fetchQueued) {
      fetchQueued = false
      void fetchAutomationState()
    }
  }
}

let flowTimer: ReturnType<typeof setInterval> | null = null
let fallbackPollingTimer: ReturnType<typeof setInterval> | null = null
let wsRefreshTimer: ReturnType<typeof setTimeout> | null = null
let wsStateListenerCleanup: (() => void) | null = null
let zoneChannel: EchoChannelLike | null = null
let commandsChannel: EchoChannelLike | null = null
let zoneChannelName: string | null = null
let commandsChannelName: string | null = null
let lastRealtimeRefreshAt = 0

const zoneEventHandlers = new Map<string, (payload: WsEventPayload) => void>()
const commandEventHandlers = new Map<string, (payload: WsEventPayload) => void>()

function clearWsRefreshTimer(): void {
  if (wsRefreshTimer !== null) {
    clearTimeout(wsRefreshTimer)
    wsRefreshTimer = null
  }
}

function stopFallbackPolling(): void {
  if (fallbackPollingTimer !== null) {
    clearInterval(fallbackPollingTimer)
    fallbackPollingTimer = null
  }
}

function startFallbackPolling(): void {
  if (fallbackPollingTimer !== null || !props.zoneId) {
    return
  }

  fallbackPollingTimer = setInterval(() => {
    void fetchAutomationState()
  }, FALLBACK_POLL_INTERVAL_MS)
}

function scheduleRealtimeRefresh(): void {
  const elapsed = Date.now() - lastRealtimeRefreshAt
  const waitMs = Math.max(0, WS_MIN_REFRESH_INTERVAL_MS - elapsed)

  if (waitMs === 0) {
    lastRealtimeRefreshAt = Date.now()
    void fetchAutomationState()
    return
  }

  if (wsRefreshTimer !== null) {
    return
  }

  wsRefreshTimer = setTimeout(() => {
    wsRefreshTimer = null
    lastRealtimeRefreshAt = Date.now()
    void fetchAutomationState()
  }, waitMs)
}

function cleanupRealtimeChannels(): void {
  const echo = getEchoInstance()

  if (zoneChannel) {
    zoneEventHandlers.forEach((handler, eventName) => {
      zoneChannel?.stopListening(eventName, handler)
    })
    zoneEventHandlers.clear()
  }

  if (commandsChannel) {
    commandEventHandlers.forEach((handler, eventName) => {
      commandsChannel?.stopListening(eventName, handler)
    })
    commandEventHandlers.clear()
  }

  if (echo && zoneChannelName) {
    echo.leave?.(zoneChannelName)
  }

  if (echo && commandsChannelName) {
    echo.leave?.(commandsChannelName)
  }

  zoneChannel = null
  commandsChannel = null
  zoneChannelName = null
  commandsChannelName = null
}

function subscribeRealtimeChannels(): boolean {
  if (!wsEnabled || !props.zoneId) {
    return false
  }

  const echo = getEchoInstance()
  if (!echo) {
    return false
  }

  cleanupRealtimeChannels()

  try {
    zoneChannelName = `hydro.zones.${props.zoneId}`
    zoneChannel = echo.private(zoneChannelName)

    WS_ZONE_EVENT_NAMES.forEach((eventName) => {
      const handler = () => {
        scheduleRealtimeRefresh()
      }
      zoneEventHandlers.set(eventName, handler)
      zoneChannel?.listen(eventName, handler)
    })

    commandsChannelName = `commands.${props.zoneId}`
    commandsChannel = echo.private(commandsChannelName)

    WS_COMMAND_EVENT_NAMES.forEach((eventName) => {
      const handler = () => {
        scheduleRealtimeRefresh()
      }
      commandEventHandlers.set(eventName, handler)
      commandsChannel?.listen(eventName, handler)
    })

    logger.debug('[AutomationProcessPanel] Realtime subscriptions started', {
      zoneId: props.zoneId,
      zoneChannel: zoneChannelName,
      commandsChannel: commandsChannelName,
    })

    return true
  } catch (error) {
    logger.warn('[AutomationProcessPanel] Failed to subscribe realtime channels', {
      zoneId: props.zoneId,
      error: error instanceof Error ? error.message : String(error),
    })
    cleanupRealtimeChannels()
    return false
  }
}

function tickFlow(): void {
  if (!(isPumpInActive.value || isCirculationActive.value)) {
    return
  }
  flowOffset.value += 0.03
  if (flowOffset.value > 1) {
    flowOffset.value = 0
  }
}

const stateCode = computed<AutomationStateType>(() => automationState.value?.state ?? 'IDLE')
const stateLabel = computed(() => {
  if (automationState.value?.state_label) {
    return automationState.value.state_label
  }
  const labels: Record<AutomationStateType, string> = {
    IDLE: 'Система в ожидании',
    TANK_FILLING: 'Набор бака с раствором',
    TANK_RECIRC: 'Рециркуляция бака',
    READY: 'Раствор готов к поливу',
    IRRIGATING: 'Полив',
    IRRIG_RECIRC: 'Рециркуляция после полива',
  }
  return labels[stateCode.value]
})

const stateVariant = computed<'neutral' | 'info' | 'warning' | 'success'>(() => {
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

const isProcessActive = computed(() => stateCode.value !== 'IDLE' && stateCode.value !== 'READY')
const tanksCount = computed(() => automationState.value?.system_config.tanks_count ?? (props.fallbackTanksCount === 3 ? 3 : 2))
const cleanTankLevel = computed(() => automationState.value?.current_levels.clean_tank_level_percent ?? 0)
const nutrientTankLevel = computed(() => automationState.value?.current_levels.nutrient_tank_level_percent ?? 0)
const bufferTankLevel = computed(() => clampPercent(automationState.value?.current_levels.buffer_tank_level_percent ?? 0))
const isPumpInActive = computed(() => Boolean(automationState.value?.active_processes.pump_in))
const isCirculationActive = computed(() => Boolean(automationState.value?.active_processes.circulation_pump))
const isPhCorrectionActive = computed(() => Boolean(automationState.value?.active_processes.ph_correction))
const isEcCorrectionActive = computed(() => Boolean(automationState.value?.active_processes.ec_correction))
const isCorrectionNodeActive = computed(() => isPhCorrectionActive.value || isEcCorrectionActive.value)
const isCorrectionPumpActive = computed(() => isCorrectionNodeActive.value)
const isInletValveOpen = computed(() => isPumpInActive.value || isCirculationActive.value)
const isOutletValveOpen = computed(() => isProcessActive.value || isCorrectionNodeActive.value)
const progressPercent = computed(() => clampPercent(automationState.value?.state_details.progress_percent ?? 0))

const flowDotForwardX = computed(() => 220 + (130 * flowOffset.value))
const flowDotReverseX = computed(() => 350 - (130 * flowOffset.value))
const correctionFlowX = computed(() => 500 + (60 * flowOffset.value))

const timelineEvents = computed<AutomationTimelineEvent[]>(() => {
  const timeline = automationState.value?.timeline ?? []
  return timeline.slice(-12)
})

function formatDuration(rawSeconds: number | null | undefined): string {
  if (!rawSeconds || rawSeconds <= 0) {
    return '00:00'
  }
  const total = Math.floor(rawSeconds)
  const mm = Math.floor(total / 60)
  const ss = total % 60
  return `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

const progressSummary = computed(() => {
  const elapsed = formatDuration(automationState.value?.state_details.elapsed_sec ?? 0)
  const eta = automationState.value?.estimated_completion_sec
  if (eta && eta > 0) {
    return `${Math.round(progressPercent.value)}% · ${elapsed} · ~${formatDuration(eta)}`
  }
  return `${Math.round(progressPercent.value)}% · ${elapsed}`
})

function tankFillY(levelPercent: number): number {
  const normalized = clampPercent(levelPercent)
  return 70 + 250 * (1 - normalized / 100)
}

function tankFillHeight(levelPercent: number): number {
  const normalized = clampPercent(levelPercent)
  return 250 * (normalized / 100)
}

function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '-'
  }
  return Number(value).toFixed(digits)
}

function elementData(element: string): Record<string, string> {
  if (element === 'clean') {
    return {
      'Уровень': `${Math.round(cleanTankLevel.value)}%`,
      'Объём': automationState.value?.system_config.clean_tank_capacity_l
        ? `${Math.round(Number(automationState.value.system_config.clean_tank_capacity_l))} л`
        : '—',
    }
  }
  if (element === 'nutrient') {
    return {
      'Уровень': `${Math.round(nutrientTankLevel.value)}%`,
      'pH': formatNumber(automationState.value?.current_levels.ph, 2),
      'EC': `${formatNumber(automationState.value?.current_levels.ec, 2)} mS/cm`,
    }
  }
  if (element === 'buffer') {
    return {
      'Уровень': `${Math.round(bufferTankLevel.value)}%`,
    }
  }
  if (element === 'pipes') {
    return {
      'Подача': isPumpInActive.value ? 'Активна' : 'Отключена',
      'Рециркуляция': isCirculationActive.value ? 'Активна' : 'Отключена',
    }
  }
  if (element === 'correction') {
    return {
      'Коррекция pH': isPhCorrectionActive.value ? 'Да' : 'Нет',
      'Коррекция EC': isEcCorrectionActive.value ? 'Да' : 'Нет',
    }
  }
  if (element === 'correction_node') {
    return {
      'Статус узла': isCorrectionNodeActive.value ? 'Активен' : 'Ожидание',
      'pH': formatNumber(automationState.value?.current_levels.ph, 2),
      'EC': `${formatNumber(automationState.value?.current_levels.ec, 2)} mS/cm`,
    }
  }
  if (element === 'valve_in') {
    return {
      'Клапан V1 (вход)': isInletValveOpen.value ? 'Открыт' : 'Закрыт',
    }
  }
  if (element === 'valve_out') {
    return {
      'Клапан V2 (выход)': isOutletValveOpen.value ? 'Открыт' : 'Закрыт',
    }
  }
  if (element === 'pump_in') {
    return {
      'Насос P1': isPumpInActive.value ? 'Включен' : 'Выключен',
    }
  }
  if (element === 'circulation') {
    return {
      'Насос P2': isCirculationActive.value ? 'Включен' : 'Выключен',
    }
  }
  if (element === 'pump_correction') {
    return {
      'Насос P3 (дозирование)': isCorrectionPumpActive.value ? 'Включен' : 'Выключен',
    }
  }
  return {}
}

function elementTitle(element: string): string {
  const map: Record<string, string> = {
    clean: 'Бак чистой воды',
    nutrient: 'Бак рабочего раствора',
    buffer: 'Буферный бак',
    pipes: 'Линии потока',
    correction: 'Контур коррекции',
    correction_node: 'Узел коррекции',
    valve_in: 'Входной клапан',
    valve_out: 'Выходной клапан',
    pump_in: 'Насос набора',
    circulation: 'Насос рециркуляции',
    pump_correction: 'Насос дозирования',
  }
  return map[element] ?? element
}

function handleHover(element: string, event: MouseEvent): void {
  const target = event.currentTarget
  if (!(target instanceof SVGGraphicsElement)) {
    return
  }
  const rect = target.getBoundingClientRect()
  hoveredElement.value = {
    title: elementTitle(element),
    data: elementData(element),
    x: rect.left + rect.width / 2,
    y: rect.top - 12,
  }
}

function handleLeave(): void {
  hoveredElement.value = null
}

const tooltipStyle = computed(() => {
  if (!hoveredElement.value) return {}
  return {
    left: `${hoveredElement.value.x}px`,
    top: `${hoveredElement.value.y}px`,
  }
})

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) {
    return timestamp
  }
  return date.toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

watch(stateCode, (value) => {
  emit('state-change', value)
})

watch(() => props.zoneId, (newZoneId, oldZoneId) => {
  if (newZoneId === oldZoneId) {
    return
  }

  clearWsRefreshTimer()
  cleanupRealtimeChannels()
  stopFallbackPolling()

  if (!newZoneId) {
    automationState.value = null
    errorMessage.value = null
    return
  }

  void fetchAutomationState()

  if (wsEnabled) {
    const subscribed = subscribeRealtimeChannels()
    if (subscribed) {
      scheduleRealtimeRefresh()
      return
    }
  }

  startFallbackPolling()
})

onMounted(() => {
  void fetchAutomationState()

  if (wsEnabled) {
    const subscribed = subscribeRealtimeChannels()
    if (subscribed) {
      scheduleRealtimeRefresh()
    } else {
      startFallbackPolling()
    }

    wsStateListenerCleanup = onWsStateChange((state) => {
      if (state === 'connected') {
        const resubscribed = subscribeRealtimeChannels()
        if (resubscribed) {
          stopFallbackPolling()
          scheduleRealtimeRefresh()
        } else {
          startFallbackPolling()
        }
        return
      }

      if (state === 'disconnected' || state === 'unavailable' || state === 'failed') {
        clearWsRefreshTimer()
        cleanupRealtimeChannels()
        startFallbackPolling()
      }
    })
  } else {
    startFallbackPolling()
  }

  flowTimer = setInterval(() => {
    tickFlow()
  }, FLOW_TICK_INTERVAL_MS)
})

onUnmounted(() => {
  if (wsStateListenerCleanup) {
    wsStateListenerCleanup()
    wsStateListenerCleanup = null
  }
  cleanupRealtimeChannels()
  clearWsRefreshTimer()
  stopFallbackPolling()
  if (flowTimer !== null) {
    clearInterval(flowTimer)
    flowTimer = null
  }
})
</script>

<style scoped>
.automation-process-panel {
  position: relative;
}

.process-svg {
  width: 100%;
  height: auto;
}

.tank-group {
  cursor: default;
}

.tank-shell {
  fill: color-mix(in srgb, var(--surface-card) 84%, transparent);
  stroke: var(--border-muted);
  stroke-width: 2;
}

.tank-fill {
  transition: y 0.35s ease, height 0.35s ease;
}

.tank-level {
  text-anchor: middle;
  fill: var(--text-primary);
  font-size: 24px;
  font-weight: 700;
}

.tank-title {
  text-anchor: middle;
  fill: var(--text-dim);
  font-size: 13px;
  font-weight: 500;
}

.pipe-line {
  stroke: var(--border-muted);
  stroke-width: 3;
  transition: stroke 0.25s ease, stroke-width 0.25s ease;
}

.pipe-line--active {
  stroke: var(--accent-cyan);
  stroke-width: 4;
}

.flow-dot {
  fill: var(--accent-cyan);
  filter: drop-shadow(0 0 4px color-mix(in srgb, var(--accent-cyan) 65%, transparent));
  animation: flow-dot-pulse 1s linear infinite;
}

.flow-dot--reverse {
  fill: var(--accent-amber);
  filter: drop-shadow(0 0 4px color-mix(in srgb, var(--accent-amber) 65%, transparent));
}

.flow-dot--correction {
  fill: var(--accent-violet, #9b8cff);
  filter: drop-shadow(0 0 4px color-mix(in srgb, var(--accent-violet, #9b8cff) 65%, transparent));
}

.correction-indicator {
  fill: color-mix(in srgb, var(--surface-card) 76%, transparent);
  stroke: var(--border-muted);
  stroke-width: 2;
  transition: fill 0.25s ease, stroke 0.25s ease, transform 0.25s ease;
  transform-origin: center;
}

.correction-indicator--ec {
  stroke: var(--border-muted);
}

.correction-indicator--active {
  fill: color-mix(in srgb, var(--accent-amber) 52%, transparent);
  stroke: var(--accent-amber);
  animation: correction-pulse 1.5s ease-in-out infinite;
}

.correction-indicator--ec.correction-indicator--active {
  fill: color-mix(in srgb, var(--accent-green) 50%, transparent);
  stroke: var(--accent-green);
}

.correction-text {
  text-anchor: middle;
  fill: var(--text-primary);
  font-size: 11px;
  font-weight: 700;
}

.correction-unit {
  fill: color-mix(in srgb, var(--surface-card) 85%, transparent);
  stroke: var(--border-muted);
  stroke-width: 2;
  transition: fill 0.25s ease, stroke 0.25s ease;
}

.correction-unit--active {
  fill: color-mix(in srgb, var(--accent-violet, #9b8cff) 28%, transparent);
  stroke: var(--accent-violet, #9b8cff);
}

.correction-unit-title {
  text-anchor: middle;
  fill: var(--text-primary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.valve-icon {
  fill: color-mix(in srgb, var(--surface-card) 80%, transparent);
  stroke: var(--border-muted);
  stroke-width: 2;
  transition: fill 0.2s ease, stroke 0.2s ease, transform 0.2s ease;
}

.valve-icon--open {
  fill: color-mix(in srgb, var(--accent-green) 48%, transparent);
  stroke: var(--accent-green);
  transform: scale(1.05);
}

.valve-label {
  text-anchor: middle;
  fill: var(--text-primary);
  font-size: 10px;
  font-weight: 700;
}

.pump-icon {
  fill: color-mix(in srgb, var(--surface-card) 86%, transparent);
  stroke: var(--border-muted);
  stroke-width: 2;
  transition: fill 0.25s ease, stroke 0.25s ease;
}

.pump-icon--active {
  fill: color-mix(in srgb, var(--accent-cyan) 56%, transparent);
  stroke: var(--accent-cyan);
  animation: pump-vibe 0.35s linear infinite;
}

.pump-icon--correction {
  fill: color-mix(in srgb, var(--accent-violet, #9b8cff) 56%, transparent);
  stroke: var(--accent-violet, #9b8cff);
}

.pump-text {
  text-anchor: middle;
  fill: var(--text-primary);
  font-size: 12px;
  font-weight: 700;
}

.details-tooltip {
  position: fixed;
  transform: translate(-50%, -100%);
  min-width: 180px;
  max-width: 260px;
  background: color-mix(in srgb, var(--bg-elevated) 94%, transparent);
  border: 1px solid var(--border-muted);
  border-radius: 10px;
  padding: 10px 12px;
  box-shadow: 0 10px 24px color-mix(in srgb, var(--bg-app) 25%, transparent);
  pointer-events: none;
  z-index: 80;
}

.tooltip-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.tooltip-grid {
  display: grid;
  gap: 4px;
}

.tooltip-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}

.tooltip-label {
  color: var(--text-dim);
}

.tooltip-value {
  color: var(--text-primary);
  font-weight: 600;
}

.timeline-item {
  display: grid;
  grid-template-columns: 12px 1fr auto;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  opacity: 0.66;
  transition: opacity 0.2s ease;
}

.timeline-item--active {
  opacity: 1;
}

.timeline-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--border-muted);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--border-muted) 25%, transparent);
}

.timeline-item--active .timeline-dot {
  background: var(--accent-cyan);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent-cyan) 35%, transparent);
}

.timeline-label {
  color: var(--text-primary);
  font-size: 12px;
}

.timeline-time {
  color: var(--text-dim);
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

@keyframes correction-pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.08);
    opacity: 0.75;
  }
}

@keyframes flow-dot-pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

@keyframes pump-vibe {
  0%, 100% {
    transform: translateX(0);
  }
  25% {
    transform: translateX(-1px);
  }
  75% {
    transform: translateX(1px);
  }
}
</style>
