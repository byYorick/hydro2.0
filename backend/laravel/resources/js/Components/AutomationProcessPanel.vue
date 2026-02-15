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

    <section class="mt-3 rounded-xl border border-[color:var(--border-muted)]/60 bg-[color:var(--surface-card)]/45 p-3">
      <div class="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
        <h4 class="text-xs uppercase tracking-[0.18em] text-[color:var(--text-dim)]">Этапы setup режима</h4>
        <p class="text-xs text-[color:var(--text-muted)]">
          Сейчас: {{ currentSetupStageLabel }}
        </p>
      </div>
      <ul class="mt-2 space-y-1">
        <li
          v-for="stage in setupStages"
          :key="stage.code"
          class="flex items-center justify-between gap-2 rounded-lg border border-[color:var(--border-muted)]/40 bg-[color:var(--surface-card)]/30 px-2 py-1.5"
        >
          <span class="text-xs text-[color:var(--text-primary)]">{{ stage.label }}</span>
          <span
            class="rounded-full px-2 py-0.5 text-[11px] font-medium"
            :class="stagePillClass(stage.status)"
          >
            {{ setupStageStatusLabel(stage.status) }}
          </span>
        </li>
      </ul>
    </section>

    <div class="mt-4 overflow-x-auto">
      <svg
        class="process-svg min-w-[900px]"
        viewBox="0 0 950 550"
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

        <!-- Вход воды сверху бака чистой воды -->
        <g class="water-inlet">
          <!-- Труба входа воды -->
          <line x1="145" y1="20" x2="145" y2="70" class="pipe-line" :class="{ 'pipe-line--active': isWaterInletActive }" stroke-width="4" />
          <circle v-if="isWaterInletActive" class="flow-dot" r="5" :cx="145" :cy="waterInletFlowY" />

          <!-- Клапан набора чистой воды -->
          <rect x="130" y="40" width="30" height="20" rx="4" class="valve" :class="{ 'valve--active': isWaterInletActive }" />
          <text x="145" y="53" class="valve-label">V1</text>

          <!-- Метка входа -->
          <text x="145" y="15" class="pipe-label">Вход воды</text>
        </g>

        <!-- Бак с чистой водой -->
        <g
          class="tank-group"
          @mouseenter="handleHover('clean', $event)"
          @mousemove="handleMouseMove('clean', $event)"
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
          <text class="tank-title" x="145" y="345">Чистая вода</text>
        </g>

        <!-- Бак с раствором -->
        <g
          class="tank-group"
          @mouseenter="handleHover('nutrient', $event)"
          @mousemove="handleMouseMove('nutrient', $event)"
          @mouseleave="handleLeave"
        >
          <rect class="tank-shell" x="650" y="70" width="150" height="250" rx="14" />
          <rect
            class="tank-fill"
            x="650"
            :y="tankFillY(nutrientTankLevel)"
            width="150"
            :height="tankFillHeight(nutrientTankLevel)"
            rx="14"
            fill="url(#automation-nutrient-gradient)"
          />
          <text class="tank-level" x="725" y="195">{{ Math.round(nutrientTankLevel) }}%</text>
          <text class="tank-title" x="725" y="345">Раствор NPK</text>
        </g>

        <!-- Выход из бака чистой воды (снизу) -->
        <g class="clean-tank-outlet">
          <!-- Труба вниз от бака -->
          <line x1="145" y1="320" x2="145" y2="385" class="pipe-line" :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }" stroke-width="4" />

          <!-- Клапан забора чистой воды -->
          <rect x="130" y="345" width="30" height="20" rx="4" class="valve" :class="{ 'valve--active': isPumpInActive || isCirculationActive }" />
          <text x="145" y="358" class="valve-label">V2</text>

          <!-- Горизонтальная труба к соединению -->
          <line x1="145" y1="385" x2="300" y2="385" class="pipe-line" :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }" stroke-width="4" />
          <circle v-if="isPumpInActive || isCirculationActive" class="flow-dot" r="5" :cx="cleanOutletFlowX" :cy="385" />
        </g>

        <!-- Выход из бака раствора (снизу) -->
        <g class="nutrient-tank-outlet">
          <!-- Труба вниз от бака -->
          <line x1="725" y1="320" x2="725" y2="385" class="pipe-line" :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }" stroke-width="4" />

          <!-- Клапан забора раствора -->
          <rect x="710" y="345" width="30" height="20" rx="4" class="valve" :class="{ 'valve--active': isPumpInActive || isCirculationActive }" />
          <text x="725" y="358" class="valve-label">V3</text>

          <!-- Горизонтальная труба к соединению -->
          <line x1="300" y1="385" x2="725" y2="385" class="pipe-line" :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }" stroke-width="4" />
          <circle v-if="isPumpInActive || isCirculationActive" class="flow-dot" r="5" :cx="nutrientOutletFlowX" :cy="385" />
        </g>

        <!-- Соединение труб (T-образное) -->
        <g class="pipe-junction">
          <circle cx="300" cy="385" r="6" class="junction-point" />
        </g>

        <!-- Труба к насосу -->
        <g class="pump-inlet">
          <line x1="300" y1="385" x2="300" y2="450" class="pipe-line" :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }" stroke-width="4" />
          <circle v-if="isPumpInActive || isCirculationActive" class="flow-dot" r="5" cx="300" :cy="pumpInletFlowY" />
        </g>

        <!-- Насос -->
        <g
          class="pump"
          @mouseenter="handleHover('pump', $event)"
          @mousemove="handleMouseMove('pump', $event)"
          @mouseleave="handleLeave"
        >
          <rect x="270" y="450" width="60" height="50" rx="6" class="pump-body" :class="{ 'pump-body--active': isPumpInActive || isCirculationActive }" />
          <text x="300" y="478" class="pump-label">НАСОС</text>
          <text x="300" y="492" class="pump-label-small">P1</text>
        </g>

        <!-- Труба от насоса к узлу коррекции -->
        <g class="pump-to-correction">
          <line x1="330" y1="475" x2="450" y2="475" class="pipe-line" :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }" stroke-width="4" />
          <circle v-if="isPumpInActive || isCirculationActive" class="flow-dot" r="5" :cx="pumpOutletFlowX" :cy="475" />
        </g>

        <!-- Узел коррекции -->
        <g
          class="correction-node"
          @mouseenter="handleHover('correction', $event)"
          @mousemove="handleMouseMove('correction', $event)"
          @mouseleave="handleLeave"
        >
          <rect x="450" y="440" width="100" height="70" rx="8" class="correction-body" :class="{ 'correction-body--active': isPhCorrectionActive || isEcCorrectionActive }" />
          <text x="500" y="465" class="correction-label">Коррекция</text>

          <!-- Индикаторы pH/EC -->
          <g transform="translate(475, 485)">
            <circle cx="0" cy="0" r="12" class="correction-indicator" :class="{ 'correction-indicator--active': isPhCorrectionActive }" />
            <text x="0" y="4" class="correction-text-small">pH</text>
          </g>
          <g transform="translate(525, 485)">
            <circle cx="0" cy="0" r="12" class="correction-indicator correction-indicator--ec" :class="{ 'correction-indicator--active': isEcCorrectionActive }" />
            <text x="0" y="4" class="correction-text-small">EC</text>
          </g>
        </g>

        <!-- Труба от узла коррекции до разделения -->
        <g class="correction-to-split">
          <line x1="550" y1="475" x2="620" y2="475" class="pipe-line" :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }" stroke-width="4" />
          <circle v-if="isPumpInActive || isCirculationActive" class="flow-dot" r="5" :cx="correctionOutletFlowX" :cy="475" />
        </g>

        <!-- Разделение потока (Y-образное) -->
        <g class="flow-split">
          <circle cx="620" cy="475" r="6" class="junction-point" />

          <!-- Ветка вверх (к баку раствора) -->
          <line x1="620" y1="475" x2="620" y2="110" class="pipe-line" :class="{ 'pipe-line--active': isTankRefillActive }" stroke-width="4" />
          <circle v-if="isTankRefillActive" class="flow-dot" r="5" cx="620" :cy="tankRefillFlowY" />

          <!-- Ветка вправо (к поливу) -->
          <line x1="620" y1="475" x2="850" y2="475" class="pipe-line" :class="{ 'pipe-line--active': isIrrigationActive }" stroke-width="4" />
          <circle v-if="isIrrigationActive" class="flow-dot" r="5" :cx="irrigationFlowX" :cy="475" />
        </g>

        <!-- Клапан набора раствора -->
        <g class="tank-refill-valve">
          <rect x="605" y="90" width="30" height="20" rx="4" class="valve" :class="{ 'valve--active': isTankRefillActive }" />
          <text x="620" y="103" class="valve-label">V4</text>
        </g>

        <!-- Труба от клапана к баку: вверх → вправо → вниз -->
        <g class="tank-inlet">
          <!-- Вертикальная труба вверх от клапана -->
          <line x1="620" y1="90" x2="620" y2="50" class="pipe-line" :class="{ 'pipe-line--active': isTankRefillActive }" stroke-width="4" />
          <circle v-if="isTankRefillActive && tankRefillFlowY >= 50" class="flow-dot" r="5" cx="620" :cy="tankRefillFlowY" />

          <!-- Горизонтальная труба вправо к центру бака -->
          <line x1="620" y1="50" x2="725" y2="50" class="pipe-line" :class="{ 'pipe-line--active': isTankRefillActive }" stroke-width="4" />
          <circle v-if="isTankRefillActive && tankRefillFlowY < 50 && tankRefillHorizontalFlowX <= 725" class="flow-dot" r="5" :cx="tankRefillHorizontalFlowX" cy="50" />

          <!-- Вертикальная труба вниз в бак -->
          <line x1="725" y1="50" x2="725" y2="85" class="pipe-line" :class="{ 'pipe-line--active': isTankRefillActive }" stroke-width="4" />
          <circle v-if="isTankRefillActive && tankRefillHorizontalFlowX > 725" class="flow-dot" r="5" cx="725" :cy="tankRefillDownFlowY" />

          <!-- Стрелка вниз в центре бака -->
          <path d="M 715,85 L 725,75 L 735,85 Z" class="arrow-down" :class="{ 'arrow-down--active': isTankRefillActive }" />
        </g>

        <!-- Клапан полива -->
        <g class="irrigation-valve">
          <rect x="770" y="465" width="30" height="20" rx="4" class="valve" :class="{ 'valve--active': isIrrigationActive }" />
          <text x="785" y="478" class="valve-label">V5</text>

          <!-- Метка выхода -->
          <text x="880" y="480" class="pipe-label">Полив</text>
          <path d="M 850,475 L 860,475 M 855,470 L 865,475 L 855,480" class="arrow-right" :class="{ 'arrow-right--active': isIrrigationActive }" stroke-width="2" />
        </g>
      </svg>
    </div>

    <Teleport to="body">
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
    </Teleport>

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

