# Frontend Refactoring & Visual Improvements Proposal

**Date:** 2026-02-16
**Version:** 1.0
**Status:** Draft for Review

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Analysis](#2-current-state-analysis)
3. [Critical Issues](#3-critical-issues)
4. [Refactoring Proposals](#4-refactoring-proposals)
5. [Visual Improvements](#5-visual-improvements)
6. [Human Readability Improvements](#6-human-readability-improvements)
7. [Performance Optimizations](#7-performance-optimizations)
8. [Accessibility Improvements](#8-accessibility-improvements)
9. [Implementation Roadmap](#9-implementation-roadmap)

---

## 1. Executive Summary

This document proposes comprehensive refactoring and visual improvements for the Hydro 2.0 frontend application. The goal is to enhance:

- **Code maintainability** through decomposition of large components
- **Visual clarity** for greenhouse operators
- **Human readability** of data and system state
- **Performance** for real-time telemetry display
- **Accessibility** for all users

### Key Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Largest component | 1577 lines | <300 lines |
| Largest composable | 63KB | <15KB |
| Components count | 86 | ~100 (modular) |
| Composables count | 77 | ~50 (consolidated) |
| CSS variables | 67 | 80+ (semantic) |

---

## 2. Current State Analysis

### 2.1 Technology Stack

```
Frontend Stack:
├── Vue 3.4+ with Composition API
├── TypeScript 5.x
├── Inertia.js (SPA navigation)
├── Tailwind CSS 3.x
├── Pinia (state management)
├── VueUse (utilities)
└── Chart.js (visualizations)
```

### 2.2 File Structure

```
resources/js/
├── Components/          # 86 files - UI components
│   ├── primitives/      # (missing) - base UI elements
│   ├── domain/          # (missing) - business components
│   └── layout/          # (missing) - layout components
├── Pages/               # 24 directories - route pages
├── Layouts/             # 1 file - AppLayout.vue
├── composables/         # 77 files - composition functions
├── stores/              # 7 files - Pinia stores
├── types/               # 18 files - TypeScript types
└── utils/               # 25 files - helper functions
```

### 2.3 Design System

Current CSS variables are well-organized:

```css
/* Colors */
--accent-green: #49e08a;
--accent-cyan: #5dd6ff;
--accent-amber: #f0b268;
--accent-red: #ff6c6c;

/* Surfaces */
--bg-main: #070b10;
--bg-surface: rgba(12, 18, 28, 0.92);
--bg-elevated: rgba(24, 34, 50, 0.96);

/* Text */
--text-primary: #e6eef7;
--text-muted: #a3b4c7;
--text-dim: #6f8094;
```

---

## 3. Critical Issues

### 3.1 Oversized Components

| File | Lines | Issue |
|------|-------|-------|
| `AutomationProcessPanel.vue` | 1577 | Monolithic SVG diagram + logic |
| `useZoneAutomationTab.ts` | ~2000 | 63KB - all automation logic |
| `Dashboard/Index.vue` | 604 | Multiple dashboard types mixed |
| `ZoneTargets.vue` | 479 | Could be split into metric cards |
| `useZoneShowPage.ts` | 1038 | Zone page orchestration |
| `MetricCard.vue` | 249 | Acceptable but could be simpler |

### 3.2 Inconsistent Patterns

```typescript
// Pattern 1: Direct ref
const activeTab = ref('overview')

// Pattern 2: useUrlState
const activeTab = useUrlState({ key: 'tab', defaultValue: 'overview' })

// Pattern 3: Computed from props
const activeTab = computed(() => props.initialTab || 'overview')
```

### 3.3 Mixed Languages in UI

```
Found mixed Russian/English:
- Labels: "Прогресс цикла" (Russian)
- Technical terms: "pH", "EC", "NPK" (International)
- Status codes: "RUNNING", "IDLE" (English)
- Code comments: Mixed
```

### 3.4 Prop Drilling & Deep Nesting

```vue
<!-- Example: 4 levels of nesting -->
<AppLayout>
  <ZonePage>
    <ZoneOverview>
      <ZoneTargets>
        <MetricCard>
          <MetricIndicator>
            <!-- Actual content -->
          </MetricIndicator>
        </MetricCard>
      </ZoneTargets>
    </ZoneOverview>
  </ZonePage>
</AppLayout>
```

---

## 4. Refactoring Proposals

### 4.1 Component Decomposition

#### 4.1.1 AutomationProcessPanel Split

**Current:** Single 1577-line file with SVG diagram + state management

**Proposed Structure:**

```
Components/Automation/
├── AutomationProcessPanel.vue      # Main container (~150 lines)
├── AutomationDiagram/
│   ├── ProcessDiagram.vue          # SVG container
│   ├── TankVisualization.vue       # Tank components
│   ├── PipeFlowAnimation.vue       # Flow animations
│   ├── ValveIndicator.vue          # Valve states
│   └── PumpIndicator.vue           # Pump states
├── AutomationStageList.vue         # Setup stages display
├── AutomationHeader.vue            # Status header
└── composables/
    ├── useProcessDiagram.ts        # Diagram state
    ├── useTankLevels.ts            # Tank calculations
    └── useFlowAnimation.ts         # Animation logic
```

**Example Refactored Component:**

```vue
<!-- AutomationProcessPanel.vue (simplified) -->
<template>
  <section class="automation-process-panel surface-card">
    <AutomationHeader
      :state="state"
      :progress="progress"
    />
    
    <AutomationStageList
      :stages="setupStages"
      :current-stage="currentStage"
    />
    
    <ProcessDiagram
      :tanks="tankLevels"
      :flows="activeFlows"
      :valves="valveStates"
    />
  </section>
</template>

<script setup lang="ts">
import { useAutomationProcess } from './composables/useAutomationProcess'
import AutomationHeader from './AutomationHeader.vue'
import AutomationStageList from './AutomationStageList.vue'
import ProcessDiagram from './ProcessDiagram.vue'

const props = defineProps<{
  zoneId: number
  state: AutomationState
}>()

const {
  setupStages,
  currentStage,
  tankLevels,
  activeFlows,
  valveStates,
  progress
} = useAutomationProcess(props.zoneId)
</script>
```

#### 4.1.2 useZoneAutomationTab Decomposition

**Current:** 63KB single file

**Proposed Structure:**

```typescript
// composables/automation/index.ts
export { useAutomationState } from './useAutomationState'
export { useAutomationTargets } from './useAutomationTargets'
export { useCorrectionCycle } from './useCorrectionCycle'
export { usePidControl } from './usePidControl'
export { useTankManagement } from './useTankManagement'
export { useAutomationCommands } from './useAutomationCommands'

// composables/automation/useAutomationState.ts
export function useAutomationState(zoneId: Ref<number>) {
  const state = ref<AutomationState>('IDLE')
  const previousState = ref<AutomationState | null>(null)
  const stateHistory = ref<StateTransition[]>([])
  
  // ~100 lines of state management
  return { state, previousState, stateHistory, transition }
}

// composables/automation/useCorrectionCycle.ts
export function useCorrectionCycle(zoneId: Ref<number>) {
  const cyclePhase = ref<CyclePhase>('IDLE')
  const progress = ref(0)
  
  // ~150 lines of cycle logic
  return { cyclePhase, progress, startCycle, pauseCycle }
}
```

### 4.2 Component Categories

Create a clear component hierarchy:

```
Components/
├── primitives/              # Base UI elements (no business logic)
│   ├── Button.vue
│   ├── Card.vue
│   ├── Badge.vue
│   ├── Input.vue
│   ├── Select.vue
│   ├── Modal.vue
│   ├── Tabs.vue
│   └── Skeleton.vue
│
├── feedback/                # User feedback components
│   ├── Toast.vue
│   ├── Alert.vue
│   ├── LoadingState.vue
│   ├── EmptyState.vue
│   └── ErrorBoundary.vue
│
├── data-display/            # Data visualization
│   ├── MetricCard.vue
│   ├── StatusIndicator.vue
│   ├── Sparkline.vue
│   ├── DataTable.vue
│   └── Charts/
│       ├── LineChart.vue
│       ├── GaugeChart.vue
│       └── ProgressRing.vue
│
├── domain/                  # Business-specific components
│   ├── Zone/
│   │   ├── ZoneCard.vue
│   │   ├── ZoneTargets.vue
│   │   ├── ZoneTelemetry.vue
│   │   └── ZoneDevices.vue
│   ├── Automation/
│   │   └── ... (see 4.1.1)
│   ├── GrowCycle/
│   │   ├── CycleProgress.vue
│   │   ├── StageTimeline.vue
│   │   └── PhaseIndicator.vue
│   └── Recipe/
│       ├── RecipeCard.vue
│       └── PhaseEditor.vue
│
└── layout/                  # Layout components
    ├── AppHeader.vue
    ├── AppSidebar.vue
    ├── PageHeader.vue
    └── Breadcrumbs.vue
```

### 4.3 Standardize State Management

Create consistent patterns for component state:

```typescript
// composables/useComponentState.ts - Standard pattern
export function useComponentState<T>(options: {
  key: string
  defaultValue: T
  persistToUrl?: boolean
  persistToStorage?: boolean
}) {
  const { key, defaultValue, persistToUrl, persistToStorage } = options
  
  // URL state (for shareable links)
  const urlState = persistToUrl 
    ? useUrlState({ key, defaultValue })
    : null
    
  // Session storage (for tabs/windows)
  const storageState = persistToStorage
    ? useSessionStorage(key, defaultValue)
    : null
    
  // Local state (default)
  const localState = ref(defaultValue)
  
  // Computed value with priority
  const state = computed({
    get: () => urlState?.value ?? storageState?.value ?? localState.value,
    set: (value) => {
      if (urlState) urlState.value = value
      if (storageState) storageState.value = value
      localState.value = value
    }
  })
  
  return { state }
}
```

---

## 5. Visual Improvements

### 5.1 Enhanced Metric Cards

**Current:** Basic metric display with target comparison

**Proposed:** Multi-state visual indicators with trend analysis

```vue
<!-- Enhanced MetricCard.vue -->
<template>
  <Card class="metric-card" :class="statusClass">
    <!-- Header with status indicator -->
    <div class="metric-card__header">
      <div class="metric-card__label">{{ label }}</div>
      <StatusBadge :status="status" :trend="trend" />
    </div>
    
    <!-- Primary value with context -->
    <div class="metric-card__value-container">
      <div class="metric-card__value" :style="{ color: valueColor }">
        {{ formattedValue }}
      </div>
      <div class="metric-card__unit">{{ unit }}</div>
    </div>
    
    <!-- Target range visualization -->
    <div class="metric-card__range">
      <RangeBar
        :min="targetMin"
        :max="targetMax"
        :value="value"
        :show-indicator="true"
      />
    </div>
    
    <!-- Trend sparkline (optional) -->
    <div v-if="showTrend" class="metric-card__trend">
      <Sparkline :data="historyData" :highlight-last="true" />
      <span class="metric-card__trend-label">
        {{ trendDirection }} {{ trendValue }}
      </span>
    </div>
    
    <!-- Quick actions (optional) -->
    <div v-if="showActions" class="metric-card__actions">
      <Button size="sm" variant="ghost" @click="adjustUp">
        <Icon name="chevron-up" />
      </Button>
      <Button size="sm" variant="ghost" @click="adjustDown">
        <Icon name="chevron-down" />
      </Button>
      <Button size="sm" variant="ghost" @click="showHistory">
        <Icon name="chart-line" />
      </Button>
    </div>
  </Card>
</template>
```

### 5.2 Improved Status Visualization

**Current:** Text-based status with colored badges

**Proposed:** Visual status tree with animation

```vue
<!-- StatusTree.vue - Visual hierarchy of system status -->
<template>
  <div class="status-tree">
    <StatusNode
      :label="'Greenhouse'"
      :status="overallStatus"
      :expanded="expanded"
      @toggle="expanded = !expanded"
    >
      <template #children>
        <StatusNode
          v-for="zone in zones"
          :key="zone.id"
          :label="zone.name"
          :status="zone.status"
          :details="zone.summary"
        >
          <template #metrics>
            <MetricPill
              v-for="metric in zone.metrics"
              :key="metric.type"
              :type="metric.type"
              :value="metric.value"
              :status="metric.status"
            />
          </template>
        </StatusNode>
      </template>
    </StatusNode>
  </div>
</template>
```

### 5.3 Enhanced Process Diagram

**Current:** Static SVG with basic animations

**Proposed:** Interactive, responsive process visualization

```vue
<!-- ProcessDiagram.vue - Enhanced visualization -->
<template>
  <div class="process-diagram" ref="containerRef">
    <!-- Responsive SVG container -->
    <svg
      :viewBox="viewBox"
      class="process-diagram__canvas"
      role="img"
      aria-label="Process flow diagram"
    >
      <!-- Gradient definitions -->
      <defs>
        <TankGradient id="clean-water" :color="colors.water" />
        <TankGradient id="nutrient" :color="colors.nutrient" />
        <TankGradient id="buffer" :color="colors.buffer" />
        
        <!-- Flow animation -->
        <FlowPattern id="flow-pattern" :active="isFlowing" />
      </defs>
      
      <!-- Interactive tanks -->
      <g
        v-for="tank in tanks"
        :key="tank.id"
        class="process-diagram__tank"
        @click="selectTank(tank)"
        @mouseenter="showTooltip(tank, $event)"
        @mouseleave="hideTooltip"
      >
        <TankShape
          :type="tank.type"
          :level="tank.level"
          :gradient="tank.gradient"
        />
        <TankLabel
          :name="tank.name"
          :level="tank.level"
          :capacity="tank.capacity"
        />
      </g>
      
      <!-- Animated pipes -->
      <g class="process-diagram__pipes">
        <PipeSegment
          v-for="pipe in pipes"
          :key="pipe.id"
          :path="pipe.path"
          :active="pipe.active"
          :flow-rate="pipe.flowRate"
        />
      </g>
      
      <!-- Interactive valves -->
      <g class="process-diagram__valves">
        <ValveIndicator
          v-for="valve in valves"
          :key="valve.id"
          :position="valve.position"
          :state="valve.state"
          :label="valve.label"
          @toggle="toggleValve(valve)"
        />
      </g>
    </svg>
    
    <!-- Tooltip overlay -->
    <Teleport to="body">
      <DiagramTooltip
        v-if="tooltipData"
        :data="tooltipData"
        :position="tooltipPosition"
      />
    </Teleport>
    
    <!-- Mini-map for large diagrams -->
    <DiagramMinimap
      v-if="showMinimap"
      :view-box="viewBox"
      :visible-area="visibleArea"
    />
  </div>
</template>
```

### 5.4 Zone Dashboard Redesign

**Current:** Tabbed interface with basic metrics

**Proposed:** Dashboard with customizable widgets

```vue
<!-- ZoneDashboard.vue - Customizable dashboard -->
<template>
  <div class="zone-dashboard">
    <!-- Dashboard toolbar -->
    <div class="zone-dashboard__toolbar">
      <DashboardControls
        :layout="currentLayout"
        :available-widgets="availableWidgets"
        @layout-change="changeLayout"
        @widget-add="addWidget"
      />
      <TimeRangeSelector v-model="timeRange" />
      <RefreshControl
        :interval="refreshInterval"
        :loading="isLoading"
        @refresh="refresh"
      />
    </div>
    
    <!-- Grid layout -->
    <GridLayout
      :columns="12"
      :row-height="80"
      :layout="currentLayout"
      @layout-update="saveLayout"
    >
      <!-- Widget slots -->
      <GridItem
        v-for="widget in widgets"
        :key="widget.id"
        :x="widget.x"
        :y="widget.y"
        :w="widget.w"
        :h="widget.h"
      >
        <component
          :is="widget.component"
          v-bind="widget.props"
          @remove="removeWidget(widget.id)"
        />
      </GridItem>
    </GridLayout>
    
    <!-- Available widgets palette -->
    <WidgetPalette
      :widgets="availableWidgets"
      :drag-enabled="true"
    />
  </div>
</template>
```

### 5.5 Alert Visualization Improvements

**Current:** Basic list with badges

**Proposed:** Severity-based visualization with actions

```vue
<!-- AlertsPanel.vue - Enhanced alerts -->
<template>
  <div class="alerts-panel">
    <!-- Alert summary header -->
    <div class="alerts-panel__summary">
      <AlertSummary
        :critical="criticalCount"
        :warning="warningCount"
        :info="infoCount"
      />
      <AlertFilters
        v-model="filters"
        :severities="['critical', 'warning', 'info']"
        :categories="alertCategories"
      />
    </div>
    
    <!-- Alert timeline -->
    <div class="alerts-panel__timeline">
      <AlertTimeline
        :alerts="filteredAlerts"
        :group-by="groupBy"
        @select="selectAlert"
      >
        <template #alert="{ alert }">
          <AlertCard
            :alert="alert"
            :expanded="selectedAlert?.id === alert.id"
            @acknowledge="acknowledgeAlert"
            @resolve="resolveAlert"
            @escalate="escalateAlert"
          >
            <template #details>
              <AlertDetails :alert="alert" />
            </template>
            <template #actions>
              <AlertActions
                :alert="alert"
                :available-actions="getAvailableActions(alert)"
              />
            </template>
          </AlertCard>
        </template>
      </AlertTimeline>
    </div>
    
    <!-- Quick actions for selected -->
    <AlertQuickActions
      v-if="selectedAlerts.length > 1"
      :count="selectedAlerts.length"
      @acknowledge-all="acknowledgeAll"
      @resolve-all="resolveAll"
    />
  </div>
</template>
```

---

## 6. Human Readability Improvements

### 6.1 Data Formatting Standards

Create consistent formatters for all data types:

```typescript
// utils/formatters.ts

/**
 * Standard formatters for human-readable data display
 */

// pH: 2 decimal places, indicate if out of range
export function formatPH(value: number | null, range?: { min: number; max: number }): string {
  if (value === null || value === undefined) return '--'
  const formatted = value.toFixed(2)
  if (range && (value < range.min || value > range.max)) {
    return `${formatted} ⚠️`
  }
  return formatted
}

// EC: 2 decimal places with unit
export function formatEC(value: number | null): string {
  if (value === null || value === undefined) return '--'
  return `${value.toFixed(2)} мСм/см`
}

// Temperature: 1 decimal place with unit
export function formatTemperature(value: number | null, unit: 'C' | 'F' = 'C'): string {
  if (value === null || value === undefined) return '--'
  const formatted = unit === 'C' ? value.toFixed(1) : (value * 9/5 + 32).toFixed(1)
  return `${formatted}°${unit}`
}

// Duration: Human readable
export function formatDuration(minutes: number): string {
  if (minutes < 60) {
    return `${Math.round(minutes)} мин`
  }
  if (minutes < 1440) {
    const hours = Math.floor(minutes / 60)
    const mins = Math.round(minutes % 60)
    return mins > 0 ? `${hours}ч ${mins}м` : `${hours}ч`
  }
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  return hours > 0 ? `${days}д ${hours}ч` : `${days}д`
}

// Relative time
export function formatRelativeTime(date: Date | string): string {
  const now = new Date()
  const target = new Date(date)
  const diffMs = now.getTime() - target.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  
  if (diffMins < 1) return 'только что'
  if (diffMins < 60) return `${diffMins} мин назад`
  if (diffMins < 1440) return `${Math.floor(diffMins / 60)}ч назад`
  return `${Math.floor(diffMins / 1440)}д назад`
}

// Status translation
export function translateStatus(status: string): string {
  const translations: Record<string, string> = {
    RUNNING: 'Работает',
    PAUSED: 'Пауза',
    ALARM: 'Авария',
    WARNING: 'Внимание',
    IDLE: 'Ожидание',
    NEW: 'Новая',
    ONLINE: 'Онлайн',
    OFFLINE: 'Офлайн',
    DEGRADED: 'Ограничен',
  }
  return translations[status] || status
}

// Trend direction
export function formatTrend(current: number, previous: number): {
  direction: 'up' | 'down' | 'stable'
  text: string
  icon: string
} {
  const diff = current - previous
  if (Math.abs(diff) < 0.01) {
    return { direction: 'stable', text: 'Стабильно', icon: '→' }
  }
  if (diff > 0) {
    return { direction: 'up', text: `+${diff.toFixed(2)}`, icon: '↑' }
  }
  return { direction: 'down', text: diff.toFixed(2), icon: '↓' }
}
```

### 6.2 Consistent Terminology

Create a terminology dictionary for UI consistency:

```typescript
// constants/terminology.ts

export const TERMINOLOGY = {
  // Metrics
  metrics: {
    ph: { short: 'pH', full: 'Водородный показатель', unit: '' },
    ec: { short: 'EC', full: 'Электропроводность', unit: 'мСм/см' },
    temperature: { short: 'Темп.', full: 'Температура', unit: '°C' },
    humidity: { short: 'Влажн.', full: 'Влажность воздуха', unit: '%' },
    co2: { short: 'CO₂', full: 'Углекислый газ', unit: 'ppm' },
  },
  
  // Equipment
  equipment: {
    tank: { singular: 'Бак', plural: 'Баки' },
    pump: { singular: 'Насос', plural: 'Насосы' },
    valve: { singular: 'Клапан', plural: 'Клапаны' },
    sensor: { singular: 'Датчик', plural: 'Датчики' },
    node: { singular: 'Узел', plural: 'Узлы' },
  },
  
  // Actions
  actions: {
    irrigation: 'Полив',
    correction: 'Коррекция',
    calibration: 'Калибровка',
    start: 'Запустить',
    stop: 'Остановить',
    pause: 'Пауза',
    resume: 'Продолжить',
  },
  
  // Time periods
  periods: {
    day: { singular: 'день', plural: 'дней', short: 'д' },
    hour: { singular: 'час', plural: 'часов', short: 'ч' },
    minute: { singular: 'минута', plural: 'минут', short: 'м' },
  },
} as const

// Helper function for pluralization
export function pluralize(count: number, forms: { singular: string; plural: string }): string {
  const mod10 = count % 10
  const mod100 = count % 100
  
  if (mod10 === 1 && mod100 !== 11) {
    return forms.singular
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) {
    return forms.singular // Russian genitive singular
  }
  return forms.plural
}
```

### 6.3 Visual Hierarchy Standards

Define clear visual hierarchy rules:

```css
/* Visual Hierarchy Standards */

/* Level 1: Page Title */
.page-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

/* Level 2: Section Header */
.section-header {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

/* Level 3: Card Header */
.card-header {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Level 4: Primary Value */
.primary-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--accent-cyan);
}

/* Level 5: Secondary Value */
.secondary-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
}

/* Level 6: Label */
.label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

/* Level 7: Hint/Caption */
.hint {
  font-size: 0.6875rem;
  color: var(--text-dim);
}
```

### 6.4 Contextual Help System

Implement inline help tooltips:

```vue
<!-- HelpTooltip.vue - Contextual help -->
<template>
  <div class="help-tooltip">
    <button
      class="help-tooltip__trigger"
      @mouseenter="show"
      @mouseleave="hide"
      @focus="show"
      @blur="hide"
    >
      <Icon name="help-circle" size="sm" />
    </button>
    
    <Teleport to="body">
      <Transition name="fade">
        <div
          v-if="visible"
          class="help-tooltip__content"
          :style="positionStyle"
        >
          <div class="help-tooltip__title">{{ title }}</div>
          <div class="help-tooltip__body">
            <slot>{{ content }}</slot>
          </div>
          <div v-if="link" class="help-tooltip__link">
            <a :href="link" target="_blank">Подробнее →</a>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<!-- Usage -->
<div class="metric-label">
  pH
  <HelpTooltip
    title="Водородный показатель"
    content="Оптимальный диапазон: 5.5-6.5. Влияет на усвоение питательных веществ."
    link="/docs/ph-guide"
  />
</div>
```

---

## 7. Performance Optimizations

### 7.1 Virtual Scrolling for Large Lists

```vue
<!-- Use vue-virtual-scroller for telemetry history -->
<template>
  <RecycleScroller
    :items="telemetryHistory"
    :item-size="48"
    key-field="id"
    class="telemetry-list"
  >
    <template #default="{ item }">
      <TelemetryRow :sample="item" />
    </template>
  </RecycleScroller>
</template>
```

### 7.2 Debounced Real-time Updates

```typescript
// composables/useOptimizedUpdates.ts - Enhanced version

export function useOptimizedUpdates<T>(
  fetchFn: () => Promise<T>,
  options: {
    debounceMs?: number
    throttleMs?: number
    maxBatchSize?: number
  } = {}
) {
  const { debounceMs = 100, throttleMs = 1000, maxBatchSize = 50 } = options
  
  const data = ref<T | null>(null)
  const pendingUpdates = ref<Partial<T>[]>([])
  const isProcessing = ref(false)
  
  // Batch updates
  const flushUpdates = useDebounceFn(() => {
    if (pendingUpdates.value.length === 0) return
    
    const batch = pendingUpdates.value.splice(0, maxBatchSize)
    data.value = Object.assign({}, data.value, ...batch)
    isProcessing.value = false
  }, debounceMs)
  
  // Throttled fetch
  const throttledFetch = useThrottleFn(fetchFn, throttleMs)
  
  // Add update to batch
  function queueUpdate(update: Partial<T>) {
    pendingUpdates.value.push(update)
    isProcessing.value = true
    flushUpdates()
  }
  
  return {
    data,
    queueUpdate,
    refresh: throttledFetch,
    isProcessing,
    pendingCount: computed(() => pendingUpdates.value.length),
  }
}
```

### 7.3 Component-level Caching

```typescript
// Use KeepAlive for expensive components
<template>
  <KeepAlive :include="['ZoneTelemetry', 'ZoneDevices']">
    <component :is="currentTabComponent" :zone-id="zoneId" />
  </KeepAlive>
</template>

// Or use defineAsyncComponent for code splitting
const ZoneTelemetry = defineAsyncComponent(() =>
  import('./components/Zone/ZoneTelemetry.vue')
)
```

### 7.4 WebSocket Optimization

```typescript
// composables/useOptimizedWebSocket.ts

export function useOptimizedWebSocket() {
  const messageQueue = ref<any[]>([])
  const isProcessing = ref(false)
  
  // Batch messages
  const processQueue = useDebounceFn(() => {
    if (messageQueue.value.length === 0) return
    
    // Group by type
    const grouped = messageQueue.value.reduce((acc, msg) => {
      const key = msg.type
      if (!acc[key]) acc[key] = []
      acc[key].push(msg)
      return acc
    }, {} as Record<string, any[]>)
    
    // Process in batch
    for (const [type, messages] of Object.entries(grouped)) {
      // Only keep latest value for telemetry
      if (type === 'telemetry') {
        const latest = messages[messages.length - 1]
        emit('telemetry', latest)
      } else {
        emit(type, messages)
      }
    }
    
    messageQueue.value = []
    isProcessing.value = false
  }, 100)
  
  function onMessage(message: any) {
    messageQueue.value.push(message)
    isProcessing.value = true
    processQueue()
  }
  
  return { onMessage, isProcessing, queueLength: computed(() => messageQueue.value.length) }
}
```

---

## 8. Accessibility Improvements

### 8.1 ARIA Labels and Roles

```vue
<!-- Proper ARIA implementation -->
<template>
  <div
    class="metric-card"
    role="region"
    :aria-label="`${label}: ${formattedValue}`"
    :aria-live="isRealTime ? 'polite' : undefined"
  >
    <!-- Status indicator with ARIA -->
    <div
      class="status-indicator"
      :role="interactive ? 'button' : undefined"
      :aria-label="`Статус: ${statusLabel}`"
      :aria-pressed="interactive ? isPressed : undefined"
      :tabindex="interactive ? 0 : undefined"
    >
      <span class="sr-only">{{ statusLabel }}</span>
    </div>
    
    <!-- Interactive controls -->
    <button
      v-if="showActions"
      class="metric-action"
      :aria-label="`Увеличить ${label}`"
      @click="adjustUp"
    >
      <Icon name="chevron-up" aria-hidden="true" />
    </button>
  </div>
</template>
```

### 8.2 Keyboard Navigation

```vue
<!-- Keyboard-friendly components -->
<template>
  <div
    class="zone-card"
    tabindex="0"
    @keydown.enter="selectZone"
    @keydown.space.prevent="selectZone"
    @keydown.arrow-right="focusNext"
    @keydown.arrow-left="focusPrev"
  >
    <!-- Card content -->
  </div>
</template>

<script setup lang="ts">
// Focus management
const { focusNext, focusPrev } = useRovingFocus(containerRef)
</script>
```

### 8.3 Color Contrast & Themes

```css
/* Ensure WCAG AA compliance */
:root {
  /* Primary text: 12.63:1 contrast ratio */
  --text-primary: #e6eef7;
  
  /* Muted text: 7.23:1 contrast ratio */
  --text-muted: #a3b4c7;
  
  /* Ensure interactive elements have sufficient contrast */
  --accent-green: #49e08a; /* 3.12:1 on dark - use with background */
  
  /* Focus states */
  --focus-ring: rgba(73, 224, 138, 0.35);
}

/* High contrast mode support */
@media (prefers-contrast: high) {
  :root {
    --text-primary: #ffffff;
    --text-muted: #d0dce8;
    --border-muted: rgba(100, 120, 140, 0.8);
    --accent-green: #5fff9a;
  }
}

/* Reduce motion for users who prefer it */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

### 8.4 Screen Reader Support

```vue
<!-- Screen reader announcements -->
<template>
  <div class="zone-status">
    <!-- Visual status -->
    <StatusIndicator :status="status" />
    
    <!-- Screen reader text -->
    <div class="sr-only" aria-live="polite" aria-atomic="true">
      Зона {{ zoneName }}: статус {{ statusLabel }}
      <template v-if="status === 'ALARM'">
        , требуется внимание
      </template>
    </div>
  </div>
</template>

<style>
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
</style>
```

---

## 9. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)

**Priority: Critical**

1. **Component Decomposition**
   - [ ] Split `AutomationProcessPanel.vue` (1577 lines → ~10 files)
   - [ ] Split `useZoneAutomationTab.ts` (63KB → 5 composables)
   - [ ] Create component directory structure

2. **Standard Patterns**
   - [ ] Create `useComponentState` composable
   - [ ] Implement standard formatters (`utils/formatters.ts`)
   - [ ] Define terminology dictionary

3. **Tests**
   - [ ] Add unit tests for new composables
   - [ ] Add component tests for decomposed components

### Phase 2: Visual Enhancements (Week 3-4)

**Priority: High**

1. **Metric Cards**
   - [ ] Enhance `MetricCard.vue` with trends
   - [ ] Add `RangeBar` component
   - [ ] Improve status indicators

2. **Process Diagram**
   - [ ] Refactor SVG to modular components
   - [ ] Add interactivity and tooltips
   - [ ] Implement responsive scaling

3. **Alerts**
   - [ ] Create `AlertSummary` component
   - [ ] Implement `AlertTimeline`
   - [ ] Add batch actions

### Phase 3: Performance (Week 5-6)

**Priority: Medium**

1. **Optimization**
   - [ ] Implement virtual scrolling
   - [ ] Add WebSocket batching
   - [ ] Create component caching strategy

2. **Code Splitting**
   - [ ] Async components for heavy views
   - [ ] Route-based splitting

### Phase 4: Accessibility (Week 7-8)

**Priority: High**

1. **ARIA**
   - [ ] Add ARIA labels to all components
   - [ ] Implement keyboard navigation
   - [ ] Add screen reader support

2. **Themes**
   - [ ] Ensure WCAG AA compliance
   - [ ] Add high contrast mode
   - [ ] Test with assistive technologies

### Phase 5: Documentation (Week 9-10)

**Priority: Medium**

1. **Component Documentation**
   - [ ] Storybook setup
   - [ ] Component API documentation
   - [ ] Usage examples

2. **Developer Guides**
   - [ ] Component development guide
   - [ ] State management patterns
   - [ ] Testing guidelines

---

## Appendix A: File Size Targets

| File Type | Current Max | Target Max | Action |
|-----------|-------------|------------|--------|
| Vue Components | 1577 lines | 300 lines | Decompose |
| Composables | 2000 lines | 200 lines | Split |
| TypeScript Types | 200 lines | 100 lines | Modularize |
| CSS | 568 lines | 800 lines | Expand (semantic) |
| Utils | 300 lines | 150 lines | Categorize |

## Appendix B: New Components to Create

### Primitives (10 components)

1. `Button.vue` - Enhanced button with variants
2. `Card.vue` - Base card with variants
3. `Badge.vue` - Status badges
4. `Input.vue` - Form input
5. `Select.vue` - Dropdown select
6. `Modal.vue` - Modal dialog
7. `Tabs.vue` - Tab navigation
8. `Skeleton.vue` - Loading skeleton
9. `Tooltip.vue` - Tooltip component
10. `Icon.vue` - Icon wrapper

### Data Display (8 components)

1. `MetricCard.vue` - Enhanced metric display
2. `StatusIndicator.vue` - Status dot/badge
3. `RangeBar.vue` - Range visualization
4. `Sparkline.vue` - Mini chart
5. `GaugeChart.vue` - Circular gauge
6. `DataTable.vue` - Virtual table
7. `TreeView.vue` - Hierarchical display
8. `Timeline.vue` - Event timeline

### Domain Components (20+ components)

1. Zone components (5)
2. Automation components (8)
3. GrowCycle components (4)
4. Recipe components (3)
5. Alert components (3)

---

**Document Status:** Ready for Review
**Next Steps:** Team review, prioritization, and sprint planning
