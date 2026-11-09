<template>
  <section
    class="agronomy-list surface-card overflow-hidden"
    aria-label="Культуры и циклы"
  >
    <div
      class="agronomy-head bg-[color:var(--bg-elevated)] text-xs text-[color:var(--text-muted)]"
      aria-hidden="true"
    >
      <span>Зона / культура</span><span>Фаза</span><span>pH</span><span>EC, мСм/см</span><span>Оценка / свежесть</span><span>Следующее действие</span>
    </div>
    <article
      v-for="zone in zones"
      :key="zone.id"
      class="agronomy-row border-t border-[color:var(--border-muted)]"
    >
      <div class="min-w-0">
        <Link
          :href="`/zones/${zone.id}?tab=cycle`"
          class="font-semibold text-[color:var(--text-primary)] hover:underline"
        >
          {{ zone.name }}
        </Link>
        <p class="mt-1 text-xs text-[color:var(--text-muted)]">
          {{ cropGroupLabel(zone) }}
        </p>
      </div>
      <div>
        <span class="text-sm">{{ zone.cycle?.current_stage?.name || (zone.cycle ? 'Фаза не определена' : 'Без цикла') }}</span>
        <p class="mt-1 text-xs text-[color:var(--text-muted)]">
          {{ zone.recipe?.name || 'Рецепт не назначен' }}
        </p>
      </div>
      <div
        v-for="metric in (['ph', 'ec'] as const)"
        :key="metric"
      >
        <div class="flex items-baseline gap-2">
          <span class="text-xs text-[color:var(--text-muted)] lg:hidden">{{ metric === 'ph' ? 'pH' : 'EC' }}</span>
          <strong
            class="text-lg tabular-nums"
            :class="metricOutside(zone, metric) ? 'text-[color:var(--status-warning)]' : ''"
          >{{ formatMetric(zone.telemetry?.[metric]) }}</strong>
        </div>
        <p class="mt-1 text-[11px] text-[color:var(--text-muted)]">
          {{ targetLabel(zone, metric) }}
        </p>
      </div>
      <div class="min-w-0 space-y-1.5">
        <Badge :variant="assessment(zone) === 'out' ? 'warning' : assessment(zone) === 'in' ? 'ok' : 'neutral'">
          {{ assessment(zone) === 'out' ? 'Вне диапазона' : assessment(zone) === 'in' ? 'В диапазоне' : 'Без оценки' }}
        </Badge>
        <p class="text-[11px] text-[color:var(--text-muted)]">
          {{ telemetrySummaryAge(zone, now) }}
        </p>
        <p
          v-if="assessment(zone) === 'unknown'"
          class="text-[11px] text-[color:var(--text-muted)]"
        >
          {{ telemetrySummaryIsFresh(zone, now) ? 'Недостаточно значений или целей' : 'Нет свежей сводки (до 5 мин)' }}
        </p>
        <Badge
          v-if="zone.estop?.active"
          variant="danger"
          data-testid="agronomy-zone-estop"
        >
          Аварийная остановка
        </Badge>
        <Badge
          v-if="zone.automation_block?.blocked"
          variant="danger"
        >
          Автоматика остановлена
        </Badge>
      </div>
      <Link
        :href="action(zone).href"
        class="btn btn-outline min-h-11 text-xs text-center"
      >
        {{ action(zone).label }} →
      </Link>
    </article>
  </section>
</template>

<script setup lang="ts">
import { Link } from '@inertiajs/vue3'
import Badge from '@/Components/Badge.vue'
import type { UnifiedZone } from '@/composables/useUnifiedDashboard'
import { cropGroupLabel, telemetrySummaryAge, telemetrySummaryIsFresh, zonePhEcCorridor } from './dashboardRoleView'

const props = defineProps<{ zones: UnifiedZone[]; now: number }>()
const assessment = (zone: UnifiedZone) => zonePhEcCorridor(zone, props.now)
function formatMetric(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '—'
}
function targetLabel(zone: UnifiedZone, metric: 'ph' | 'ec'): string {
  const range = zone.targets?.[metric]
  return range?.min != null && range.max != null ? `Цель ${range.min}–${range.max}` : 'Диапазон не задан'
}
function metricOutside(zone: UnifiedZone, metric: 'ph' | 'ec'): boolean {
  const value = zone.telemetry?.[metric], range = zone.targets?.[metric]
  return telemetrySummaryIsFresh(zone, props.now) && typeof value === 'number' && range?.min != null && range.max != null && (value < range.min || value > range.max)
}
function action(zone: UnifiedZone): { label: string; href: string } {
  if (zone.automation_block?.blocked) return { label: 'Причина остановки', href: `/zones/${zone.id}?tab=alerts` }
  if (assessment(zone) === 'out') return { label: 'Проверить отклонение', href: `/zones/${zone.id}?tab=telemetry` }
  if (assessment(zone) === 'unknown') return { label: 'Проверить данные', href: `/zones/${zone.id}?tab=telemetry` }
  return { label: 'Открыть цикл', href: `/zones/${zone.id}?tab=cycle` }
}
</script>

<style scoped>
.agronomy-list { container: agronomy / inline-size; }
.agronomy-head, .agronomy-row { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1.1fr) .7fr .7fr minmax(0, 1.3fr) minmax(0, 1.1fr); align-items: center; gap: 1rem; padding: 1rem 1.25rem; }
.agronomy-row { min-height: 6.5rem; }
@container agronomy (max-width: 1040px) {
  .agronomy-head { display: none; }
  .agronomy-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .agronomy-row > :last-child { grid-column: 1 / -1; }
}
@media (max-width: 480px) {
  .agronomy-row { padding: 1rem; gap: .875rem; }
  .agronomy-row > :nth-child(5) { grid-column: 1 / -1; }
}
</style>