type SetupStageCode = 'clean_fill' | 'solution_fill' | 'parallel_correction' | 'setup_transition'
type SetupStageStatus = 'pending' | 'running' | 'completed' | 'failed'

interface SetupStageView {
  code: SetupStageCode
  label: string
  status: SetupStageStatus
}

const AUTOMATION_EVENT_LABELS: Record<string, string> = {
  SCHEDULE_TASK_ACCEPTED: 'Scheduler: задача принята',
  SCHEDULE_TASK_COMPLETED: 'Scheduler: задача завершена',
  SCHEDULE_TASK_FAILED: 'Scheduler: задача с ошибкой',
  SCHEDULE_TASK_EXECUTION_STARTED: 'Automation-engine: запуск выполнения',
  SCHEDULE_TASK_EXECUTION_FINISHED: 'Automation-engine: выполнение завершено',
  TASK_RECEIVED: 'Automation-engine: задача получена',
  TASK_STARTED: 'Automation-engine: выполнение начато',
  DECISION_MADE: 'Automation-engine: решение принято',
  COMMAND_DISPATCHED: 'Команда отправлена узлу',
  COMMAND_FAILED: 'Ошибка отправки команды',
  TASK_FINISHED: 'Automation-engine: задача завершена',
  CLEAN_FILL_COMPLETED: 'Бак чистой воды заполнен',
  SOLUTION_FILL_COMPLETED: 'Бак рабочего раствора заполнен',
  CLEAN_FILL_RETRY_STARTED: 'Запущен повторный цикл clean-fill',
  PREPARE_TARGETS_REACHED: 'Целевые pH/EC достигнуты',
  TWO_TANK_STARTUP_INITIATED: 'Запущен старт 2-баковой схемы',
}

