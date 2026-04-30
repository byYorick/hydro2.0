<template>
  <Link
    :href="`/zones/${zone.id}`"
    class="zone-dashboard-card surface-card flex flex-col rounded-2xl border transition-all duration-150 no-underline"
    :class="[
      dense ? 'p-3 gap-3' : 'p-4 gap-4',
      cardBorderClass,
      'hover:border-[color:var(--border-strong)] hover:shadow-[var(--shadow-card)]',
    ]"
    data-testid="zone-dashboard-card"
  >
    <!-- ── Header: зона, статусы, счётчик алертов ── -->
    <header class="flex items-start justify-between gap-3">
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2 flex-wrap">
          <span
            class="w-2 h-2 rounded-full shrink-0"
            :class="dotClass"
          ></span>
          <span class="text-lg font-semibold truncate text-[color:var(--text-primary)]">
            {{ zone.name }}
          </span>
          <Badge :variant="getZoneStatusVariant(zone.status)">
            {{ translateStatus(zone.status) }}
          </Badge>
          <Badge
            v-if="zone.cycle"
            :variant="getCycleStatusVariant(zone.cycle.status, 'center')"
          >
            {{ getCycleStatusLabel(zone.cycle.status, 'short') }}
          </Badge>
        </div>
        <div class="text-xs text-[color:var(--text-dim)] mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span v-if="zone.greenhouse">{{ zone.greenhouse.name }}</span>
          <span
            v-if="zone.recipe"
            class="truncate"
          >· {{ zone.recipe.name }}</span>
          <span v-if="zone.devices?.total">· Устр: {{ zone.devices.online }}/{{ zone.devices.total }}</span>
        </div>
      </div>

      <div class="flex flex-col items-end gap-1 shrink-0">
        <div
          v-if="automationBlock"
          class="status-chip status-chip--alarm shrink-0 animate-pulse"
          data-testid="zone-card-automation-block"
          :title="automationBlockHint"
        >
          ⚠ Автоматика остановлена
        </div>
        <div
          v-else-if="zone.alerts_count > 0"
          class="status-chip status-chip--alarm shrink-0"
        >
          Алертов: {{ zone.alerts_count }}
        </div>
        <div
          v-else
          class="status-chip status-chip--running shrink-0"
        >
          ОК
        </div>
        <div
          v-if="automationBlock && zone.alerts_count > 0"
          class="text-[10px] text-[color:var(--text-dim)]"
        >
          Алертов: {{ zone.alerts_count }}
        </div>
      </div>
    </header>

    <!-- Подсказка о причине блокировки автоматики -->
    <div
      v-if="automationBlock"
      class="rounded-md border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)]/10 px-2.5 py-1.5 text-[11px] leading-snug text-[color:var(--accent-red)]"
      data-testid="zone-card-automation-block-reason"
    >
      <div class="font-medium">
        {{ automationBlockLabelText }}
      </div>
      <div
        v-if="automationBlockMessageText"
        class="text-[color:var(--text-secondary)] truncate"
        :title="automationBlockMessageText"
      >
        {{ automationBlockMessageText }}
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════════════
         DENSE MODE: исходный вертикальный layout
         ═══════════════════════════════════════════════════════ -->
    <template v-if="dense">
      <CycleProgressStack
        :overall-pct="cycleOverallPct"
        :overall-day-label="cycleOverallDayLabel"
        :phase="phaseStrip"
      />
      <div class="grid grid-cols-3 gap-3">
        <MetricPillBar
          label="pH"
          :value="zone.telemetry.ph"
          :target-min="resolveTarget('ph', 'min')"
          :target-max="resolveTarget('ph', 'max')"
          :axis-min="0"
          :axis-max="14"
          :decimals="2"
          :offline="telemetryOffline"
        />
        <MetricPillBar
          label="EC"
          :value="zone.telemetry.ec"
          :target-min="resolveTarget('ec', 'min')"
          :target-max="resolveTarget('ec', 'max')"
          unit="мСм"
          :decimals="2"
          :offline="telemetryOffline"
        />
        <MetricPillBar
          label="T°C"
          :value="zone.telemetry.temperature"
          :target-min="resolveTarget('temperature', 'min')"
          :target-max="resolveTarget('temperature', 'max')"
          :axis-min="10"
          :axis-max="40"
          :decimals="1"
          :offline="telemetryOffline"
        />
      </div>
      <CombinedTelemetrySparkline
        :series="sparklineSeries"
        :width="220"
        :height="30"
      />
      <SystemStatePanel
        :phase-label="zone.system_state?.label ?? null"
        :phase-code="zone.system_state?.phase ?? null"
        :offline="systemStateOffline"
        :irrig-node-online="irrigNodeOnline"
        :tank-levels="zone.tank_levels ?? null"
        :automation-blocked="Boolean(automationBlock)"
        :automation-block-reason="automationBlockLabelText"
      />
    </template>

    <!-- ═══════════════════════════════════════════════════════
         NON-DENSE: двухколонный layout (Вариант C)
         ═══════════════════════════════════════════════════════ -->
    <template v-else>
      <!-- Два столбца: метрики (лево) + цикл и система (право) -->
      <div class="grid grid-cols-2 gap-3 items-start">
        <!-- Левый столбец: метрики стопкой -->
        <div class="flex flex-col gap-3">
          <MetricPillBar
            label="pH"
            :value="zone.telemetry.ph"
            :target-min="resolveTarget('ph', 'min')"
            :target-max="resolveTarget('ph', 'max')"
            :axis-min="0"
            :axis-max="14"
            :decimals="2"
            :offline="telemetryOffline"
          />
          <MetricPillBar
            label="EC"
            :value="zone.telemetry.ec"
            :target-min="resolveTarget('ec', 'min')"
            :target-max="resolveTarget('ec', 'max')"
            unit="мСм"
            :decimals="2"
            :offline="telemetryOffline"
          />
          <MetricPillBar
            label="T°C"
            :value="zone.telemetry.temperature"
            :target-min="resolveTarget('temperature', 'min')"
            :target-max="resolveTarget('temperature', 'max')"
            :axis-min="10"
            :axis-max="40"
            :decimals="1"
            :offline="telemetryOffline"
          />
        </div>

        <!-- Правый столбец: цикл + состояние системы -->
        <div class="flex flex-col gap-2.5">
          <CycleProgressStack
            :overall-pct="cycleOverallPct"
            :overall-day-label="cycleOverallDayLabel"
            :phase="phaseStrip"
          />
          <SystemStatePanel
            :phase-label="zone.system_state?.label ?? null"
            :phase-code="zone.system_state?.phase ?? null"
            :offline="systemStateOffline"
            :irrig-node-online="irrigNodeOnline"
            :tank-levels="zone.tank_levels ?? null"
            :automation-blocked="Boolean(automationBlock)"
            :automation-block-reason="automationBlockLabelText"
          />
        </div>
      </div>

      <!-- Телеметрия с переключателем метрики -->
      <div class="flex flex-col gap-1.5">
        <div class="flex items-center justify-between">
          <span class="text-[10px] uppercase tracking-wider text-[color:var(--text-muted)]">
            Телеметрия · 24ч
          </span>
          <!-- Переключатель: pH / EC / T°C  (click.stop чтобы не триггерить Link) -->
          <div
            class="flex items-center gap-1"
            @click.stop
          >
            <button
              v-for="m in metricOptions"
              :key="m.key"
              type="button"
              class="metric-tab px-2 py-0.5 rounded text-[10px] font-medium transition-colors"
              :class="selectedMetric === m.key ? activeMetricClass(m.key) : inactiveMetricClass"
              @click.stop.prevent="selectedMetric = m.key"
            >
              {{ m.label }}
            </button>
          </div>
        </div>
        <CombinedTelemetrySparkline
          :series="filteredSparklineSeries"
          :show-header="false"
          :width="500"
          :height="38"
        />
      </div>
    </template>

    <!-- Алерты (до 3 строк) -->
    <AlertPreviewList
      v-if="alertPreviewItems.length > 0"
      :alerts="alertPreviewItems"
      :limit="3"
    />

    <!-- Футер: время обновления -->
    <div
      v-if="zone.telemetry.updated_at"
      class="text-[10px] text-[color:var(--text-dim)] pt-1 border-t border-[color:var(--border-muted)]"
    >
      Обновление: {{ formatTime(zone.telemetry.updated_at) }}
    </div>
  </Link>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Link } from '@inertiajs/vue3'
