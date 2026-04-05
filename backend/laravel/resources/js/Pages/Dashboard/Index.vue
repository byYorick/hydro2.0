<template>
  <AppLayout>
    <template #default>
      <div class="space-y-5">
        <section class="ui-hero p-6">
          <div class="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
            <div>
              <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
                операционный центр
              </p>
              <h1 class="text-2xl font-semibold tracking-tight mt-1">
                Операционный центр
              </h1>
              <p class="text-sm text-[color:var(--text-muted)] mt-1">
                Зоны, телеметрия, циклы и действия на одном экране.
              </p>
            </div>
            <div class="flex flex-wrap gap-2">
              <Button
                v-if="canConfigureCycle"
                size="sm"
                variant="secondary"
                @click="router.visit('/recipes')"
              >
                Фазы и рецепты
              </Button>
              <Button
                v-if="canManageCycle"
                size="sm"
                @click="router.visit('/grow-cycle-wizard')"
              >
                Запустить цикл
              </Button>
            </div>
          </div>
          <div class="ui-kpi-grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 mt-6">
            <div
              class="ui-kpi-card"
              data-testid="dashboard-zones-count"
            >
              <div class="ui-kpi-label">
                Зоны (всего / в работе)
              </div>
              <div class="ui-kpi-value text-[color:var(--accent-green)]">
                {{ summary.zones_total }} / {{ summary.zones_running }}
              </div>
            </div>
            <div class="ui-kpi-card">
              <div class="ui-kpi-label">
                Warning
              </div>
              <div
                class="ui-kpi-value"
                :class="summary.zones_warning > 0 ? 'text-[color:var(--accent-amber)]' : ''"
              >
                {{ summary.zones_warning }}
              </div>
            </div>
            <div class="ui-kpi-card">
              <div class="ui-kpi-label">
                Alarm
              </div>
              <div
                class="ui-kpi-value"
                :class="summary.zones_alarm > 0 ? 'text-[color:var(--accent-red)]' : ''"
              >
                {{ summary.zones_alarm }}
              </div>
            </div>
            <div class="ui-kpi-card">
              <div class="ui-kpi-label">
                Циклы active
              </div>
              <div class="ui-kpi-value text-[color:var(--accent-cyan)]">
                {{ summary.cycles_running }}
              </div>
            </div>
            <div class="ui-kpi-card">
              <div class="ui-kpi-label">
                Устройства
              </div>
              <div class="ui-kpi-value">
                {{ summary.devices_online }}/{{ summary.devices_total }}
              </div>
            </div>
            <div
              class="ui-kpi-card"
              data-testid="dashboard-alerts-count"
            >
              <div class="ui-kpi-label">
                Алерты
              </div>
              <div class="ui-kpi-value text-[color:var(--accent-red)]">
                {{ summary.alerts_active }}
              </div>
            </div>
          </div>
        </section>

        <section class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
          <div class="flex flex-col lg:flex-row lg:items-center gap-3">
            <div class="flex flex-col sm:flex-row sm:items-center gap-2 flex-1">
              <input
                v-model="query"
                class="input-field flex-1"
                placeholder="Поиск зоны, культуры или теплицы"
              >
              <select
                v-model="statusFilter"
                class="input-select w-full sm:w-44"
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
                  Warning
                </option>
                <option value="ALARM">
                  Alarm
                </option>
                <option value="NONE">
                  Без цикла
                </option>
              </select>
              <select
                v-model="greenhouseFilter"
                class="input-select w-full sm:w-48"
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
              </select>
            </div>
            <div class="flex items-center gap-2">
              <button
                type="button"
                class="btn btn-ghost h-9 px-3 text-xs"
                @click="showOnlyAlerts = !showOnlyAlerts"
              >
                {{ showOnlyAlerts ? 'Показать все' : 'Только алерты' }}
              </button>
              <button
                type="button"
                class="btn btn-ghost h-9 px-3 text-xs"
                @click="toggleDense"
              >
                {{ denseView ? 'Стандартный вид' : 'Компактный вид' }}
              </button>
            </div>
          </div>
        </section>

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
                Добавьте теплицу и зоны, чтобы видеть их в операционном центре.
              </div>
            </div>
            <Link href="/greenhouses">
              <Button size="sm">
                Перейти к теплицам
              </Button>
            </Link>
          </div>
        </div>

        <div
          v-else-if="!filteredZones.length"
          class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-6 text-sm text-[color:var(--text-muted)] text-center"
        >
          Нет зон по текущим фильтрам.
        </div>

        <div
          v-else
          class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
        >
          <ZoneDashboardCard
            v-for="zone in pagedZones"
            :key="zone.id"
            :zone="zone as UnifiedZone"
            :can-manage-cycle="canManageCycle"
            :can-issue-commands="canIssueZoneCommands"
            :sparkline-data="sparklines[zone.id] ?? null"
            :sparkline-color="sparklineColor(zone as UnifiedZone)"
            :is-action-loading="isActionLoading"
            :dense="denseView"
            @pause="pauseCycle"
            @resume="resumeCycle"
            @irrigate="openActionModal($event, 'START_IRRIGATION')"
            @flush="openActionModal($event, 'FORCE_IRRIGATION')"
            @harvest="openHarvestModal"
            @abort="openAbortModal"
          />
        </div>

        <Pagination
          v-if="filteredZones.length > perPage"
          v-model:current-page="currentPage"
          v-model:per-page="perPage"
          :total="filteredZones.length"
        />

        <ZoneActionModal
          v-if="actionModal.zone"
          :show="actionModal.open"
          :zone-id="actionModal.zone.id"
          :action-type="actionModal.actionType"
          :default-params="dashboardZoneActionDefaultParams"
          :irrigation-correction-summary="actionModal.zone.irrigation_correction_summary ?? null"
          @close="closeActionModal"
          @submit="submitAction"
        />

        <ConfirmModal
          :open="harvestModal.open"
          title="Зафиксировать сбор"
          message=" "
          confirm-text="Подтвердить"
          :loading="isActionLoading(harvestModal.zone?.id || 0, 'harvest')"
          @close="closeHarvestModal"
          @confirm="confirmHarvest"
        >
          <div class="space-y-3 text-sm text-[color:var(--text-muted)]">
            <div>Зафиксировать сбор урожая и завершить цикл?</div>
            <div>
              <label class="text-xs text-[color:var(--text-dim)]">Метка партии (опционально)</label>
              <input
                v-model="harvestModal.batchLabel"
                class="input-field mt-1 w-full"
                placeholder="Например: Batch-042"
              >
            </div>
          </div>
        </ConfirmModal>

        <ConfirmModal
          :open="abortModal.open"
          title="Аварийная остановка"
          message=" "
          confirm-text="Остановить"
          confirm-variant="danger"
          :loading="isActionLoading(abortModal.zone?.id || 0, 'abort')"
          @close="closeAbortModal"
          @confirm="confirmAbort"
        >
          <div class="space-y-3 text-sm text-[color:var(--text-muted)]">
            <div>Остановить цикл? Это действие нельзя отменить.</div>
            <div>
              <label class="text-xs text-[color:var(--text-dim)]">Причина (опционально)</label>
              <textarea
                v-model="abortModal.notes"
                class="input-field mt-1 w-full h-20 resize-none"
                placeholder="Короткое описание причины"
              />
            </div>
          </div>
        </ConfirmModal>
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
            <div class="w-1.5 h-1.5 rounded-full bg-[color:var(--accent-green)] animate-pulse" />
            <span>Live</span>
          </div>
        </div>
        <div class="mb-3 flex gap-1 flex-wrap shrink-0">
          <button
            v-for="kind in (['ALL', 'ALERT', 'WARNING', 'INFO'] as const)"
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
import { computed, ref, toRef } from 'vue'
import { pickIrrigationDurationFromTargets } from '@/utils/irrigationModalDefaults'
import { Link, router, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Pagination from '@/Components/Pagination.vue'
import ZoneActionModal from '@/Components/ZoneActionModal.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import ZoneDashboardCard from '@/Components/ZoneDashboardCard.vue'
import { formatTime } from '@/utils/formatTime'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useTheme } from '@/composables/useTheme'
import { useDashboardRealtimeFeed } from '@/composables/useDashboardRealtimeFeed'
import {
  useUnifiedDashboard,
  type UnifiedSummary,
  type UnifiedZone,
  type Greenhouse,
} from '@/composables/useUnifiedDashboard'
import type { Alert } from '@/types'

