<template>
  <div class="process-diagram">
    <div class="process-frame">
      <svg
        class="process-svg"
        :viewBox="`0 0 ${T.view.w} ${T.view.h}`"
        role="img"
        aria-label="Схема контура: баки, насос, дозирование, полив"
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
              stop-color="rgba(56,189,248,0.92)"
            />
            <stop
              offset="100%"
              stop-color="rgba(56,189,248,0.42)"
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
              stop-color="rgba(52,211,153,0.92)"
            />
            <stop
              offset="100%"
              stop-color="rgba(52,211,153,0.42)"
            />
          </linearGradient>
        </defs>

        <!-- ── Вход (V1) → бак чистой воды ── -->
        <g class="diagram-group">
          <text
            :x="G.cleanCx"
            :y="T.inlet.top - 3"
            class="pipe-label"
          >
            Вход
          </text>
          <line
            :x1="G.cleanCx"
            :y1="T.inlet.top"
            :x2="G.cleanCx"
            :y2="T.tank.top"
            class="pipe-line"
            :class="{ 'pipe-line--active': isWaterInletActive }"
          />
          <circle
            v-if="isWaterInletActive"
            class="flow-dot"
            r="3.5"
            :cx="G.cleanCx"
            :cy="flow.waterInletFlowY.value"
          />
          <g
            class="valve-node"
            @mouseenter="handleHover('valve_in', $event)"
            @mousemove="handleMouseMove('valve_in', $event)"
            @mouseleave="handleLeave"
          >
            <rect
              :x="G.cleanCx - 12"
              :y="T.inlet.valveY"
              width="24"
              height="13"
              rx="3"
              class="valve"
              :class="{ 'valve--active': isWaterInletActive }"
            />
            <text
              :x="G.cleanCx"
              :y="T.inlet.valveY + 9.5"
              class="valve-label"
              text-anchor="middle"
            >
              V1
            </text>
          </g>
        </g>

        <!-- ── Бак чистой воды ── -->
        <g
          class="tank-group"
          @mouseenter="handleHover('clean', $event)"
          @mousemove="handleMouseMove('clean', $event)"
          @mouseleave="handleLeave"
        >
          <rect
            class="tank-shell"
            :x="T.cleanX"
            :y="T.tank.top"
            :width="T.tank.w"
            :height="T.tank.h"
            :rx="T.tank.radius"
          />
          <clipPath :id="`clip-clean-${uid}`">
            <rect
              :x="T.cleanX"
              :y="T.tank.top"
              :width="T.tank.w"
              :height="T.tank.h"
              :rx="T.tank.radius"
            />
          </clipPath>
          <g :clip-path="`url(#clip-clean-${uid})`">
            <rect
              class="tank-fill"
              :x="T.cleanX"
              :y="tankFillY(cleanTankLevel)"
              :width="T.tank.w"
              :height="tankFillHeight(cleanTankLevel) + T.tank.radius"
              fill="url(#automation-clean-water-gradient)"
            />
            <line
              v-if="cleanTankLevel > 0 && cleanTankLevel < 100"
              :x1="T.cleanX"
              :y1="tankFillY(cleanTankLevel)"
              :x2="T.cleanX + T.tank.w"
              :y2="tankFillY(cleanTankLevel)"
              class="tank-surface"
            />
          </g>
          <text
            class="tank-level"
            :x="G.cleanCx"
            :y="T.tank.top + T.tank.h * 0.56"
          >
            {{ Math.round(cleanTankLevel) }}%
          </text>
        </g>

        <!-- ── Бак раствора ── -->
        <g
          class="tank-group"
          @mouseenter="handleHover('nutrient', $event)"
          @mousemove="handleMouseMove('nutrient', $event)"
          @mouseleave="handleLeave"
        >
          <rect
            class="tank-shell"
            :x="T.solutionX"
            :y="T.tank.top"
            :width="T.tank.w"
            :height="T.tank.h"
            :rx="T.tank.radius"
          />
          <clipPath :id="`clip-solution-${uid}`">
            <rect
              :x="T.solutionX"
              :y="T.tank.top"
              :width="T.tank.w"
              :height="T.tank.h"
              :rx="T.tank.radius"
            />
          </clipPath>
          <g :clip-path="`url(#clip-solution-${uid})`">
            <rect
              class="tank-fill"
              :x="T.solutionX"
              :y="tankFillY(nutrientTankLevel)"
              :width="T.tank.w"
              :height="tankFillHeight(nutrientTankLevel) + T.tank.radius"
              fill="url(#automation-nutrient-gradient)"
            />
            <line
              v-if="nutrientTankLevel > 0 && nutrientTankLevel < 100"
              :x1="T.solutionX"
              :y1="tankFillY(nutrientTankLevel)"
              :x2="T.solutionX + T.tank.w"
              :y2="tankFillY(nutrientTankLevel)"
              class="tank-surface"
            />
          </g>
          <text
            class="tank-level"
            :x="G.solutionCx"
            :y="T.tank.top + T.tank.h * 0.56"
          >
            {{ Math.round(nutrientTankLevel) }}%
          </text>
        </g>

        <!-- ── Магистраль сбора: V2 (чистая) + V3 (раствор) → насос ── -->
        <g class="diagram-group">
          <line
            :x1="G.cleanCx"
            :y1="G.tankBottom"
            :x2="G.cleanCx"
            :y2="T.busY"
            class="pipe-line"
            :class="{ 'pipe-line--active': isMainLineActive }"
          />
          <line
            :x1="G.solutionCx"
            :y1="G.tankBottom"
            :x2="G.solutionCx"
            :y2="T.busY"
            class="pipe-line"
            :class="{ 'pipe-line--active': isMainLineActive }"
          />
          <line
            :x1="G.cleanCx"
            :y1="T.busY"
            :x2="G.pumpInletX"
            :y2="T.busY"
            class="pipe-line"
            :class="{ 'pipe-line--active': isMainLineActive }"
          />
          <circle
            v-if="isMainLineActive"
            class="flow-dot"
            r="3.5"
            :cx="flow.busFlowX.value"
            :cy="T.busY"
          />
          <circle
            :cx="G.cleanCx"
            :cy="T.busY"
            r="2.5"
            class="junction-point"
          />
          <circle
            :cx="G.solutionCx"
            :cy="T.busY"
            r="2.5"
            class="junction-point"
          />

          <g
            class="valve-node"
            @mouseenter="handleHover('valve_out', $event)"
            @mousemove="handleMouseMove('valve_out', $event)"
            @mouseleave="handleLeave"
          >
            <rect
              :x="G.cleanCx - 12"
              :y="T.drainValveY"
              width="24"
              height="13"
              rx="3"
              class="valve"
              :class="{ 'valve--active': isMainLineActive }"
            />
            <text
              :x="G.cleanCx - 16"
              :y="T.drainValveY + 9.5"
              class="valve-label valve-label--side"
              text-anchor="end"
            >
              V2
            </text>
          </g>
          <g
            class="valve-node"
            @mouseenter="handleHover('valve_out', $event)"
            @mousemove="handleMouseMove('valve_out', $event)"
            @mouseleave="handleLeave"
          >
            <rect
              :x="G.solutionCx - 12"
              :y="T.drainValveY"
              width="24"
              height="13"
              rx="3"
              class="valve"
              :class="{ 'valve--active': isMainLineActive }"
            />
            <text
              :x="G.solutionCx + 16"
              :y="T.drainValveY + 9.5"
              class="valve-label valve-label--side"
              text-anchor="start"
            >
              V3
            </text>
          </g>
        </g>

        <!-- ── Подписи баков ── -->
        <g class="tank-labels">
          <text
            class="tank-title"
            :x="G.cleanCx"
            :y="T.titleY"
            text-anchor="middle"
          >
            Чистая вода
          </text>
          <text
            class="tank-title"
            :x="G.solutionCx"
            :y="T.titleY"
            text-anchor="middle"
          >
            Раствор NPK
          </text>
        </g>

        <!-- ── Насос P1 (иконка-ротор) ── -->
        <g
          class="pump-node"
          @mouseenter="handleHover('pump', $event)"
          @mousemove="handleMouseMove('pump', $event)"
          @mouseleave="handleLeave"
        >
          <circle
            :cx="T.pump.cx"
            :cy="T.busY"
            :r="T.pump.r"
            class="equipment-chip pump-body"
            :class="{ 'pump-body--active': isMainLineActive }"
          />
          <g
            class="pump-rotor"
            :class="{ 'pump-rotor--active': isMainLineActive }"
          >
            <path
              :d="rotorPath"
              class="pump-rotor-blades"
            />
            <circle
              :cx="T.pump.cx"
              :cy="T.busY"
              r="2.4"
              class="pump-rotor-hub"
            />
          </g>
          <text
            :x="T.pump.cx"
            :y="T.busY + T.pump.r + 12"
            class="equipment-caption"
            text-anchor="middle"
          >
            Насос P1
          </text>
        </g>

        <line
          :x1="G.pumpOutletX"
          :y1="T.busY"
          :x2="T.dosing.x"
          :y2="T.busY"
          class="pipe-line"
          :class="{ 'pipe-line--active': isMainLineActive }"
        />
        <circle
          v-if="isMainLineActive"
          class="flow-dot"
          r="3.5"
          :cx="flow.pumpOutletFlowX.value"
          :cy="T.busY"
        />

        <!-- ── Дозирование pH / EC ── -->
        <g
          class="correction-node"
          @mouseenter="handleHover('correction', $event)"
          @mousemove="handleMouseMove('correction', $event)"
          @mouseleave="handleLeave"
        >
          <rect
            :x="T.dosing.x"
            :y="T.dosing.y"
            :width="T.dosing.w"
            :height="T.dosing.h"
            rx="7"
            class="equipment-chip correction-body"
            :class="{ 'correction-body--active': isCorrectionNodeActive }"
          />
          <text
            :x="T.dosing.x + T.dosing.w / 2"
            :y="T.dosing.y + 14"
            class="equipment-label"
            text-anchor="middle"
          >
            Дозирование
          </text>
          <g :transform="`translate(${T.dosing.x + 26}, ${T.dosing.y + 28})`">
            <circle
              r="9"
              class="dose-indicator"
              :class="{ 'dose-indicator--ph': isPhCorrectionActive }"
            />
            <text
              y="3"
              class="dose-text"
            >
              pH
            </text>
          </g>
          <g :transform="`translate(${T.dosing.x + T.dosing.w - 26}, ${T.dosing.y + 28})`">
            <circle
              r="9"
              class="dose-indicator"
              :class="{ 'dose-indicator--ec': isEcCorrectionActive }"
            />
            <text
              y="3"
              class="dose-text"
            >
              EC
            </text>
          </g>
        </g>

        <!-- ── Тройник → рециркуляция (V4) / полив (V5) ── -->
        <g class="diagram-group">
          <line
            :x1="G.dosingRight"
            :y1="T.busY"
            :x2="T.teeX"
            :y2="T.busY"
            class="pipe-line"
            :class="{ 'pipe-line--active': isMainLineActive }"
          />
          <circle
            :cx="T.teeX"
            :cy="T.busY"
            r="2.5"
            class="junction-point"
          />

          <!-- Рециркуляция ↑ в бак раствора -->
          <text
            :x="T.teeX + 6"
            :y="T.recirc.topY - 4"
            class="pipe-label pipe-label--side"
          >
            Рецирк.
          </text>
          <path
            :d="`M ${T.teeX} ${T.busY} L ${T.teeX} ${T.recirc.topY} L ${G.solutionCx} ${T.recirc.topY} L ${G.solutionCx} ${T.tank.top}`"
            class="pipe-line"
            :class="{ 'pipe-line--active': isRecircActive }"
            fill="none"
          />
          <circle
            v-if="isRecircActive"
            class="flow-dot"
            r="3.5"
            :cx="flow.recircFlowX.value"
            :cy="flow.recircFlowY.value"
          />
          <g
            class="valve-node"
            @mouseenter="handleHover('circulation', $event)"
            @mousemove="handleMouseMove('circulation', $event)"
            @mouseleave="handleLeave"
          >
            <rect
              :x="T.teeX - 12"
              :y="T.recirc.valveY"
              width="24"
              height="13"
              rx="3"
              class="valve"
              :class="{ 'valve--active': isRecircActive }"
            />
            <text
              :x="T.teeX + 16"
              :y="T.recirc.valveY + 9.5"
              class="valve-label valve-label--side"
              text-anchor="start"
            >
              V4
            </text>
          </g>

          <!-- Полив → -->
          <text
            :x="T.irr.endX - 4"
            :y="T.busY - 10"
            class="pipe-label"
            text-anchor="end"
          >
            Полив
          </text>
          <line
            :x1="T.teeX"
            :y1="T.busY"
            :x2="T.irr.endX"
            :y2="T.busY"
            class="pipe-line"
            :class="{ 'pipe-line--active': isIrrigationActive }"
          />
          <circle
            v-if="isIrrigationActive"
            class="flow-dot"
            r="3.5"
            :cx="flow.irrigationFlowX.value"
            :cy="T.busY"
          />
          <g
            class="valve-node"
            @mouseenter="handleHover('valve_irr', $event)"
            @mousemove="handleMouseMove('valve_irr', $event)"
            @mouseleave="handleLeave"
          >
            <rect
              :x="T.irr.valveX - 12"
              :y="T.busY - 6.5"
              width="24"
              height="13"
              rx="3"
              class="valve"
              :class="{ 'valve--active': isIrrigationActive }"
            />
            <text
              :x="T.irr.valveX"
              :y="T.busY + 3"
              class="valve-label"
              text-anchor="middle"
            >
              V5
            </text>
          </g>
          <path
            :d="`M ${T.irr.endX} ${T.busY} l 6 0 m -3 -3 l 3 3 l -3 3`"
            class="arrow-right"
            :class="{ 'arrow-right--active': isIrrigationActive }"
          />
        </g>
      </svg>

      <ul class="diagram-legend">
        <li>
          <span class="legend-dot legend-dot--flow" />
          Поток активен
        </li>
        <li>
          <span class="legend-dot legend-dot--valve" />
          Клапан открыт
        </li>
        <li>
          <span class="legend-dot legend-dot--dose" />
          Дозирование pH/EC
        </li>
        <li>
          <span class="legend-dot legend-dot--idle" />
          Ожидание
        </li>
      </ul>
    </div>

    <div
      v-if="irrNodeState"
      class="irr-snapshot"
    >
      <div class="irr-snapshot__head">
        <span class="irr-snapshot__title">Состояние irr-узла</span>
        <span
          v-if="irrNodeState.updated_at"
          class="irr-snapshot__time"
        >
          {{ formatUpdatedAt(irrNodeState.updated_at) }}
        </span>
      </div>
      <div class="irr-snapshot__chips">
        <span
          v-for="item in irrStateRows"
          :key="item.key"
          class="irr-snapshot__chip"
          :class="{ 'irr-snapshot__chip--on': item.value === 'Вкл' }"
        >
          {{ item.label }}: <strong>{{ item.value }}</strong>
        </span>
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
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import type { AutomationState, HoveredElement, IrrNodeState } from '@/types/Automation'
import {
  elementTitle,
  formatIrrStateValue,
  formatNumber,
  formatUpdatedAt,
  tankFillHeight,
  tankFillY,
} from '@/composables/automationProcessDiagramHelpers'
import {
  DIAGRAM_GEO,
  DIAGRAM_LAYOUT,
  createDiagramFlow,
} from '@/composables/automationDiagramLayout'

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

