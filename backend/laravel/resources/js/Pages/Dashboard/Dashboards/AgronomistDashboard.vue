<template>
  <div class="space-y-6">
    <div class="glass-panel border border-[color:var(--border-strong)] rounded-2xl p-5 shadow-[var(--shadow-card)]">
      <div class="flex flex-col gap-4">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
              мониторинг агронома
            </p>
            <h1 class="text-2xl font-semibold tracking-tight mt-1">
              Циклы выращивания и здоровье зон
            </h1>
            <p class="text-sm text-[color:var(--text-muted)] mt-1">
              Фокус на фазах, аномалиях и активных рецептах.
            </p>
          </div>
          <div class="flex flex-wrap gap-2 justify-end">
            <Link
              href="/recipes/create"
              class="flex-1 sm:flex-none min-w-[140px]"
            >
              <Button
                size="sm"
                variant="primary"
                class="w-full sm:w-auto"
              >
                Создать рецепт
              </Button>
            </Link>
            <Link
              href="/analytics"
              class="flex-1 sm:flex-none min-w-[120px]"
            >
              <Button
                size="sm"
                variant="secondary"
                class="w-full sm:w-auto"
              >
                Аналитика
              </Button>
            </Link>
          </div>
        </div>
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div class="glass-panel border border-[color:var(--badge-success-border)] rounded-xl p-3 shadow-[inset_0_0_0_1px_var(--badge-success-border)]">
            <div class="text-xs text-[color:var(--text-dim)] uppercase tracking-[0.15em] mb-1">
              Активные зоны
            </div>
            <div class="flex items-end gap-2">
              <div class="text-3xl font-semibold text-[color:var(--accent-green)]">
                {{ activeZonesCount }}
              </div>
              <div class="text-sm text-[color:var(--text-dim)]">
                из {{ totalZonesCount }}
              </div>
            </div>
          </div>
          <div class="glass-panel border border-[color:var(--badge-warning-border)] rounded-xl p-3">
            <div class="text-xs text-[color:var(--text-dim)] uppercase tracking-[0.15em] mb-1">
              Предупреждения
            </div>
            <div class="flex items-center gap-2">
              <div class="text-3xl font-semibold text-[color:var(--accent-amber)]">
                {{ warningZonesCount }}
              </div>
              <Badge
                variant="warning"
                size="sm"
              >
                warning
              </Badge>
            </div>
          </div>
          <div class="glass-panel border border-[color:var(--badge-danger-border)] rounded-xl p-3">
            <div class="text-xs text-[color:var(--text-dim)] uppercase tracking-[0.15em] mb-1">
              Критические
            </div>
            <div class="flex items-center gap-2">
              <div class="text-3xl font-semibold text-[color:var(--accent-red)]">
                {{ alarmZonesCount }}
              </div>
              <Badge
                variant="danger"
                size="sm"
              >
                alarm
              </Badge>
            </div>
          </div>
          <div class="glass-panel border border-[color:var(--badge-info-border)] rounded-xl p-3">
            <div class="text-xs text-[color:var(--text-dim)] uppercase tracking-[0.15em] mb-1">
              Активных рецептов
            </div>
            <div class="flex items-center gap-2">
              <div class="text-3xl font-semibold text-[color:var(--accent-cyan)]">
                {{ activeRecipesCount }}
              </div>
              <Badge
                variant="info"
                size="sm"
              >
                recipes
              </Badge>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Обзор зон по культурам -->
    <div
      v-if="zonesByCrop.length > 0"
      class="space-y-4"
    >
      <h2 class="text-md font-semibold">
        Зоны по культурам
      </h2>
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <Card
          v-for="crop in zonesByCrop"
          :key="crop.cropName"
          class="hover:border-[color:var(--border-strong)] transition-colors"
        >
          <div class="flex items-start justify-between mb-3">
            <div>
              <div class="text-sm font-semibold">
                {{ crop.cropName }}
              </div>
              <div class="text-xs text-[color:var(--text-muted)] mt-1">
                {{ crop.zones.length }} {{ crop.zones.length === 1 ? 'зона' : 'зон' }}
              </div>
            </div>
            <Badge :variant="crop.overallStatus === 'OK' ? 'success' : crop.overallStatus === 'WARNING' ? 'warning' : 'danger'">
              {{ crop.overallStatus }}
            </Badge>
          </div>
          
          <!-- Прогресс фазы -->
          <div
            v-if="crop.averageProgress !== null"
            class="mb-3"
          >
            <div class="flex items-center justify-between text-xs mb-1">
              <span class="text-[color:var(--text-muted)]">Общий прогресс</span>
              <span class="font-medium">{{ Math.round(crop.averageProgress) }}%</span>
            </div>
            <div class="w-full bg-[color:var(--border-muted)] rounded-full h-2">
              <div
                class="bg-[color:var(--accent-green)] h-2 rounded-full transition-all duration-300"
                :style="{ width: `${crop.averageProgress}%` }"
              ></div>
            </div>
          </div>

          <!-- Средние метрики -->
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div v-if="crop.avgPh !== null">
              <span class="text-[color:var(--text-muted)]">pH:</span>
              <span class="ml-1 font-medium">{{ crop.avgPh.toFixed(2) }}</span>
            </div>
            <div v-if="crop.avgEc !== null">
              <span class="text-[color:var(--text-muted)]">EC:</span>
              <span class="ml-1 font-medium">{{ crop.avgEc.toFixed(2) }}</span>
            </div>
          </div>

          <!-- Фаза -->
          <div
            v-if="crop.currentPhase"
            class="mt-3 text-xs text-[color:var(--text-muted)]"
          >
            Фаза: {{ crop.currentPhase }} (день {{ crop.averageDay }}/{{ crop.totalDays }})
          </div>
        </Card>
      </div>
    </div>

    <!-- Ключевые метрики всех зон -->
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
      <MetricCard
        label="Средний pH"
        :value="averagePh"
        color="var(--accent-cyan)"
        :status="getPhStatus(averagePh)"
        :trend="phTrend"
        trend-label="за 24ч"
        :target="phTarget"
        :decimals="2"
      >
        <template #icon>
          <svg
            class="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"
            />
          </svg>
        </template>
      </MetricCard>
      
      <MetricCard
        label="Средний EC"
        :value="averageEc"
        unit="мСм/см"
        color="var(--accent-green)"
        :status="getEcStatus(averageEc)"
        :trend="ecTrend"
        trend-label="за 24ч"
        :target="ecTarget"
        :decimals="2"
      >
        <template #icon>
          <svg
            class="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M13 10V3L4 14h7v7l9-11h-7z"
            />
          </svg>
        </template>
      </MetricCard>
      
      <MetricCard
        label="Активных зон"
        :value="activeZonesCount"
        color="var(--accent-green)"
        status="success"
        :subtitle="`из ${totalZonesCount}`"
        data-testid="dashboard-zones-count"
      >
        <template #icon>
          <svg
            class="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"
            />
          </svg>
        </template>
      </MetricCard>
      
      <MetricCard
        label="Активных рецептов"
        :value="activeRecipesCount"
        color="var(--accent-lime)"
        status="info"
      >
        <template #icon>
          <svg
            class="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
            />
          </svg>
        </template>
      </MetricCard>
    </div>

    <!-- Активные рецепты -->
    <div
      v-if="activeRecipes.length > 0"
      class="space-y-4"
    >
      <h2 class="text-md font-semibold">
        Активные рецепты
      </h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card
          v-for="recipe in activeRecipes"
          :key="recipe.id"
          class="hover:border-[color:var(--border-strong)] transition-colors"
        >
          <div class="flex items-start justify-between mb-3">
            <div>
              <div class="text-sm font-semibold">
                {{ recipe.name }}
              </div>
              <div class="text-xs text-[color:var(--text-muted)] mt-1">
                Применен в {{ recipe.zonesCount }} {{ recipe.zonesCount === 1 ? 'зоне' : 'зонах' }}
              </div>
            </div>
            <Link :href="`/recipes/${recipe.id}`">
              <Button
                size="sm"
                variant="secondary"
              >
                Открыть
              </Button>
            </Link>
          </div>
          
          <!-- Прогресс по фазам -->
          <div
            v-if="recipe.currentPhase"
            class="space-y-2"
          >
            <div class="flex items-center justify-between text-xs">
              <span class="text-[color:var(--text-muted)]">Текущая фаза</span>
              <span class="font-medium">{{ recipe.currentPhase }}</span>
            </div>
            <div class="w-full bg-[color:var(--border-muted)] rounded-full h-2">
              <div
                class="bg-[color:var(--accent-cyan)] h-2 rounded-full transition-all duration-300"
                :style="{ width: `${recipe.phaseProgress}%` }"
              ></div>
            </div>
            <div
              v-if="recipe.nextPhaseTransition"
              class="text-xs text-[color:var(--text-muted)]"
            >
              Следующая фаза через: {{ formatTimeUntil(recipe.nextPhaseTransition) }}
            </div>
          </div>
        </Card>
      </div>
    </div>

    <!-- Проблемные зоны -->
    <div
      v-if="problematicZones.length > 0"
      class="space-y-4"
    >
      <h2 class="text-md font-semibold">
        Требуют внимания
      </h2>
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <Card
          v-for="zone in problematicZones"
          :key="zone.id"
          class="hover:border-[color:var(--border-strong)] transition-colors"
        >
          <div class="flex items-start justify-between mb-2">
            <div>
              <div class="text-sm font-semibold">
                {{ zone.name }}
              </div>
              <div
                v-if="(zone as any).crop"
                class="text-xs text-[color:var(--text-muted)] mt-1"
              >
                {{ (zone as any).crop }}
              </div>
            </div>
            <Badge :variant="zone.status === 'ALARM' ? 'danger' : 'warning'">
              {{ translateStatus(zone.status) }}
            </Badge>
          </div>
          <div
            v-if="(zone as any).issues && (zone as any).issues.length > 0"
            class="text-xs text-[color:var(--accent-red)] mt-2"
          >
            <div
              v-for="issue in (zone as any).issues"
              :key="issue"
            >
              • {{ issue }}
            </div>
          </div>
          <div class="mt-3">
            <Link :href="`/zones/${zone.id}`">
              <Button
                size="sm"
                variant="secondary"
              >
                Подробнее
              </Button>
            </Link>
          </div>
        </Card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { Link } from '@inertiajs/vue3'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import MetricCard from '@/Components/MetricCard.vue'
