import { computed, getCurrentScope, onScopeDispose, ref, watch, type Ref } from 'vue'
import { api } from '@/services/api'
import type { ZoneEstopApplyResult, ZoneEstopStatus } from '@/types/ZoneEstop'
import { readEstopStatus, readSolutionPercent } from '@/utils/zoneEstop'

export function useZoneEstop(zoneId: Ref<number | null | undefined>) {
  const status = ref<ZoneEstopStatus | null>(null)
  const solutionPercent = ref<number | null | undefined>(undefined)
  const loading = ref(false)
  const busy = ref(false)
  const active = computed(() => status.value?.active === true)
  let generation = 0
  let statusRequest = 0

  async function refreshStatus(): Promise<void> {
    const id = zoneId.value
    if (!id || busy.value) return
    const current = generation
    const request = ++statusRequest
    try {
      const next = readEstopStatus(await api.zones.getEstop(id))
      if (current === generation && request === statusRequest && next) status.value = next
    } catch {
      // Keep the last known latch on transport failures.
    }
  }

  async function refresh(): Promise<void> {
    const id = zoneId.value
    if (!id) return
    const current = generation
    loading.value = true
    await Promise.all([
      refreshStatus(),
      (async () => {
        try {
          const level = readSolutionPercent(await api.zones.getSnapshot<unknown>(id))
          if (current === generation && level !== undefined) solutionPercent.value = level
        } catch {
          // The status endpoint remains independent from the heavier snapshot.
        }
      })(),
    ])
    if (current === generation) loading.value = false
  }

  async function apply(action: 'engage' | 'release', reason?: string): Promise<ZoneEstopApplyResult> {
    const id = zoneId.value
    if (!id) throw new Error('Зона не найдена')
    const current = generation
    ++statusRequest
    busy.value = true
    try {
      const result = await api.zones.applyEstop(id, { action, ...(reason ? { reason } : {}) })
      const next = readEstopStatus(result)
      if (current === generation && next) status.value = next
      return result
    } finally {
      if (current === generation) busy.value = false
    }
  }

  watch(zoneId, () => {
    ++generation
    status.value = null
    solutionPercent.value = undefined
    busy.value = false
    void refresh()
  }, { immediate: true })

  if (getCurrentScope()) {
    const timer = setInterval(() => { void refreshStatus() }, 3000)
    onScopeDispose(() => { ++generation; clearInterval(timer) })
  }

  return {
    status, active, solutionPercent, loading, busy, refresh,
    engage: (reason?: string) => apply('engage', reason),
    release: (reason: string) => apply('release', reason),
  }
}