const T = DIAGRAM_LAYOUT
const G = DIAGRAM_GEO
const flow = createDiagramFlow(toRef(props, 'flowOffset'))

const uid = Math.random().toString(36).slice(2, 8)

const hoveredElement = ref<HoveredElement | null>(null)

const isMainLineActive = computed(() =>
  props.isPumpInActive
  || props.isCirculationActive
  || props.isPhCorrectionActive
  || props.isEcCorrectionActive,
)
const isCorrectionNodeActive = computed(() => props.isPhCorrectionActive || props.isEcCorrectionActive)
const isRecircActive = computed(() => props.isTankRefillActive || props.isCirculationActive)
const isInletValveOpen = computed(() => props.isWaterInletActive)
const isOutletValveOpen = computed(() => props.isProcessActive || isCorrectionNodeActive.value)

const rotorPath = computed(() => {
  const { cx, r } = T.pump
  const cy = T.busY
  const blade = r * 0.7
  return [
    `M ${cx} ${cy - blade} L ${cx} ${cy + blade}`,
    `M ${cx - blade} ${cy} L ${cx + blade} ${cy}`,
    `M ${cx - blade * 0.7} ${cy - blade * 0.7} L ${cx + blade * 0.7} ${cy + blade * 0.7}`,
    `M ${cx - blade * 0.7} ${cy + blade * 0.7} L ${cx + blade * 0.7} ${cy - blade * 0.7}`,
  ].join(' ')
})

