<template>
  <AppLayout>
    <template #default>
      <div class="dashboard-workspace min-w-0 space-y-5">
        <section class="surface-card space-y-5 p-5 md:p-6">
          <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div class="min-w-0 space-y-1.5">
              <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-muted)]">
                {{ DASHBOARD_HERO_EYEBROW[dashboardView] }}
              </p>
              <h1 class="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
                {{ heroTitle }}
              </h1>
              <p class="max-w-2xl text-sm text-[color:var(--text-muted)]">
                {{ heroSubtitle }}
              </p>
            </div>
            <div class="flex shrink-0 flex-wrap gap-2">
              <Button
                v-if="canConfigureCycle"
                size="sm"
                variant="secondary"
                @click="router.visit('/recipes')"
              >
                Фазы и рецепты
              </Button>
              <Button
                v-if="canLaunchCycle"
                size="sm"
                @click="router.visit('/launch')"
              >
                Запустить цикл
              </Button>
            </div>
          </div>

          <DashboardSummary
            :summary="summary"
            :expanded="dashboardView === 'operations' || dashboardView === 'admin'"
          />
        </section>

        <OperationsShiftPanel
          v-if="dashboardView === 'operations'"
          :items="shiftQueue"
        />
        <AgronomyOverviewPanel
          v-else-if="dashboardView === 'agronomy'"
          :corridor="agronomyCorridor"
          :decision-count="agronomyDecisionCount"
          :transitions="phaseTransitions"
        />
        <EngineeringEquipmentPanel
          v-else-if="dashboardView === 'engineering'"
          :zones="zones"
          :now="now"
        />
        <AdminHealthPanel
          v-else-if="dashboardView === 'admin'"
          :blocked-count="summary.zones_blocked ?? blockedZonesCount"
        />

        <section
          v-if="dashboardView !== 'engineering'"
          class="surface-card rounded-2xl border border-[color:var(--border-muted)] p-3 md:p-4"
        >
          <div class="dashboard-filters flex min-w-0 flex-col gap-3">
            <div class="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-center">
              <TextField
                v-model="query"
                class="min-w-0 flex-1"
                placeholder="Поиск зоны, культуры или теплицы"
                aria-label="Поиск зоны, культуры или теплицы"
              />
              <SelectField
                v-model="statusFilter"
                class="w-full sm:w-44"
                aria-label="Статус зоны"
              >
                <option value="">
                  Все статусы зоны
                </option>
                <option value="RUNNING">
                  Активные зоны
                </option>
                <option value="PAUSED">
                  Пауза
                </option>
                <option value="WARNING">
                  Предупреждение
                </option>
                <option value="ALARM">
                  Тревога
                </option>
                <option value="NONE">
                  Без цикла
                </option>
              </SelectField>
              <SelectField
                v-model="greenhouseFilter"
                class="w-full sm:w-48"
                aria-label="Теплица"
              >
                <option value="">
                  Все теплицы
                </option>
                <option
                  v-for="gh in greenhouses"
                  :key="gh.id"
                  :value="String(gh.id)"
                >
                  {{ gh.name }}
                </option>
              </SelectField>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <template v-if="dashboardView === 'agronomy'">
                <button
                  v-for="item in agronomyFilters"
                  :key="item.id"
                  type="button"
                  class="btn min-h-11 px-3 text-xs"
                  :class="agronomyFilter === item.id ? 'btn-outline' : 'btn-ghost'"
                  :aria-pressed="agronomyFilter === item.id"
                  @click="agronomyFilter = item.id"
                >
                  {{ item.label }}
                </button>
              </template>
              <button
                type="button"
                class="btn h-9 px-3 text-xs"
                :class="showOnlyAlerts ? 'btn-outline' : 'btn-ghost'"
                @click="showOnlyAlerts = !showOnlyAlerts"
              >
                {{ showOnlyAlerts ? 'Показать все' : 'Только алерты' }}
              </button>
              <button
                v-if="dashboardView !== 'agronomy'"
                type="button"
                class="btn h-9 px-3 text-xs"
                :class="denseView ? 'btn-outline' : 'btn-ghost'"
                @click="toggleDense"
              >
                {{ denseView ? 'Стандартный вид' : 'Компактный вид' }}
              </button>
            </div>
          </div>
        </section>

        <template v-if="dashboardView !== 'engineering'">
          <div
            v-if="summary.zones_total === 0"
            class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-6"
          >
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <div class="text-sm font-semibold">
                  Создайте теплицу
                </div>
                <div class="text-xs text-[color:var(--text-muted)] mt-1">
                  Добавьте теплицу и зоны, чтобы видеть их на обзоре.
                </div>
              </div>
              <Link href="/greenhouses">
                <Button size="sm">
                  Перейти к теплицам
                </Button>
              </Link>
            </div>
          </div>

          <EmptyState
            v-else-if="!filteredZones.length"
            title="Нет зон по текущим фильтрам"
            description="Сбросьте статус, теплицу или поиск, чтобы снова увидеть зоны."
            container-class="surface-card rounded-card border border-line py-8"
          />

          <AgronomyZoneList
            v-else-if="dashboardView === 'agronomy'"
            :zones="pagedZones as UnifiedZone[]"
            :now="now"
          />

          <div
            v-else
            class="dashboard-zone-grid"
          >
            <ZoneDashboardCard
              v-for="zone in pagedZones"
              :key="zone.id"
              :zone="zone as UnifiedZone"
              :sparkline-series-data="sparklines[zone.id] ?? null"
              :dense="denseView"
            />
          </div>

          <Pagination
            v-if="filteredZones.length > perPage"
            v-model:current-page="currentPage"
            v-model:per-page="perPage"
            :total="filteredZones.length"
          />
        </template>
      </div>
    </template>

    <template #context>
      <div
        class="flex flex-col flex-1 min-h-0"
        data-testid="dashboard-events-panel"
      >
        <div class="flex items-center justify-between mb-3 shrink-0 gap-2">
          <div class="text-[color:var(--text-primary)] font-medium">
            {{ contextTitle }}
          </div>
          <div class="flex items-center gap-1.5 text-xs text-[color:var(--text-dim)]">
            <div class="w-1.5 h-1.5 rounded-full bg-[color:var(--status-ok)] animate-pulse"></div>
            <span>Live</span>
          </div>
        </div>
        <div
          v-if="dashboardView === 'admin'"
          class="mb-3 flex flex-wrap gap-2 shrink-0 text-xs"
        >
          <Link
            href="/audit"
            class="text-[color:var(--status-info)] hover:underline"
          >
            Аудит
          </Link>
          <Link
            href="/monitoring"
            class="text-[color:var(--status-info)] hover:underline"
          >
            Здоровье системы
          </Link>
        </div>
        <div class="mb-3 flex gap-1 flex-wrap shrink-0">
          <button
            v-for="kind in eventFilterKinds"
            :key="kind"
            :data-testid="`dashboard-event-filter-${kind}`"
            class="px-2.5 py-1 text-xs rounded-md border transition-all duration-200"
            :class="
              eventFilter === kind
                ? 'border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)] text-[color:var(--text-primary)]'
                : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)]'
            "
            @click="eventFilter = kind"
          >
            {{ eventFilterLabel(kind) }}
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
            :class="
              e.kind === 'ALERT'
                ? 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)]'
                : e.kind === 'WARNING'
                  ? 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)]'
                  : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]'
            "
          >
            <div class="flex items-start justify-between mb-1.5">
              <Badge
                :variant="e.kind === 'ALERT' ? 'danger' : e.kind === 'WARNING' ? 'warning' : 'info'"
                class="text-xs"
              >
                {{ eventKindLabel(e.kind) }}
              </Badge>
              <span class="text-xs text-[color:var(--text-dim)]">{{ formatTime(e.occurred_at || e.created_at) }}</span>
            </div>
            <div
              v-if="e.zone_id"
              class="text-xs text-[color:var(--text-muted)] mb-1.5"
            >
              <Link
                :href="`/zones/${e.zone_id}`"
                class="text-[color:var(--status-info)] hover:underline transition-colors"
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
import { computed, onBeforeUnmount, onMounted, ref, toRef, watch } from 'vue'
import { Link, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import EmptyState from '@/Components/EmptyState.vue'
import SelectField from '@/Components/SelectField.vue'
import TextField from '@/Components/TextField.vue'
import Pagination from '@/Components/Pagination.vue'
import ZoneDashboardCard from '@/Components/ZoneDashboardCard.vue'
import { formatTime } from '@/utils/formatTime'
import { translateEventKind } from '@/utils/i18n'
import { useRole } from '@/composables/useRole'
import { useToast } from '@/composables/useToast'
import { useTheme } from '@/composables/useTheme'
import { useDashboardRealtimeFeed } from '@/composables/useDashboardRealtimeFeed'
import {
  useUnifiedDashboard,
  type UnifiedSummary,
  type UnifiedZone,
  type Greenhouse,
} from '@/composables/useUnifiedDashboard'
import type { Alert, EventKind } from '@/types'
import OperationsShiftPanel from './OperationsShiftPanel.vue'
import DashboardSummary from './DashboardSummary.vue'
import AgronomyOverviewPanel from './AgronomyOverviewPanel.vue'
import AgronomyZoneList from './AgronomyZoneList.vue'
import EngineeringEquipmentPanel from './EngineeringEquipmentPanel.vue'
import { useUrlState } from '@/composables/useUrlState'
import AdminHealthPanel from './AdminHealthPanel.vue'
import {
  DASHBOARD_CONTEXT_TITLE,
  DASHBOARD_HERO_EYEBROW,
  DASHBOARD_HERO_SUBTITLE,
  DASHBOARD_HERO_TITLE,
  buildShiftQueue,
  eventScopeForView,
  resolveDashboardView,
  summarizePhEcCorridor,
  upcomingPhaseTransitions,
  zonePhEcCorridor,
  zoneNeedsAgronomyDecision,
} from './dashboardRoleView'

interface Props {
  summary: UnifiedSummary
  zones: UnifiedZone[]
  greenhouses: Greenhouse[]
  latestAlerts: Alert[]
}

const props = defineProps<Props>()
const { role, canLaunchCycle, canEditRecipes: canConfigureCycle } = useRole()

const dashboardView = computed(() => resolveDashboardView(role.value))
const heroTitle = computed(() => DASHBOARD_HERO_TITLE[dashboardView.value])
const heroSubtitle = computed(() => DASHBOARD_HERO_SUBTITLE[dashboardView.value])
const contextTitle = computed(() => DASHBOARD_CONTEXT_TITLE[dashboardView.value])
const eventScope = computed(() => eventScopeForView(dashboardView.value))

const { showToast } = useToast()
const { theme } = useTheme()
const latestAlertsRef = toRef(props, 'latestAlerts')
const selectedZoneId = ref<number | null>(null)
const telemetryPeriod = ref<'1h' | '24h' | '7d'>('24h')
const { eventFilter, filteredEvents } = useDashboardRealtimeFeed({
  theme,
  selectedZoneId,
  telemetryPeriod,
  latestAlerts: latestAlertsRef,
  eventScope,
})

const now = ref(Date.now())
let observationTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => { observationTimer = setInterval(() => { now.value = Date.now() }, 30_000) })
onBeforeUnmount(() => { clearInterval(observationTimer) })
type AgronomyFilter = 'all' | 'attention' | 'unknown'
const agronomyFilter = useUrlState<AgronomyFilter>({ key: 'focus', defaultValue: 'all', parse: value => value === 'attention' || value === 'unknown' ? value : 'all' })
const agronomyFilters: Array<{ id: AgronomyFilter; label: string }> = [
  { id: 'all', label: 'Все циклы' }, { id: 'attention', label: 'Требуют решения' }, { id: 'unknown', label: 'Без оценки' },
]
const zonesRef = computed(() => dashboardView.value !== 'agronomy' || agronomyFilter.value === 'all' ? props.zones : props.zones.filter(zone => agronomyFilter.value === 'attention' ? zoneNeedsAgronomyDecision(zone, now.value) : zonePhEcCorridor(zone, now.value) === 'unknown'))
const {
  query,
  statusFilter,
  greenhouseFilter,
  showOnlyAlerts,
  denseView,
  currentPage,
  perPage,
  filteredZones,
  pagedZones,
  toggleDense,
  sparklines,
} = useUnifiedDashboard({
  zones: zonesRef,
  showToast,
  defaultDense: dashboardView.value !== 'agronomy',
})