import { translateStatus } from '@/utils/i18n'
import { useTelemetry } from '@/composables/useTelemetry'
import type { Zone, Recipe } from '@/types'

type TrendDirection = 'up' | 'down' | 'stable' | null

interface Props {
  dashboard: {
    zones?: Zone[]
    recipes?: Recipe[]
    zonesByStatus?: Record<string, number>
    problematicZones?: Zone[]
  }
}

const props = defineProps<Props>()

const { fetchHistory } = useTelemetry()
const phTrendData = ref<TrendDirection>(null)
const ecTrendData = ref<TrendDirection>(null)

// Группировка зон по культурам
const zonesByCrop = computed(() => {
  if (!props.dashboard.zones) return []
  
  const grouped = new Map<string, {
    cropName: string
    zones: Zone[]
    avgPh: number | null
    avgEc: number | null
    averageProgress: number | null
    currentPhase: string | null
    averageDay: number
    totalDays: number
    overallStatus: 'OK' | 'WARNING' | 'ALARM'
  }>()
  
  props.dashboard.zones.forEach(zone => {
    // Используем новую модель: activeGrowCycle -> recipeRevision -> recipe
    const cropName = (zone as any).activeGrowCycle?.recipeRevision?.recipe?.name 
      || 'Без рецепта'
    
    if (!grouped.has(cropName)) {
      grouped.set(cropName, {
        cropName,
        zones: [],
        avgPh: null,
        avgEc: null,
        averageProgress: null,
        currentPhase: null,
        averageDay: 0,
        totalDays: 0,
        overallStatus: 'OK'
      })
    }
    
    const group = grouped.get(cropName)!
    group.zones.push(zone)
    
    // Определяем общий статус (если хотя бы одна зона в ALARM, то ALARM)
    if (zone.status === 'ALARM') {
      group.overallStatus = 'ALARM'
    } else if (zone.status === 'WARNING' && group.overallStatus === 'OK') {
      group.overallStatus = 'WARNING'
    }
  })
  
  return Array.from(grouped.values())
})