const AUTOMATION_REASON_LABELS: Record<string, string> = {
  clean_fill_started: 'Запущено наполнение бака чистой воды',
  clean_fill_in_progress: 'Идёт наполнение бака чистой воды',
  clean_fill_completed: 'Бак чистой воды наполнен',
  clean_fill_timeout: 'Таймаут набора чистой воды',
  solution_fill_started: 'Запущено наполнение бака раствора',
  solution_fill_in_progress: 'Идёт наполнение бака раствора',
  solution_fill_completed: 'Бак раствора наполнен',
  solution_fill_timeout: 'Таймаут набора бака раствора',
  prepare_recirculation_started: 'Запущена рециркуляция и коррекция',
  prepare_targets_reached: 'Целевые pH/EC достигнуты',
  prepare_targets_not_reached: 'Цели pH/EC не достигнуты',
  prepare_npk_ph_target_not_reached: 'Цели подготовки раствора не достигнуты',
  setup_completed: 'Setup завершен',
  setup_to_working: 'Переход в рабочий режим',
  working_mode_activated: 'Рабочий режим активирован',
}

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

// Анимации потоков (старые, оставляем для совместимости)
const flowDotForwardX = computed(() => 220 + (130 * flowOffset.value))
const flowDotReverseX = computed(() => 350 - (130 * flowOffset.value))
const correctionFlowX = computed(() => 500 + (60 * flowOffset.value))