import Badge from '@/Components/Badge.vue'
import MetricPillBar from '@/Components/ZoneDashboardCard/MetricPillBar.vue'
import CycleProgressStack from '@/Components/ZoneDashboardCard/CycleProgressStack.vue'
import SystemStatePanel from '@/Components/ZoneDashboardCard/SystemStatePanel.vue'
import CombinedTelemetrySparkline, {
  type TelemetrySeries,
} from '@/Components/ZoneDashboardCard/CombinedTelemetrySparkline.vue'
import AlertPreviewList, {
  type AlertPreviewItem,
} from '@/Components/ZoneDashboardCard/AlertPreviewList.vue'
import { translateStatus } from '@/utils/i18n'
import { getCycleStatusLabel, getCycleStatusVariant } from '@/utils/growCycleStatus'
import {
  automationBlockHint as resolveAutomationBlockHint,
  automationBlockLabel as resolveAutomationBlockLabel,
} from '@/utils/automationBlock'
import type { UnifiedZone } from '@/composables/useUnifiedDashboard'
import type { GrowCycle } from '@/composables/useCycleCenterView'

interface PhaseStripInfo {
  name: string
  dayElapsed: number
  dayTotal: number
  progress: number
}

interface Props {
  zone: UnifiedZone
  sparklineSeriesData?: {
    ph?: number[] | null
    ec?: number[] | null
    temperature?: number[] | null
  } | null
  dense?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  sparklineSeriesData: null,
  dense: false,
})