interface Props {
  summary: UnifiedSummary
  zones: UnifiedZone[]
  greenhouses: Greenhouse[]
  latestAlerts: Alert[]
}

const props = defineProps<Props>()
const page = usePage()
const role = computed(() => (page.props.auth as { user?: { role?: string } })?.user?.role || 'viewer')
const canConfigureCycle = computed(() => ['admin', 'agronomist'].includes(role.value))
const canManageCycle = computed(() => ['admin', 'agronomist', 'operator'].includes(role.value))
const canIssueZoneCommands = computed(() => ['admin', 'operator', 'agronomist', 'engineer'].includes(role.value))

const { showToast } = useToast()
const { api } = useApi(showToast)
const { theme } = useTheme()
const latestAlertsRef = toRef(props, 'latestAlerts')
const selectedZoneId = ref<number | null>(null)
const telemetryPeriod = ref<'1h' | '24h' | '7d'>('24h')
const { eventFilter, filteredEvents } = useDashboardRealtimeFeed({
  theme,
  selectedZoneId,
  telemetryPeriod,
  latestAlerts: latestAlertsRef,
})

const zonesRef = computed(() => props.zones)
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
  sparklineColor,
  harvestModal,
  abortModal,
  actionModal,
  isActionLoading,
  pauseCycle,
  resumeCycle,
  openHarvestModal,
  closeHarvestModal,
  confirmHarvest,
  openAbortModal,
  closeAbortModal,
  confirmAbort,
  openActionModal,
  closeActionModal,
  submitAction,
} = useUnifiedDashboard({
  zones: zonesRef,
  api,
  showToast,
})

const dashboardZoneActionDefaultParams = computed(() => {
  const z = actionModal.zone
  if (!z || (actionModal.actionType !== 'START_IRRIGATION' && actionModal.actionType !== 'FORCE_IRRIGATION')) {
    return {}
  }
  const sec = pickIrrigationDurationFromTargets(z.current_phase_targets ?? null)
  return sec != null ? { duration_sec: sec } : {}
})
</script>
