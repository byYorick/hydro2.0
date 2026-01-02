<template>
  <AppLayout>
    <template #default>
      <!-- Ролевые Dashboard -->
      <AgronomistDashboard 
        v-if="isAgronomist"
        :dashboard="dashboard as any"
      />
      <AdminDashboard 
        v-else-if="isAdmin"
        :dashboard="dashboard as any"
      />
      <EngineerDashboard 
        v-else-if="isEngineer"
        :dashboard="dashboard as any"
      />
      <OperatorDashboard 
        v-else-if="isOperator"
        :dashboard="dashboard as any"
      />
      <ViewerDashboard 
        v-else-if="isViewer"
        :dashboard="dashboard as any"
      />
      <!-- Дефолтный Dashboard для остальных случаев -->
      <div
        v-else
        class="space-y-6"
      >
        <div class="glass-panel glass-panel--elevated border border-[color:var(--border-strong)] rounded-2xl p-5">
          <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
                обзор системы
              </p>
              <h1 class="text-2xl font-semibold tracking-tight mt-1">
                Мониторинг теплиц и зон
              </h1>
              <p class="text-sm text-[color:var(--text-muted)] mt-1">
                Сводка по теплицам, зонам, устройствам и активным алертам.
              </p>
            </div>
            <div class="flex gap-2 justify-end">
              <Link href="/greenhouses">
                <Button
                  size="sm"
                  variant="secondary"
                >
                  Перейти к теплицам
                </Button>
              </Link>
            </div>
          </div>
          <!-- Промышленный стиль: Крупные индикаторы метрик -->
          <div class="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4 mt-4">
            <MetricIndicator
              label="Теплицы"
              :value="dashboard.greenhousesCount"
              :status="dashboard.greenhousesCount > 0 ? 'success' : 'neutral'"
              size="large"
            />
            
            <MetricIndicator
              label="Зоны"
              :value="dashboard.zonesCount"
              :status="zonesStatusSummary?.ALARM > 0 ? 'danger' : zonesStatusSummary?.WARNING > 0 ? 'warning' : zonesStatusSummary?.RUNNING > 0 ? 'success' : 'neutral'"
              size="large"
              data-testid="dashboard-zones-count"
            >
              <template
                v-if="zonesStatusSummary"
                #footer
              >
                <div class="flex flex-wrap gap-1.5 text-xs mt-2">
                  <StatusIndicator
                    v-if="zonesStatusSummary.RUNNING"
                    status="RUNNING"
                    size="small"
                    show-label
                  />
                  <StatusIndicator
                    v-if="zonesStatusSummary.PAUSED"
                    status="PAUSED"
                    size="small"
                    show-label
                  />
                  <StatusIndicator
                    v-if="zonesStatusSummary.ALARM"
                    status="ALARM"
                    size="small"
                    show-label
                    :pulse="true"
                  />
                  <StatusIndicator
                    v-if="zonesStatusSummary.WARNING"
                    status="WARNING"
                    size="small"
                    show-label
                  />
                </div>
              </template>
            </MetricIndicator>
            
            <MetricIndicator
              label="Устройства"
              :value="dashboard.devicesCount"
              :status="nodesStatusSummary?.offline > 0 ? 'danger' : nodesStatusSummary?.online > 0 ? 'success' : 'neutral'"
              size="large"
            >
              <template
                v-if="nodesStatusSummary"
                #footer
              >
                <div class="flex flex-wrap gap-1.5 text-xs mt-2">
                  <StatusIndicator
                    v-if="nodesStatusSummary.online"
                    status="ONLINE"
                    size="small"
                    show-label
                  />
                  <StatusIndicator
                    v-if="nodesStatusSummary.offline"
                    status="OFFLINE"
                    size="small"
                    show-label
                    :pulse="true"
                  />
                </div>
              </template>
            </MetricIndicator>
            
            <MetricIndicator
              label="Активные алерты"
              :value="dashboard.alertsCount"
              :status="dashboard.alertsCount > 0 ? 'danger' : 'success'"
              size="large"
              data-testid="dashboard-alerts-count"
            />
          </div>
        </div>

        <!-- Быстрые действия -->
        <div
          v-if="!hasGreenhouses || dashboard.greenhousesCount === 0"
          class="mb-6"
        >
          <Card class="bg-[color:var(--badge-info-bg)] border-[color:var(--badge-info-border)]">
            <div class="flex items-center justify-between">
              <div>
                <div class="text-sm font-semibold mb-1">
                  Начать работу
                </div>
                <div class="text-xs text-[color:var(--text-muted)]">
                  Создайте теплицу и зоны для начала работы с системой
                </div>
              </div>
              <div class="flex gap-2">
                <Link href="/greenhouses">
                  <Button size="sm">
                    Создать теплицу
                  </Button>
                </Link>
              </div>
            </div>
          </Card>
        </div>

        <!-- Теплицы -->
        <div
          v-if="hasGreenhouses"
          class="mb-6"
        >
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-base font-semibold text-[color:var(--text-primary)]">
              Теплицы
            </h2>
            <Link href="/greenhouses">
              <Button
                size="sm"
                variant="outline"
              >
                Все теплицы
              </Button>
            </Link>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            <Card 
              v-for="gh in dashboard.greenhouses" 
              :key="gh.id" 
              v-memo="[gh.id, gh.name, (gh as any).zones_count, (gh as any).zones_running]"
              class="surface-card-hover hover:border-[color:var(--border-strong)] transition-all duration-200"
            >
              <div class="flex items-start justify-between">
                <div>
                  <div class="text-sm font-semibold">
                    {{ gh.name }}
                  </div>
                  <div class="text-xs text-[color:var(--text-muted)] mt-1">
                    <span v-if="(gh as any).type">{{ (gh as any).type }}</span>
                    <span
                      v-if="(gh as any).uid"
                      class="ml-2"
                    >UID: {{ (gh as any).uid }}</span>
                  </div>
                </div>
              </div>
              <div class="mt-3 text-xs text-[color:var(--text-muted)]">
                <div>Зон: {{ (gh as any).zones_count || 0 }}</div>
                <div class="text-[color:var(--accent-green)]">
                  Запущено: {{ (gh as any).zones_running || 0 }}
                </div>
              </div>
            </Card>
          </div>
        </div>

        <!-- Проблемные зоны -->
        <div
          v-if="hasProblematicZones"
          class="mb-6"
        >
          <h2 class="text-base font-semibold text-[color:var(--text-primary)] mb-4">
            Проблемные зоны
          </h2>
          <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            <Card 
              v-for="zone in dashboard.problematicZones" 
              :key="zone.id" 
              v-memo="[zone.id, zone.status, (zone as any).alerts_count]"
              class="surface-card-hover hover:border-[color:var(--badge-danger-border)] transition-all duration-200 border-[color:var(--badge-danger-border)]"
            >
              <div class="flex items-start justify-between mb-2">
                <div>
                  <div class="text-sm font-semibold">
                    {{ zone.name }}
                  </div>
                  <div
                    v-if="zone.greenhouse"
                    class="text-xs text-[color:var(--text-muted)] mt-1"
                  >
                    {{ zone.greenhouse.name }}
                  </div>
                </div>
                <Badge :variant="zone.status === 'ALARM' ? 'danger' : 'warning'">
                  {{ translateStatus(zone.status) }}
                </Badge>
              </div>
              <div
                v-if="zone.description"
                class="text-xs text-[color:var(--text-muted)] mb-2"
              >
                {{ zone.description }}
              </div>
              <div
                v-if="(zone as any).alerts_count > 0"
                class="text-xs text-[color:var(--accent-red)] mb-2"
              >
                Активных алертов: {{ (zone as any).alerts_count }}
              </div>
              <!-- Быстрые действия -->
              <div class="mt-3 flex items-center gap-2 flex-wrap">
                <Link :href="`/zones/${zone.id}`">
                  <Button
                    size="sm"
                    variant="secondary"
                  >
                    Подробнее
                  </Button>
                </Link>
                <Button
                  v-if="zone.status === 'RUNNING'"
                  size="sm"
                  variant="outline"
                  class="text-xs"
                  :disabled="isQuickActionLoading(zone.id)"
                  @click="handleQuickAction(zone, 'PAUSE')"
                >
                  <template v-if="isQuickActionLoading(zone.id, 'PAUSE')">
                    <span class="inline-flex items-center gap-1">
                      <svg
                        class="w-3.5 h-3.5 animate-spin text-[color:var(--text-muted)]"
                        viewBox="0 0 24 24"
                      >
                        <circle
                          class="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          stroke-width="4"
                        />
                        <path
                          class="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                        />
                      </svg>
                      <span>Пауза...</span>
                    </span>
                  </template>
                  <template v-else>
                    ⏸ Пауза
                  </template>
                </Button>
                <Button
                  v-if="zone.status === 'PAUSED'"
                  size="sm"
                  variant="outline"
                  class="text-xs"
                  :disabled="isQuickActionLoading(zone.id)"
                  @click="handleQuickAction(zone, 'RESUME')"
                >
                  <template v-if="isQuickActionLoading(zone.id, 'RESUME')">
                    <span class="inline-flex items-center gap-1">
                      <svg
                        class="w-3.5 h-3.5 animate-spin text-[color:var(--text-muted)]"
                        viewBox="0 0 24 24"
                      >
                        <circle
                          class="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          stroke-width="4"
                        />
                        <path
                          class="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                        />
                      </svg>
                      <span>Запуск...</span>
                    </span>
                  </template>
                  <template v-else>
                    ▶ Запустить
                  </template>
                </Button>
                <Button
                  v-if="zone.status === 'ALARM' || zone.status === 'WARNING'"
                  size="sm"
                  variant="outline"
                  class="text-xs text-[color:var(--accent-green)] border-[color:var(--badge-success-border)] hover:bg-[color:var(--badge-success-bg)]"
                  :disabled="isQuickActionLoading(zone.id)"
                  @click="handleQuickAction(zone, 'FORCE_IRRIGATION')"
                >
                  <template v-if="isQuickActionLoading(zone.id, 'FORCE_IRRIGATION')">
                    <span class="inline-flex items-center gap-1">
                      <svg
                        class="w-3.5 h-3.5 animate-spin text-[color:var(--badge-success-text)]"
                        viewBox="0 0 24 24"
                      >
                        <circle
                          class="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          stroke-width="4"
                        />
                        <path
                          class="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                        />
                      </svg>
                      <span>Полив...</span>
                    </span>
                  </template>
                  <template v-else>
                    💧 Полив
                  </template>
                </Button>
              </div>
            </Card>
          </div>
        </div>
        <div
          v-else
          class="mb-6"
        >
          <Card>
            <div class="text-sm text-[color:var(--text-dim)]">
              Нет проблемных зон
            </div>
          </Card>
        </div>

        <!-- Мини-графики телеметрии (если есть зоны) -->
        <div class="mb-6">
          <template v-if="hasZonesForTelemetry">
            <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-4">
              <div>
                <h2 class="text-base font-semibold text-[color:var(--text-primary)]">
                  Телеметрия
                  <span
                    v-if="selectedZoneLabel"
                    class="text-[color:var(--text-muted)] font-normal"
                  >· {{ selectedZoneLabel }}</span>
                  <span class="text-[color:var(--text-dim)] font-normal">· {{ telemetryPeriodLabel }}</span>
                </h2>
                <div class="flex items-center gap-1.5 text-xs text-[color:var(--text-dim)] mt-1">
                  <div class="w-2 h-2 rounded-full bg-[color:var(--accent-green)] animate-pulse"></div>
                  <span>Обновляется в реальном времени</span>
                </div>
              </div>
              <div class="flex flex-wrap items-center gap-3">
                <div
                  v-if="telemetryZones.length > 0"
                  class="flex items-center gap-2"
                >
                  <label class="text-xs text-[color:var(--text-muted)]">Зона</label>
                  <select
                    v-model.number="selectedZoneId"
                    class="input-select h-8 text-xs min-w-[160px]"
                  >
                    <option
                      v-for="zone in telemetryZones"
                      :key="zone.id"
                      :value="zone.id"
                    >
                      {{ zone.greenhouse?.name ? `${zone.name} · ${zone.greenhouse.name}` : zone.name }}
                    </option>
                  </select>
                </div>
                <div class="flex items-center gap-1">
                  <button
                    v-for="range in telemetryRangeOptions"
                    :key="range.value"
                    class="px-3 py-1 rounded-md text-xs border transition-colors"
                    :class="telemetryPeriod === range.value
                      ? 'border-[color:var(--accent-cyan)] bg-[color:var(--badge-info-bg)] text-[color:var(--accent-cyan)]'
                      : 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)]'"
                    @click="telemetryPeriod = range.value"
                  >
                    {{ range.label }}
                  </button>
                </div>
              </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
              <MiniTelemetryChart
                v-for="metric in telemetryMetrics"
                :key="metric.key"
                v-memo="[metric.data, metric.currentValue, metric.loading, selectedZoneId]"
                :label="metric.label"
                :data="metric.data as any"
                :current-value="metric.currentValue === null ? undefined : metric.currentValue"
                :unit="metric.unit"
                :loading="metric.loading"
                :color="metric.color"
                :zone-id="selectedZoneId || undefined"
                :metric="metric.key"
                @open-detail="handleOpenDetail"
              />
            </div>
          </template>
          <template v-else>
            <Card>
              <div class="text-sm text-[color:var(--text-dim)]">
                Нет доступных зон с телеметрией
              </div>
            </Card>
          </template>
        </div>

        <!-- Heatmap зон по статусам -->
        <div
          v-if="hasZones"
          class="mb-6"
        >
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-base font-semibold text-[color:var(--text-primary)]">
              Статусы зон
            </h2>
            <Link
              href="/zones"
              class="text-xs text-[color:var(--accent-cyan)] hover:underline transition-colors"
            >
              Все зоны →
            </Link>
          </div>
          <ZonesHeatmap :zones-by-status="zonesStatusSummary" />
        </div>
      </div>
    </template>
    <template #context>
      <div
        class="flex flex-col flex-1 min-h-0"
        data-testid="dashboard-events-panel"
      >
        <div class="flex items-center justify-between mb-3 shrink-0">
          <div class="text-[color:var(--text-primary)] font-medium">
            Последние события
          </div>
          <div class="flex items-center gap-1.5 text-xs text-[color:var(--text-dim)]">
            <div class="w-1.5 h-1.5 rounded-full bg-[color:var(--accent-green)] animate-pulse"></div>
            <span>Live</span>
          </div>
        </div>
        
        <!-- Фильтр по типу событий -->
        <div class="mb-3 flex gap-1 flex-wrap shrink-0">
          <button
            v-for="kind in ['ALL', 'ALERT', 'WARNING', 'INFO']"
            :key="kind"
            :data-testid="`dashboard-event-filter-${kind}`"
            class="px-2.5 py-1 text-xs rounded-md border transition-all duration-200"
            :class="eventFilter === kind 
              ? 'border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)] text-[color:var(--text-primary)]' 
              : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)]'"
            @click="eventFilter = kind as any"
          >
            {{ kind === 'ALL' ? 'Все' : kind }}
          </button>
        </div>
        
        <div
          v-if="filteredEvents.length > 0"
          class="space-y-2 flex-1 min-h-0 overflow-y-auto scrollbar-thin scrollbar-thumb-[color:var(--border-muted)] scrollbar-track-transparent pr-1"
        >
          <div 
            v-for="e in filteredEvents" 
            :key="e.id" 
            v-memo="[e.id, e.kind, e.message, e.occurred_at]"
            class="rounded-lg border p-2.5 transition-all duration-200 hover:shadow-[var(--shadow-card)]"
            :class="e.kind === 'ALERT' 
              ? 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)]' 
              : e.kind === 'WARNING' 
                ? 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)]' 
                : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]'"
          >
            <div class="flex items-start justify-between mb-1.5">
              <Badge 
                :variant="e.kind === 'ALERT' ? 'danger' : e.kind === 'WARNING' ? 'warning' : 'info'" 
                class="text-xs"
              >
                {{ e.kind }}
              </Badge>
              <span class="text-xs text-[color:var(--text-dim)]">{{ formatTime(e.occurred_at || e.created_at) }}</span>
            </div>
            <div
              v-if="e.zone_id"
              class="text-xs text-[color:var(--text-muted)] mb-1.5"
            >
              <Link
                :href="`/zones/${e.zone_id}`"
                class="text-[color:var(--accent-cyan)] hover:underline transition-colors"
              >
                Зона #{{ e.zone_id }} →
              </Link>
            </div>
            <div class="text-sm text-[color:var(--text-primary)] leading-relaxed">
              {{ e.message }}
            </div>
          </div>
        </div>
        <div
          v-else
          class="text-[color:var(--text-dim)] text-sm text-center py-4"
        >
          Нет событий
        </div>
      </div>
    </template>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, shallowRef, watch, reactive } from 'vue'
