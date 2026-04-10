<template>
  <div class="mt-4 overflow-x-auto">
    <svg
      class="process-svg min-w-[900px]"
      viewBox="0 0 950 550"
      role="img"
      aria-label="Схема процесса автоматизации зоны"
    >
      <defs>
        <linearGradient
          id="automation-clean-water-gradient"
          x1="0%"
          y1="0%"
          x2="0%"
          y2="100%"
        >
          <stop
            offset="0%"
            stop-color="rgba(93,214,255,0.88)"
          />
          <stop
            offset="100%"
            stop-color="rgba(93,214,255,0.34)"
          />
        </linearGradient>
        <linearGradient
          id="automation-nutrient-gradient"
          x1="0%"
          y1="0%"
          x2="0%"
          y2="100%"
        >
          <stop
            offset="0%"
            stop-color="rgba(73,224,138,0.9)"
          />
          <stop
            offset="100%"
            stop-color="rgba(73,224,138,0.36)"
          />
        </linearGradient>
        <linearGradient
          id="automation-buffer-gradient"
          x1="0%"
          y1="0%"
          x2="0%"
          y2="100%"
        >
          <stop
            offset="0%"
            stop-color="rgba(240,178,104,0.88)"
          />
          <stop
            offset="100%"
            stop-color="rgba(240,178,104,0.34)"
          />
        </linearGradient>
      </defs>

      <!-- Вход воды сверху бака чистой воды -->
      <g class="water-inlet">
        <line
          x1="145"
          y1="20"
          x2="145"
          y2="70"
          class="pipe-line"
          :class="{ 'pipe-line--active': isWaterInletActive }"
          stroke-width="4"
        />
        <circle
          v-if="isWaterInletActive"
          class="flow-dot"
          r="5"
          :cx="145"
          :cy="waterInletFlowY"
        />
        <rect
          x="130"
          y="40"
          width="30"
          height="20"
          rx="4"
          class="valve"
          :class="{ 'valve--active': isWaterInletActive }"
        />
        <text
          x="145"
          y="53"
          class="valve-label"
        >V1</text>
        <text
          x="145"
          y="15"
          class="pipe-label"
        >Вход воды</text>
      </g>

      <!-- Бак с чистой водой -->
      <g
        class="tank-group"
        @mouseenter="handleHover('clean', $event)"
        @mousemove="handleMouseMove('clean', $event)"
        @mouseleave="handleLeave"
      >
        <rect
          class="tank-shell"
          x="70"
          y="70"
          width="150"
          height="250"
          rx="14"
        />
        <rect
          class="tank-fill"
          x="70"
          :y="tankFillY(cleanTankLevel)"
          width="150"
          :height="tankFillHeight(cleanTankLevel)"
          rx="14"
          fill="url(#automation-clean-water-gradient)"
        />
        <text
          class="tank-level"
          x="145"
          y="195"
        >{{ Math.round(cleanTankLevel) }}%</text>
        <text
          class="tank-title"
          x="145"
          y="345"
        >Чистая вода</text>
      </g>

      <!-- Бак с раствором -->
      <g
        class="tank-group"
        @mouseenter="handleHover('nutrient', $event)"
        @mousemove="handleMouseMove('nutrient', $event)"
        @mouseleave="handleLeave"
      >
        <rect
          class="tank-shell"
          x="650"
          y="70"
          width="150"
          height="250"
          rx="14"
        />
        <rect
          class="tank-fill"
          x="650"
          :y="tankFillY(nutrientTankLevel)"
          width="150"
          :height="tankFillHeight(nutrientTankLevel)"
          rx="14"
          fill="url(#automation-nutrient-gradient)"
        />
        <text
          class="tank-level"
          x="725"
          y="195"
        >{{ Math.round(nutrientTankLevel) }}%</text>
        <text
          class="tank-title"
          x="725"
          y="345"
        >Раствор NPK</text>
      </g>

      <!-- Выход из бака чистой воды (снизу) -->
      <g class="clean-tank-outlet">
        <line
          x1="145"
          y1="320"
          x2="145"
          y2="385"
          class="pipe-line"
          :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }"
          stroke-width="4"
        />
        <rect
          x="130"
          y="345"
          width="30"
          height="20"
          rx="4"
          class="valve"
          :class="{ 'valve--active': isPumpInActive || isCirculationActive }"
        />
        <text
          x="145"
          y="358"
          class="valve-label"
        >V2</text>
        <line
          x1="145"
          y1="385"
          x2="300"
          y2="385"
          class="pipe-line"
          :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }"
          stroke-width="4"
        />
        <circle
          v-if="isPumpInActive || isCirculationActive"
          class="flow-dot"
          r="5"
          :cx="cleanOutletFlowX"
          :cy="385"
        />
      </g>

      <!-- Выход из бака раствора (снизу) -->
      <g class="nutrient-tank-outlet">
        <line
          x1="725"
          y1="320"
          x2="725"
          y2="385"
          class="pipe-line"
          :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }"
          stroke-width="4"
        />
        <rect
          x="710"
          y="345"
          width="30"
          height="20"
          rx="4"
          class="valve"
          :class="{ 'valve--active': isPumpInActive || isCirculationActive }"
        />
        <text
          x="725"
          y="358"
          class="valve-label"
        >V3</text>
        <line
          x1="300"
          y1="385"
          x2="725"
          y2="385"
          class="pipe-line"
          :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }"
          stroke-width="4"
        />
        <circle
          v-if="isPumpInActive || isCirculationActive"
          class="flow-dot"
          r="5"
          :cx="nutrientOutletFlowX"
          :cy="385"
        />
      </g>

      <!-- Соединение труб (T-образное) -->
      <g class="pipe-junction">
        <circle
          cx="300"
          cy="385"
          r="6"
          class="junction-point"
        />
      </g>

      <!-- Труба к насосу -->
      <g class="pump-inlet">
        <line
          x1="300"
          y1="385"
          x2="300"
          y2="450"
          class="pipe-line"
          :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }"
          stroke-width="4"
        />
        <circle
          v-if="isPumpInActive || isCirculationActive"
          class="flow-dot"
          r="5"
          cx="300"
          :cy="pumpInletFlowY"
        />
      </g>

      <!-- Насос -->
      <g
        class="pump"
        @mouseenter="handleHover('pump', $event)"
        @mousemove="handleMouseMove('pump', $event)"
        @mouseleave="handleLeave"
      >
        <rect
          x="270"
          y="450"
          width="60"
          height="50"
          rx="6"
          class="pump-body"
          :class="{ 'pump-body--active': isPumpInActive || isCirculationActive }"
        />
        <text
          x="300"
          y="478"
          class="pump-label"
        >НАСОС</text>
        <text
          x="300"
          y="492"
          class="pump-label-small"
        >P1</text>
      </g>

      <!-- Труба от насоса к узлу коррекции -->
      <g class="pump-to-correction">
        <line
          x1="330"
          y1="475"
          x2="450"
          y2="475"
          class="pipe-line"
          :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }"
          stroke-width="4"
        />
        <circle
          v-if="isPumpInActive || isCirculationActive"
          class="flow-dot"
          r="5"
          :cx="pumpOutletFlowX"
          :cy="475"
        />
      </g>

      <!-- Узел коррекции -->
      <g
        class="correction-node"
        @mouseenter="handleHover('correction', $event)"
        @mousemove="handleMouseMove('correction', $event)"
        @mouseleave="handleLeave"
      >
        <rect
          x="450"
          y="440"
          width="100"
          height="70"
          rx="8"
          class="correction-body"
          :class="{ 'correction-body--active': isPhCorrectionActive || isEcCorrectionActive }"
        />
        <text
          x="500"
          y="465"
          class="correction-label"
        >Коррекция</text>
        <g transform="translate(475, 485)">
          <circle
            cx="0"
            cy="0"
            r="12"
            class="correction-indicator"
            :class="{ 'correction-indicator--active': isPhCorrectionActive }"
          />
          <text
            x="0"
            y="4"
            class="correction-text-small"
          >pH</text>
        </g>
        <g transform="translate(525, 485)">
          <circle
            cx="0"
            cy="0"
            r="12"
            class="correction-indicator correction-indicator--ec"
            :class="{ 'correction-indicator--active': isEcCorrectionActive }"
          />
          <text
            x="0"
            y="4"
            class="correction-text-small"
          >EC</text>
        </g>
      </g>

      <!-- Труба от узла коррекции до разделения -->
      <g class="correction-to-split">
        <line
          x1="550"
          y1="475"
          x2="620"
          y2="475"
          class="pipe-line"
          :class="{ 'pipe-line--active': isPumpInActive || isCirculationActive }"
          stroke-width="4"
        />
        <circle
          v-if="isPumpInActive || isCirculationActive"
          class="flow-dot"
          r="5"
          :cx="correctionOutletFlowX"
          :cy="475"
        />
      </g>

      <!-- Разделение потока (Y-образное) -->
      <g class="flow-split">
        <circle
          cx="620"
          cy="475"
          r="6"
          class="junction-point"
        />
        <line
          x1="620"
          y1="475"
          x2="620"
          y2="110"
          class="pipe-line"
          :class="{ 'pipe-line--active': isTankRefillActive }"
          stroke-width="4"
        />
        <circle
          v-if="isTankRefillActive"
          class="flow-dot"
          r="5"
          cx="620"
          :cy="tankRefillFlowY"
        />
        <line
          x1="620"
          y1="475"
          x2="850"
          y2="475"
          class="pipe-line"
          :class="{ 'pipe-line--active': isIrrigationActive }"
          stroke-width="4"
        />
        <circle
          v-if="isIrrigationActive"
          class="flow-dot"
          r="5"
          :cx="irrigationFlowX"
          :cy="475"
        />
      </g>

      <!-- Клапан набора раствора -->
      <g class="tank-refill-valve">
        <rect
          x="605"
          y="90"
          width="30"
          height="20"
          rx="4"
          class="valve"
          :class="{ 'valve--active': isTankRefillActive }"
        />
        <text
          x="620"
          y="103"
          class="valve-label"
        >V4</text>
      </g>

      <!-- Труба от клапана к баку: вверх → вправо → вниз -->
      <g class="tank-inlet">
        <line
          x1="620"
          y1="90"
          x2="620"
          y2="50"
          class="pipe-line"
          :class="{ 'pipe-line--active': isTankRefillActive }"
          stroke-width="4"
        />
        <circle
          v-if="isTankRefillActive && tankRefillFlowY >= 50"
          class="flow-dot"
          r="5"
          cx="620"
          :cy="tankRefillFlowY"
        />
        <line
          x1="620"
          y1="50"
          x2="725"
          y2="50"
          class="pipe-line"
          :class="{ 'pipe-line--active': isTankRefillActive }"
          stroke-width="4"
        />
        <circle
          v-if="isTankRefillActive && tankRefillFlowY < 50 && tankRefillHorizontalFlowX <= 725"
          class="flow-dot"
          r="5"
          :cx="tankRefillHorizontalFlowX"
          cy="50"
        />
        <line
          x1="725"
          y1="50"
          x2="725"
          y2="85"
          class="pipe-line"
          :class="{ 'pipe-line--active': isTankRefillActive }"
          stroke-width="4"
        />
        <circle
          v-if="isTankRefillActive && tankRefillHorizontalFlowX > 725"
          class="flow-dot"
          r="5"
          cx="725"
          :cy="tankRefillDownFlowY"
        />
        <path
          d="M 715,85 L 725,75 L 735,85 Z"
          class="arrow-down"
          :class="{ 'arrow-down--active': isTankRefillActive }"
        />
      </g>

      <!-- Клапан полива -->
      <g class="irrigation-valve">
        <rect
          x="770"
          y="465"
          width="30"
          height="20"
          rx="4"
          class="valve"
          :class="{ 'valve--active': isIrrigationActive }"
        />
        <text
          x="785"
          y="478"
          class="valve-label"
        >V5</text>
        <text
          x="880"
          y="480"
          class="pipe-label"
        >Полив</text>
        <path
          d="M 850,475 L 860,475 M 855,470 L 865,475 L 855,480"
          class="arrow-right"
          :class="{ 'arrow-right--active': isIrrigationActive }"
          stroke-width="2"
        />
      </g>
    </svg>
  </div>
  <div
    v-if="irrNodeState"
    class="mt-3 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)] p-3"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="text-xs font-semibold uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
        IRR state snapshot
      </div>
      <div
        v-if="irrNodeState.updated_at"
        class="text-[11px] text-[color:var(--text-dim)]"
      >
        {{ formatUpdatedAt(irrNodeState.updated_at) }}
      </div>
    </div>
    <div class="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
      <div
        v-for="item in irrStateRows"
        :key="item.key"
        class="rounded-lg border border-[color:var(--border-muted)]/70 px-2 py-1.5 text-xs"
      >
        <div class="text-[color:var(--text-dim)]">
          {{ item.label }}
        </div>
        <div class="mt-0.5 font-semibold text-[color:var(--text-primary)]">
          {{ item.value }}
        </div>
      </div>
    </div>
  </div>

  <Teleport to="body">
    <div
      v-if="hoveredElement"
      class="details-tooltip"
      :style="tooltipStyle"
    >
      <div class="tooltip-title">
        {{ hoveredElement.title }}
      </div>
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
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AutomationState, HoveredElement, IrrNodeState } from '@/types/Automation'

