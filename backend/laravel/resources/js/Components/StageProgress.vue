<template>
  <Card
    v-if="recipeInstance?.recipe || growCycle"
    class="bg-[color:var(--bg-surface-strong)] border-[color:var(--border-muted)]"
  >
    <div class="space-y-4">
      <!-- Заголовок с бейджем стадии -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-[color:var(--accent-cyan)] animate-pulse"></div>
          <div class="text-sm font-semibold">
            Прогресс цикла
          </div>
        </div>
        <GrowCycleStageHeader :stage="currentStage" />
      </div>

      <!-- Timeline стадий -->
      <GrowCycleTimeline
        v-if="allStages.length > 0"
        :stages="allStages"
        :current-stage-index="currentStageIndex"
        :stage-dates="stageDates"
      />

      <!-- Прогресс: кольцо + детали фазы -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2 border-t border-[color:var(--border-muted)]">
        <!-- Кольцо прогресса -->
        <div class="flex flex-col items-center justify-center md:col-span-1">
          <GrowCycleProgressRing
            :progress="overallProgress"
            :label="'Цикл'"
            :variant="progressVariant"
            :size="120"
          />
          <div
            v-if="totalPhases > 1"
            class="mt-2 text-center"
          >
            <div class="text-xs text-[color:var(--text-muted)]">
              Фаза {{ currentPhaseIndex + 1 }} из {{ totalPhases }}
            </div>
            <div class="text-xs font-medium text-[color:var(--text-primary)]">
              {{ Math.round(overallProgress) }}% завершено
            </div>
          </div>
        </div>

        <!-- Детали текущей фазы -->
        <div class="md:col-span-2 space-y-3">
          <div
            v-if="phaseProgress !== null"
            class="space-y-3"
          >
            <!-- Заголовок фазы -->
            <div>
              <div class="flex items-center justify-between mb-1">
                <span class="text-sm font-semibold text-[color:var(--text-primary)]">
                  {{ currentPhaseName || `Фаза ${currentPhaseIndex + 1}` }}
                </span>
                <span class="text-lg font-bold text-[color:var(--accent-cyan)]">{{ Math.round(phaseProgress) }}%</span>
              </div>
              <div
                v-if="phaseDaysElapsed !== null && phaseDaysTotal !== null"
                class="text-xs text-[color:var(--text-muted)]"
              >
                День {{ phaseDaysElapsed }} из {{ phaseDaysTotal }}
                <span
                  v-if="phaseDaysElapsed >= 0 && phaseDaysTotal > 0 && (phaseDaysTotal - phaseDaysElapsed) > 0"
                  class="text-[color:var(--text-dim)]"
                >
                  (осталось {{ formatDays(Math.max(0, phaseDaysTotal - phaseDaysElapsed)) }})
                </span>
              </div>
            </div>
            
            <!-- Прогресс-бар фазы с улучшенной визуализацией -->
            <div class="space-y-1">
              <div class="relative w-full h-3 bg-[color:var(--border-muted)] rounded-full overflow-hidden">
                <div
                  class="absolute inset-0 bg-[linear-gradient(90deg,var(--accent-cyan),var(--accent-green))] rounded-full transition-all duration-500 ease-out"
                  :style="{ width: `${phaseProgress}%` }"
                >
                  <div class="absolute inset-0 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.15),transparent)] animate-shimmer"></div>
                </div>
                <!-- Маркер текущей позиции -->
                <div
                  v-if="phaseProgress > 0 && phaseProgress < 100"
                  class="absolute top-0 bottom-0 w-0.5 bg-[color:var(--text-primary)] opacity-50"
                  :style="{ left: `${phaseProgress}%`, transform: 'translateX(-50%)' }"
                ></div>
              </div>
              <div class="flex items-center justify-between text-xs text-[color:var(--text-dim)]">
                <span>Начало</span>
                <span>Завершение</span>
              </div>
            </div>

            <!-- Информация о следующей фазе -->
            <div
              v-if="nextPhaseInfo"
              class="pt-2 border-t border-[color:var(--border-muted)]"
            >
              <div class="flex items-center justify-between text-xs">
                <span class="text-[color:var(--text-muted)]">Следующая фаза:</span>
                <span class="font-medium text-[color:var(--text-primary)]">{{ nextPhaseInfo.name }}</span>
              </div>
              <div
                v-if="nextPhaseInfo.daysRemaining !== null"
                class="flex items-center justify-between text-xs mt-1"
              >
                <span class="text-[color:var(--text-muted)]">Осталось до перехода:</span>
                <span class="font-semibold text-[color:var(--accent-cyan)]">
                  {{ formatDays(nextPhaseInfo.daysRemaining) }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Общий прогресс по фазам -->
      <div
        v-if="totalPhases > 1"
        class="pt-2 border-t border-[color:var(--border-muted)]"
      >
        <div class="flex items-center justify-between text-xs mb-2">
          <span class="text-[color:var(--text-muted)]">Прогресс по фазам</span>
          <span class="font-medium text-[color:var(--text-primary)]">
            {{ currentPhaseIndex + 1 }} / {{ totalPhases }} фаз
          </span>
        </div>
        <div class="flex gap-1">
          <div
            v-for="idx in totalPhases"
            :key="idx"
            class="flex-1 h-1.5 rounded-full transition-all duration-300"
            :class="getPhaseBarClass(idx)"
            :title="`Фаза ${idx + 1}${idx === currentPhaseIndex ? ' (текущая)' : idx < currentPhaseIndex ? ' (завершена)' : ' (предстоит)'}`"
          ></div>
        </div>
      </div>

      <!-- Информация о рецепте -->
      <div
        v-if="recipeName"
        class="pt-2 border-t border-[color:var(--border-muted)] text-xs text-[color:var(--text-muted)]"
      >
        <div class="flex items-center justify-between">
          <span>Рецепт: {{ recipeName }}</span>
          <Link
            v-if="recipeId"
            :href="`/recipes/${recipeId}`"
            class="text-[color:var(--accent-cyan)] hover:text-[color:var(--accent-green)] transition-colors"
          >
            Открыть →
          </Link>
        </div>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import Card from './Card.vue'
import GrowCycleStageHeader from './GrowCycleStageHeader.vue'
import GrowCycleTimeline from './GrowCycleTimeline.vue'
import GrowCycleProgressRing from './GrowCycleProgressRing.vue'
import {
  getStageForPhase,
  calculateCycleProgress,
  type GrowStage,
} from '@/utils/growStages'
import type { RecipeInstance } from '@/types'

interface Props {
  recipeInstance?: RecipeInstance | null
  growCycle?: any | null // GrowCycle из новой модели
  phaseProgress?: number | null // Прогресс текущей фазы (0-100)
  phaseDaysElapsed?: number | null // Дней в текущей фазе
  phaseDaysTotal?: number | null // Всего дней в текущей фазе
  startedAt?: string | null // Дата начала цикла
}

const props = withDefaults(defineProps<Props>(), {
  recipeInstance: null,
  growCycle: null,
  phaseProgress: null,
  phaseDaysElapsed: null,
  phaseDaysTotal: null,
  startedAt: null,
})

// Используем growCycle если доступен, иначе fallback на recipeInstance
const currentPhaseIndex = computed(() => {
  if (props.growCycle?.currentPhase) {
    return props.growCycle.currentPhase.phase_index ?? -1
  }
  return props.recipeInstance?.current_phase_index ?? -1
})

const currentPhaseName = computed(() => {
  if (props.growCycle?.currentPhase) {
    return props.growCycle.currentPhase.name || null
  }
  if (!props.recipeInstance?.recipe?.phases) return null
  const phase = props.recipeInstance.recipe.phases.find(
    p => p.phase_index === currentPhaseIndex.value
  )
  return phase?.name || null
})

const totalPhases = computed(() => {
  if (props.growCycle?.phases) {
    return props.growCycle.phases.length || 0
  }
  return props.recipeInstance?.recipe?.phases?.length || 0
})

const recipeName = computed(() => {
  if (props.growCycle?.recipeRevision?.recipe) {
    return props.growCycle.recipeRevision.recipe.name
  }
  return props.recipeInstance?.recipe?.name || null
})

const recipeId = computed(() => {
  if (props.growCycle?.recipeRevision?.recipe) {
    return props.growCycle.recipeRevision.recipe.id
  }
  return props.recipeInstance?.recipe?.id || null
})

// Определяем текущую стадию
const currentStage = computed<GrowStage | null>(() => {
  if (currentPhaseIndex.value < 0) {
    return null
  }
  
  // Проверяем наличие фаз
  const hasPhases = (props.growCycle?.phases?.length ?? 0) > 0 || (props.recipeInstance?.recipe?.phases?.length ?? 0) > 0
  if (!hasPhases) {
    return null
  }
  
  return getStageForPhase(
    currentPhaseName.value,
    currentPhaseIndex.value,
    totalPhases.value
  )
})

// Определяем все стадии для timeline
const allStages = computed<GrowStage[]>(() => {
  const stages: GrowStage[] = []
  const seenStages = new Set<GrowStage>()
  
  // Используем фазы из growCycle если доступны
  if (props.growCycle?.phases) {
    props.growCycle.phases.forEach((phase: any) => {
      const stage = getStageForPhase(phase.name, phase.phase_index, totalPhases.value)
      if (!seenStages.has(stage)) {
        stages.push(stage)
        seenStages.add(stage)
      }
    })
  } else if (props.recipeInstance?.recipe?.phases) {
  props.recipeInstance.recipe.phases.forEach((phase) => {
    const stage = getStageForPhase(phase.name, phase.phase_index, totalPhases.value)
    if (!seenStages.has(stage)) {
      stages.push(stage)
      seenStages.add(stage)
    }
  })
  }
  
  return stages
})

// Индекс текущей стадии в списке всех стадий
const currentStageIndex = computed(() => {
  const stage = currentStage.value
  if (!stage) return 0
  return allStages.value.findIndex(s => s === stage)
})

// Даты для стадий (можно расширить, когда будут данные)
const stageDates = computed<(string | null)[]>(() => {
  // Пока возвращаем пустой массив, можно расширить позже
  return []
})

// Общий прогресс цикла
const overallProgress = computed(() => {
  const phases = props.growCycle?.phases || props.recipeInstance?.recipe?.phases
  const startedAt = props.startedAt || props.growCycle?.started_at
  
  if (!phases || !startedAt) {
    return 0
  }
  
  // Если phaseProgress не предоставлен, вычисляем его на основе времени
  let phaseProgress = props.phaseProgress
  if (phaseProgress === null || phaseProgress === undefined) {
    const currentPhase = phases.find(
      (p: any) => p.phase_index === currentPhaseIndex.value
    )
    if (currentPhase && startedAt) {
      const startedAtDate = new Date(startedAt)
      const now = new Date()
      
      // Вычисляем время начала текущей фазы
      let phaseStartTime = startedAtDate.getTime()
      for (let i = 0; i < currentPhaseIndex.value; i++) {
        const prevPhase = phases[i]
        if (prevPhase) {
          const durationHours = prevPhase.duration_hours || (prevPhase.duration_days ? prevPhase.duration_days * 24 : 0)
          if (durationHours) {
            phaseStartTime += durationHours * 60 * 60 * 1000
          }
        }
      }
      
      const phaseStart = new Date(phaseStartTime)
      const durationHours = currentPhase.duration_hours || (currentPhase.duration_days ? currentPhase.duration_days * 24 : 0)
      const phaseEnd = new Date(phaseStartTime + durationHours * 60 * 60 * 1000)
      
      const totalMs = phaseEnd.getTime() - phaseStart.getTime()
      if (totalMs > 0) {
        const elapsedMs = now.getTime() - phaseStart.getTime()
        if (elapsedMs > 0 && elapsedMs < totalMs) {
          phaseProgress = Math.min(100, Math.max(0, (elapsedMs / totalMs) * 100))
        } else if (elapsedMs >= totalMs) {
          phaseProgress = 100
        } else {
          phaseProgress = 0
        }
      } else {
        phaseProgress = 0
      }
    } else {
      phaseProgress = 0
    }
  }
  
  return calculateCycleProgress(
    currentPhaseIndex.value,
    phases,
    startedAt,
    phaseProgress
  )
})

const nextPhaseInfo = computed(() => {
  const phases = props.growCycle?.phases || props.recipeInstance?.recipe?.phases
  if (!phases || currentPhaseIndex.value < 0) return null
  
  const nextPhase = phases.find(
    (p: any) => p.phase_index === currentPhaseIndex.value + 1
  )
  if (!nextPhase) return null

  const daysRemaining = props.phaseDaysTotal && props.phaseDaysElapsed !== null
    ? Math.max(0, props.phaseDaysTotal - props.phaseDaysElapsed)
    : null

  return {
    name: nextPhase.name || `Фаза ${currentPhaseIndex.value + 2}`,
    daysRemaining,
  }
})

const progressVariant = computed<'primary' | 'success' | 'warning' | 'danger'>(() => {
  const progress = overallProgress.value
  if (progress >= 90) return 'success'
  if (progress >= 50) return 'primary'
  if (progress >= 25) return 'warning'
  return 'primary'
})

function getPhaseBarClass(phaseIndex: number): string {
  if (phaseIndex < currentPhaseIndex.value) {
    return 'bg-[color:var(--accent-green)]'
  } else if (phaseIndex === currentPhaseIndex.value) {
    return 'bg-[color:var(--accent-cyan)]'
  } else {
    return 'bg-[color:var(--border-muted)]'
  }
}

function formatDays(days: number): string {
  if (days === 0) return 'сегодня'
  if (days === 1) return '1 день'
  if (days < 5) return `${days} дня`
  return `${days} дней`
}
</script>

<style scoped>
@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

.animate-shimmer {
  animation: shimmer 2s infinite;
}
</style>