// Новые анимации для полной схемы
const isWaterInletActive = computed(() => {
  // Вход воды активен при состояниях TANK_FILLING или когда набираем бак
  return stateCode.value === 'TANK_FILLING' || cleanTankLevel.value < 90
})

const isTankRefillActive = computed(() => {
  // Набор бака раствора активен при TANK_FILLING, TANK_RECIRC
  return stateCode.value === 'TANK_FILLING' || stateCode.value === 'TANK_RECIRC'
})

const isIrrigationActive = computed(() => {
  // Полив активен при IRRIGATING, IRRIG_RECIRC
  return stateCode.value === 'IRRIGATING' || stateCode.value === 'IRRIG_RECIRC'
})

function setupStageStatusLabel(status: SetupStageStatus): string {
  if (status === 'running') return 'Выполняется'
  if (status === 'completed') return 'Выполнено'
  if (status === 'failed') return 'Ошибка'
  return 'Ожидание'
}

function stagePillClass(status: SetupStageStatus): string {
  if (status === 'running') {
    return 'bg-amber-500/20 text-amber-300 border border-amber-400/40'
  }
  if (status === 'completed') {
    return 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/40'
  }
  if (status === 'failed') {
    return 'bg-red-500/20 text-red-300 border border-red-400/40'
  }
  return 'bg-slate-500/20 text-slate-300 border border-slate-400/40'
}

const hasFailedState = computed(() => {
  if (errorMessage.value) {
    return true
  }

  const timeline = automationState.value?.timeline ?? []
  const latest = timeline[timeline.length - 1]
  if (!latest) {
    return false
  }

  const eventCode = String(latest.event ?? '').toUpperCase()
  const label = String(latest.label ?? '').toLowerCase()
  return eventCode.includes('FAILED') || eventCode.includes('TIMEOUT') || label.includes('ошиб') || label.includes('таймаут')
})