const storedSearch = useUrlState({ key: 'q', defaultValue: '', debounceMs: 200 })
const storedStatus = useUrlState({ key: 'status', defaultValue: '' })
const storedGreenhouse = useUrlState({ key: 'greenhouse', defaultValue: '' })
const storedAlerts = useUrlState({ key: 'alerts', defaultValue: false, parse: value => value === '1', serialize: value => value ? '1' : null })
query.value = storedSearch.value
statusFilter.value = storedStatus.value
greenhouseFilter.value = storedGreenhouse.value
showOnlyAlerts.value = storedAlerts.value
watch(query, value => { storedSearch.value = value })
watch(storedSearch, value => { query.value = value })
watch(statusFilter, value => { storedStatus.value = value })
watch(storedStatus, value => { statusFilter.value = value })
watch(greenhouseFilter, value => { storedGreenhouse.value = value })
watch(storedGreenhouse, value => { greenhouseFilter.value = value })
watch(showOnlyAlerts, value => { storedAlerts.value = value })
watch(storedAlerts, value => { showOnlyAlerts.value = value })
watch(() => filteredZones.value.length, count => { currentPage.value = Math.max(1, Math.min(currentPage.value, Math.ceil(count / perPage.value))) })

const shiftQueue = computed(() => buildShiftQueue(props.zones))
const agronomyCorridor = computed(() => summarizePhEcCorridor(props.zones, now.value))
const phaseTransitions = computed(() => upcomingPhaseTransitions(props.zones, now.value))
const blockedZonesCount = computed(() => (
  props.zones.filter((zone) => zone.automation_block?.blocked).length
))
const agronomyDecisionCount = computed(() => props.zones.filter(zone => zoneNeedsAgronomyDecision(zone, now.value)).length)
watch(agronomyFilter, () => { currentPage.value = 1 })

const eventFilterKinds = computed((): Array<'ALL' | EventKind> => {
  if (dashboardView.value === 'admin') {
    return ['ALERT']
  }
  if (dashboardView.value === 'agronomy') {
    return ['ALL', 'ALERT', 'WARNING']
  }
  return ['ALL', 'ALERT', 'WARNING', 'INFO']
})

function eventFilterLabel(kind: 'ALL' | EventKind): string {
  return kind === 'ALL' ? 'Все' : translateEventKind(kind)
}

function eventKindLabel(kind: string): string {
  return translateEventKind(kind) || kind
}
</script>

<style scoped>
.dashboard-workspace {
  container: dashboard / inline-size;
}

.dashboard-zone-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1rem;
}

@container dashboard (min-width: 760px) {
  .dashboard-zone-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@container dashboard (min-width: 1100px) {
  .dashboard-filters { flex-direction: row; align-items: center; }
}

@container dashboard (min-width: 1360px) {
  .dashboard-zone-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
</style>
