<template>
  <Card v-if="recipeInstance?.recipe" class="bg-gradient-to-br from-neutral-900 to-neutral-925 border-neutral-800">
    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-sky-500 animate-pulse"></div>
          <div class="text-sm font-semibold">Прогресс рецепта</div>
        </div>
        <Badge :variant="progressVariant" class="text-xs">
          {{ currentPhaseName || `Фаза ${currentPhaseIndex + 1}` }}
        </Badge>
      </div>

      <!-- Прогресс текущей фазы -->
      <div v-if="phaseProgress !== null" class="space-y-2">
        <div class="flex items-center justify-between text-xs">
          <span class="text-neutral-400">
            {{ currentPhaseName || `Фаза ${currentPhaseIndex + 1}` }}
            <span v-if="phaseDaysElapsed !== null && phaseDaysTotal !== null">
              (день {{ phaseDaysElapsed }}/{{ phaseDaysTotal }})
            </span>
          </span>
          <span class="font-semibold text-sky-400">{{ Math.round(phaseProgress) }}%</span>
        </div>
        
        <!-- Прогресс-бар -->
        <div class="relative w-full h-3 bg-neutral-800 rounded-full overflow-hidden">
          <div
            class="absolute inset-0 bg-gradient-to-r from-sky-500 to-sky-400 rounded-full transition-all duration-500 ease-out"
            :style="{ width: `${phaseProgress}%` }"
          >
            <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer"></div>
          </div>
          <!-- Индикатор цели -->
          <div
            v-if="phaseProgress < 100"
            class="absolute top-0 bottom-0 w-0.5 bg-sky-300/50"
            :style="{ left: `${phaseProgress}%` }"
          ></div>
        </div>

        <!-- Информация о следующей фазе -->
        <div v-if="nextPhaseInfo" class="flex items-center justify-between text-xs text-neutral-400">
          <span>Следующая фаза: {{ nextPhaseInfo.name }}</span>
          <span v-if="nextPhaseInfo.daysRemaining !== null" class="font-medium text-neutral-300">
            через {{ formatDays(nextPhaseInfo.daysRemaining) }}
          </span>
        </div>
      </div>

      <!-- Общий прогресс рецепта (все фазы) -->
      <div v-if="totalPhases > 1" class="pt-2 border-t border-neutral-800">
        <div class="flex items-center justify-between text-xs mb-1">
          <span class="text-neutral-400">Общий прогресс рецепта</span>
          <span class="font-medium text-neutral-300">
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
      <div class="pt-2 border-t border-neutral-800 text-xs text-neutral-400">
        <div class="flex items-center justify-between">
          <span>Рецепт: {{ recipeInstance.recipe.name }}</span>
          <Link
            v-if="recipeInstance.recipe.id"
            :href="`/recipes/${recipeInstance.recipe.id}`"
            class="text-sky-400 hover:text-sky-300 transition-colors"
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
import Badge from './Badge.vue'
import type { ZoneRecipeInstance } from '@/types'

interface Props {
  recipeInstance?: ZoneRecipeInstance | null
  phaseProgress?: number | null // Прогресс текущей фазы (0-100)
  phaseDaysElapsed?: number | null // Дней в текущей фазе
  phaseDaysTotal?: number | null // Всего дней в текущей фазе
}

const props = withDefaults(defineProps<Props>(), {
  recipeInstance: null,
  phaseProgress: null,
  phaseDaysElapsed: null,
  phaseDaysTotal: null,
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

const nextPhaseInfo = computed(() => {
  if (!props.recipeInstance?.recipe?.phases || currentPhaseIndex.value < 0) return null
  const nextPhase = props.recipeInstance.recipe.phases.find(
    p => p.phase_index === currentPhaseIndex.value + 1
  )
  if (!nextPhase) return null

  // Вычисляем оставшиеся дни в текущей фазе
  const daysRemaining = props.phaseDaysTotal && props.phaseDaysElapsed !== null
    ? Math.max(0, props.phaseDaysTotal - props.phaseDaysElapsed)
    : null

  return {
    name: nextPhase.name || `Фаза ${currentPhaseIndex.value + 2}`,
    daysRemaining,
  }
})

const progressVariant = computed(() => {
  if (props.phaseProgress === null) return 'secondary'
  if (props.phaseProgress >= 90) return 'success'
  if (props.phaseProgress >= 50) return 'info'
  return 'warning'
})

function getPhaseBarClass(phaseIndex: number): string {
  if (phaseIndex < currentPhaseIndex.value) {
    return 'bg-emerald-500' // Завершенные фазы
  } else if (phaseIndex === currentPhaseIndex.value) {
    return 'bg-sky-500' // Текущая фаза
  } else {
    return 'bg-neutral-700' // Предстоящие фазы
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