const hasSetupTransitionCompleted = computed(() => {
  return stateCode.value === 'READY' || stateCode.value === 'IRRIGATING' || stateCode.value === 'IRRIG_RECIRC'
})

const setupStages = computed<SetupStageView[]>(() => {
  const isCleanDone = cleanTankLevel.value >= 90 || stateCode.value === 'TANK_RECIRC' || hasSetupTransitionCompleted.value
  const isSolutionDone = nutrientTankLevel.value >= 90 || stateCode.value === 'TANK_RECIRC' || hasSetupTransitionCompleted.value
  const isCorrectionRunning = stateCode.value === 'TANK_RECIRC' || isPhCorrectionActive.value || isEcCorrectionActive.value
  const isCorrectionDone = hasSetupTransitionCompleted.value

  const cleanFillStatus: SetupStageStatus = hasFailedState.value
    ? (isCleanDone ? 'completed' : 'failed')
    : (stateCode.value === 'TANK_FILLING' && !isCleanDone ? 'running' : (isCleanDone ? 'completed' : 'pending'))

  const solutionFillStatus: SetupStageStatus = hasFailedState.value
    ? (isSolutionDone ? 'completed' : 'failed')
    : (stateCode.value === 'TANK_FILLING' && !isSolutionDone ? 'running' : (isSolutionDone ? 'completed' : 'pending'))

  const correctionStatus: SetupStageStatus = hasFailedState.value
    ? (isCorrectionDone ? 'completed' : 'failed')
    : (isCorrectionRunning ? 'running' : (isCorrectionDone ? 'completed' : 'pending'))

  const transitionStatus: SetupStageStatus = hasFailedState.value
    ? (hasSetupTransitionCompleted.value ? 'completed' : 'failed')
    : (hasSetupTransitionCompleted.value ? 'completed' : (stateCode.value === 'TANK_RECIRC' ? 'running' : 'pending'))

  return [
    { code: 'clean_fill', label: 'Набор бака с чистой водой', status: cleanFillStatus },
    { code: 'solution_fill', label: 'Набор бака с раствором', status: solutionFillStatus },
    { code: 'parallel_correction', label: 'Параллельная коррекция pH/EC', status: correctionStatus },
    { code: 'setup_transition', label: 'Завершение setup и переход в рабочий режим', status: transitionStatus },
  ]
})

const currentSetupStageLabel = computed(() => {
  const running = setupStages.value.find((stage) => stage.status === 'running')
  if (running) return running.label

  const failed = setupStages.value.find((stage) => stage.status === 'failed')
  if (failed) return `${failed.label} (ошибка)`

  if (setupStages.value.every((stage) => stage.status === 'completed')) {
    return 'Setup завершен, система в рабочем режиме'
  }

  const pending = setupStages.value.find((stage) => stage.status === 'pending')
  return pending?.label ?? 'Ожидание данных процесса'
})

// Анимация входа воды (движется вниз от 20 до 70)
const waterInletFlowY = computed(() => 20 + (50 * flowOffset.value))

// Анимация потока из бака чистой воды (движется вправо от 145 до 300)
const cleanOutletFlowX = computed(() => 145 + (155 * flowOffset.value))

// Анимация потока из бака раствора (движется влево от 725 до 300)
const nutrientOutletFlowX = computed(() => 725 - (425 * flowOffset.value))

// Анимация входа в насос (движется вниз от 385 до 450)
const pumpInletFlowY = computed(() => 385 + (65 * flowOffset.value))

// Анимация выхода из насоса (движется вправо от 330 до 450)
const pumpOutletFlowX = computed(() => 330 + (120 * flowOffset.value))

// Анимация выхода из узла коррекции (движется вправо от 550 до 620)
const correctionOutletFlowX = computed(() => 550 + (70 * flowOffset.value))

// Анимация набора бака раствора - сложный путь: вверх → вправо → вниз
// Общий путь: 475→50 (425px вверх) + 620→725 (105px вправо) + 50→85 (35px вниз)
// Всего: 565px, распределяем offset: 0-0.75 (вверх), 0.75-0.93 (вправо), 0.93-1.0 (вниз)

