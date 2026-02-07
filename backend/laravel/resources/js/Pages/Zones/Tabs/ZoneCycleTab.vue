<template>
  <div class="space-y-4">
    <Card>
      <div class="flex items-center justify-between mb-2">
        <div class="text-sm font-semibold">
          Рецепт
        </div>
        <template v-if="canManageRecipe">
          <Button
            size="sm"
            :variant="activeGrowCycle ? 'secondary' : 'primary'"
            data-testid="recipe-attach-btn"
            @click="activeGrowCycle ? $emit('change-recipe') : $emit('run-cycle')"
          >
            <span
              v-if="!activeGrowCycle"
              data-testid="zone-start-btn"
            >
              Запустить цикл
            </span>
            <span v-else>
              Сменить ревизию
            </span>
          </Button>
        </template>
      </div>
      <div
        v-if="activeGrowCycle?.recipeRevision?.recipe"
        class="text-sm text-[color:var(--text-muted)]"
      >
        <div class="font-semibold">
          {{ activeGrowCycle.recipeRevision.recipe.name }}
        </div>
        <div class="text-xs text-[color:var(--text-dim)]">
          Фаза {{ (activeGrowCycle?.currentPhase?.phase_index ?? 0) + 1 }}
          из {{ activeGrowCycle?.phases?.length || 0 }}
          <span v-if="activeGrowCycle?.currentPhase?.name">
            — {{ activeGrowCycle.currentPhase.name }}
          </span>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-2">
          <Badge
            :variant="cycleStatusVariant"
            class="text-[10px] px-2 py-0.5"
          >
            {{ cycleStatusLabel }}
          </Badge>
          <span
            v-if="phaseTimeLeftLabel"
            class="text-[11px] text-[color:var(--text-dim)]"
          >
            {{ phaseTimeLeftLabel }}
          </span>
        </div>
      </div>
      <div
        v-else
        class="space-y-2"
      >
        <div class="text-sm text-[color:var(--text-dim)]">
          Цикл выращивания не запущен
        </div>
        <template v-if="canManageRecipe">
          <div class="text-xs text-[color:var(--text-dim)]">
            Запустите цикл выращивания, чтобы применить рецепт и отслеживать фазы
          </div>
        </template>
      </div>
    </Card>

    <Card>
      <div class="text-sm font-semibold mb-3">
        Циклы
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
        <div
          v-for="cycle in cyclesList"
          :key="cycle.type"
          class="text-xs text-[color:var(--text-dim)] p-3 rounded border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] hover:border-[color:var(--border-strong)] transition-colors"
        >
          <div class="font-semibold text-sm mb-1 text-[color:var(--text-primary)] flex items-center justify-between gap-2">
            <span>{{ translateCycleType(cycle.type) }}</span>
            <span
              class="px-1.5 py-0.5 rounded-full text-[10px]"
              :class="cycle.required ? 'bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)]' : 'bg-[color:var(--bg-elevated)] text-[color:var(--text-dim)]'"
            >
              {{ cycle.required ? 'Обязательно' : 'Опционально' }}
            </span>
          </div>

          <div class="text-[11px] mb-2 space-y-0.5 text-[color:var(--text-muted)]">
            <div v-if="cycle.recipeTargets && cycle.type === 'PH_CONTROL' && typeof cycle.recipeTargets.min === 'number' && typeof cycle.recipeTargets.max === 'number'">
              pH: {{ cycle.recipeTargets.min }}–{{ cycle.recipeTargets.max }}
            </div>
            <div v-else-if="cycle.recipeTargets && cycle.type === 'EC_CONTROL' && typeof cycle.recipeTargets.min === 'number' && typeof cycle.recipeTargets.max === 'number'">
              EC: {{ cycle.recipeTargets.min }}–{{ cycle.recipeTargets.max }}
            </div>
            <div v-else-if="cycle.recipeTargets && cycle.type === 'CLIMATE' && typeof cycle.recipeTargets.temperature === 'number' && typeof cycle.recipeTargets.humidity === 'number'">
              Климат: t={{ cycle.recipeTargets.temperature }}°C, RH={{ cycle.recipeTargets.humidity }}%
            </div>
            <div v-else-if="cycle.recipeTargets && cycle.type === 'LIGHTING' && typeof cycle.recipeTargets.hours_on === 'number'">
              Свет: {{ cycle.recipeTargets.hours_on }}ч / пауза {{ typeof cycle.recipeTargets.hours_off === 'number' ? cycle.recipeTargets.hours_off : (24 - cycle.recipeTargets.hours_on) }}ч
            </div>
            <div v-else-if="cycle.recipeTargets && cycle.type === 'IRRIGATION' && typeof cycle.recipeTargets.interval_minutes === 'number' && typeof cycle.recipeTargets.duration_seconds === 'number'">
              Полив: каждые {{ cycle.recipeTargets.interval_minutes }} мин, {{ cycle.recipeTargets.duration_seconds }} с
            </div>
            <div
              v-else
              class="text-[color:var(--text-dim)]"
            >
              Таргеты для этой фазы не заданы
            </div>
          </div>

          <div class="text-xs mb-1">
            Стратегия: {{ translateStrategy(cycle.strategy || 'periodic') }}
          </div>
          <div class="text-xs mb-2">
            Интервал: {{ cycle.interval ? formatInterval(cycle.interval) : 'Не настроено' }}
          </div>

          <div class="mb-2">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">
              Последний запуск:
            </div>
            <div class="flex items-center gap-2">
              <div
                v-if="cycle.last_run"
                class="w-2 h-2 rounded-full bg-[color:var(--accent-green)]"
              ></div>
              <div
                v-else
                class="w-2 h-2 rounded-full bg-[color:var(--text-dim)]"
              ></div>
              <span class="text-xs text-[color:var(--text-muted)]">{{ formatTimeShort(cycle.last_run) }}</span>
            </div>
          </div>

          <div class="mb-2">
            <div class="text-xs text-[color:var(--text-dim)] mb-1">
              Следующий запуск:
            </div>
            <div
              v-if="cycle.next_run"
              class="space-y-1"
            >
              <div class="flex items-center gap-2">
                <div class="w-2 h-2 rounded-full bg-[color:var(--accent-amber)] animate-pulse"></div>
                <span class="text-xs text-[color:var(--text-muted)]">{{ formatTimeShort(cycle.next_run) }}</span>
              </div>
              <div
                v-if="cycle.last_run && cycle.interval"
                class="w-full h-1.5 bg-[color:var(--border-muted)] rounded-full overflow-hidden"
              >
                <div
                  class="h-full bg-[color:var(--accent-amber)] transition-all duration-300"
                  :style="{ width: `${getProgressToNextRun(cycle)}%` }"
                ></div>
              </div>
              <div
                v-if="cycle.last_run && cycle.interval"
                class="text-xs text-[color:var(--text-dim)]"
              >
                {{ getTimeUntilNextRun(cycle) }}
              </div>
            </div>
            <div
              v-else
              class="text-xs text-[color:var(--text-dim)]"
            >
              Не запланирован
            </div>
          </div>
        </div>
      </div>
    </Card>

    <CycleControlPanel
      v-if="activeGrowCycle"
      :cycle="activeGrowCycle"
      :grow-cycle="activeGrowCycle"
      :phase-progress="computedPhaseProgress"
      :phase-days-elapsed="computedPhaseDaysElapsed"
      :phase-days-total="computedPhaseDaysTotal"
      :can-manage="canManageCycle"
      :loading="loading.cyclePause || loading.cycleResume || loading.cycleHarvest || loading.cycleAbort"
      :loading-next-phase="loading.nextPhase"
      @pause="$emit('pause')"
      @resume="$emit('resume')"
      @harvest="$emit('harvest')"
      @abort="$emit('abort')"
      @next-phase="$emit('next-phase')"
    />
  </div>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import CycleControlPanel from '@/Components/GrowCycle/CycleControlPanel.vue'
