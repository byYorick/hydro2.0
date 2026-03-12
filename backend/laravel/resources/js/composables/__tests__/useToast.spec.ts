import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useToast, clearAllToasts } from '../useToast'

describe('useToast', () => {
  beforeEach(() => {
    clearAllToasts() // Очищаем глобальное состояние перед каждым тестом
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should initialize with empty toasts', () => {
    const { toasts } = useToast()
    expect(toasts.value).toEqual([])
  })

  it('should show toast notification', () => {
    const { showToast, toasts } = useToast()
    
    const id = showToast('Test message', 'info', 3000)
    
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0]).toMatchObject({
      id,
      message: 'Test message',
      variant: 'info',
      duration: 3000
    })
  })

  it('should remove toast after duration', () => {
    const { showToast, toasts } = useToast()
    
    showToast('Test message', 'info', 3000)
    expect(toasts.value).toHaveLength(1)
    
    vi.advanceTimersByTime(3000)
    
    expect(toasts.value).toHaveLength(0)
  })

  it('should not remove toast with duration 0', () => {
    const { showToast, toasts } = useToast()
    
    showToast('Persistent message', 'info', 0)
    expect(toasts.value).toHaveLength(1)
    
    vi.advanceTimersByTime(10000)
    
    expect(toasts.value).toHaveLength(1) // Still there
  })

  it('should remove toast manually', () => {
    const { showToast, removeToast, toasts } = useToast()
    
    const id = showToast('Test message', 'info', 5000)
    expect(toasts.value).toHaveLength(1)
    
    removeToast(id)
    
    expect(toasts.value).toHaveLength(0)
  })

  it('should show success toast', () => {
    const { success, toasts } = useToast()
    
    const id = success('Operation successful')
    
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0]).toMatchObject({
      id,
      message: 'Operation successful',
      variant: 'success',
      duration: 3000
    })
  })

  it('should show error toast', () => {
    const { error, toasts } = useToast()
    
    const id = error('Operation failed')
    
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0]).toMatchObject({
      id,
      message: 'Operation failed',
      variant: 'error',
      duration: 5000
    })
  })

  it('should show warning toast', () => {
    const { warning, toasts } = useToast()
    
    const id = warning('Warning message')
    
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0]).toMatchObject({
      id,
      message: 'Warning message',
      variant: 'warning',
      duration: 3000 // TOAST_TIMEOUT.NORMAL
    })
  })

  it('should show info toast', () => {
    const { info, toasts } = useToast()
    
    const id = info('Info message')
    
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0]).toMatchObject({
      id,
      message: 'Info message',
      variant: 'info',
      duration: 3000
    })
  })

  it('should allow custom duration for helper methods', () => {
    const { success, toasts } = useToast()
    
    success('Custom duration', 10000)
    
    expect(toasts.value[0].duration).toBe(10000)
  })

  it('should clear all toasts', () => {
    const { showToast, clearAll, toasts } = useToast()
    
    showToast('Message 1', 'info')
    showToast('Message 2', 'success')
    showToast('Message 3', 'error')
    
    expect(toasts.value).toHaveLength(3)
    
    clearAll()
    
    expect(toasts.value).toHaveLength(0)
  })

  it('should generate unique IDs for toasts', () => {
    const { showToast } = useToast()
    
    const id1 = showToast('Message 1')
    const id2 = showToast('Message 2')
    const id3 = showToast('Message 3')
    
    expect(id1).not.toBe(id2)
    expect(id2).not.toBe(id3)
    expect(id1).not.toBe(id3)
  })

  it('should handle multiple toasts with different durations', () => {
    const { showToast, toasts } = useToast()
    
    showToast('Short', 'info', 1000)
    showToast('Medium', 'info', 3000)
    showToast('Long', 'info', 5000)
    
    expect(toasts.value).toHaveLength(3)
    
    vi.advanceTimersByTime(1000)
    expect(toasts.value).toHaveLength(2)
    
    vi.advanceTimersByTime(2000)
    expect(toasts.value).toHaveLength(1)
    
    vi.advanceTimersByTime(2000)
    expect(toasts.value).toHaveLength(0)
  })
})

