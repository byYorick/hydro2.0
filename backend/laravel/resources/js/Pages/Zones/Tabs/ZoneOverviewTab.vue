<template>
  <div class="space-y-4">
    <section class="ui-hero p-5">
      <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div class="flex-1 min-w-0">
          <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
            зона выращивания
          </p>
          <div class="flex items-center gap-3 mt-1">
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
          <div class="text-sm text-[color:var(--text-dim)] mt-1 space-y-1">
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
              <span class="text-[color:var(--accent-cyan)] font-semibold">
                {{ activeGrowCycle.recipeRevision.recipe.name }}
              </span>
              <span
                v-if="activeGrowCycle?.currentPhase"
                class="text-[color:var(--text-dim)]"
              >
                фаза {{ activeGrowCycle.currentPhase.phase_index + 1 }}
              </span>
            </div>
            <div
              v-else-if="displayCycle"
              class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]"
            >
              Цикл активен
            </div>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2 justify-end">
          <template v-if="canOperateZone">
            <Button
              size="sm"
              variant="outline"
              :disabled="loading.irrigate"
              class="flex-1 sm:flex-none"
              data-testid="force-irrigation-button"
              @click="$emit('force-irrigation')"
            >
              <template v-if="loading.irrigate">
                <LoadingState
                  loading
                  size="sm"
                  :container-class="'inline-flex mr-2'"
                />
              </template>
              <span class="hidden sm:inline">Полить сейчас</span>
              <span class="sm:hidden">💧</span>
            </Button>
          </template>
          <Link
            :href="`/zones/${zone.id}/simulation`"
            class="flex-1 sm:flex-none"
          >
            <Button
              size="sm"
              variant="outline"
              class="w-full"
            >
              <span class="hidden sm:inline">Симуляция</span>
              <span class="sm:hidden">🧪</span>
            </Button>
          </Link>
        </div>
      </div>
      <div class="ui-kpi-grid grid-cols-2 xl:grid-cols-4 mt-4">
        <article class="ui-kpi-card">
          <div class="ui-kpi-label">
            pH факт
          </div>
          <div class="ui-kpi-value text-[color:var(--accent-cyan)]">
            {{ formatMetric(telemetry?.ph, 2) }}
          </div>
          <div class="ui-kpi-hint">
            Текущее значение
          </div>
        </article>
        <article class="ui-kpi-card">
          <div class="ui-kpi-label">
            EC факт
          </div>
          <div class="ui-kpi-value text-[color:var(--accent-cyan)]">
            {{ formatMetric(telemetry?.ec, 2) }}
          </div>
          <div class="ui-kpi-hint">
            мСм/см
          </div>
        </article>
        <article class="ui-kpi-card">
          <div class="ui-kpi-label">
            Температура
          </div>
          <div class="ui-kpi-value">
            {{ formatMetric(telemetry?.temperature, 1) }}
          </div>
          <div class="ui-kpi-hint">
            °C воздух
          </div>
        </article>
        <article class="ui-kpi-card">
          <div class="ui-kpi-label">
            Влажность
          </div>
          <div class="ui-kpi-value">
            {{ formatMetric(telemetry?.humidity, 0) }}
          </div>
          <div class="ui-kpi-hint">
            % относительная
          </div>
        </article>
      </div>
    </section>

    <div class="space-y-4">
      <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
        <ZoneTargets
          v-if="hasTargets"
          :telemetry="telemetry"
          :targets="targets"
        />
        <div
          v-else
          class="text-center py-6"
        >
          <div class="text-4xl mb-2">
            🎯
          </div>
          <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
            Целевые значения не настроены
          </div>
          <div class="text-xs text-[color:var(--text-muted)]">
            Настройте целевые значения для отслеживания параметров зоны
          </div>
        </div>
      </div>

      <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
        <StageProgress
          v-if="activeGrowCycle"
          :grow-cycle="activeGrowCycle"
          :phase-progress="computedPhaseProgress"
          :phase-days-elapsed="computedPhaseDaysElapsed"
          :phase-days-total="computedPhaseDaysTotal"
          :started-at="activeGrowCycle.started_at"
        />
        <div
          v-else-if="displayCycle"
          class="text-center py-6"
        >
          <div class="text-4xl mb-2">
            🌱
          </div>
          <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
            Цикл выращивания активен
          </div>
          <div class="text-xs text-[color:var(--text-muted)] space-y-1">
            <div v-if="zone.status">
              Статус зоны: <span class="font-semibold">{{ translateStatus(zone.status) }}</span>
            </div>
            <div v-if="activeGrowCycle?.status">
              Статус цикла: <span class="font-semibold">{{ translateStatus(activeGrowCycle.status) }}</span>
            </div>
            <div v-if="activeGrowCycle?.started_at">
              Запущен: {{ formatTimeShort(new Date(activeGrowCycle.started_at)) }}
            </div>
            <div class="mt-2 text-[color:var(--text-dim)]">
              Привяжите рецепт для детального отслеживания прогресса фаз
            </div>
          </div>
        </div>
        <div
          v-else-if="zone.status === 'RUNNING' || zone.status === 'PAUSED'"
          class="text-center py-6"
        >
          <div class="text-4xl mb-2">
            🔄
          </div>
          <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
            Данные цикла ещё загружаются
          </div>
          <div class="text-xs text-[color:var(--text-muted)]">
            Обновите данные зоны на вкладке «Цикл», чтобы синхронизировать активный цикл и таргеты
          </div>
        </div>
        <div
          v-else
          class="text-center py-6"
        >
          <div class="text-4xl mb-2">
            🌱
          </div>
          <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
            Цикл выращивания не запущен
          </div>
          <div class="text-xs text-[color:var(--text-muted)]">
            Привяжите рецепт и запустите цикл выращивания для отслеживания прогресса
          </div>
        </div>
      </div>

      <Card>
        <div class="flex items-center justify-between mb-2">
          <div class="text-sm font-semibold">
            События (последние {{ recentEvents.length }})
          </div>
        </div>
        <div
          v-if="recentEvents.length > 0"
          class="space-y-1 max-h-[280px] overflow-y-auto"
          data-testid="zone-events-list"
        >
          <div
            v-for="e in recentEvents"
            :key="e.id"
            :data-testid="`zone-event-item-${e.id}`"
            class="text-sm text-[color:var(--text-muted)] flex items-start gap-2 py-1 border-b border-[color:var(--border-muted)] last:border-0"
          >
            <Badge
              :variant="getEventVariant(e.kind)"
              class="text-xs shrink-0"
            >
              {{ translateEventKind(e.kind) }}
            </Badge>
            <div class="flex-1 min-w-0">
              <div class="text-xs text-[color:var(--text-dim)]">
                {{ e.occurred_at ? new Date(e.occurred_at).toLocaleString('ru-RU') : '—' }}
              </div>
              <div class="text-sm">
                {{ e.message }}
              </div>
            </div>
          </div>
        </div>
        <div
          v-else
          class="text-sm text-[color:var(--text-dim)]"
        >
          Нет событий
        </div>
      </Card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import LoadingState from '@/Components/LoadingState.vue'
