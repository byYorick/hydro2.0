<template>
  <AppLayout>
    <template #default>
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
                    :class="
                      telemetryPeriod === range.value
                        ? 'border-[color:var(--accent-cyan)] bg-[color:var(--badge-info-bg)] text-[color:var(--accent-cyan)]'
                        : 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)]'
                    "
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
        <div class="mb-3 flex gap-1 flex-wrap shrink-0">
          <button
            v-for="kind in ['ALL', 'ALERT', 'WARNING', 'INFO']"
            :key="kind"
            :data-testid="`dashboard-event-filter-${kind}`"
            class="px-2.5 py-1 text-xs rounded-md border transition-all duration-200"
            :class="
              eventFilter === kind
                ? 'border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)] text-[color:var(--text-primary)]'
                : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-muted)] hover:border-[color:var(--border-strong)]'
            "
            @click="eventFilter = kind as any"
          >
            {{ kind === "ALL" ? "Все" : kind }}
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
import { computed } from "vue";
import { Link } from "@inertiajs/vue3";
import AppLayout from "@/Layouts/AppLayout.vue";
import Card from "@/Components/Card.vue";
import Badge from "@/Components/Badge.vue";
import Button from "@/Components/Button.vue";
import MetricIndicator from "@/Components/MetricIndicator.vue";
import StatusIndicator from "@/Components/StatusIndicator.vue";
import MiniTelemetryChart from "@/Components/MiniTelemetryChart.vue";
import ZonesHeatmap from "@/Components/ZonesHeatmap.vue";
import AgronomistDashboard from "./Dashboards/AgronomistDashboard.vue";
import AdminDashboard from "./Dashboards/AdminDashboard.vue";
import EngineerDashboard from "./Dashboards/EngineerDashboard.vue";
import OperatorDashboard from "./Dashboards/OperatorDashboard.vue";
import ViewerDashboard from "./Dashboards/ViewerDashboard.vue";
import { translateStatus } from "@/utils/i18n";
import { formatTime } from "@/utils/formatTime";
import { useRole } from "@/composables/useRole";
import { useDashboardPage, telemetryRangeOptions, type DashboardData, type QuickAction } from "@/composables/useDashboardPage";
import type { Zone } from "@/types";

interface Props {
    dashboard: DashboardData;
}

const props = defineProps<Props>();
const dashboard = computed(() => props.dashboard);
const { isAgronomist, isAdmin, isEngineer, isOperator, isViewer } = useRole();

const {
    zonesStatusSummary,
    nodesStatusSummary,
    hasGreenhouses,
    hasProblematicZones,
    hasZones,
    telemetryPeriod,
    selectedZoneId,
    telemetryZones,
    selectedZoneLabel,
    telemetryPeriodLabel,
    hasZonesForTelemetry,
    isQuickActionLoading,
    eventFilter,
    filteredEvents,
    telemetryMetrics,
    handleOpenDetail,
    handleQuickAction,
} = useDashboardPage({ dashboard });
</script>