const tooltipStyle = computed(() => {
  if (!hoveredElement.value) return {}
  return {
    left: `${hoveredElement.value.x}px`,
    top: `${hoveredElement.value.y}px`,
  }
})

const irrStateRows = computed(() => {
  const state = props.irrNodeState
  if (!state) return []
  return [
    { key: 'pump', label: 'P1', value: formatIrrStateValue(state.pump_main) },
    { key: 'v1', label: 'V1', value: formatIrrStateValue(state.valve_clean_fill) },
    { key: 'v2', label: 'V2', value: formatIrrStateValue(state.valve_clean_supply) },
    { key: 'v3', label: 'V3', value: formatIrrStateValue(state.valve_solution_fill) },
    { key: 'v4', label: 'V4', value: formatIrrStateValue(state.valve_solution_supply) },
    { key: 'v5', label: 'V5', value: formatIrrStateValue(state.valve_irrigation) },
    { key: 'clean_max', label: 'Чист. max', value: formatIrrStateValue(state.clean_level_max) },
    { key: 'sol_max', label: 'Раств. max', value: formatIrrStateValue(state.solution_level_max) },
  ]
})

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
  if (element === 'correction') {
    return {
      'Коррекция pH': props.isPhCorrectionActive ? 'Да' : 'Нет',
      'Коррекция EC': props.isEcCorrectionActive ? 'Да' : 'Нет',
    }
  }
  if (element === 'valve_in') {
    return { 'V1 (вход)': isInletValveOpen.value ? 'Открыт' : 'Закрыт' }
  }
  if (element === 'valve_out') {
    return { 'Отбор (V2/V3)': isOutletValveOpen.value ? 'Открыт' : 'Закрыт' }
  }
  if (element === 'valve_irr') {
    return { 'V5 (полив)': props.isIrrigationActive ? 'Открыт' : 'Закрыт' }
  }
  if (element === 'pump') {
    return {
      'Насос P1': isMainLineActive.value ? 'Включен' : 'Выключен',
      'Режим': props.isPumpInActive ? 'Набор' : props.isCirculationActive ? 'Рециркуляция' : '—',
    }
  }
  if (element === 'circulation') {
    return {
      'V4 (рециркуляция)': isRecircActive.value ? 'Открыт' : 'Закрыт',
    }
  }
  return {}
}