const tankRefillFlowY = computed(() => {
  const offset = flowOffset.value
  if (offset <= 0.75) {
    // Движение вверх: от 475 до 50
    return 475 - (425 * (offset / 0.75))
  }
  return 50 // На горизонтальном и вертикальном вниз участках
})

const tankRefillHorizontalFlowX = computed(() => {
  const offset = flowOffset.value
  if (offset <= 0.75) {
    return 620 // Еще на вертикальном участке
  } else if (offset <= 0.93) {
    // Движение вправо: от 620 до 725
    return 620 + (105 * ((offset - 0.75) / 0.18))
  }
  return 725 // На вертикальном вниз участке
})

const tankRefillDownFlowY = computed(() => {
  const offset = flowOffset.value
  if (offset <= 0.93) {
    return 50 // Еще на верхних участках
  }
  // Движение вниз: от 50 до 85
  return 50 + (35 * ((offset - 0.93) / 0.07))
})

// Анимация полива (движется вправо от 620 до 850)
const irrigationFlowX = computed(() => 620 + (230 * flowOffset.value))

function normalizeReasonCode(reasonCode: string): string {
  const normalized = reasonCode.trim().toLowerCase()
  return normalized.replace(/\s+/g, '_')
}

function extractReasonCodeFromEventLabel(label: string): string | null {
  const match = label.match(/\(([^()]+)\)\s*$/)
  if (!match || !match[1]) {
    return null
  }
  return normalizeReasonCode(match[1])
}

function stagePrefixForEvent(eventCode: string, reasonCode: string | null): string | null {
  const normalizedEvent = eventCode.trim().toUpperCase()
  const normalizedReason = reasonCode ? normalizeReasonCode(reasonCode) : null

  if (
    normalizedReason !== null
    && (
      normalizedReason.startsWith('clean_fill_')
      || normalizedReason.startsWith('tank_refill_')
      || normalizedEvent === 'CLEAN_FILL_COMPLETED'
    )
  ) {
    return 'Набор чистой воды'
  }

  if (
    normalizedReason !== null
    && (
      normalizedReason.startsWith('solution_fill_')
      || normalizedEvent === 'SOLUTION_FILL_COMPLETED'
    )
  ) {
    return 'Набор раствора'
  }

  if (
    normalizedReason !== null
    && (
      normalizedReason.startsWith('prepare_')
      || normalizedReason.includes('correction')
      || normalizedEvent === 'PREPARE_TARGETS_REACHED'
    )
  ) {
    return 'Параллельная коррекция'
  }

  if (
    normalizedReason !== null
    && (
      normalizedReason.startsWith('setup_')
      || normalizedReason.includes('working_mode')
      || normalizedReason.includes('setup_to_working')
    )
  ) {
    return 'Переход в рабочий режим'
  }

  return null
}

function formatTimelineLabel(event: AutomationTimelineEvent): string {
  const eventCode = String(event.event ?? '').trim().toUpperCase()
  const sourceLabel = String(event.label ?? '').trim()

  const reasonFromLabel = extractReasonCodeFromEventLabel(sourceLabel)
  const baseFromLabel = sourceLabel.replace(/\s*\([^()]+\)\s*$/, '').trim()
  const baseLabel = baseFromLabel || AUTOMATION_EVENT_LABELS[eventCode] || eventCode || 'Событие'
  const reasonLabel = reasonFromLabel ? (AUTOMATION_REASON_LABELS[reasonFromLabel] ?? reasonFromLabel) : null
  const stagePrefix = stagePrefixForEvent(eventCode, reasonFromLabel)

  let formatted = baseLabel
  if (reasonLabel && baseLabel.trim().toLowerCase() !== reasonLabel.trim().toLowerCase()) {
    formatted = `${formatted} — ${reasonLabel}`
  }
  if (stagePrefix) {
    formatted = `${stagePrefix}: ${formatted}`
  }
  return formatted
}