import StageProgress from '@/Components/StageProgress.vue'
import ZoneTargets from '@/Components/ZoneTargets.vue'
import { Link } from '@inertiajs/vue3'
import { translateEventKind, translateStatus, classifyEventKind } from '@/utils/i18n'
import { formatTimeShort } from '@/utils/formatTime'
import type { BadgeVariant } from '@/Components/Badge.vue'
import type { Zone, ZoneTargets as ZoneTargetsType, ZoneTelemetry } from '@/types'
import type { ZoneEvent } from '@/types/ZoneEvent'

interface OverviewLoadingState {
  irrigate: boolean
}

interface Props {
  zone: Zone
  variant: BadgeVariant
  activeGrowCycle?: any
  activeCycle?: any
  loading: OverviewLoadingState
  canOperateZone: boolean
  targets: ZoneTargetsType
  telemetry: ZoneTelemetry
  computedPhaseProgress: number | null
  computedPhaseDaysElapsed: number | null
  computedPhaseDaysTotal: number | null
  events: ZoneEvent[]
}

defineEmits<{
  (e: 'force-irrigation'): void
}>()

const props = defineProps<Props>()
const displayCycle = computed(() => props.activeGrowCycle ?? props.activeCycle ?? null)

const hasTargets = computed(() => {
  // Бэкенд присылает вложенный формат: { ph: {...}, ec: {...}, climate_request: {...} }
  // Плоских полей ph_min / ec_min в runtime нет — проверяем вложенные ключи
  if (!props.targets) return false
  const t = props.targets as Record<string, unknown>
  return Boolean(t.ph !== undefined || t.ec !== undefined || t.climate_request !== undefined)
})

const recentEvents = computed(() => {
  return Array.isArray(props.events) ? props.events.slice(0, 5) : []
})

function getEventVariant(kind: string): 'danger' | 'warning' | 'info' | 'neutral' {
  const category = classifyEventKind(kind)
  if (category === 'ALERT') return 'danger'
  if (category === 'WARNING') return 'warning'
  if (category === 'INFO') return 'info'
  return 'neutral'
}

function formatMetric(value: number | null | undefined, precision = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }
  return Number(value).toFixed(precision)
}

</script>
