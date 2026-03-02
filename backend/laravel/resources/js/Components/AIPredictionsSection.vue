<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h3 class="text-lg font-semibold text-[color:var(--text-primary)]">
          AI Прогнозы
        </h3>
        <p class="text-sm text-[color:var(--text-muted)] mt-1">
          Прогнозирование параметров на основе текущих данных и исторических паттернов
        </p>
      </div>
      <Button 
        v-if="!expanded" 
        size="sm" 
        variant="outline" 
        @click="expanded = true"
      >
        Показать прогнозы
      </Button>
      <Button 
        v-else 
        size="sm" 
        variant="outline" 
        @click="expanded = false"
      >
        Скрыть
      </Button>
    </div>

    <div v-if="expanded">
      <div
        v-if="metrics.length === 0"
        class="py-8 text-center border border-[color:var(--border-muted)] rounded-lg bg-[color:var(--bg-elevated)]"
      >
        <div class="text-4xl mb-3">
          🤖
        </div>
        <div class="text-sm font-medium text-[color:var(--text-primary)] mb-2">
          Прогнозы недоступны
        </div>
        <div class="text-xs text-[color:var(--text-muted)] max-w-md mx-auto">
          Для отображения AI прогнозов необходимо настроить целевые значения параметров зоны в текущей фазе рецепта.
        </div>
      </div>
      <div
        v-else
        class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"
      >
        <AIPredictionCard
          v-for="metric in metrics"
          :key="metric.type"
          :zone-id="zoneId"
          :metric-type="metric.type"
          :horizon-minutes="horizonMinutes"
          :auto-refresh="autoRefresh"
          :refresh-interval="refreshInterval"
          :target-range="metric.targetRange"
        />
      </div>
    </div>
    
    <div
      v-else
      class="py-6 text-center border border-[color:var(--border-muted)] rounded-lg bg-[color:var(--bg-elevated)]"
    >
      <div class="text-3xl mb-2">
        🔮
      </div>
      <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
        AI Прогнозы параметров
      </div>
      <div class="text-xs text-[color:var(--text-muted)] mb-3">
        Нажмите кнопку выше, чтобы увидеть прогнозы pH, EC, температуры и влажности
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import AIPredictionCard from './AIPredictionCard.vue'
import Button from './Button.vue'

interface Props {
  zoneId: number
  targets?: Record<string, { min?: number; max?: number }>
  horizonMinutes?: number
  autoRefresh?: boolean
  refreshInterval?: number
  defaultExpanded?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  horizonMinutes: 60,
  autoRefresh: true,
  refreshInterval: 300000, // 5 минут
  defaultExpanded: true, // По умолчанию развернуто для лучшего UX
})

const expanded = ref(props.defaultExpanded)

const metrics = computed(() => {
  const targets = props.targets || {}

  // Включаем только метрики с настроенными целевыми диапазонами.
  // Без фильтрации массив всегда содержит 4 элемента и v-if="metrics.length === 0"
  // (блок «Прогнозы недоступны») никогда не срабатывает.
  return [
    {
      type: 'PH' as const,
      targetRange: targets.ph ? {
        min: targets.ph.min || 0,
        max: targets.ph.max || 14,
      } : undefined,
    },
    {
      type: 'EC' as const,
      targetRange: targets.ec ? {
        min: targets.ec.min || 0,
        max: targets.ec.max || 5,
      } : undefined,
    },
    {
      type: 'TEMPERATURE' as const,
      targetRange: targets.temp_air ? {
        min: targets.temp_air.min || 0,
        max: targets.temp_air.max || 50,
      } : undefined,
    },
    {
      type: 'HUMIDITY' as const,
      targetRange: targets.humidity_air ? {
        min: targets.humidity_air.min || 0,
        max: targets.humidity_air.max || 100,
      } : undefined,
    },
  ].filter((m) => m.targetRange !== undefined)
})
</script>