function handleHover(element: string, event: MouseEvent): void {
  hoveredElement.value = {
    title: elementTitle(element),
    data: elementData(element),
    x: event.clientX + 2,
    y: event.clientY + 20,
  }
}

function handleMouseMove(_element: string, event: MouseEvent): void {
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
.process-diagram {
  width: 100%;
}

.process-frame {
  border: 1px solid color-mix(in srgb, var(--border-muted) 60%, transparent);
  border-radius: 1rem;
  background:
    radial-gradient(circle at 1px 1px, color-mix(in srgb, var(--border-muted) 35%, transparent) 1px, transparent 0)
    0 0 / 22px 22px,
    color-mix(in srgb, var(--surface-card) 35%, transparent);
  padding: 0.85rem 1rem 0.6rem;
}

.process-svg {
  display: block;
  width: 100%;
  max-width: 560px;
  height: auto;
  margin-inline: auto;
  color: var(--text-primary, #0f172a);
}

.diagram-group,
.tank-labels {
  pointer-events: none;
}

.valve-node,
.pump-node,
.correction-node,
.tank-group {
  pointer-events: auto;
  cursor: default;
}

.tank-shell {
  fill: color-mix(in srgb, var(--surface-card) 88%, transparent);
  stroke: var(--border-muted);
  stroke-width: 1.5;
}

.tank-fill {
  transition: y 0.4s ease, height 0.4s ease;
}

.tank-surface {
  stroke: rgba(255, 255, 255, 0.7);
  stroke-width: 1.5;
}

.tank-level {
  text-anchor: middle;
  fill: var(--text-primary, #0f172a);
  font-size: 13px;
  font-weight: 700;
  opacity: 0.78;
}

.tank-title {
  fill: var(--text-muted, #475569);
  font-size: 10px;
  font-weight: 600;
}

.pipe-line {
  stroke: color-mix(in srgb, var(--border-muted) 90%, transparent);
  stroke-width: 2.5;
  stroke-linecap: round;
  transition: stroke 0.25s ease, stroke-width 0.25s ease;
}

.pipe-line--active {
  stroke: var(--accent-cyan, #06b6d4);
  stroke-width: 3;
}

.flow-dot {
  fill: var(--accent-cyan, #06b6d4);
  filter: drop-shadow(0 0 3px color-mix(in srgb, var(--accent-cyan, #06b6d4) 65%, transparent));
  animation: flow-dot-pulse 1s linear infinite;
}

.junction-point {
  fill: color-mix(in srgb, var(--border-muted) 90%, transparent);
}

.valve,
.equipment-chip {
  fill: var(--surface-card, #f8fafc);
  stroke: var(--border-muted, #94a3b8);
  stroke-width: 1.5;
  transition: fill 0.25s ease, stroke 0.25s ease;
}

.valve--active {
  fill: color-mix(in srgb, var(--accent-green, #22c55e) 18%, var(--surface-card, #f8fafc));
  stroke: var(--accent-green, #16a34a);
}

.pump-body--active {
  fill: color-mix(in srgb, var(--accent-cyan, #06b6d4) 16%, var(--surface-card, #f8fafc));
  stroke: var(--accent-cyan, #0891b2);
}

.pump-rotor {
  transform-box: fill-box;
  transform-origin: center;
}

.pump-rotor-blades {
  stroke: var(--text-muted, #94a3b8);
  stroke-width: 1.4;
  stroke-linecap: round;
  fill: none;
  transition: stroke 0.25s ease;
}

.pump-rotor-hub {
  fill: var(--text-muted, #94a3b8);
}

.pump-rotor--active {
  animation: rotor-spin 1.4s linear infinite;
}

.pump-rotor--active .pump-rotor-blades {
  stroke: var(--accent-cyan, #0891b2);
}

.pump-rotor--active .pump-rotor-hub {
  fill: var(--accent-cyan, #0891b2);
}

.correction-body--active {
  fill: color-mix(in srgb, var(--accent-violet, #7c3aed) 12%, var(--surface-card, #f8fafc));
  stroke: var(--accent-violet, #7c3aed);
}

.equipment-label {
  fill: var(--text-primary, #0f172a);
  font-size: 9px;
  font-weight: 700;
}

.equipment-caption {
  fill: var(--text-muted, #64748b);
  font-size: 9px;
  font-weight: 600;
}

.valve-label {
  fill: var(--text-primary, #0f172a);
  font-size: 9px;
  font-weight: 700;
}

.valve-label--side {
  font-size: 8px;
  fill: var(--text-muted, #64748b);
}

.dose-indicator {
  fill: color-mix(in srgb, var(--surface-card) 80%, transparent);
  stroke: var(--border-muted);
  stroke-width: 1.5;
  transition: fill 0.25s ease, stroke 0.25s ease;
}

.dose-indicator--ph,
.dose-indicator--ec {
  fill: color-mix(in srgb, var(--accent-violet, #7c3aed) 45%, transparent);
  stroke: var(--accent-violet, #7c3aed);
  animation: dose-pulse 1.2s ease-in-out infinite;
}

.dose-text {
  text-anchor: middle;
  fill: var(--text-primary, #0f172a);
  font-size: 8px;
  font-weight: 700;
}

.pipe-label {
  text-anchor: middle;
  fill: var(--text-dim);
  font-size: 9px;
  font-weight: 600;
}

.pipe-label--side {
  text-anchor: start;
}

.arrow-right {
  fill: none;
  stroke: color-mix(in srgb, var(--border-muted) 90%, transparent);
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.arrow-right--active {
  stroke: var(--accent-cyan, #06b6d4);
}

.diagram-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 1rem;
  margin-top: 0.6rem;
  padding-top: 0.55rem;
  border-top: 1px solid color-mix(in srgb, var(--border-muted) 45%, transparent);
  list-style: none;
}

.diagram-legend li {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 11px;
  color: var(--text-muted);
}

.legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 9999px;
  border: 1px solid transparent;
}

.legend-dot--flow {
  background: var(--accent-cyan, #06b6d4);
}

.legend-dot--valve {
  background: var(--accent-green, #22c55e);
}

.legend-dot--dose {
  background: var(--accent-violet, #7c3aed);
}

.legend-dot--idle {
  background: transparent;
  border-color: var(--border-muted, #94a3b8);
}

.irr-snapshot {
  margin-top: 0.75rem;
  padding: 0.65rem 0.75rem;
  border-radius: 0.65rem;
  border: 1px solid color-mix(in srgb, var(--border-muted) 70%, transparent);
  background: color-mix(in srgb, var(--surface-card) 60%, transparent);
}

.irr-snapshot__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
}

.irr-snapshot__title {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-dim);
}

.irr-snapshot__time {
  font-size: 10px;
  color: var(--text-dim);
}

.irr-snapshot__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.irr-snapshot__chip {
  font-size: 10px;
  padding: 0.2rem 0.45rem;
  border-radius: 9999px;
  border: 1px solid color-mix(in srgb, var(--border-muted) 80%, transparent);
  color: var(--text-muted);
}

.irr-snapshot__chip--on {
  border-color: color-mix(in srgb, var(--accent-green) 50%, transparent);
  color: var(--text-primary);
  background: color-mix(in srgb, var(--accent-green) 12%, transparent);
}

.details-tooltip {
  position: fixed;
  min-width: 160px;
  max-width: 240px;
  background: color-mix(in srgb, var(--bg-elevated) 94%, transparent);
  border: 1px solid var(--border-muted);
  border-radius: 8px;
  padding: 8px 10px;
  box-shadow: 0 8px 20px color-mix(in srgb, var(--bg-app) 25%, transparent);
  pointer-events: none;
  z-index: 80;
  backdrop-filter: blur(8px);
}

.tooltip-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.tooltip-grid {
  display: grid;
  gap: 3px;
}

.tooltip-row {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  font-size: 11px;
}

.tooltip-label {
  color: var(--text-dim);
}

.tooltip-value {
  color: var(--text-primary);
  font-weight: 600;
}

@keyframes dose-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

@keyframes flow-dot-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

@keyframes rotor-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .flow-dot,
  .pump-rotor--active,
  .dose-indicator--ph,
  .dose-indicator--ec {
    animation: none;
  }
}
</style>
