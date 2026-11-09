import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { api } from '@/services/api'
import type { ZoneEstopStatus } from '@/types/ZoneEstop'
import { readEstopStatus } from '@/utils/zoneEstop'

const REFRESH_MS = 20_000

/**
 * Подтягивает защёлку E-STOP для карточек дашборда.
 * Снимок дашборда это поле не отдаёт, статус берётся из GET /zones/{id}/estop.
 */
export function useZoneEstopIndex(zoneIds: Ref<number[]>) {
  const estopByZoneId = ref<Record<number, ZoneEstopStatus>>({})
  let requestSeq = 0
  const timer = setInterval(() => {
    void refresh()
  }, REFRESH_MS)

  async function refresh(): Promise<void> {
    const ids = [...new Set(zoneIds.value.filter((id) => Number.isFinite(id) && id > 0))]
    const getter = api.zones?.getEstop
    if (ids.length === 0 || typeof getter !== 'function') return

    const seq = ++requestSeq
    const entries = await Promise.all(ids.map(async (id) => {
      try {
        const payload = await getter(id)
        const status = readEstopStatus(payload)
        return status ? [id, status] as const : null
      } catch {
        return null
      }
    }))
    if (seq !== requestSeq) return

    const next: Record<number, ZoneEstopStatus> = {}
    for (const entry of entries) {
      if (!entry) continue
      next[entry[0]] = entry[1]
    }
    estopByZoneId.value = next
  }

  watch(zoneIds, () => {
    void refresh()
  }, { immediate: true, deep: true })

  onBeforeUnmount(() => {
    requestSeq += 1
    if (timer) clearInterval(timer)
  })

  return { estopByZoneId, refreshEstop: refresh }
}