interface Props {
  flowOffset: number
  cleanTankLevel: number
  nutrientTankLevel: number
  bufferTankLevel: number
  isPumpInActive: boolean
  isCirculationActive: boolean
  isPhCorrectionActive: boolean
  isEcCorrectionActive: boolean
  isWaterInletActive: boolean
  isTankRefillActive: boolean
  isIrrigationActive: boolean
  isProcessActive: boolean
  automationState: AutomationState | null
  irrNodeState: IrrNodeState | null
}

const props = defineProps<Props>()

const hoveredElement = ref<HoveredElement | null>(null)

// ─── Local derived flags ────────────────────────────────────────────────────

const isCorrectionNodeActive = computed(() => props.isPhCorrectionActive || props.isEcCorrectionActive)
const isCorrectionPumpActive = computed(() => isCorrectionNodeActive.value)
const isInletValveOpen = computed(() => props.isPumpInActive || props.isCirculationActive)
const isOutletValveOpen = computed(() => props.isProcessActive || isCorrectionNodeActive.value)

// ─── Flow animation computed ────────────────────────────────────────────────

const waterInletFlowY = computed(() => 20 + (50 * props.flowOffset))
const cleanOutletFlowX = computed(() => 145 + (155 * props.flowOffset))
const nutrientOutletFlowX = computed(() => 725 - (425 * props.flowOffset))
const pumpInletFlowY = computed(() => 385 + (65 * props.flowOffset))
const pumpOutletFlowX = computed(() => 330 + (120 * props.flowOffset))
const correctionOutletFlowX = computed(() => 550 + (70 * props.flowOffset))
const irrigationFlowX = computed(() => 620 + (230 * props.flowOffset))

