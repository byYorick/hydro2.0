import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  createThrottledTask,
  isSparklineCacheFresh,
  SPARKLINE_CACHE_TTL_MS,
  DASHBOARD_ZONES_RELOAD_THROTTLE_MS,
} from '../useUnifiedDashboard'

describe('useUnifiedDashboard helpers', () => {
  describe('isSparklineCacheFresh', () => {
    it('returns false when never fetched', () => {
      expect(isSparklineCacheFresh(undefined, Date.now())).toBe(false)
    })

    it('returns true within TTL', () => {
      const now = 1_000_000
      expect(isSparklineCacheFresh(now - 30_000, now)).toBe(true)
    })

    it('returns false after TTL expires', () => {
      const now = 1_000_000
      expect(isSparklineCacheFresh(now - SPARKLINE_CACHE_TTL_MS - 1, now)).toBe(false)
    })
  })

  describe('createThrottledTask', () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('runs first schedule immediately (leading)', async () => {
      const run = vi.fn()
      const { schedule } = createThrottledTask(run, DASHBOARD_ZONES_RELOAD_THROTTLE_MS)

      schedule()
      expect(run).not.toHaveBeenCalled()

      await vi.advanceTimersByTimeAsync(0)
      expect(run).toHaveBeenCalledTimes(1)
    })

    it('coalesces bursts into one trailing run inside the throttle window', async () => {
      const run = vi.fn()
      const { schedule } = createThrottledTask(run, DASHBOARD_ZONES_RELOAD_THROTTLE_MS)

      schedule()
      await vi.advanceTimersByTimeAsync(0)
      expect(run).toHaveBeenCalledTimes(1)

      schedule()
      schedule()
      schedule()
      expect(run).toHaveBeenCalledTimes(1)

      await vi.advanceTimersByTimeAsync(DASHBOARD_ZONES_RELOAD_THROTTLE_MS)
      expect(run).toHaveBeenCalledTimes(2)
    })

    it('cancel prevents a pending trailing run', async () => {
      const run = vi.fn()
      const { schedule, cancel } = createThrottledTask(run, DASHBOARD_ZONES_RELOAD_THROTTLE_MS)

      schedule()
      await vi.advanceTimersByTimeAsync(0)
      schedule()
      cancel()

      await vi.advanceTimersByTimeAsync(DASHBOARD_ZONES_RELOAD_THROTTLE_MS)
      expect(run).toHaveBeenCalledTimes(1)
    })
  })
})
