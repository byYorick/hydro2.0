import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  useDebounce,
  useThrottle,
  useBatchUpdates,
  useOptimizedWatcher,
  useVirtualList,
  useTelemetryBatch
} from '../useOptimizedUpdates'

describe('useOptimizedUpdates', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('useDebounce', () => {
    it('should debounce function calls', () => {
      const fn = vi.fn()
      const debouncedFn = useDebounce(fn, 300)
      
      debouncedFn('arg1')
      debouncedFn('arg2')
      debouncedFn('arg3')
      
      expect(fn).not.toHaveBeenCalled()
      
      vi.advanceTimersByTime(300)
      
      expect(fn).toHaveBeenCalledTimes(1)
      expect(fn).toHaveBeenCalledWith('arg3')
    })

    it('should reset timer on new calls', () => {
      const fn = vi.fn()
      const debouncedFn = useDebounce(fn, 300)
      
      debouncedFn('call1')
      vi.advanceTimersByTime(200)
      
      debouncedFn('call2')
      vi.advanceTimersByTime(200)
      
      expect(fn).not.toHaveBeenCalled()
      
      vi.advanceTimersByTime(100)
      
      expect(fn).toHaveBeenCalledTimes(1)
      expect(fn).toHaveBeenCalledWith('call2')
    })
  })

  describe('useThrottle', () => {
    it('should throttle function calls', () => {
      const fn = vi.fn()
      const throttledFn = useThrottle(fn, 300)
      
      throttledFn('call1')
      expect(fn).toHaveBeenCalledTimes(1)
      expect(fn).toHaveBeenCalledWith('call1')
      
      throttledFn('call2')
      throttledFn('call3')
      
      expect(fn).toHaveBeenCalledTimes(1) // Still only 1 call
      
      vi.advanceTimersByTime(300)
      
      throttledFn('call4')
      expect(fn).toHaveBeenCalledTimes(2)
      expect(fn).toHaveBeenCalledWith('call4')
    })
  })

  describe('useBatchUpdates', () => {
    it('should batch updates', () => {
      const updateFn = vi.fn()
      const { add } = useBatchUpdates(updateFn, { debounceMs: 100 })
      
      add('item1')
      add('item2')
      add('item3')
      
      expect(updateFn).not.toHaveBeenCalled()
      
      vi.advanceTimersByTime(100)
      
      expect(updateFn).toHaveBeenCalledTimes(1)
      expect(updateFn).toHaveBeenCalledWith(['item1', 'item2', 'item3'])
    })

    it('should flush immediately when max batch size reached', () => {
      const updateFn = vi.fn()
      const { add } = useBatchUpdates(updateFn, { 
        debounceMs: 100,
        maxBatchSize: 3
      })
      
      add('item1')
      add('item2')
      add('item3')
      
      // Should flush immediately
      expect(updateFn).toHaveBeenCalledTimes(1)
      expect(updateFn).toHaveBeenCalledWith(['item1', 'item2', 'item3'])
    })

    it('should flush when max wait time reached', () => {
      const updateFn = vi.fn()
      const { add } = useBatchUpdates(updateFn, { 
        debounceMs: 100,
        maxWaitMs: 200
      })
      
      add('item1')
      vi.advanceTimersByTime(200)
      
      expect(updateFn).toHaveBeenCalledTimes(1)
      expect(updateFn).toHaveBeenCalledWith(['item1'])
    })

    it('should allow manual flush', () => {
      const updateFn = vi.fn()
      const { add, flush } = useBatchUpdates(updateFn, { debounceMs: 1000 })
      
      add('item1')
      add('item2')
      
      expect(updateFn).not.toHaveBeenCalled()
      
      flush()
      
      expect(updateFn).toHaveBeenCalledTimes(1)
      expect(updateFn).toHaveBeenCalledWith(['item1', 'item2'])
    })

    it('should return batch size', () => {
      const updateFn = vi.fn()
      const { add, getBatchSize } = useBatchUpdates(updateFn)
      
      expect(getBatchSize()).toBe(0)
      
      add('item1')
      expect(getBatchSize()).toBe(1)
      
      add('item2')
      expect(getBatchSize()).toBe(2)
    })
  })

  describe('useOptimizedWatcher', () => {
    it('should debounce watcher callbacks', async () => {
      const callback = vi.fn()
      const source = ref(1)
      
      useOptimizedWatcher(source, callback, 100)
      
      // watch с immediate: true вызывает callback сразу, но это может быть асинхронно
      await vi.runAllTimersAsync()
      expect(callback).toHaveBeenCalledWith(1)
      callback.mockClear()
      
      source.value = 2
      source.value = 3
      source.value = 4
      
      // Callback не должен быть вызван сразу после изменений
      expect(callback).not.toHaveBeenCalled()
      
      // Используем runAllTimersAsync для обработки всех таймеров
      await vi.runAllTimersAsync()
      
      // После debounce должен быть вызван с последним значением
      expect(callback).toHaveBeenCalledTimes(1)
      expect(callback).toHaveBeenCalledWith(4)
    })

    it('should call immediately on function source', async () => {
      const callback = vi.fn()
      const value = ref(1)
      const source = () => value.value
      
      useOptimizedWatcher(source, callback, 100)
      
      // watch с immediate: true вызывает callback сразу, но это может быть асинхронно
      // Используем runAllTimersAsync для обработки всех асинхронных операций
      await vi.runAllTimersAsync()
      expect(callback).toHaveBeenCalledWith(1)
    })
  })

  describe('useVirtualList', () => {
    it('should calculate visible range', () => {
      const items = ref([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
      const { visibleRange, visibleItems } = useVirtualList(items, {
        itemHeight: 50,
        containerHeight: 200,
        overscan: 1
      })
      
      expect(visibleRange.value.start).toBeGreaterThanOrEqual(0)
      expect(visibleRange.value.end).toBeLessThanOrEqual(items.value.length)
      expect(visibleItems.value.length).toBeGreaterThan(0)
    })

    it('should calculate total height', () => {
      const items = ref([1, 2, 3, 4, 5])
      const { totalHeight } = useVirtualList(items, {
        itemHeight: 50,
        containerHeight: 200
      })
      
      expect(totalHeight.value).toBe(250) // 5 items * 50px
    })

    it('should calculate offset Y', () => {
      const items = ref([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
      const { offsetY, onScroll } = useVirtualList(items, {
        itemHeight: 50,
        containerHeight: 200
      })
      
      const mockEvent = {
        target: {
          scrollTop: 100
        }
      } as unknown as Event
      
      onScroll(mockEvent)
      
      expect(offsetY.value).toBeGreaterThanOrEqual(0)
    })
  })

  describe('useTelemetryBatch', () => {
    it('should batch telemetry updates', () => {
      const updateFn = vi.fn()
      const { addUpdate } = useTelemetryBatch(updateFn, 100)
      
      addUpdate('zone1', 'ph', 6.0)
      addUpdate('zone1', 'ec', 1.5)
      addUpdate('zone2', 'ph', 5.8)
      
      expect(updateFn).not.toHaveBeenCalled()
      
      vi.advanceTimersByTime(100)
      
      expect(updateFn).toHaveBeenCalledTimes(1)
      const updates = updateFn.mock.calls[0][0] as Map<string, Map<string, number>>
      
      expect(updates.has('zone1')).toBe(true)
      expect(updates.has('zone2')).toBe(true)
      expect(updates.get('zone1')?.get('ph')).toBe(6.0)
      expect(updates.get('zone1')?.get('ec')).toBe(1.5)
      expect(updates.get('zone2')?.get('ph')).toBe(5.8)
    })

    it('should allow manual flush', () => {
      const updateFn = vi.fn()
      const { addUpdate, flush } = useTelemetryBatch(updateFn, 1000)
      
      addUpdate('zone1', 'ph', 6.0)
      
      flush()
      
      expect(updateFn).toHaveBeenCalledTimes(1)
    })
  })
})

