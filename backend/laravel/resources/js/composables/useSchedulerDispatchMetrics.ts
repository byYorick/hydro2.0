import { onMounted, onUnmounted, ref, type Ref } from 'vue'
import axios from 'axios'
import {
  parseSchedulerDispatchMetrics,
  type SchedulerDispatchMetricsSnapshot,
} from '@/utils/prometheusText'

const POLL_INTERVAL_MS = 15_000

export interface SchedulerDispatchMetricsState {
  metrics: Ref<SchedulerDispatchMetricsSnapshot | null>
  loading: Ref<boolean>
  error: Ref<string | null>
  refreshedAt: Ref<string | null>
}

export function useSchedulerDispatchMetrics(): SchedulerDispatchMetricsState {
  const metrics = ref<SchedulerDispatchMetricsSnapshot | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const refreshedAt = ref<string | null>(null)
  let timer: ReturnType<typeof setInterval> | null = null

  async function refresh(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const response = await axios.get<string>('/api/system/scheduler/metrics', {
        responseType: 'text',
        headers: { Accept: 'text/plain' },
      })
      metrics.value = parseSchedulerDispatchMetrics(String(response.data ?? ''))
      refreshedAt.value = new Date().toISOString()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Не удалось загрузить метрики планировщика'
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    void refresh()
    timer = setInterval(() => {
      void refresh()
    }, POLL_INTERVAL_MS)
  })

  onUnmounted(() => {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  })

  return { metrics, loading, error, refreshedAt }
}
