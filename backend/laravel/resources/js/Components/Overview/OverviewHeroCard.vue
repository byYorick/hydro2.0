<template>
  <section class="ui-hero p-5">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <div class="min-w-0 flex-1">
        <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
          зона выращивания
        </p>
        <div class="mt-1 flex items-center gap-3">
          <div class="text-2xl font-semibold truncate">
            {{ zone.name }}
          </div>
          <Badge
            :variant="variant"
            class="shrink-0"
            data-testid="zone-status-badge"
          >
            {{ translateStatus(zone.status) }}
          </Badge>
        </div>
        <div class="mt-1 space-y-1 text-sm text-[color:var(--text-dim)]">
          <div
            v-if="zone.description"
            class="truncate"
          >
            {{ zone.description }}
          </div>
          <div
            v-if="activeGrowCycle?.recipeRevision"
            class="flex items-center gap-2 text-xs uppercase tracking-[0.12em]"
          >
            <span class="text-[color:var(--text-dim)]">Рецепт</span>
            <span class="font-semibold text-[color:var(--accent-cyan)]">
              {{ activeGrowCycle.recipeRevision.recipe.name }}
            </span>
            <span
              v-if="activeGrowCycle.currentPhase"
              class="text-[color:var(--text-dim)]"
            >
              фаза {{ activeGrowCycle.currentPhase.phase_index + 1 }}
            </span>
          </div>
          <div
            v-else-if="hasCycle"
            class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]"
          >
            Цикл активен
          </div>
        </div>
      </div>

      <div class="flex flex-wrap items-center justify-end gap-2">
        <template v-if="canOperateZone">
          <div class="inline-flex items-center rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 p-1 backdrop-blur gap-1">
            <Button
              size="sm"
              :disabled="loadingIrrigate"
              data-testid="start-irrigation-button"
              @click="$emit('start-irrigation')"
            >
              <LoadingState
                v-if="loadingIrrigate"
                loading
                size="sm"
                :container-class="'inline-flex mr-1'"
              />
              <span class="hidden sm:inline">Полить</span>
              <span class="sm:hidden">💧</span>
            </Button>
            <Button
              size="sm"
              variant="ghost"
              :disabled="loadingIrrigate"
              data-testid="force-irrigation-button"
              @click="$emit('force-irrigation')"
            >
              <LoadingState
                v-if="loadingIrrigate"
                loading
                size="sm"
                :container-class="'inline-flex mr-1'"
              />
              <span class="hidden sm:inline">Принудительно</span>
              <span class="sm:hidden">⚡</span>
            </Button>
          </div>
        </template>
        <Link :href="`/zones/${zone.id}/simulation`">
          <Button
            size="sm"
            variant="outline"
          >
            <span class="hidden sm:inline">Симуляция</span>
            <span class="sm:hidden">🧪</span>
          </Button>
        </Link>
      </div>
    </div>

    <div class="ui-kpi-grid mt-4 grid-cols-2 xl:grid-cols-4">
      <article class="ui-kpi-card">
        <div class="flex items-center justify-between">
          <div class="ui-kpi-label">pH факт</div>
          <span
            class="ui-state-dot"
            :class="metricDotClass(telemetry?.ph)"
          />
        </div>
        <div class="ui-kpi-value text-[color:var(--accent-cyan)]">
          {{ formatMetric(telemetry?.ph, 2) }}
        </div>
        <div class="ui-kpi-hint">Текущее значение</div>
      </article>

      <article class="ui-kpi-card">
        <div class="flex items-center justify-between">
          <div class="ui-kpi-label">EC факт</div>
          <span
            class="ui-state-dot"
            :class="metricDotClass(telemetry?.ec)"
          />
        </div>
        <div class="ui-kpi-value text-[color:var(--accent-cyan)]">
          {{ formatMetric(telemetry?.ec, 2) }}
        </div>
        <div class="ui-kpi-hint">мСм/см</div>
      </article>

      <article class="ui-kpi-card">
        <div class="flex items-center justify-between">
          <div class="ui-kpi-label">Температура</div>
          <span
            class="ui-state-dot"
            :class="metricDotClass(telemetry?.temperature)"
          />
        </div>
        <div class="ui-kpi-value">
          {{ formatMetric(telemetry?.temperature, 1) }}
        </div>
        <div class="ui-kpi-hint">°C воздух</div>
      </article>

      <article class="ui-kpi-card">
        <div class="flex items-center justify-between">
          <div class="ui-kpi-label">Влажность</div>
          <span
            class="ui-state-dot"
            :class="metricDotClass(telemetry?.humidity)"
          />
        </div>
        <div class="ui-kpi-value">
          {{ formatMetric(telemetry?.humidity, 0) }}
        </div>
        <div class="ui-kpi-hint">% относительная</div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import LoadingState from '@/Components/LoadingState.vue'
import { Link } from '@inertiajs/vue3'
import { translateStatus } from '@/utils/i18n'
import type { BadgeVariant } from '@/Components/Badge.vue'
import type { Zone, ZoneTelemetry } from '@/types'

defineProps<{
  zone: Zone
  variant: BadgeVariant
  activeGrowCycle?: any
  hasCycle: boolean
  canOperateZone: boolean
  loadingIrrigate: boolean
  telemetry: ZoneTelemetry
}>()

defineEmits<{
  'start-irrigation': []
  'force-irrigation': []
}>()

function formatMetric(value: number | null | undefined, precision = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return Number(value).toFixed(precision)
}

function metricDotClass(value: number | null | undefined): string {
  return value !== null && value !== undefined && !Number.isNaN(value)
    ? 'text-[color:var(--accent-green)]'
    : 'text-[color:var(--text-dim)]'
}
</script>
