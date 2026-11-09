import { computed, ref, watch, type Ref } from 'vue'
import { api } from '@/services/api'
import type { ZoneEstopApplyResult, ZoneEstopStatus } from '@/types/ZoneEstop'
import { readEstopStatus, readSolutionPercent } from '@/utils/zoneEstop'

export function useZoneEstop(zoneId: Ref<number | null | undefined>) {
  const status = ref<ZoneEstopStatus | null>(null)
  const solutionPercent = ref<number | null | undefined>(undefined)
  const loading = ref(false)
  const busy = ref(false)
  const active = computed(() => status.value?.active === true)

  async function refresh(): Promise<void> {
    const id = zoneId.value
    if (!id) return
    loading.value = true
    try {
      const snapshot = await api.zones.getSnapshot<unknown>(id)
      const next = readEstopStatus(snapshot)
      if (next) status.value = next
      const level = readSolutionPercent(snapshot)
      if (level !== undefined) solutionPercent.value = level
    } catch {
      // Снимок недоступен — оставляем последнее известное состояние.
    } finally {
      loading.value = false
    }
  }

  async function apply(action: 'engage' | 'release', reason?: string): Promise<ZoneEstopApplyResult> {
    const id = zoneId.value
    if (!id) {
      throw new Error('Зона не найдена')
    }
    busy.value = true
    try {
      const result = await api.zones.applyEstop(id, {
        action,
        ...(reason ? { reason } : {}),
      })
      const next = readEstopStatus(result)
      if (next) status.value = next
      return result
    } finally {
      busy.value = false
    }
  }

  function engage(reason?: string): Promise<ZoneEstopApplyResult> {
    return apply('engage', reason)
  }

  function release(reason: string): Promise<ZoneEstopApplyResult> {
    return apply('release', reason)
  }

  watch(zoneId, () => {
    void refresh()
  }, { immediate: true })

  return {
    status,
    active,
    solutionPercent,
    loading,
    busy,
    refresh,
    engage,
    release,
  }
}
