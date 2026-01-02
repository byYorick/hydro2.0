/**
 * Unit-тесты для реестра подписок WebSocket
 * Проверяет инварианты: нет дублей, корректная регистрация/отписка
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useWebSocket, __testExports } from '../useWebSocket'

// Мокаем зависимости
vi.mock('@/utils/echoClient', () => ({
  onWsStateChange: vi.fn(() => () => {}),
  getEchoInstance: vi.fn(() => null),
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/composables/useApi', () => ({
  useApi: vi.fn(() => ({
    api: {
      get: vi.fn(() => Promise.resolve({ data: { status: 'ok', data: {} } })),
    },
  })),
}))

// Мокаем window.Echo для тестов
const mockEcho = {
  private: vi.fn((channel: string) => ({
    listen: vi.fn(),
    stopListening: vi.fn(),
  })),
  channel: vi.fn((channel: string) => ({
    listen: vi.fn(),
    stopListening: vi.fn(),
  })),
  leave: vi.fn(),
  connector: {
    pusher: {
      connection: {
        state: 'connected',
        socket_id: 'test-socket-id',
      },
      channels: {
        channels: {},
      },
    },
  },
}

beforeEach(() => {
  // Очищаем состояние перед каждым тестом
  __testExports.reset()
  
  // Мокаем window.Echo
  if (typeof window !== 'undefined') {
    (window as any).Echo = mockEcho
  }
  
  // Сбрасываем моки
  vi.clearAllMocks()
})

describe('WebSocket Subscription Registry', () => {
  describe('register → resubscribe → unregister', () => {
    it('should register subscription without duplicates', () => {
      const { subscribeToZoneCommands } = useWebSocket()
      const handler = vi.fn()
      
      // Первая подписка
      const unsubscribe1 = subscribeToZoneCommands(1, handler)
      
      expect(__testExports.getSubscriptionCount('commands.1')).toBe(1)
      expect(__testExports.hasSubscription('sub-1')).toBe(true)
      
      // Вторая подписка на тот же канал (другой handler)
      const handler2 = vi.fn()
      const unsubscribe2 = subscribeToZoneCommands(1, handler2)
      
      expect(__testExports.getSubscriptionCount('commands.1')).toBe(2)
      
      // Проверяем, что нет дублей
      const channelSet = __testExports.channelSubscribers().get('commands.1')
      expect(channelSet?.size).toBe(2)
      
      // Отписываемся
      unsubscribe1()
      expect(__testExports.getSubscriptionCount('commands.1')).toBe(1)
      
      unsubscribe2()
      expect(__testExports.getSubscriptionCount('commands.1')).toBe(0)
    })
    
    it('should handle resubscribe correctly', () => {
      const { subscribeToZoneCommands } = useWebSocket()
      const handler = vi.fn()
      
      // Подписываемся
      const unsubscribe = subscribeToZoneCommands(1, handler)
      expect(__testExports.getSubscriptionCount('commands.1')).toBe(1)
      
      // Отписываемся
      unsubscribe()
      expect(__testExports.getSubscriptionCount('commands.1')).toBe(0)
      
      // Подписываемся снова (resubscribe)
      const unsubscribe2 = subscribeToZoneCommands(1, handler)
      expect(__testExports.getSubscriptionCount('commands.1')).toBe(1)
      
      unsubscribe2()
      expect(__testExports.getSubscriptionCount('commands.1')).toBe(0)
    })
    
    it('should not allow duplicate subscription IDs', () => {
      const { subscribeToZoneCommands } = useWebSocket()
      const handler = vi.fn()
      
      // Первая подписка
      subscribeToZoneCommands(1, handler)
      
      // Проверяем, что subscription ID уникален
      const subscriptions = Array.from(__testExports.activeSubscriptions().keys())
      const uniqueIds = new Set(subscriptions)
      expect(uniqueIds.size).toBe(subscriptions.length)
    })
  })
  
  describe('no duplicates invariant', () => {
    it('should detect duplicate subscription on same channel', () => {
      const { subscribeToZoneCommands } = useWebSocket()
      const handler = vi.fn()
      
      // Подписываемся дважды на один канал с одним handler
      const unsubscribe1 = subscribeToZoneCommands(1, handler)
      const unsubscribe2 = subscribeToZoneCommands(1, handler)
      
      // Должно быть 2 подписки (разные instanceId)
      expect(__testExports.getSubscriptionCount('commands.1')).toBe(2)
      
      // Но subscription IDs должны быть уникальными
      const subscriptions = Array.from(__testExports.activeSubscriptions().values())
      const ids = subscriptions.map(s => s.id)
      const uniqueIds = new Set(ids)
      expect(uniqueIds.size).toBe(ids.length)
      
      unsubscribe1()
      unsubscribe2()
    })
    
    it('should handle multiple channels correctly', () => {
      const { subscribeToZoneCommands } = useWebSocket()
      const handler = vi.fn()
      
      // Подписываемся на разные каналы
      const unsub1 = subscribeToZoneCommands(1, handler)
      const unsub2 = subscribeToZoneCommands(2, handler)
      const unsub3 = subscribeToZoneCommands(3, handler)
      
      expect(__testExports.getSubscriptionCount('commands.1')).toBe(1)
      expect(__testExports.getSubscriptionCount('commands.2')).toBe(1)
      expect(__testExports.getSubscriptionCount('commands.3')).toBe(1)
      
      // Все подписки должны быть уникальными
      const allSubscriptions = __testExports.activeSubscriptions()
      expect(allSubscriptions.size).toBe(3)
      
      unsub1()
      unsub2()
      unsub3()
    })
  })
  
  describe('global events channel', () => {
    it('should register global events subscription', () => {
      const { subscribeToGlobalEvents } = useWebSocket()
      const handler = vi.fn()
      
      const unsubscribe = subscribeToGlobalEvents(handler)
      
      expect(__testExports.getSubscriptionCount('events.global')).toBe(1)
      
      // Проверяем реестр глобальных каналов
      const registry = __testExports.globalChannelRegistry().get('events.global')
      expect(registry).toBeDefined()
      expect(registry?.subscriptionRefCount).toBe(1)
      expect(registry?.handlers.size).toBe(1)
      
      unsubscribe()
      expect(__testExports.getSubscriptionCount('events.global')).toBe(0)
    })
    
    it('should reuse global channel on multiple subscriptions', () => {
      const { subscribeToGlobalEvents } = useWebSocket()
      const handler1 = vi.fn()
      const handler2 = vi.fn()
      
      const unsub1 = subscribeToGlobalEvents(handler1)
      const unsub2 = subscribeToGlobalEvents(handler2)
      
      // Оба handler'а должны быть в реестре
      const registry = __testExports.globalChannelRegistry().get('events.global')
      expect(registry?.subscriptionRefCount).toBe(2)
      expect(registry?.handlers.size).toBe(2)
      
      // Но канал должен быть один
      const channelControl = __testExports.getChannelControl('events.global')
      expect(channelControl).toBeDefined()
      
      unsub1()
      expect(registry?.subscriptionRefCount).toBe(1)
      
      unsub2()
      expect(registry?.subscriptionRefCount).toBe(0)
    })
  })
  
  describe('unsubscribeAll', () => {
    it('should remove all subscriptions for instance', () => {
      const { subscribeToZoneCommands, subscribeToGlobalEvents, unsubscribeAll } = useWebSocket()
      const handler = vi.fn()
      
      // Создаем несколько подписок
      subscribeToZoneCommands(1, handler)
      subscribeToZoneCommands(2, handler)
      subscribeToGlobalEvents(handler)
      
      expect(__testExports.activeSubscriptions().size).toBe(3)
      
      // Отписываемся все
      unsubscribeAll()
      
      expect(__testExports.activeSubscriptions().size).toBe(0)
      expect(__testExports.getSubscriptionCount('commands.1')).toBe(0)
      expect(__testExports.getSubscriptionCount('commands.2')).toBe(0)
      expect(__testExports.getSubscriptionCount('events.global')).toBe(0)
    })
  })
})