import { translateCycleType, translateStrategy } from '@/utils/i18n'
import { formatInterval, formatTimeShort } from '@/utils/formatTime'
import type { BadgeVariant } from '@/Components/Badge.vue'
import type { Cycle } from '@/types'

interface LoadingStateProps {
  cyclePause: boolean
  cycleResume: boolean
  cycleHarvest: boolean
  cycleAbort: boolean
  nextPhase: boolean
}

interface Props {
  activeGrowCycle?: any
  activeCycle?: any
  currentPhase?: any
  cyclesList: Array<Cycle & { required?: boolean; recipeTargets?: any; last_run?: string | null; next_run?: string | null; interval?: number | null }>
  computedPhaseProgress: number | null
  computedPhaseDaysElapsed: number | null
  computedPhaseDaysTotal: number | null
  cycleStatusLabel: string
  cycleStatusVariant: BadgeVariant
  phaseTimeLeftLabel: string
  canManageRecipe: boolean
  canManageCycle: boolean
  loading: LoadingStateProps
}

defineProps<Props>()

defineEmits<{
  (e: 'run-cycle'): void
  (e: 'change-recipe'): void
  (e: 'pause'): void
  (e: 'resume'): void
  (e: 'harvest'): void
  (e: 'abort'): void
  (e: 'next-phase'): void
}>()

function getProgressToNextRun(cycle: Cycle & { last_run?: string | null; next_run?: string | null; interval?: number | null }): number {
  if (!cycle.last_run || !cycle.interval || !cycle.next_run) return 0
  const lastRun = new Date(cycle.last_run).getTime()
  const nextRun = new Date(cycle.next_run).getTime()
  if (Number.isNaN(lastRun) || Number.isNaN(nextRun)) return 0

  const total = nextRun - lastRun
  if (total <= 0) return 0

  const elapsed = Date.now() - lastRun
  return Math.min(100, Math.max(0, (elapsed / total) * 100))
}

function getTimeUntilNextRun(cycle: Cycle & { next_run?: string | null }): string {
  if (!cycle.next_run) return ''

  const now = Date.now()
  const nextRun = new Date(cycle.next_run).getTime()
  const diff = nextRun - now

  if (diff <= 0) return 'Просрочено'

  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (days > 0) return `Через ${days} дн.`
  if (hours > 0) return `Через ${hours} ч.`
  if (minutes > 0) return `Через ${minutes} мин.`
  return 'Скоро'
}
</script>
