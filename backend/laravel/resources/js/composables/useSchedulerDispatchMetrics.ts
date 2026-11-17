import { onMounted, onUnmounted, ref, computed } from 'vue'
import { api } from '@/services/api'
import type { SchedulerDispatchSnapshot } from '@/services/api/system'

/** Read-only authenticated UI polling; scrape tokens never enter the browser. */
export function useSchedulerDispatchMetrics() {
  const snapshot = ref<SchedulerDispatchSnapshot | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const refreshedAt = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  let disposed = false
  let pending: Promise<void> | null = null
  // Retain the existing shape for callers while exposing richer evidence separately.
  const metrics = computed(() => snapshot.value ? {
    pendingIntents: snapshot.value.pending_intents,
    oldestPendingAgeSec: snapshot.value.oldest_pending_age_sec,
    dispatchCycleOverrunSec: snapshot.value.cycle_overrun_sec,
  } : null)

  function clearTimer() { if (timer) clearTimeout(timer); timer = null }
  async function read() {
    loading.value = true
    try {
      const value = await api.system.schedulerObservability()
      if (disposed) return
      snapshot.value = value
      refreshedAt.value = new Date().toISOString()
      error.value = null
    } catch {
      if (!disposed) error.value = 'Не удалось обновить данные диспетчера. Проверьте соединение и повторите попытку.'
    } finally {
      if (!disposed) loading.value = false
    }
  }
  function refresh(): Promise<void> {
    if (disposed) return Promise.resolve()
    if (pending) return pending
    clearTimer()
    pending = read().finally(() => {
      pending = null
      if (!disposed && document.visibilityState !== 'hidden') timer = setTimeout(() => { void refresh() }, 15000)
    })
    return pending
  }
  function visibilityChanged() {
    if (document.visibilityState === 'hidden') clearTimer()
    else void refresh()
  }
  onMounted(() => { void refresh(); document.addEventListener('visibilitychange', visibilityChanged) })
  onUnmounted(() => { disposed = true; clearTimer(); document.removeEventListener('visibilitychange', visibilityChanged) })
  return { metrics, snapshot, loading, error, refreshedAt, refresh }
}
