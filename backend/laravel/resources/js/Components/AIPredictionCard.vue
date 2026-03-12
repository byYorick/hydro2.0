<template>
  <Card class="surface-card-hover">
    <div class="flex items-center justify-between mb-3">
      <div class="text-sm font-semibold text-[color:var(--text-primary)]">
        Прогноз {{ metricLabel }}
      </div>
      <div
        v-if="loading"
        class="w-4 h-4"
      >
        <LoadingState
          loading
          size="sm"
        />
      </div>
      <Badge
        v-else-if="prediction"
        :variant="confidenceVariant"
        class="text-xs"
      >
        {{ confidenceText }}
      </Badge>
    </div>

    <div
      v-if="loading"
      class="py-6 text-center"
    >
      <LoadingState
        loading
        size="md"
      />
      <div class="text-sm font-medium text-[color:var(--text-primary)] mt-3 mb-1">
        Загрузка прогноза {{ metricLabel }}
      </div>
      <div class="text-xs text-[color:var(--text-muted)]">
        Анализ исторических данных и генерация прогноза...
      </div>
    </div>

    <div
      v-else-if="error"
      class="py-6 text-center"
    >
      <div class="text-4xl mb-2">
        ⚠️
      </div>
      <div class="text-sm font-medium text-[color:var(--accent-red)] mb-1">
        Ошибка загрузки прогноза
      </div>
      <div class="text-xs text-[color:var(--text-muted)] mb-3">
        {{ error }}
      </div>
      <Button
        size="sm"
        variant="outline"
        @click="fetchPrediction"
      >
        Повторить попытку
      </Button>
    </div>

    <div
      v-else-if="prediction"
      class="space-y-3"
    >
      <div class="flex items-baseline gap-2">
        <div
          class="text-3xl font-bold"
          :style="{ color: metricColor }"
        >
          {{ formatValue(prediction.predicted_value) }}
        </div>
        <div class="text-sm text-[color:var(--text-muted)]">
          {{ metricUnit }}
        </div>
      </div>

      <div class="text-xs text-[color:var(--text-dim)] space-y-1">
        <div>Горизонт прогноза: {{ horizonMinutes }} мин</div>
        <div>Уверенность: {{ Math.round(prediction.confidence * 100) }}%</div>
        <div v-if="prediction.predicted_at">
          Время прогноза: {{ formatTime(prediction.predicted_at) }}
        </div>
      </div>

      <div
        v-if="targetRange"
        class="pt-2 border-t border-[color:var(--border-muted)]"
      >
        <div class="text-xs text-[color:var(--text-dim)] mb-1">
          Целевой диапазон:
        </div>
        <div class="text-sm font-medium">
          {{ formatValue(targetRange.min) }} — {{ formatValue(targetRange.max) }} {{ metricUnit }}
        </div>
        <div 
          v-if="isOutOfRange" 
          class="text-xs mt-1"
          :class="isAboveRange ? 'text-[color:var(--accent-red)]' : 'text-[color:var(--accent-amber)]'"
        >
          ⚠️ Прогноз {{ isAboveRange ? 'выше' : 'ниже' }} целевого диапазона
        </div>
      </div>
    </div>

    <div
      v-else
      class="py-6 text-center"
    >
      <div class="text-4xl mb-2">
        📊
      </div>
      <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
        Нет данных для прогноза
      </div>
      <div class="text-xs text-[color:var(--text-muted)] space-y-1">
        <div>Для генерации прогноза {{ metricLabel }} необходимо:</div>
        <div class="mt-2 text-left pl-4">
          <div class="flex items-start gap-2">
            <span class="text-[color:var(--text-dim)]">•</span>
            <span>Наличие исторических данных телеметрии</span>
          </div>
          <div class="flex items-start gap-2 mt-1">
            <span class="text-[color:var(--text-dim)]">•</span>
            <span>Минимум 24 часа записей для точного прогноза</span>
          </div>
          <div class="flex items-start gap-2 mt-1">
            <span class="text-[color:var(--text-dim)]">•</span>
            <span>Активная работа датчиков в зоне</span>
          </div>
        </div>
      </div>
      <Button 
        size="sm" 
        variant="outline" 
        class="mt-4"
        @click="fetchPrediction"
      >
        Обновить
      </Button>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import Card from './Card.vue'
import Badge from './Badge.vue'
import Button from './Button.vue'
import LoadingState from './LoadingState.vue'
import { formatTimeShort } from '@/utils/formatTime'
import { logger } from '@/utils/logger'

interface Props {
  zoneId: number
  metricType: 'PH' | 'EC' | 'TEMPERATURE' | 'HUMIDITY'
  horizonMinutes?: number
  autoRefresh?: boolean
  refreshInterval?: number
  targetRange?: {
    min: number
    max: number
  }
}

const props = withDefaults(defineProps<Props>(), {
  horizonMinutes: 60,
  autoRefresh: false,
  refreshInterval: 300000, // 5 минут по умолчанию
})

interface Prediction {
  predicted_value: number
  confidence: number
  predicted_at: string
  horizon_minutes: number
}

interface PredictionResponse {
  status: string
  data?: Prediction
  message?: string
}

const { api } = useApi()
const { showToast } = useToast()

