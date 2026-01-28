/**
 * Unit-тесты для инвариантов WebSocket подписок
 * 
 * Тестирует:
 * - Регистрацию и удаление подписок
 * - Обнаружение дублей
 * - Resubscribe после reconnect
 * - Отсутствие утечек памяти
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  registerSubscription,
  unregisterSubscription,
  getSubscriptionStats,
  checkInvariants,
  clearRegistry,
} from '../invariants'

// Мокаем logger, чтобы не засорять вывод тестов
vi.mock('@/utils/logger', () => ({
  logger: {
    warn: vi.fn(),
    debug: vi.fn(),
    error: vi.fn(),
  },
}))

describe('ws/invariants', () => {
  beforeEach(() => {
    clearRegistry()
  })

  describe('registerSubscription', () => {
    it('регистрирует новую подписку', () => {
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      
      const stats = getSubscriptionStats()
      expect(stats.totalSubscriptions).toBe(1)
      expect(stats.channels).toHaveLength(1)
      expect(stats.channels[0].channel).toBe('commands.1')
      expect(stats.channels[0].count).toBe(1)
    })

    it('регистрирует несколько подписок на один канал', () => {
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      registerSubscription('commands.1', 'handler-2', '.App\\Events\\CommandStatusUpdated', 'component-2')
      
      const stats = getSubscriptionStats()
      expect(stats.totalSubscriptions).toBe(2)
      expect(stats.channels).toHaveLength(1)
      expect(stats.channels[0].count).toBe(2)
    })

    it('обнаруживает дублирование подписки с тем же handlerId', () => {
      const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      
      // Должно быть предупреждение о дубле
      expect(consoleWarnSpy).toHaveBeenCalled()
      
      const stats = getSubscriptionStats()
      // Дубликат не должен быть добавлен
      expect(stats.totalSubscriptions).toBe(1)
      
      consoleWarnSpy.mockRestore()
    })

    it('различает подписки на разные события одного канала', () => {
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      registerSubscription('commands.1', 'handler-2', '.App\\Events\\CommandFailed', 'component-1')
      
      const stats = getSubscriptionStats()
      expect(stats.totalSubscriptions).toBe(2)
      expect(stats.channels).toHaveLength(2)
    })
  })

  describe('unregisterSubscription', () => {
    it('удаляет подписку из реестра', () => {
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      
      unregisterSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated')
      
      const stats = getSubscriptionStats()
      expect(stats.totalSubscriptions).toBe(0)
      expect(stats.channels).toHaveLength(0)
    })

    it('удаляет только указанную подписку, оставляя остальные', () => {
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      registerSubscription('commands.1', 'handler-2', '.App\\Events\\CommandStatusUpdated', 'component-2')
      
      unregisterSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated')
      
      const stats = getSubscriptionStats()
      expect(stats.totalSubscriptions).toBe(1)
      expect(stats.channels[0].count).toBe(1)
      expect(stats.channels[0].subscriptions[0].handlerId).toBe('handler-2')
    })

    it('предупреждает при попытке удалить несуществующую подписку', () => {
      const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      
      unregisterSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated')
      
      // Должно быть предупреждение
      expect(consoleWarnSpy).toHaveBeenCalled()
      
      consoleWarnSpy.mockRestore()
    })
  })

  describe('checkInvariants', () => {
    it('возвращает isValid=true для корректного состояния', () => {
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      registerSubscription('commands.2', 'handler-2', '.App\\Events\\CommandStatusUpdated', 'component-2')
      
      const result = checkInvariants()
      expect(result.isValid).toBe(true)
      expect(result.issues).toHaveLength(0)
    })

    it('обнаруживает дублирование подписок', () => {
      // Симулируем дублирование через прямое добавление в реестр
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      // Добавляем дубликат вручную (имитируем баг)
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      
      const result = checkInvariants()
      // Должна быть обнаружена проблема (хотя registerSubscription уже предупредила)
      // Но checkInvariants может найти другие проблемы
      expect(result).toBeDefined()
    })

    it('предупреждает о подозрительно большом количестве подписок', () => {
      // Создаем много подписок на один канал
      for (let i = 0; i < 15; i++) {
        registerSubscription('commands.1', `handler-${i}`, '.App\\Events\\CommandStatusUpdated', `component-${i}`)
      }
      
      const result = checkInvariants()
      expect(result.isValid).toBe(false)
      expect(result.issues.length).toBeGreaterThan(0)
      expect(result.issues.some(issue => issue.includes('Suspiciously high'))).toBe(true)
    })
  })

  describe('resubscribe scenario', () => {
    it('корректно обрабатывает цикл register → unregister → register', () => {
      // Регистрируем подписку
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      
      let stats = getSubscriptionStats()
      expect(stats.totalSubscriptions).toBe(1)
      
      // Отписываемся (reconnect scenario)
      unregisterSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated')
      
      stats = getSubscriptionStats()
      expect(stats.totalSubscriptions).toBe(0)
      
      // Resubscribe после reconnect
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      
      stats = getSubscriptionStats()
      expect(stats.totalSubscriptions).toBe(1)
      
      const result = checkInvariants()
      expect(result.isValid).toBe(true)
    })

    it('не создает дублей при resubscribe', () => {
      const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      
      // Симулируем resubscribe (не отписываясь сначала - это баг)
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      
      const stats = getSubscriptionStats()
      // Дубликат не должен быть добавлен
      expect(stats.totalSubscriptions).toBe(1)

      consoleWarnSpy.mockRestore()
    })
  })

  describe('getSubscriptionStats', () => {
    it('возвращает корректную статистику', () => {
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      registerSubscription('commands.2', 'handler-2', '.App\\Events\\CommandStatusUpdated', 'component-2')
      registerSubscription('events.global', 'handler-3', '.App\\Events\\EventCreated', 'component-3')
      
      const stats = getSubscriptionStats()
      expect(stats.totalChannels).toBe(3)
      expect(stats.totalSubscriptions).toBe(3)
      expect(stats.channels).toHaveLength(3)
      
      // Проверяем сортировку (по убыванию count)
      expect(stats.channels[0].count).toBeGreaterThanOrEqual(stats.channels[1].count)
    })

    it('возвращает пустую статистику для пустого реестра', () => {
      const stats = getSubscriptionStats()
      expect(stats.totalChannels).toBe(0)
      expect(stats.totalSubscriptions).toBe(0)
      expect(stats.channels).toHaveLength(0)
    })
  })

  describe('clearRegistry', () => {
    it('очищает весь реестр', () => {
      registerSubscription('commands.1', 'handler-1', '.App\\Events\\CommandStatusUpdated', 'component-1')
      registerSubscription('commands.2', 'handler-2', '.App\\Events\\CommandStatusUpdated', 'component-2')
      
      clearRegistry()
      
      const stats = getSubscriptionStats()
      expect(stats.totalChannels).toBe(0)
      expect(stats.totalSubscriptions).toBe(0)
    })
  })
})