// Средние метрики
const averagePh = computed(() => {
  if (!props.dashboard.zones || props.dashboard.zones.length === 0) return null
  const zonesWithPh = props.dashboard.zones.filter(z => z.telemetry?.ph !== null && z.telemetry?.ph !== undefined)
  if (zonesWithPh.length === 0) return null
  const sum = zonesWithPh.reduce((acc, z) => acc + (z.telemetry?.ph || 0), 0)
  return sum / zonesWithPh.length
})

const averageEc = computed(() => {
  if (!props.dashboard.zones || props.dashboard.zones.length === 0) return null
  const zonesWithEc = props.dashboard.zones.filter(z => z.telemetry?.ec !== null && z.telemetry?.ec !== undefined)
  if (zonesWithEc.length === 0) return null
  const sum = zonesWithEc.reduce((acc, z) => acc + (z.telemetry?.ec || 0), 0)
  return sum / zonesWithEc.length
})

// Вычисление трендов на основе исторических данных
async function calculateTrend(zoneId: number, metric: 'PH' | 'EC', currentValue: number | null): Promise<TrendDirection> {
  if (currentValue === null) return null

  try {
    const now = new Date()
    const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000)
    
    const history = await fetchHistory(zoneId, metric, {
      from: yesterday.toISOString(),
      to: now.toISOString(),
    }, true)

    if (history.length < 2) return null

    // Берем значения из начала и конца периода
    const oldValue = history[0].value
    const newValue = history[history.length - 1].value
    
    const diff = newValue - oldValue
    const threshold = metric === 'PH' ? 0.1 : 0.2 // Порог для определения тренда

    if (Math.abs(diff) < threshold) return 'stable'
    return diff > 0 ? 'up' : 'down'
  } catch (error) {
    console.error(`[AgronomistDashboard] Failed to calculate ${metric} trend:`, error)
    return null
  }
}