const timelineEvents = computed<AutomationTimelineEvent[]>(() => {
  const timeline = automationState.value?.timeline ?? []
  return timeline.slice(-12).map((event) => ({
    ...event,
    label: formatTimelineLabel(event),
  }))
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
  if (element === 'pump') {
    return {
      'Насос P1': isPumpInActive.value || isCirculationActive.value ? 'Включен' : 'Выключен',
      'Режим': isPumpInActive.value ? 'Подача' : isCirculationActive.value ? 'Рециркуляция' : '—',
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
    pump: 'Главный насос',
    circulation: 'Насос рециркуляции',
    pump_correction: 'Насос дозирования',
  }
  return map[element] ?? element
}

function handleHover(element: string, event: MouseEvent): void {
  // Tooltip прямо под курсором
  const x = event.clientX + 2
  const y = event.clientY + 20

  hoveredElement.value = {
    title: elementTitle(element),
    data: elementData(element),
    x,
    y,
  }
}

function handleMouseMove(element: string, event: MouseEvent): void {
  // Обновляем позицию tooltip при движении курсора
  if (hoveredElement.value) {
    hoveredElement.value = {
      ...hoveredElement.value,
      x: event.clientX + 2,
      y: event.clientY + 20,
    }
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
  min-width: 180px;
  max-width: 260px;
  background: color-mix(in srgb, var(--bg-elevated) 94%, transparent);
  border: 1px solid var(--border-muted);
  border-radius: 10px;
  padding: 10px 12px;
  box-shadow: 0 10px 24px color-mix(in srgb, var(--bg-app) 25%, transparent);
  pointer-events: none;
  z-index: 80;
  backdrop-filter: blur(8px);
  transition: left 0.05s ease-out, top 0.05s ease-out;
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

/* Новые стили для полной схемы */

.valve {
  fill: color-mix(in srgb, var(--surface-card) 80%, transparent);
  stroke: var(--border-muted);
  stroke-width: 2;
  transition: fill 0.25s ease, stroke 0.25s ease;
}

.valve--active {
  fill: color-mix(in srgb, var(--accent-green) 52%, transparent);
  stroke: var(--accent-green);
}

.valve-label {
  text-anchor: middle;
  fill: var(--text-primary);
  font-size: 10px;
  font-weight: 700;
}

.pump-body {
  fill: color-mix(in srgb, var(--surface-card) 86%, transparent);
  stroke: var(--border-muted);
  stroke-width: 2.5;
  transition: fill 0.25s ease, stroke 0.25s ease;
}

.pump-body--active {
  fill: color-mix(in srgb, var(--accent-cyan) 58%, transparent);
  stroke: var(--accent-cyan);
  animation: pump-vibe 0.35s linear infinite;
}

.pump-label {
  text-anchor: middle;
  fill: var(--text-primary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
}

.pump-label-small {
  text-anchor: middle;
  fill: var(--text-dim);
  font-size: 9px;
  font-weight: 600;
}

.correction-body {
  fill: color-mix(in srgb, var(--surface-card) 85%, transparent);
  stroke: var(--border-muted);
  stroke-width: 2.5;
  transition: fill 0.25s ease, stroke 0.25s ease;
}

.correction-body--active {
  fill: color-mix(in srgb, var(--accent-violet, #9b8cff) 30%, transparent);
  stroke: var(--accent-violet, #9b8cff);
}

.correction-label {
  text-anchor: middle;
  fill: var(--text-primary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.correction-text-small {
  text-anchor: middle;
  fill: var(--text-primary);
  font-size: 9px;
  font-weight: 700;
}

.pipe-label {
  text-anchor: middle;
  fill: var(--text-dim);
  font-size: 11px;
  font-weight: 600;
}

.junction-point {
  fill: var(--accent-cyan);
  stroke: none;
}

.arrow-down {
  fill: var(--border-muted);
  transition: fill 0.25s ease;
}

.arrow-down--active {
  fill: var(--accent-cyan);
}

.arrow-right {
  fill: none;
  stroke: var(--border-muted);
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: stroke 0.25s ease;
}

.arrow-right--active {
  stroke: var(--accent-cyan);
}
</style>
