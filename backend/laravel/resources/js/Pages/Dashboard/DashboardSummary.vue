<template>
  <details :open="expanded">
    <summary class="mb-3 cursor-pointer text-xs text-[color:var(--text-muted)]">
      Общая сводка теплицы
    </summary>
    <div
      class="ui-kpi-grid dashboard-kpi-grid"
      :class="{ 'dashboard-kpi-grid--blocked': (summary.zones_blocked ?? 0) > 0 }"
    >
      <div
        class="ui-kpi-card"
        data-testid="dashboard-zones-count"
      >
        <div class="ui-kpi-label">
          Зоны
        </div>
        <div class="ui-kpi-value text-status-ok">
          {{ summary.zones_total }}<span class="text-base font-semibold text-[color:var(--text-muted)]"> / {{ summary.zones_running }}</span>
        </div>
        <div class="ui-kpi-hint">
          Всего / в работе
        </div>
      </div>
      <div class="ui-kpi-card">
        <div class="ui-kpi-label">
          Предупреждение
        </div>
        <div
          class="ui-kpi-value"
          :class="summary.zones_warning > 0 ? 'text-status-warning' : ''"
        >
          {{ summary.zones_warning }}
        </div>
      </div>
      <div class="ui-kpi-card">
        <div class="ui-kpi-label">
          Тревога
        </div>
        <div
          class="ui-kpi-value"
          :class="summary.zones_alarm > 0 ? 'text-status-critical' : ''"
        >
          {{ summary.zones_alarm }}
        </div>
      </div>
      <div class="ui-kpi-card">
        <div class="ui-kpi-label">
          Устройства
        </div>
        <div class="ui-kpi-value text-status-info">
          {{ summary.devices_online }}<span class="text-base font-semibold text-[color:var(--text-muted)]">/{{ summary.devices_total }}</span>
        </div>
        <div class="ui-kpi-hint">
          Online / всего
        </div>
      </div>
      <div
        class="ui-kpi-card"
        data-testid="dashboard-alerts-count"
        :class="summary.alerts_active > 0 ? 'border-[color:var(--status-critical)]' : ''"
      >
        <div class="ui-kpi-label">
          Алерты
        </div>
        <div
          class="ui-kpi-value"
          :class="summary.alerts_active > 0 ? 'text-status-critical' : ''"
        >
          {{ summary.alerts_active }}
        </div>
      </div>
      <div
        v-if="(summary.zones_blocked ?? 0) > 0"
        class="ui-kpi-card border border-[color:var(--status-critical)]"
        data-testid="dashboard-zones-blocked"
      >
        <div class="ui-kpi-label text-status-critical">
          Авто остановлено
        </div>
        <div class="ui-kpi-value text-status-critical">
          {{ summary.zones_blocked }}
        </div>
      </div>
    </div>
  </details>
</template>

<script setup lang="ts">
import type { UnifiedSummary } from '@/composables/useUnifiedDashboard'
defineProps<{ summary: UnifiedSummary; expanded: boolean }>()
</script>

<style scoped>
.dashboard-kpi-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.dashboard-kpi-grid .ui-kpi-card {
  min-width: 0;
  padding: 1rem;
  border-radius: var(--radius-control);
  background: var(--bg-surface);
  box-shadow: none;
  animation: none;
}

.dashboard-kpi-grid .ui-kpi-card:hover { transform: none; }
.dashboard-kpi-grid .ui-kpi-card::after { display: none; }

.dashboard-kpi-grid .ui-kpi-label {
  font-size: 0.75rem;
  letter-spacing: 0;
  text-transform: none;
}

.dashboard-kpi-grid .ui-kpi-value {
  font-family: 'IBM Plex Sans', ui-sans-serif, system-ui, sans-serif;
  font-size: 1.875rem;
}

.dashboard-kpi-grid .text-status-ok { color: var(--status-ok); }
.dashboard-kpi-grid .text-status-info { color: var(--status-info); }
.dashboard-kpi-grid .text-status-warning { color: var(--status-warning); }
.dashboard-kpi-grid .text-status-critical { color: var(--status-critical); }

@container dashboard (min-width: 560px) {
  .dashboard-kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@container dashboard (min-width: 960px) {
  .dashboard-kpi-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
  .dashboard-kpi-grid--blocked { grid-template-columns: repeat(6, minmax(0, 1fr)); }
}

</style>