const tankRefillFlowY = computed(() => {
  const offset = props.flowOffset
  if (offset <= 0.75) {
    return 475 - (425 * (offset / 0.75))
  }
  return 50
})

const tankRefillHorizontalFlowX = computed(() => {
  const offset = props.flowOffset
  if (offset <= 0.75) {
    return 620
  } else if (offset <= 0.93) {
    return 620 + (105 * ((offset - 0.75) / 0.18))
  }
  return 725
})

const tankRefillDownFlowY = computed(() => {
  const offset = props.flowOffset
  if (offset <= 0.93) {
    return 50
  }
  return 50 + (35 * ((offset - 0.93) / 0.07))
})

const tooltipStyle = computed(() => {
  if (!hoveredElement.value) return {}
  return {
    left: `${hoveredElement.value.x}px`,
    top: `${hoveredElement.value.y}px`,
  }
})

function formatUpdatedAt(value: string | null | undefined): string {
  if (!value) return ''
  const d = new Date(value)
  if (isNaN(d.getTime())) return value
  return d.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatIrrStateValue(value: boolean | null | undefined): string {
  if (value === true) return 'Вкл'
  if (value === false) return 'Выкл'
  return '—'
}

const irrStateRows = computed(() => {
  const state = props.irrNodeState
  if (!state) return []
  return [
    { key: 'clean_max', label: 'Датчик чистая вода max', value: formatIrrStateValue(state.clean_level_max) },
    { key: 'clean_min', label: 'Датчик чистая вода min', value: formatIrrStateValue(state.clean_level_min) },
    { key: 'solution_max', label: 'Датчик раствор max', value: formatIrrStateValue(state.solution_level_max) },
    { key: 'solution_min', label: 'Датчик раствор min', value: formatIrrStateValue(state.solution_level_min) },
    { key: 'valve_clean_fill', label: 'Клапан набор чистой', value: formatIrrStateValue(state.valve_clean_fill) },
    { key: 'valve_clean_supply', label: 'Клапан отбор чистой', value: formatIrrStateValue(state.valve_clean_supply) },
    { key: 'valve_solution_fill', label: 'Клапан набор раствора', value: formatIrrStateValue(state.valve_solution_fill) },
    { key: 'valve_solution_supply', label: 'Клапан отбор раствора', value: formatIrrStateValue(state.valve_solution_supply) },
    { key: 'valve_irrigation', label: 'Клапан полива', value: formatIrrStateValue(state.valve_irrigation) },
    { key: 'pump_main', label: 'Помпа', value: formatIrrStateValue(state.pump_main) },
  ]
})

// ─── Tank geometry helpers ──────────────────────────────────────────────────

function clampPercent(value: unknown): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 0
  return Math.max(0, Math.min(100, parsed))
}

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

