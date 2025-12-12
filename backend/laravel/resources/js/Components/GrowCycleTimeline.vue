<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between text-sm">
      <span class="font-semibold text-neutral-200">Стадии цикла</span>
      <span v-if="totalStages > 0" class="text-xs text-neutral-400">
        {{ currentStageIndex + 1 }} / {{ totalStages }}
      </span>
    </div>
    
    <div class="relative">
      <!-- Линия прогресса -->
      <div class="absolute top-6 left-0 right-0 h-0.5 bg-neutral-800"></div>
      <div
        class="absolute top-6 left-0 h-0.5 bg-gradient-to-r from-sky-500 to-emerald-500 transition-all duration-500"
        :style="{ width: `${progressLineWidth}%` }"
      ></div>
      
      <!-- Стадии -->
      <div class="relative flex justify-between">
        <div
          v-for="(stage, index) in visibleStages"
          :key="stage.id"
          class="flex flex-col items-center flex-1"
          :class="{ 'min-w-0': true }"
        >
          <!-- Иконка стадии -->
          <div
            class="relative z-10 w-12 h-12 rounded-full flex items-center justify-center text-lg transition-all duration-300"
            :class="getStageCircleClass(stage.id, index)"
            :style="getStageCircleStyle(stage.id, index)"
          >
            <span>{{ stage.icon }}</span>
          </div>
          
          <!-- Название стадии -->
          <div class="mt-2 text-center">
            <div
              class="text-xs font-medium truncate max-w-full"
              :class="getStageLabelClass(stage.id, index)"
            >
              {{ stage.label }}
            </div>
            <!-- Дата (если есть) -->
            <div
              v-if="stageDates[index]"
              class="text-[10px] text-neutral-500 mt-0.5"
            >
              {{ formatDate(stageDates[index]) }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { GROW_STAGES, getStageInfo, type GrowStage } from '@/utils/growStages'

interface Props {
  stages: GrowStage[]
  currentStageIndex: number
  stageDates?: (string | null)[]
  showAll?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  stageDates: () => [],
  showAll: false,
})

const totalStages = computed(() => props.stages.length)

const visibleStages = computed(() => {
  // Всегда показываем все стадии для timeline
  return props.stages.map(stageId => getStageInfo(stageId)).filter(Boolean) as Array<NonNullable<ReturnType<typeof getStageInfo>>>
})

const progressLineWidth = computed(() => {
  if (totalStages.value === 0) return 0
  if (props.currentStageIndex >= totalStages.value - 1) return 100
  
  const baseProgress = (props.currentStageIndex / (totalStages.value - 1)) * 100
  // Можно добавить дополнительный прогресс в пределах текущей стадии
  return baseProgress
})

function getStageCircleClass(stageId: GrowStage, index: number): string {
  const currentIndex = props.currentStageIndex
  const isCurrent = index === currentIndex
  const isPast = index < currentIndex
  const isFuture = index > currentIndex
  
  if (isCurrent) {
    return 'bg-gradient-to-br from-sky-500 to-emerald-500 scale-110 shadow-lg shadow-sky-500/50'
  }
  if (isPast) {
    return 'bg-emerald-500'
  }
  return 'bg-neutral-700 border-2 border-neutral-600'
}

function getStageCircleStyle(stageId: GrowStage, index: number): Record<string, string> {
  const stageInfo = getStageInfo(stageId)
  if (!stageInfo) return {}
  
  const currentIndex = props.currentStageIndex
  const isCurrent = index === currentIndex
  const isPast = index < currentIndex
  
  if (isCurrent || isPast) {
    return {
      borderColor: `${stageInfo.color}40`,
    }
  }
  
  return {}
}

function getStageLabelClass(stageId: GrowStage, index: number): string {
  const currentIndex = props.currentStageIndex
  const isCurrent = index === currentIndex
  const isPast = index < currentIndex
  
  if (isCurrent) {
    return 'text-sky-400 font-semibold'
  }
  if (isPast) {
    return 'text-emerald-400'
  }
  return 'text-neutral-400'
}

function formatDate(date: string | null | undefined): string {
  if (!date) return ''
  
  try {
    const d = new Date(date)
    if (isNaN(d.getTime())) return ''
    
    return d.toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
    })
  } catch {
    return ''
  }
}
</script>