// ── Переключатель метрики на графике ─────────────────────────────────────────

type MetricKey = 'ph' | 'ec' | 'temperature'

const selectedMetric = ref<MetricKey>('ph')

const metricOptions: Array<{ key: MetricKey; label: string }> = [
  { key: 'ph', label: 'pH' },
  { key: 'ec', label: 'EC' },
  { key: 'temperature', label: 'T°C' },
]

const metricColorVar: Record<MetricKey, string> = {
  ph: 'var(--accent-green)',
  ec: 'var(--accent-amber)',
  temperature: 'var(--accent-cyan)',
}

function activeMetricClass(key: MetricKey): string {
  const colorVarMap: Record<MetricKey, string> = {
    ph: 'text-[color:var(--accent-green)] bg-[color:var(--accent-green)]/10 border border-[color:var(--accent-green)]/30',
    ec: 'text-[color:var(--accent-amber)] bg-[color:var(--accent-amber)]/10 border border-[color:var(--accent-amber)]/30',
    temperature: 'text-[color:var(--accent-cyan)] bg-[color:var(--accent-cyan)]/10 border border-[color:var(--accent-cyan)]/30',
  }
  return colorVarMap[key]
}

const inactiveMetricClass = 'text-[color:var(--text-muted)] hover:text-[color:var(--text-secondary)]'

// ── Targets / telemetry ───────────────────────────────────────────────────────

function resolveTarget(
  key: 'ph' | 'ec' | 'temperature',
  side: 'min' | 'max',
): number | null {
  const t = props.zone.targets?.[key]
  if (!t) return null
  return t[side] ?? null
}

const telemetryOffline = computed(() => {
  const updatedAt = props.zone.telemetry?.updated_at
  if (!updatedAt) return true
  const ts = new Date(updatedAt).getTime()
  if (Number.isNaN(ts)) return true
  return Date.now() - ts > 5 * 60 * 1000
})

const systemStateOffline = computed(() => {
  if (!props.zone.system_state) {
    return !props.zone.irrig_node?.online
  }
  // Если workflow stale, но IRR-нода online — не показываем «нет связи» как hard-error.
  return Boolean(props.zone.system_state.stale) && !props.zone.irrig_node?.online
})

const irrigNodeOnline = computed(() => Boolean(props.zone.irrig_node?.online))

// ── Блокировка автоматики ────────────────────────────────────────────────────

const automationBlock = computed(() => {
  const block = props.zone.automation_block
  return block && block.blocked ? block : null
})

const automationBlockLabelText = computed(() =>
  resolveAutomationBlockLabel(automationBlock.value?.reason_code ?? null),
)

const automationBlockHint = computed(() =>
  resolveAutomationBlockHint(automationBlock.value?.reason_code ?? null),
)

const automationBlockMessageText = computed(() => {
  const msg = automationBlock.value?.message
  return typeof msg === 'string' && msg.trim() ? msg.trim() : null
})

// ── Цикл / фаза ──────────────────────────────────────────────────────────────

const phaseStrip = computed((): PhaseStripInfo | null => {
  const cycle = props.zone.cycle as GrowCycle | null
  if (!cycle?.stages?.length) return null
  const active = cycle.stages.find((s) => s.state === 'ACTIVE')
  if (!active?.from) return null
  const start = new Date(active.from)
  if (Number.isNaN(start.getTime())) return null
  const end = active.to ? new Date(active.to) : null
  const daysElapsed = Math.max(0, Math.floor((Date.now() - start.getTime()) / (1000 * 60 * 60 * 24)))
  let daysTotal = daysElapsed || 1
  if (end && !Number.isNaN(end.getTime())) {
    daysTotal = Math.max(1, Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)))
  }
  const progress = Math.min(100, Math.round((daysElapsed / daysTotal) * 100))
  const stageName = cycle.current_stage?.name ?? active.name ?? 'Фаза'
  return { name: stageName, dayElapsed: daysElapsed, dayTotal: daysTotal, progress }
})

const cycleOverallPct = computed(() => props.zone.cycle?.progress?.overall_pct ?? null)