// ─── Tooltip helpers ────────────────────────────────────────────────────────

function elementData(element: string): Record<string, string> {
  if (element === 'clean') {
    return {
      'Уровень': `${Math.round(props.cleanTankLevel)}%`,
      'Объём': props.automationState?.system_config.clean_tank_capacity_l
        ? `${Math.round(Number(props.automationState.system_config.clean_tank_capacity_l))} л`
        : '—',
    }
  }
  if (element === 'nutrient') {
    return {
      'Уровень': `${Math.round(props.nutrientTankLevel)}%`,
      'pH': formatNumber(props.automationState?.current_levels.ph, 2),
      'EC': `${formatNumber(props.automationState?.current_levels.ec, 2)} mS/cm`,
    }
  }
  if (element === 'buffer') {
    return {
      'Уровень': `${Math.round(props.bufferTankLevel)}%`,
    }
  }
  if (element === 'pipes') {
    return {
      'Подача': props.isPumpInActive ? 'Активна' : 'Отключена',
      'Рециркуляция': props.isCirculationActive ? 'Активна' : 'Отключена',
    }
  }
  if (element === 'correction') {
    return {
      'Коррекция pH': props.isPhCorrectionActive ? 'Да' : 'Нет',
      'Коррекция EC': props.isEcCorrectionActive ? 'Да' : 'Нет',
    }
  }
  if (element === 'correction_node') {
    return {
      'Статус узла': isCorrectionNodeActive.value ? 'Активен' : 'Ожидание',
      'pH': formatNumber(props.automationState?.current_levels.ph, 2),
      'EC': `${formatNumber(props.automationState?.current_levels.ec, 2)} mS/cm`,
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
      'Насос P1': props.isPumpInActive ? 'Включен' : 'Выключен',
    }
  }
  if (element === 'circulation') {
    return {
      'Насос P2': props.isCirculationActive ? 'Включен' : 'Выключен',
    }
  }
  if (element === 'pump_correction') {
    return {
      'Насос P3 (дозирование)': isCorrectionPumpActive.value ? 'Включен' : 'Выключен',
    }
  }
  if (element === 'pump') {
    return {
      'Насос P1': props.isPumpInActive || props.isCirculationActive ? 'Включен' : 'Выключен',
      'Режим': props.isPumpInActive ? 'Подача' : props.isCirculationActive ? 'Рециркуляция' : '—',
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
  hoveredElement.value = {
    title: elementTitle(element),
    data: elementData(element),
    x: event.clientX + 2,
    y: event.clientY + 20,
  }
}

function handleMouseMove(element: string, event: MouseEvent): void {
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
</script>

<style scoped>
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

.correction-text-small {
  text-anchor: middle;
  fill: var(--text-primary);
  font-size: 9px;
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