// Вычисляем тренды для всех зон
onMounted(async () => {
  if (!props.dashboard.zones || props.dashboard.zones.length === 0) return

  // Вычисляем тренд pH на основе первой зоны с pH
  const zoneWithPh = props.dashboard.zones.find(z => z.telemetry?.ph !== null && z.telemetry?.ph !== undefined)
  if (zoneWithPh) {
    phTrendData.value = await calculateTrend(zoneWithPh.id, 'PH', zoneWithPh.telemetry?.ph || null)
  }

  // Вычисляем тренд EC на основе первой зоны с EC
  const zoneWithEc = props.dashboard.zones.find(z => z.telemetry?.ec !== null && z.telemetry?.ec !== undefined)
  if (zoneWithEc) {
    ecTrendData.value = await calculateTrend(zoneWithEc.id, 'EC', zoneWithEc.telemetry?.ec || null)
  }
})

const phTrend = computed(() => trendToNumber(phTrendData.value))
const ecTrend = computed(() => trendToNumber(ecTrendData.value))

// Целевые значения для pH (стандартный диапазон для гидропоники)
const phTarget = computed(() => {
  return { min: 5.5, max: 6.5 }
})

// Целевые значения для EC (зависит от культуры, используем общий диапазон)
const ecTarget = computed(() => {
  return { min: 1.0, max: 3.0 }
})

// Определение статуса pH
function getPhStatus(ph: number | null): 'success' | 'warning' | 'danger' | 'neutral' {
  if (ph === null) return 'neutral'
  const target = phTarget.value
  if (ph >= target.min && ph <= target.max) return 'success'
  if (ph >= target.min - 0.3 && ph <= target.max + 0.3) return 'warning'
  return 'danger'
}

