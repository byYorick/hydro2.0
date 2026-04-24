import { computed, onBeforeUnmount, ref, watch, type Ref, type ComputedRef } from 'vue'

/**
 * Live-countdown от указанной конечной точки (`target`).
 *
 * Обновляется через requestAnimationFrame с throttling в 1 сек — чтобы
 * не ререндерить DOM каждый кадр (30-60 Hz), но UI оставался «живым».
 * Автоматически ставит цикл на паузу, когда документ скрыт
 * (`visibilitychange`), и возобновляет при возврате.
 *
 * Возвращает remaining-секунды (отрицательные → формат оставит `—`) и
 * `label` уже форматированный `MM:SS` или `HH:MM:SS`.
 */
export interface RafCountdown {
  remainingSeconds: ComputedRef<number | null>
  label: ComputedRef<string>
  expired: ComputedRef<boolean>
  stop: () => void
}

export function useRafCountdown(target: Ref<Date | string | null | undefined>): RafCountdown {
  const now = ref<number>(Date.now())

  const targetMs = computed<number | null>(() => {
    const value = target.value
    if (!value) return null
    if (value instanceof Date) return value.getTime()
    const parsed = new Date(String(value)).getTime()
    return Number.isFinite(parsed) ? parsed : null
  })

  const remainingSeconds = computed<number | null>(() => {
    if (targetMs.value === null) return null
    return Math.round((targetMs.value - now.value) / 1000)
  })

  const expired = computed<boolean>(() => {
    const remaining = remainingSeconds.value
    return remaining !== null && remaining <= 0
  })

  const label = computed<string>(() => {
    const remaining = remainingSeconds.value
    if (remaining === null) return '—'
    if (remaining <= 0) return '00:00'
    const hours = Math.floor(remaining / 3600)
    const minutes = Math.floor((remaining % 3600) / 60)
    const seconds = remaining % 60
    const mm = String(minutes).padStart(2, '0')
    const ss = String(seconds).padStart(2, '0')
    if (hours > 0) {
      return `${String(hours).padStart(2, '0')}:${mm}:${ss}`
    }
    return `${mm}:${ss}`
  })

  let rafHandle: number | null = null
  let lastTickAt = 0
  let stopped = false

  const isBrowser = typeof window !== 'undefined' && typeof document !== 'undefined'

  function tick(timestamp: number): void {
    if (stopped) return
    if (timestamp - lastTickAt >= 1000) {
      now.value = Date.now()
      lastTickAt = timestamp
    }
    rafHandle = window.requestAnimationFrame(tick)
  }

  function cancelRaf(): void {
    if (rafHandle !== null && isBrowser) {
      window.cancelAnimationFrame(rafHandle)
      rafHandle = null
    }
  }

  function startRaf(): void {
    if (!isBrowser || stopped) return
    if (rafHandle !== null) return
    lastTickAt = 0
    now.value = Date.now()
    rafHandle = window.requestAnimationFrame(tick)
  }

  function handleVisibility(): void {
    if (document.hidden) {
      cancelRaf()
    } else {
      startRaf()
    }
  }

  function stop(): void {
    if (stopped) return
    stopped = true
    cancelRaf()
    if (isBrowser) {
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }

  watch(
    targetMs,
    (value) => {
      if (value === null) {
        cancelRaf()
      } else {
        startRaf()
      }
    },
    { immediate: true },
  )

  if (isBrowser) {
    document.addEventListener('visibilitychange', handleVisibility)
  }

  onBeforeUnmount(stop)

  return { remainingSeconds, label, expired, stop }
}