import { Link, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import MetricIndicator from '@/Components/MetricIndicator.vue'
import StatusIndicator from '@/Components/StatusIndicator.vue'
import MiniTelemetryChart from '@/Components/MiniTelemetryChart.vue'
import ZonesHeatmap from '@/Components/ZonesHeatmap.vue'
import AgronomistDashboard from './Dashboards/AgronomistDashboard.vue'
import AdminDashboard from './Dashboards/AdminDashboard.vue'
import EngineerDashboard from './Dashboards/EngineerDashboard.vue'
import OperatorDashboard from './Dashboards/OperatorDashboard.vue'
import ViewerDashboard from './Dashboards/ViewerDashboard.vue'
import { translateStatus } from '@/utils/i18n'
import { formatTime } from '@/utils/formatTime'
import { logger } from '@/utils/logger'
import { useTelemetry } from '@/composables/useTelemetry'
import { useWebSocket } from '@/composables/useWebSocket'
import { useRole } from '@/composables/useRole'
import { useCommands } from '@/composables/useCommands'
import { useToast } from '@/composables/useToast'
import { useTheme } from '@/composables/useTheme'
import type { Zone, Greenhouse, Alert, ZoneEvent, EventKind } from '@/types'

type QuickAction = 'PAUSE' | 'RESUME' | 'FORCE_IRRIGATION'
type TelemetryPeriod = '1h' | '24h' | '7d'
type TelemetryZone = Pick<Zone, 'id' | 'name' | 'status'> & {
  greenhouse?: { name?: string | null } | null
}

interface DashboardData {
  greenhousesCount: number
  zonesCount: number
  devicesCount: number
  alertsCount: number
  zonesByStatus?: Record<string, number>
  nodesByStatus?: Record<string, number>
  greenhouses?: Greenhouse[]
  problematicZones?: Zone[]
  zones?: TelemetryZone[]
  latestAlerts?: Alert[]
}

const TELEMETRY_ZONE_STORAGE_KEY = 'dashboard.telemetry.zone'
const TELEMETRY_PERIOD_STORAGE_KEY = 'dashboard.telemetry.period'

const telemetryRangeOptions: Array<{ label: string; value: TelemetryPeriod }> = [
  { label: '1ч', value: '1h' },
  { label: '24ч', value: '24h' },
  { label: '7д', value: '7d' },
]

interface Props {
  dashboard: DashboardData
}

const props = defineProps<Props>()

const { isAgronomist, isAdmin, isEngineer, isOperator, isViewer } = useRole()
const { theme } = useTheme()

const zonesStatusSummary = computed(() => props.dashboard.zonesByStatus || {})
const nodesStatusSummary = computed(() => props.dashboard.nodesByStatus || {})
// @ts-ignore hasAlerts - not used
const hasAlerts = computed(() => {
  const alerts = props.dashboard.latestAlerts
  return alerts && Array.isArray(alerts) && alerts.length > 0
})
const hasGreenhouses = computed(() => {
  const gh = props.dashboard.greenhouses
  return gh && Array.isArray(gh) && gh.length > 0
})
const hasProblematicZones = computed(() => {
  const zones = props.dashboard.problematicZones
  return zones && Array.isArray(zones) && zones.length > 0
})

const hasZones = computed(() => {
  return props.dashboard.zonesCount > 0
})

const telemetryPeriod = ref<TelemetryPeriod>('24h')
const selectedZoneId = ref<number | null>(null)
const telemetryZones = computed<TelemetryZone[]>(() => {
  const uniqueZones = new Map<number, TelemetryZone>()
  const problemZones = Array.isArray(props.dashboard.problematicZones) ? props.dashboard.problematicZones : []
  const payloadZones = Array.isArray(props.dashboard.zones) ? props.dashboard.zones : []

  const pushZone = (zone: any) => {
    if (!zone?.id) {
      return
    }
    const normalizedId = typeof zone.id === 'string' ? parseInt(zone.id, 10) : zone.id
    if (!normalizedId || Number.isNaN(normalizedId) || uniqueZones.has(normalizedId)) {
      return
    }
    uniqueZones.set(normalizedId, {
      id: normalizedId,
      name: zone.name || `Зона ${zone.id}`,
      status: zone.status,
      greenhouse: zone.greenhouse ? { name: zone.greenhouse.name } : null,
    })
  }

  problemZones.forEach(pushZone)
  payloadZones.forEach(pushZone)

  return Array.from(uniqueZones.values())
})
const selectedZone = computed(() => {
  if (!selectedZoneId.value) {
    return null
  }
  return telemetryZones.value.find(zone => zone.id === selectedZoneId.value) ?? null
})
const selectedZoneLabel = computed(() => selectedZone.value?.name ?? '')
const telemetryPeriodLabel = computed(() => telemetryRangeOptions.find(option => option.value === telemetryPeriod.value)?.label ?? '24ч')

const hasZonesForTelemetry = computed(() => telemetryZones.value.length > 0)
const quickActionLoading = reactive<Record<number, QuickAction | null>>({})

function isQuickActionLoading(zoneId: number, action?: QuickAction): boolean {
  const state = quickActionLoading[zoneId]
  if (!state) {
    return false
  }
  return action ? state === action : true
}

watch(telemetryZones, (zones) => {
  if (!zones.length) {
    selectedZoneId.value = null
    return
  }
  if (selectedZoneId.value && zones.some(zone => zone.id === selectedZoneId.value)) {
    return
  }
  selectedZoneId.value = zones[0].id
}, { immediate: true })

watch(selectedZoneId, (zoneId) => {
  if (typeof window === 'undefined') {
    return
  }
  if (zoneId) {
    window.localStorage.setItem(TELEMETRY_ZONE_STORAGE_KEY, String(zoneId))
  } else {
    window.localStorage.removeItem(TELEMETRY_ZONE_STORAGE_KEY)
  }
})

watch(telemetryPeriod, (period) => {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(TELEMETRY_PERIOD_STORAGE_KEY, period)
})

watch([selectedZoneId, telemetryPeriod], ([zoneId]) => {
  if (!zoneId) {
    resetTelemetryData()
    return
  }
  loadTelemetryMetrics()
})

function restoreTelemetryPreferences(): void {
  if (typeof window === 'undefined') {
    return
  }
  const storedZoneId = window.localStorage.getItem(TELEMETRY_ZONE_STORAGE_KEY)
  if (storedZoneId) {
    const parsed = Number(storedZoneId)
    if (!Number.isNaN(parsed) && telemetryZones.value.some(zone => zone.id === parsed)) {
      selectedZoneId.value = parsed
    }
  } else if (selectedZoneId.value) {
    window.localStorage.setItem(TELEMETRY_ZONE_STORAGE_KEY, String(selectedZoneId.value))
  }
  const storedPeriod = window.localStorage.getItem(TELEMETRY_PERIOD_STORAGE_KEY) as TelemetryPeriod | null
  if (storedPeriod && telemetryRangeOptions.some(option => option.value === storedPeriod)) {
    telemetryPeriod.value = storedPeriod
  } else {
    window.localStorage.setItem(TELEMETRY_PERIOD_STORAGE_KEY, telemetryPeriod.value)
  }
}

// Телеметрия для мини-графиков
const { fetchAggregates } = useTelemetry()
const { subscribeToGlobalEvents } = useWebSocket()
const telemetryMetricKeys = ['ph', 'ec', 'temp', 'humidity'] as const
type TelemetryMetricKey = typeof telemetryMetricKeys[number]

interface TelemetryMiniChartState {
  data: Array<{ ts: number; value?: number | null; avg?: number | null; min?: number | null; max?: number | null }>
  currentValue: number | null
  loading: boolean
}

// Используем shallowRef для больших объектов телеметрии
const telemetryData = shallowRef<Record<TelemetryMetricKey, TelemetryMiniChartState>>({
  ph: { data: [], currentValue: null, loading: false },
  ec: { data: [], currentValue: null, loading: false },
  temp: { data: [], currentValue: null, loading: false },
  humidity: { data: [], currentValue: null, loading: false },
})

// События для боковой панели - используем shallowRef для массива
const events = shallowRef<Array<ZoneEvent & { created_at?: string }>>([])
const eventFilter = ref<'ALL' | EventKind>('ALL')

// Объединяем события из props и WebSocket
// Мемоизируем propsEvents для избежания пересоздания при каждом рендере
const propsEvents = computed(() => {
  return (props.dashboard.latestAlerts || []).map(a => ({
    id: a.id,
    kind: 'ALERT' as const,
    message: (a as any).details?.message || a.type,
    zone_id: a.zone_id,
    occurred_at: a.created_at,
    created_at: a.created_at
  }))
})

const allEvents = computed(() => {
  return [...events.value, ...propsEvents.value].sort((a, b) => {
    const timeA = new Date(a.occurred_at || a.created_at || 0).getTime()
    const timeB = new Date(b.occurred_at || b.created_at || 0).getTime()
    return timeB - timeA
  }).slice(0, 20)
})

const filteredEvents = computed(() => {
  if (eventFilter.value === 'ALL') {
    return allEvents.value
  }
  return allEvents.value.filter(e => e.kind === eventFilter.value)
})

// Получаем первую зону для отображения телеметрии (можно расширить для всех зон)
// Обработчик клика на мини-график для перехода к детальному графику
function handleOpenDetail(zoneId: number, _metric: string): void {
  if (zoneId) {
    router.visit(`/zones/${zoneId}`, {
      preserveUrl: false,
    })
  }
}

const { showToast } = useToast()

// Инициализация useCommands для быстрых действий
const { sendZoneCommand } = useCommands(showToast)

// Обработчик быстрых действий для проблемных зон
async function handleQuickAction(zone: Zone, action: 'PAUSE' | 'RESUME' | 'FORCE_IRRIGATION'): Promise<void> {
  const zoneId = typeof zone.id === 'string' ? parseInt(zone.id, 10) : zone.id
  quickActionLoading[zoneId] = action
  try {
    if (action === 'PAUSE') {
      await sendZoneCommand(zoneId, 'PAUSE', {})
      showToast(`Зона "${zone.name}" приостановлена`, 'success')
    } else if (action === 'RESUME') {
      await sendZoneCommand(zoneId, 'RESUME', {})
      showToast(`Зона "${zone.name}" запущена`, 'success')
    } else if (action === 'FORCE_IRRIGATION') {
      await sendZoneCommand(zoneId, 'FORCE_IRRIGATION', {})
      showToast(`Запущен полив для зоны "${zone.name}"`, 'success')
    }
  } catch (error) {
    logger.error('[Dashboard] Failed to execute quick action:', error)
    showToast(`Ошибка выполнения действия для зоны "${zone.name}"`, 'error')
  } finally {
    quickActionLoading[zoneId] = null
  }
}

const resolveCssColor = (variable: string, fallback: string): string => {
  if (typeof window === 'undefined') {
    return fallback
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

const telemetryPalette = computed(() => {
  theme.value
  return {
    ph: resolveCssColor('--accent-cyan', '#3b82f6'),
    ec: resolveCssColor('--accent-green', '#10b981'),
    temp: resolveCssColor('--accent-amber', '#f59e0b'),
    humidity: resolveCssColor('--accent-lime', '#8b5cf6'),
  }
})

// Мемоизируем метрики телеметрии для избежания пересоздания массива
const telemetryMetrics = computed(() => {
  const data = telemetryData.value
  const palette = telemetryPalette.value
  return [
    {
      key: 'ph',
      label: 'pH',
      data: data.ph.data,
      currentValue: data.ph.currentValue === null ? undefined : data.ph.currentValue,
      unit: '',
      loading: data.ph.loading,
      color: palette.ph
    },
    {
      key: 'ec',
      label: 'EC',
      data: data.ec.data,
      currentValue: data.ec.currentValue === null ? undefined : data.ec.currentValue,
      unit: 'мСм/см',
      loading: data.ec.loading,
      color: palette.ec
    },
    {
      key: 'temp',
      label: 'Температура',
      data: data.temp.data,
      currentValue: data.temp.currentValue === null ? undefined : data.temp.currentValue,
      unit: '°C',
      loading: data.temp.loading,
      color: palette.temp
    },
    {
      key: 'humidity',
      label: 'Влажность',
      data: data.humidity.data,
      currentValue: data.humidity.currentValue === null ? undefined : data.humidity.currentValue,
      unit: '%',
      loading: data.humidity.loading,
      color: palette.humidity
    }
  ]
})

function resetTelemetryData(): void {
  telemetryMetricKeys.forEach(metric => {
    telemetryData.value[metric].data = []
    telemetryData.value[metric].currentValue = null
    telemetryData.value[metric].loading = false
  })
}

async function loadTelemetryMetrics() {
  const zoneId = selectedZoneId.value
  const period = telemetryPeriod.value
  if (!zoneId) {
    resetTelemetryData()
    return
  }

  for (const metric of telemetryMetricKeys) {
    telemetryData.value[metric].loading = true
    try {
      const data = await fetchAggregates(zoneId, metric, period)
      // Если за время загрузки зона или период сменились — пропускаем обновление
      if (selectedZoneId.value !== zoneId || telemetryPeriod.value !== period) {
        continue
      }
      telemetryData.value[metric].data = data.map(item => ({
        ts: new Date(item.ts).getTime(),
        value: item.value ?? undefined,
        avg: (item as any).avg ?? undefined,
        min: (item as any).min ?? undefined,
        max: (item as any).max ?? undefined
      }))
      if (data.length > 0) {
        telemetryData.value[metric].currentValue = data[data.length - 1].value ?? (data[data.length - 1] as any).avg ?? null
      }
    } catch (err) {
      logger.error(`[Dashboard] Failed to load ${metric} telemetry:`, err)
    } finally {
      telemetryData.value[metric].loading = false
    }
  }
}

// Сохраняем функцию отписки для очистки при размонтировании
let unsubscribeGlobalEvents: (() => void) | null = null

onMounted(async () => {
  restoreTelemetryPreferences()
  
  // Подписаться на глобальные события с оптимизацией
  const { useBatchUpdates } = await import('@/composables/useOptimizedUpdates')
  // @ts-ignore flushEvents - not used
  const { add: addEvent, flush: flushEvents } = useBatchUpdates<any>(
    (eventBatch) => {
      // Применяем события пакетом
      eventBatch.forEach(event => {
        events.value.unshift({
          id: event.id,
          kind: event.kind,
          message: event.message,
          zone_id: event.zoneId,
          occurred_at: event.occurredAt,
          created_at: event.occurredAt
        })
      })
      
      // Ограничиваем список 20 событиями
      if (events.value.length > 20) {
        events.value = events.value.slice(0, 20)
      }
    },
    { debounceMs: 200, maxBatchSize: 5, maxWaitMs: 1000 }
  )
  
  // Сохраняем функцию отписки
  unsubscribeGlobalEvents = subscribeToGlobalEvents((event) => {
    // Используем batch updates для оптимизации
    addEvent({
      id: event.id,
      kind: event.kind,
      message: event.message,
      zoneId: event.zoneId,
      occurredAt: event.occurredAt
    })
  })
})

// Отписываемся при размонтировании
onUnmounted(() => {
  if (unsubscribeGlobalEvents) {
    unsubscribeGlobalEvents()
    unsubscribeGlobalEvents = null
  }
})

</script>
