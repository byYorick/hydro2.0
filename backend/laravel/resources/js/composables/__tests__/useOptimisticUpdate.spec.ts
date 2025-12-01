import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { useOptimisticUpdate, createOptimisticZoneUpdate, createOptimisticDeviceUpdate, createOptimisticCreate } from '../useOptimisticUpdate'
import { setActivePinia, createPinia } from 'pinia'
import { useZonesStore } from '@/stores/zones'
import { useDevicesStore } from '@/stores/devices'
import type { Zone } from '@/types/Zone'
import type { Device } from '@/types/Device'

// Моки
vi.mock('@/utils/logger', () => ({
  logger: {
    warn: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}))

vi.mock('@/composables/useStoreEvents', () => ({
  zoneEvents: {
    updated: vi.fn(),
    created: vi.fn(),
    deleted: vi.fn(),
  },
  deviceEvents: {
    updated: vi.fn(),
    created: vi.fn(),
    deleted: vi.fn(),
  },
}))

describe('useOptimisticUpdate', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('should apply update immediately', async () => {
    const { performUpdate } = useOptimisticUpdate()
    let applied = false

    const promise = performUpdate('test-1', {
      applyUpdate: () => {
        applied = true
      },
      rollback: () => {
        applied = false
      },
      syncWithServer: async () => {
        return { success: true }
      },
      showLoading: false,
    })

    // Обновление должно быть применено сразу
    expect(applied).toBe(true)

    await promise
    expect(applied).toBe(true)
  })

  it('should rollback on error', async () => {
    const { performUpdate } = useOptimisticUpdate()
    let applied = false
    let rolledBack = false

    try {
      await performUpdate('test-2', {
        applyUpdate: () => {
          applied = true
        },
        rollback: () => {
          rolledBack = true
          applied = false
        },
        syncWithServer: async () => {
          throw new Error('Server error')
        },
        showLoading: false,
      })
    } catch (error) {
      // Ожидаем ошибку
    }

    expect(applied).toBe(false)
    expect(rolledBack).toBe(true)
  })

  it('should call onSuccess callback on success', async () => {
    const { performUpdate } = useOptimisticUpdate()
    let successCalled = false
    let successData: any = null

    await performUpdate('test-3', {
      applyUpdate: () => {},
      rollback: () => {},
      syncWithServer: async () => {
        return { data: 'test' }
      },
      onSuccess: (data) => {
        successCalled = true
        successData = data
      },
      showLoading: false,
    })

    expect(successCalled).toBe(true)
    expect(successData).toEqual({ data: 'test' })
  })

  it('should call onError callback on error', async () => {
    const { performUpdate } = useOptimisticUpdate()
    let errorCalled = false
    let errorData: Error | null = null

    try {
      await performUpdate('test-4', {
        applyUpdate: () => {},
        rollback: () => {},
        syncWithServer: async () => {
          throw new Error('Test error')
        },
        onError: (error) => {
          errorCalled = true
          errorData = error
        },
        showLoading: false,
      })
    } catch (error) {
      // Ожидаем ошибку
    }

    expect(errorCalled).toBe(true)
    expect(errorData?.message).toBe('Test error')
  })

  it('should timeout and rollback if operation takes too long', async () => {
    const { performUpdate } = useOptimisticUpdate()
    let rolledBack = false

    const promise = performUpdate('test-5', {
      applyUpdate: () => {},
      rollback: () => {
        rolledBack = true
      },
      syncWithServer: async () => {
        // Симулируем долгую операцию - используем fake timers
        await new Promise<void>(resolve => {
          setTimeout(() => {
            resolve()
          }, 10000)
        })
        return { data: 'test' }
      },
      timeout: 1000, // 1 секунда таймаут
      showLoading: false,
      onError: () => {},
    })

    const timeoutExpectation = expect(promise).rejects.toThrow('Update timeout')
    
    await vi.advanceTimersByTimeAsync(1500)
    await vi.advanceTimersByTimeAsync(10000)
    
    await timeoutExpectation
    expect(rolledBack).toBe(true)
  })

  it('should track pending updates', async () => {
    const { performUpdate, hasPendingUpdates, getPendingUpdateIds } = useOptimisticUpdate()

    const promise1 = performUpdate('test-6', {
      applyUpdate: () => {},
      rollback: () => {},
      syncWithServer: async () => {
        await new Promise<void>(resolve => setTimeout(() => resolve(), 100))
        return { data: 'test1' }
      },
      showLoading: false,
    })

    const promise2 = performUpdate('test-7', {
      applyUpdate: () => {},
      rollback: () => {},
      syncWithServer: async () => {
        await new Promise<void>(resolve => setTimeout(() => resolve(), 100))
        return { data: 'test2' }
      },
      showLoading: false,
    })

    expect(hasPendingUpdates()).toBe(true)
    expect(getPendingUpdateIds().length).toBe(2)
    expect(getPendingUpdateIds()).toContain('test-6')
    expect(getPendingUpdateIds()).toContain('test-7')

    // Продвигаем время для выполнения промисов
    await vi.advanceTimersByTimeAsync(200)
    
    await Promise.all([promise1, promise2])
  })

  it('should rollback all pending updates', async () => {
    const { performUpdate, rollbackAll } = useOptimisticUpdate()
    let rollbackCount = 0

    const promise1 = performUpdate('test-8', {
      applyUpdate: () => {},
      rollback: () => {
        rollbackCount++
      },
      syncWithServer: async () => {
        await new Promise<void>(resolve => setTimeout(() => resolve(), 100))
        return { data: 'test1' }
      },
      showLoading: false,
    })

    const promise2 = performUpdate('test-9', {
      applyUpdate: () => {},
      rollback: () => {
        rollbackCount++
      },
      syncWithServer: async () => {
        await new Promise<void>(resolve => setTimeout(() => resolve(), 100))
        return { data: 'test2' }
      },
      showLoading: false,
    })

    rollbackAll()
    await vi.advanceTimersByTimeAsync(200)

    expect(rollbackCount).toBe(2)

    // Очищаем промисы
    await promise1.catch(() => {})
    await promise2.catch(() => {})
  })
})

