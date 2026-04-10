<template>
  <div
    class="text-xs text-[color:var(--text-dim)] p-3 rounded border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] hover:border-[color:var(--border-strong)] transition-colors"
  >
    <!-- Заголовок: тип + обязательность -->
    <div class="font-semibold text-sm mb-1 text-[color:var(--text-primary)] flex items-center justify-between gap-2">
      <span>{{ translateCycleType(cycle.type) }}</span>
      <span
        class="px-1.5 py-0.5 rounded-full text-[10px]"
        :class="cycle.required
          ? 'bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)]'
          : 'bg-[color:var(--bg-elevated)] text-[color:var(--text-dim)]'"
      >
        {{ cycle.required ? 'Обязательно' : 'Опционально' }}
      </span>
    </div>

    <!-- Таргеты рецепта -->
    <CycleTargetDisplay
      :type="cycle.type"
      :targets="cycle.recipeTargets"
    />

    <!-- Стратегия и интервал -->
    <div class="text-xs mb-1">
      Стратегия: {{ translateStrategy(cycle.strategy ?? 'periodic') }}
    </div>
    <div class="text-xs mb-2">
      Интервал: {{ cycle.interval != null ? formatInterval(cycle.interval) : 'Не настроено' }}
    </div>

    <!-- Последний запуск -->
    <div class="mb-2">
      <div class="text-xs text-[color:var(--text-dim)] mb-1">
        Последний запуск:
      </div>
      <div class="flex items-center gap-2">
        <div
          class="w-2 h-2 rounded-full"
          :class="cycle.last_run ? 'bg-[color:var(--accent-green)]' : 'bg-[color:var(--text-dim)]'"
        ></div>
        <span class="text-xs text-[color:var(--text-muted)]">{{ formatTimeShort(cycle.last_run) }}</span>
      </div>
    </div>

    <!-- Следующий запуск -->
    <div class="mb-2">
      <div class="text-xs text-[color:var(--text-dim)] mb-1">
        Следующий запуск:
      </div>
      <template v-if="cycle.next_run">
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-[color:var(--accent-amber)] animate-pulse"></div>
          <span class="text-xs text-[color:var(--text-muted)]">{{ formatTimeShort(cycle.next_run) }}</span>
        </div>
        <template v-if="cycle.last_run && cycle.interval">
          <div class="w-full h-1.5 bg-[color:var(--border-muted)] rounded-full overflow-hidden mt-1">
            <div
              class="h-full bg-[color:var(--accent-amber)] transition-all duration-300"
              :style="{ width: `${progressPercent}%` }"
            ></div>
          </div>
          <div class="text-xs text-[color:var(--text-dim)] mt-0.5">
            {{ timeUntilLabel }}
          </div>
        </template>
      </template>
      <div
        v-else
        class="text-xs text-[color:var(--text-dim)]"
      >
        Не запланирован
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import CycleTargetDisplay from './CycleTargetDisplay.vue'
import { translateCycleType, translateStrategy } from '@/utils/i18n'
import { formatInterval, formatTimeShort } from '@/utils/formatTime'
import { useCycleTimer } from '@/composables/useCycleTimer'
import type { SubsystemCycle } from '@/types/Cycle'

const props = defineProps<{ cycle: SubsystemCycle }>()

const { now } = useCycleTimer()

const progressPercent = computed((): number => {
  const { last_run, next_run, interval } = props.cycle
  if (!last_run || interval == null || !next_run) return 0

  const lastMs = new Date(last_run).getTime()
  const nextMs = new Date(next_run).getTime()
  if (Number.isNaN(lastMs) || Number.isNaN(nextMs)) return 0

  const total = nextMs - lastMs
  if (total <= 0) return 0

  return Math.min(100, Math.max(0, ((now.value - lastMs) / total) * 100))
})

const timeUntilLabel = computed((): string => {
  const next_run = props.cycle.next_run
  if (!next_run) return ''

  const diff = new Date(next_run).getTime() - now.value
  if (diff <= 0) return 'Просрочено'

  const minutes = Math.floor(diff / 60_000)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (days > 0) return `Через ${days} дн.`
  if (hours > 0) return `Через ${hours} ч.`
  if (minutes > 0) return `Через ${minutes} мин.`
  return 'Скоро'
})
</script>