const prediction = ref<Prediction | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
let refreshTimer: ReturnType<typeof setInterval> | null = null

const metricLabel = computed(() => {
  const labels: Record<string, string> = {
    PH: 'pH',
    EC: 'EC',
    TEMPERATURE: 'Температура',
    HUMIDITY: 'Влажность',
  }
  return labels[props.metricType] || props.metricType
})

const metricUnit = computed(() => {
  const units: Record<string, string> = {
    PH: '',
    EC: 'мСм/см',
    TEMPERATURE: '°C',
    HUMIDITY: '%',
  }
  return units[props.metricType] || ''
})

const metricColor = computed(() => {
  const colors: Record<string, string> = {
    PH: 'var(--accent-cyan)',
    EC: 'var(--accent-green)',
    TEMPERATURE: 'var(--accent-amber)',
    HUMIDITY: 'var(--accent-blue)',
  }
  return colors[props.metricType] || 'var(--text-primary)'
})

const confidenceVariant = computed(() => {
  if (!prediction.value) return 'neutral'
  const conf = prediction.value.confidence
  if (conf >= 0.8) return 'success'
  if (conf >= 0.6) return 'warning'
  return 'danger'
})

const confidenceText = computed(() => {
  if (!prediction.value) return ''
  const conf = Math.round(prediction.value.confidence * 100)
  if (conf >= 80) return 'Высокая'
  if (conf >= 60) return 'Средняя'
  return 'Низкая'
})

const isOutOfRange = computed(() => {
  if (!prediction.value || !props.targetRange) return false
  const value = prediction.value.predicted_value
  return value < props.targetRange.min || value > props.targetRange.max
})

const isAboveRange = computed(() => {
  if (!prediction.value || !props.targetRange) return false
  return prediction.value.predicted_value > props.targetRange.max
})

function formatValue(value: number): string {
  if (props.metricType === 'PH') {
    return value.toFixed(2)
  }
  if (props.metricType === 'EC') {
    return value.toFixed(2)
  }
  if (props.metricType === 'TEMPERATURE') {
    return value.toFixed(1)
  }
  if (props.metricType === 'HUMIDITY') {
    return Math.round(value).toString()
  }
  return value.toFixed(2)
}

function formatTime(timeString: string): string {
  try {
    return formatTimeShort(new Date(timeString))
  } catch {
    return timeString
  }
}

async function fetchPrediction(): Promise<void> {
  if (loading.value) return

  // Захватываем ID зоны до await: если зона сменится пока запрос в-полёте,
  // ответ старой зоны будет проигнорирован
  const requestedZoneId = props.zoneId

  loading.value = true
  error.value = null

  try {
    const response = await api.post<PredictionResponse>('/api/ai/predict', {
      zone_id: requestedZoneId,
      metric_type: props.metricType,
      horizon_minutes: props.horizonMinutes,
    })

    if (props.zoneId !== requestedZoneId) return

    if (response.data?.status === 'ok' && response.data?.data) {
      prediction.value = response.data.data
      error.value = null
      logger.debug('[AIPredictionCard] Prediction fetched', {
        zoneId: requestedZoneId,
        metricType: props.metricType,
        predictedValue: response.data.data.predicted_value,
      })
    } else {
      const message = response.data?.message || 'Не удалось получить прогноз'
      throw new Error(message)
    }
  } catch (err: any) {
    if (props.zoneId !== requestedZoneId) return

    const errorMessage = err?.response?.data?.message || err?.message || 'Ошибка при загрузке прогноза'
    const statusCode = err?.response?.status

    // Специальная обработка ошибки "Not enough data" (422) - это не ошибка, а нормальное состояние
    if (
      (errorMessage.includes('Not enough data') || errorMessage.includes('недостаточно данных')) ||
      (statusCode === 422 && errorMessage.includes('Failed to generate prediction'))
    ) {
      prediction.value = null
      error.value = null
      logger.debug('[AIPredictionCard] Not enough data for prediction', {
        zoneId: requestedZoneId,
        metricType: props.metricType,
        statusCode,
      })
    } else {
      error.value = errorMessage
      logger.error('[AIPredictionCard] Failed to fetch prediction', {
        zoneId: requestedZoneId,
        metricType: props.metricType,
        error: err,
        statusCode,
      })

      if (prediction.value || statusCode >= 500) {
        showToast(errorMessage, 'error', 5000)
      }
    }
  } finally {
    loading.value = false
  }
}

function startAutoRefresh(): void {
  if (!props.autoRefresh || refreshTimer) return

  refreshTimer = setInterval(() => {
    fetchPrediction()
  }, props.refreshInterval)
}

function stopAutoRefresh(): void {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

watch(() => [props.zoneId, props.metricType, props.horizonMinutes], () => {
  // Сбрасываем loading, чтобы in-flight запрос старых параметров не блокировал новый фетч
  // (fetchPrediction возвращается сразу при loading=true)
  loading.value = false
  prediction.value = null
  error.value = null
  fetchPrediction()
}, { immediate: false })

watch(() => props.autoRefresh, (enabled) => {
  if (enabled) {
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
})

onMounted(() => {
  fetchPrediction()
  if (props.autoRefresh) {
    startAutoRefresh()
  }
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>
