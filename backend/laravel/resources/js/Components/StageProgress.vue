<template>
  <Card v-if="recipeInstance?.recipe" class="bg-[color:var(--bg-surface-strong)] border-[color:var(--border-muted)]">
    <div class="space-y-4">
      <!-- Заголовок с бейджем стадии -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-[color:var(--accent-cyan)] animate-pulse"></div>
          <div class="text-sm font-semibold">Прогресс цикла</div>
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
        <div class="flex items-center justify-center md:col-span-1">
          <GrowCycleProgressRing
            :progress="overallProgress"
            :label="'Цикл'"
            :variant="progressVariant"
            :size="100"
          />
        </div>

        <!-- Детали текущей фазы -->
        <div class="md:col-span-2 space-y-2">
          <div v-if="phaseProgress !== null" class="space-y-2">
            <div class="flex items-center justify-between text-xs">
              <span class="text-[color:var(--text-muted)]">
                Фаза: {{ currentPhaseName || `Фаза ${currentPhaseIndex + 1}` }}
                <span v-if="phaseDaysElapsed !== null && phaseDaysTotal !== null" class="text-[color:var(--text-dim)]">
                  (день {{ phaseDaysElapsed }}/{{ phaseDaysTotal }})
                </span>
              </span>
              <span class="font-semibold text-[color:var(--accent-cyan)]">{{ Math.round(phaseProgress) }}%</span>
            </div>
            
            <!-- Прогресс-бар фазы -->
            <div class="relative w-full h-2 bg-[color:var(--border-muted)] rounded-full overflow-hidden">
              <div
                class="absolute inset-0 bg-[linear-gradient(90deg,var(--accent-cyan),var(--accent-green))] rounded-full transition-all duration-500 ease-out"
                :style="{ width: `${phaseProgress}%` }"
              >
                <div class="absolute inset-0 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.12),transparent)] animate-shimmer"></div>
              </div>
            </div>

            <!-- Информация о следующей фазе -->
            <div v-if="nextPhaseInfo" class="flex items-center justify-between text-xs text-[color:var(--text-muted)]">
              <span>Следующая: {{ nextPhaseInfo.name }}</span>
              <span v-if="nextPhaseInfo.daysRemaining !== null" class="font-medium text-[color:var(--text-primary)]">
                через {{ formatDays(nextPhaseInfo.daysRemaining) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Общий прогресс по фазам -->
      <div v-if="totalPhases > 1" class="pt-2 border-t border-[color:var(--border-muted)]">
        <div class="flex items-center justify-between text-xs mb-2">
          <span class="text-[color:var(--text-muted)]">Прогресс по фазам</span>
          <span class="font-medium text-[color:var(--text-primary)]">
            {{ currentPhaseIndex + 1 }} / {{ totalPhases }} фаз
          </span>
        </div>
        <div class="flex gap-1">
          <div
            v-for="(phase, idx) in totalPhases"
            :key="idx"
            class="flex-1 h-1.5 rounded-full transition-all duration-300"
            :class="getPhaseBarClass(idx)"
            :title="`Фаза ${idx + 1}${idx === currentPhaseIndex ? ' (текущая)' : idx < currentPhaseIndex ? ' (завершена)' : ' (предстоит)'}`"
          ></div>
        </div>
      </div>

      <!-- Информация о рецепте -->
      <div class="pt-2 border-t border-[color:var(--border-muted)] text-xs text-[color:var(--text-muted)]">
        <div class="flex items-center justify-between">
          <span>Рецепт: {{ recipeInstance.recipe.name }}</span>
          <Link
            v-if="recipeInstance.recipe.id"
            :href="`/recipes/${recipeInstance.recipe.id}`"
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

// ZoneRecipeInstance is an alias used in PhaseProgress, we use RecipeInstance directly

interface Props {
  recipeInstance?: RecipeInstance | null
  phaseProgress?: number | null // Прогресс текущей фазы (0-100)
  phaseDaysElapsed?: number | null // Дней в текущей фазе
  phaseDaysTotal?: number | null // Всего дней в текущей фазе
  startedAt?: string | null // Дата начала цикла
}

const props = withDefaults(defineProps<Props>(), {
  recipeInstance: null,
  phaseProgress: null,
  phaseDaysElapsed: null,
  phaseDaysTotal: null,
  startedAt: null,
})

const currentPhaseIndex = computed(() => {
  return props.recipeInstance?.current_phase_index ?? -1
})

const currentPhaseName = computed(() => {
  if (!props.recipeInstance?.recipe?.phases) return null
  const phase = props.recipeInstance.recipe.phases.find(
    p => p.phase_index === currentPhaseIndex.value
  )
  return phase?.name || null
})

const totalPhases = computed(() => {
  return props.recipeInstance?.recipe?.phases?.length || 0
})

// Определяем текущую стадию
const currentStage = computed<GrowStage | null>(() => {
  if (currentPhaseIndex.value < 0 || !props.recipeInstance?.recipe?.phases) {
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
  if (!props.recipeInstance?.recipe?.phases) {
    return []
  }
  
  const stages: GrowStage[] = []
  const seenStages = new Set<GrowStage>()
  
  props.recipeInstance.recipe.phases.forEach((phase, index) => {
    const stage = getStageForPhase(phase.name, phase.phase_index, totalPhases.value)
    if (!seenStages.has(stage)) {
      stages.push(stage)
      seenStages.add(stage)
    }
  })
  
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
  if (!props.recipeInstance?.recipe?.phases || !props.startedAt) {
    return 0
  }
  
  return calculateCycleProgress(
    currentPhaseIndex.value,
    props.recipeInstance.recipe.phases,
    props.startedAt,
    props.phaseProgress
  )
})

const nextPhaseInfo = computed(() => {
  if (!props.recipeInstance?.recipe?.phases || currentPhaseIndex.value < 0) return null
  const nextPhase = props.recipeInstance.recipe.phases.find(
    p => p.phase_index === currentPhaseIndex.value + 1
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