const cycleOverallDayLabel = computed(() => {
  const cycle = props.zone.cycle
  if (!cycle?.planting_at) return null
  const start = new Date(cycle.planting_at)
  if (Number.isNaN(start.getTime())) return null
  const elapsed = Math.max(0, Math.floor((Date.now() - start.getTime()) / (1000 * 60 * 60 * 24)))
  if (cycle.expected_harvest_at) {
    const end = new Date(cycle.expected_harvest_at)
    if (!Number.isNaN(end.getTime())) {
      const total = Math.max(1, Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)))
      return `День ${elapsed}/${total}`
    }
  }
  return `День ${elapsed}`
})

// ── Sparklines ────────────────────────────────────────────────────────────────

const sparklineSeries = computed<TelemetrySeries[]>(() => {
  const data = props.sparklineSeriesData
  return [
    { key: 'ph', label: 'pH', color: metricColorVar.ph, data: data?.ph ?? null },
    { key: 'ec', label: 'EC', color: metricColorVar.ec, data: data?.ec ?? null },
    { key: 'temperature', label: 'T°C', color: metricColorVar.temperature, data: data?.temperature ?? null },
  ]
})

/** В режиме non-dense показываем только выбранную метрику на графике. */
const filteredSparklineSeries = computed<TelemetrySeries[]>(() =>
  sparklineSeries.value.filter((s) => s.key === selectedMetric.value),
)

// ── Алерты ───────────────────────────────────────────────────────────────────

const alertPreviewItems = computed<AlertPreviewItem[]>(() => {
  const preview = props.zone.alerts_preview ?? []
  return preview.map((alert) => ({
    id: alert.id,
    severity: detectAlertSeverity(alert.type),
    title: shortenAlertTitle(alert.type),
    reason: extractAlertMessage(alert.details),
    created_at: alert.created_at,
  }))
})

function detectAlertSeverity(type: string): AlertPreviewItem['severity'] {
  const lower = (type || '').toLowerCase()
  if (lower.includes('critical') || lower.includes('alarm') || lower.includes('error') || lower.includes('fail')) {
    return 'alert'
  }
  if (lower.includes('warn') || lower.includes('degraded') || lower.includes('stale')) {
    return 'warning'
  }
  return 'warning'
}

function shortenAlertTitle(type: string): string {
  if (!type) return 'Алерт'
  const normalized = type.replace(/_/g, ' ').trim()
  return normalized.charAt(0).toUpperCase() + normalized.slice(1)
}

function extractAlertMessage(details: unknown): string | null {
  if (typeof details !== 'string') {
    return null
  }
  const raw = details.trim()
  if (!raw) {
    return null
  }

  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>
    const candidates: Array<unknown> = [
      parsed.message,
      parsed.human_error_message,
      parsed.error_message,
      parsed.title,
      parsed.reason,
    ]
    for (const candidate of candidates) {
      if (typeof candidate === 'string' && candidate.trim()) {
        return candidate.trim()
      }
    }

    const code = typeof parsed.code === 'string' ? parsed.code : null
    const stage = typeof parsed.stage === 'string' ? parsed.stage : null
    if (code || stage) {
      return [code, stage].filter(Boolean).join(' · ')
    }
    return null
  } catch {
    // Не JSON — уже текстовое сообщение.
    return raw
  }
}

// ── Визуальные классы ─────────────────────────────────────────────────────────

function getZoneStatusVariant(status: string): 'success' | 'info' | 'warning' | 'danger' | 'neutral' {
  switch (status) {
    case 'RUNNING': return 'success'
    case 'PAUSED': return 'info'
    case 'WARNING': return 'warning'
    case 'ALARM': return 'danger'
    default: return 'neutral'
  }
}

const cardBorderClass = computed(() => {
  if (automationBlock.value) return 'border-[color:var(--badge-danger-border)]'
  if (props.zone.status === 'ALARM') return 'border-[color:var(--badge-danger-border)]'
  if (props.zone.status === 'WARNING') return 'border-[color:var(--badge-warning-border)]'
  return 'border-[color:var(--border-muted)]'
})

const dotClass = computed(() => {
  const map: Record<string, string> = {
    RUNNING: 'bg-[color:var(--accent-green)] shadow-[0_0_6px_var(--accent-green)]',
    WARNING: 'bg-[color:var(--accent-amber)]',
    ALARM: 'bg-[color:var(--accent-red)] animate-pulse',
    PAUSED: 'bg-[color:var(--text-dim)]',
    IDLE: 'bg-[color:var(--text-dim)]',
    NEW: 'bg-[color:var(--text-dim)]',
  }
  return map[props.zone.status] ?? 'bg-[color:var(--text-dim)]'
})

function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
</script>

<style scoped>
.zone-dashboard-card {
  color: inherit;
  text-decoration: none;
}
.zone-dashboard-card:hover {
  cursor: pointer;
}

.metric-tab {
  cursor: pointer;
  border: 1px solid transparent;
  background: none;
  line-height: 1.4;
}
</style>
