<template>
  <!-- Compact single-line AI hint. Shows nothing on loading or no data. -->
  <div
    v-if="hintText"
    class="flex items-center gap-1.5 text-[11px] rounded-md px-2 py-1 border"
    :class="hintClass"
  >
    <span class="shrink-0">{{ hintIcon }}</span>
    <span class="truncate">{{ hintText }}</span>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useApi } from '@/composables/useApi'
import { logger } from '@/utils/logger'

interface Props {
  zoneId: number
  metricType: 'PH' | 'EC'
  targetMin?: number | null
  targetMax?: number | null
  horizonMinutes?: number
}

const props = withDefaults(defineProps<Props>(), {
  horizonMinutes: 90,
})

interface Prediction {
  predicted_value: number
  confidence: number
  predicted_at: string
}

interface PredictionResponse {
  status: string
  data?: Prediction
  message?: string
}

const { api } = useApi()
const prediction = ref<Prediction | null>(null)

async function fetchPrediction(): Promise<void> {
  const requestedZoneId = props.zoneId
  try {
    const response = await api.post<PredictionResponse>('/api/ai/predict', {
      zone_id: requestedZoneId,
      metric_type: props.metricType,
      horizon_minutes: props.horizonMinutes,
    })
    if (props.zoneId !== requestedZoneId) return
    if (response.data?.status === 'ok' && response.data?.data) {
      prediction.value = response.data.data
    }
  } catch (err: any) {
    // Gracefully suppress errors — hint is non-critical
    logger.debug('[ZoneAIPredictionHint] No prediction data', {
      zoneId: requestedZoneId,
      metric: props.metricType,
    })
  }
}

watch(() => [props.zoneId, props.metricType], () => {
  prediction.value = null
  fetchPrediction()
})

onMounted(() => {
  fetchPrediction()
})

// ─── Display logic ────────────────────────────────────────────────────────────
const isOutOfRange = computed(() => {
  if (!prediction.value || props.targetMin == null || props.targetMax == null) return false
  const v = prediction.value.predicted_value
  return v < props.targetMin || v > props.targetMax
})

const isNearEdge = computed(() => {
  if (!prediction.value || props.targetMin == null || props.targetMax == null) return false
  if (isOutOfRange.value) return false
  const v = prediction.value.predicted_value
  const span = props.targetMax - props.targetMin
  const margin = span * 0.1 // 10% buffer
  return v < props.targetMin + margin || v > props.targetMax - margin
})

const metricLabel = computed(() => props.metricType === 'PH' ? 'pH' : 'EC')
const unit = computed(() => props.metricType === 'EC' ? ' мСм/см' : '')

function fmtVal(v: number): string {
  return props.metricType === 'PH' ? v.toFixed(2) : v.toFixed(2)
}

const hintText = computed(() => {
  if (!prediction.value) return null
  const v = fmtVal(prediction.value.predicted_value)
  const h = props.horizonMinutes < 60
    ? `${props.horizonMinutes} мин`
    : `${props.horizonMinutes / 60} ч`

  if (isOutOfRange.value) {
    const dir = prediction.value.predicted_value > (props.targetMax ?? 0) ? 'выйдет ↑' : 'выйдет ↓'
    return `${metricLabel.value} ${dir} ${v}${unit.value} через ${h}`
  }
  if (isNearEdge.value) {
    return `${metricLabel.value} у границы: ${v}${unit.value} через ${h}`
  }
  if (prediction.value.confidence >= 0.75) {
    return `${metricLabel.value} стабилен: ${v}${unit.value} через ${h}`
  }
  return null
})

const hintIcon = computed(() => {
  if (isOutOfRange.value) return '⚡'
  if (isNearEdge.value) return '⚠️'
  return '✦'
})

const hintClass = computed(() => {
  if (isOutOfRange.value) {
    return 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] text-[color:var(--accent-red)]'
  }
  if (isNearEdge.value) {
    return 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] text-[color:var(--accent-amber)]'
  }
  return 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[color:var(--text-dim)]'
})
</script>