describe('createOptimisticZoneUpdate', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('should create optimistic update for zone', () => {
    const store = useZonesStore()
    const mockZone: Zone = {
      id: 1,
      uid: 'z-1',
      name: 'Zone 1',
      status: 'RUNNING',
      greenhouse_id: 1,
      targets: {
        ph_min: 5.5,
        ph_max: 6.5,
        ec_min: 1.0,
        ec_max: 2.0,
      },
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    }

    store.setZones([mockZone])

    store.initFromProps({ zones: [mockZone] })

    const { applyUpdate, rollback } = createOptimisticZoneUpdate(store, 1, {
      status: 'PAUSED',
    })

    // Применяем обновление (использует optimisticUpsert)
    applyUpdate()
    expect(store.zoneById(1)?.status).toBe('PAUSED')

    // Откатываем (использует rollbackOptimisticUpdate)
    rollback()
    expect(store.zoneById(1)?.status).toBe('RUNNING')
  })
})

describe('createOptimisticDeviceUpdate', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('should create optimistic update for device', () => {
    const store = useDevicesStore()
    const mockDevice: Device = {
      id: 1,
      uid: 'device-1',
      name: 'Device 1',
      type: 'sensor',
      status: 'online',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    }

    store.initFromProps({ devices: [mockDevice] })

    const { applyUpdate, rollback } = createOptimisticDeviceUpdate(store, 1, {
      status: 'offline',
    })

    // Применяем обновление (использует optimisticUpsert)
    applyUpdate()
    expect(store.deviceById(1)?.status).toBe('offline')

    // Откатываем (использует rollbackOptimisticUpdate)
    rollback()
    expect(store.deviceById(1)?.status).toBe('online')
  })
})

describe('createOptimisticCreate', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('should create optimistic create for new item', () => {
    const store = useZonesStore()
    const mockZone: Zone = {
      id: 999, // Временный ID
      uid: 'z-temp',
      name: 'Temp Zone',
      status: 'RUNNING',
      greenhouse_id: 1,
      targets: {
        ph_min: 5.5,
        ph_max: 6.5,
        ec_min: 1.0,
        ec_max: 2.0,
      },
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    }

    const { applyUpdate, rollback } = createOptimisticCreate(store, mockZone, 999)

    // Применяем создание
    applyUpdate()
    expect(store.zoneById(999)).toBeDefined()
    expect(store.zonesCount).toBe(1)

    // Откатываем
    rollback()
    expect(store.zoneById(999)).toBeUndefined()
    expect(store.zonesCount).toBe(0)
  })
})

