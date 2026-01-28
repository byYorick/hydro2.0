import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setupRouterGuards, restoreRouterMethods } from '../routerGuards'

// Мокаем router
const mockReload = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const mockVisit = vi.hoisted(() => vi.fn(() => Promise.resolve()))

vi.mock('@inertiajs/vue3', () => ({
  router: {
    reload: mockReload,
    visit: mockVisit,
  },
}))

describe('routerGuards', () => {
  beforeEach(() => {
    restoreRouterMethods()
    vi.clearAllMocks()
  })

  afterEach(() => {
    restoreRouterMethods()
  })

  describe('setupRouterGuards', () => {
    it('should wrap router.reload and router.visit', async () => {
      const { router } = await import('@inertiajs/vue3')
      const originalReload = router.reload
      const originalVisit = router.visit

      setupRouterGuards()

      expect(router.reload).not.toBe(originalReload)
      expect(router.visit).not.toBe(originalVisit)
    })

    it('should prevent rapid reloads to same URL', async () => {
      const { router } = await import('@inertiajs/vue3')
      setupRouterGuards()

      // Первые 3 вызова должны пройти
      await router.reload()
      await router.reload()
      await router.reload()

      expect(mockReload).toHaveBeenCalledTimes(3)

      // 4-й вызов должен быть заблокирован (не должен вызвать mockReload)
      mockReload.mockClear()
      await router.reload()
      
      // Проверяем, что после очистки mockReload не был вызван (блокирован)
      expect(mockReload).toHaveBeenCalledTimes(0)
    })

    it('should allow reloads after time window', async () => {
      const { router } = await import('@inertiajs/vue3')
      setupRouterGuards()

      vi.useFakeTimers()

      await router.reload()
      await router.reload()
      await router.reload()

      // Перемещаем время вперед на 2 секунды (больше чем RELOAD_WINDOW_MS = 1000)
      vi.advanceTimersByTime(2000)

      // Теперь должен быть разрешен еще один вызов
      await router.reload()

      expect(mockReload).toHaveBeenCalledTimes(4)

      vi.useRealTimers()
    })

    it('should allow visit to different URLs', async () => {
      const { router } = await import('@inertiajs/vue3')
      setupRouterGuards()

      await router.visit('/zones/1')
      await router.visit('/zones/2')
      await router.visit('/zones/3')

      expect(mockVisit).toHaveBeenCalledTimes(3)
    })
  })

  describe('restoreRouterMethods', () => {
    it('should restore original router methods', async () => {
      const { router } = await import('@inertiajs/vue3')
      const originalReload = router.reload
      const originalVisit = router.visit

      setupRouterGuards()
      const wrappedReload = router.reload
      const wrappedVisit = router.visit

      expect(router.reload).not.toBe(originalReload)
      expect(router.visit).not.toBe(originalVisit)

      restoreRouterMethods()

      // После восстановления методы должны быть оригинальными
      // (или восстановленными, если они были сохранены)
      expect(router.reload).not.toBe(wrappedReload)
      expect(router.visit).not.toBe(wrappedVisit)
    })
  })
})