// Определение статуса EC
function getEcStatus(ec: number | null): 'success' | 'warning' | 'danger' | 'neutral' {
  if (ec === null) return 'neutral'
  const target = ecTarget.value
  if (ec >= target.min && ec <= target.max) return 'success'
  if (ec >= target.min - 0.5 && ec <= target.max + 0.5) return 'warning'
  return 'danger'
}

const activeZonesCount = computed(() => {
  return props.dashboard.zonesByStatus?.RUNNING || 0
})

const totalZonesCount = computed(() => {
  return props.dashboard.zones?.length || 0
})

const warningZonesCount = computed(() => {
  return props.dashboard.zonesByStatus?.WARNING || 0
})

const alarmZonesCount = computed(() => {
  return props.dashboard.zonesByStatus?.ALARM || 0
})

const activeRecipes = computed(() => {
  if (!props.dashboard.recipes) return []
  // Рецепты считаются активными, если они применены к зонам через activeGrowCycle
  return props.dashboard.recipes.slice(0, 6).map(recipe => {
    const zonesWithRecipe = props.dashboard.zones?.filter(z =>
      (z as any).activeGrowCycle?.recipeRevision?.recipe_id === recipe.id
    ) || []
    
    // Вычисляем информацию о фазах из зон
    let currentPhase: string | null = null
    let phaseProgress = 0
    let nextPhaseTransition: string | null = null

    if (zonesWithRecipe.length > 0 && recipe.phases && recipe.phases.length > 0) {
      // Берем первую зону для определения текущей фазы
      const firstZone = zonesWithRecipe[0]
      
      // Используем новую модель: activeGrowCycle
      let currentPhaseIndex = 0
      let startedAt: Date | null = null
      
      if ((firstZone as any).activeGrowCycle?.currentPhase) {
        currentPhaseIndex = (firstZone as any).activeGrowCycle.currentPhase.phase_index ?? 0
        startedAt = (firstZone as any).activeGrowCycle.phase_started_at
          ? new Date((firstZone as any).activeGrowCycle.phase_started_at)
          : ((firstZone as any).activeGrowCycle.started_at ? new Date((firstZone as any).activeGrowCycle.started_at) : null)
      }
      
      const currentPhaseData = recipe.phases.find(p => p.phase_index === currentPhaseIndex)
      
      if (currentPhaseData) {
        currentPhase = currentPhaseData.name || `Фаза ${currentPhaseIndex + 1}`
        
        // Вычисляем прогресс фазы на основе времени
        if (startedAt) {
          const now = new Date()
          const phaseDuration = ((currentPhaseData as any).duration_days || 0) * 24 * 60 * 60 * 1000
          const elapsed = now.getTime() - startedAt.getTime()
          phaseProgress = phaseDuration > 0 ? Math.min(100, Math.max(0, (elapsed / phaseDuration) * 100)) : 0
          
          // Вычисляем время до следующей фазы
          const nextPhaseStart = new Date(startedAt.getTime() + phaseDuration)
          if (nextPhaseStart > now) {
            nextPhaseTransition = nextPhaseStart.toISOString()
          }
        }
      }
    }

    return {
      ...recipe,
      zonesCount: zonesWithRecipe.length,
      currentPhase,
      phaseProgress,
      nextPhaseTransition
    }
  }).filter(r => r.zonesCount > 0)
})

const activeRecipesCount = computed(() => {
  return activeRecipes.value.length
})

const problematicZones = computed(() => {
  return props.dashboard.problematicZones || []
})

function formatTimeUntil(timestamp: string | Date): string {
  const now = new Date()
  const target = new Date(timestamp)
  const diff = target.getTime() - now.getTime()
  
  if (diff < 0) return 'Прошло'
  
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
  
  if (days > 0) return `${days} дн. ${hours} ч.`
  if (hours > 0) return `${hours} ч. ${minutes} мин.`
  return `${minutes} мин.`
}

function trendToNumber(trend: TrendDirection): number | null | undefined {
  if (trend === null) return null
  if (trend === 'up') return 1
  if (trend === 'down') return -1
  return 0 // stable
}
</script>
