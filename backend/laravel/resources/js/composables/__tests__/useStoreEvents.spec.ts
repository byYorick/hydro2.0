import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useStoreEvents, storeEvents, zoneEvents, deviceEvents, recipeEvents } from '../useStoreEvents'

describe('useStoreEvents', () => {
  beforeEach(() => {
    // Очищаем все слушатели перед каждым тестом
    storeEvents.removeAllListeners()
  })

  it('should subscribe to events', () => {
    const { subscribe } = useStoreEvents()
    let receivedData: unknown = null

    subscribe('zone:updated', (data) => {
      receivedData = data
    })

    zoneEvents.updated({ id: 1, name: 'Zone 1' })

    expect(receivedData).toEqual({ id: 1, name: 'Zone 1' })
  })

  it('should unsubscribe from events', () => {
    const { subscribe } = useStoreEvents()
    let callCount = 0

    const unsubscribe = subscribe('zone:updated', () => {
      callCount++
    })

    zoneEvents.updated({ id: 1 })
    expect(callCount).toBe(1)

    unsubscribe()
    zoneEvents.updated({ id: 2 })
    expect(callCount).toBe(1) // Не должно увеличиться
  })

  it('should emit events', () => {
    const { emit, subscribe } = useStoreEvents()
    let receivedData: unknown = null

    subscribe('zone:created', (data) => {
      receivedData = data
    })

    emit('zone:created', { id: 1, name: 'New Zone' })

    expect(receivedData).toEqual({ id: 1, name: 'New Zone' })
  })

  it('should handle multiple listeners for same event', () => {
    const { subscribe } = useStoreEvents()
    let callCount1 = 0
    let callCount2 = 0

    subscribe('zone:updated', () => {
      callCount1++
    })

    subscribe('zone:updated', () => {
      callCount2++
    })

    zoneEvents.updated({ id: 1 })

    expect(callCount1).toBe(1)
    expect(callCount2).toBe(1)
  })

  it('should handle zone events', () => {
    const { subscribe } = useStoreEvents()
    const events: Array<{ type: string; data: unknown }> = []

    subscribe('zone:updated', (data) => events.push({ type: 'updated', data }))
    subscribe('zone:created', (data) => events.push({ type: 'created', data }))
    subscribe('zone:deleted', (data) => events.push({ type: 'deleted', data }))
    subscribe('zone:recipe:attached', (data) => events.push({ type: 'recipe:attached', data }))
    subscribe('zone:recipe:detached', (data) => events.push({ type: 'recipe:detached', data }))

    zoneEvents.updated({ id: 1 })
    zoneEvents.created({ id: 2 })
    zoneEvents.deleted(3)
    zoneEvents.recipeAttached({ zoneId: 1, recipeId: 10 })
    zoneEvents.recipeDetached({ zoneId: 1, recipeId: 10 })

    expect(events.length).toBe(5)
    expect(events[0]).toEqual({ type: 'updated', data: { id: 1 } })
    expect(events[1]).toEqual({ type: 'created', data: { id: 2 } })
    expect(events[2]).toEqual({ type: 'deleted', data: 3 })
    expect(events[3]).toEqual({ type: 'recipe:attached', data: { zoneId: 1, recipeId: 10 } })
    expect(events[4]).toEqual({ type: 'recipe:detached', data: { zoneId: 1, recipeId: 10 } })
  })

  it('should handle device events', () => {
    const { subscribe } = useStoreEvents()
    const events: Array<{ type: string; data: unknown }> = []

    subscribe('device:updated', (data) => events.push({ type: 'updated', data }))
    subscribe('device:created', (data) => events.push({ type: 'created', data }))
    subscribe('device:deleted', (data) => events.push({ type: 'deleted', data }))
    subscribe('device:lifecycle:transitioned', (data) => events.push({ type: 'lifecycle:transitioned', data }))

    deviceEvents.updated({ id: 1 })
    deviceEvents.created({ id: 2 })
    deviceEvents.deleted(3)
    deviceEvents.lifecycleTransitioned({ deviceId: 1, fromState: 'ACTIVE', toState: 'DEGRADED' })

    expect(events.length).toBe(4)
    expect(events[0]).toEqual({ type: 'updated', data: { id: 1 } })
    expect(events[1]).toEqual({ type: 'created', data: { id: 2 } })
    expect(events[2]).toEqual({ type: 'deleted', data: 3 })
    expect(events[3]).toEqual({ type: 'lifecycle:transitioned', data: { deviceId: 1, fromState: 'ACTIVE', toState: 'DEGRADED' } })
  })

  it('should handle recipe events', () => {
    const { subscribe } = useStoreEvents()
    const events: Array<{ type: string; data: unknown }> = []

    subscribe('recipe:updated', (data) => events.push({ type: 'updated', data }))
    subscribe('recipe:created', (data) => events.push({ type: 'created', data }))
    subscribe('recipe:deleted', (data) => events.push({ type: 'deleted', data }))

    recipeEvents.updated({ id: 1 })
    recipeEvents.created({ id: 2 })
    recipeEvents.deleted(3)

    expect(events.length).toBe(3)
    expect(events[0]).toEqual({ type: 'updated', data: { id: 1 } })
    expect(events[1]).toEqual({ type: 'created', data: { id: 2 } })
    expect(events[2]).toEqual({ type: 'deleted', data: 3 })
  })

  it('should handle errors in listeners gracefully', () => {
    const { subscribe } = useStoreEvents()
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    subscribe('zone:updated', () => {
      throw new Error('Listener error')
    })

    // Не должно выбрасывать ошибку
    expect(() => {
      zoneEvents.updated({ id: 1 })
    }).not.toThrow()

    consoleErrorSpy.mockRestore()
  })
})
