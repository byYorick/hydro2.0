import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useSchedulerHotkeys } from '../useSchedulerHotkeys'

interface Handlers {
  next: ReturnType<typeof vi.fn>
  prev: ReturnType<typeof vi.fn>
  open: ReturnType<typeof vi.fn>
  refresh: ReturnType<typeof vi.fn>
  close: ReturnType<typeof vi.fn>
}

function createHarness(handlers: Handlers) {
  return defineComponent({
    setup() {
      useSchedulerHotkeys({
        onNext: handlers.next,
        onPrev: handlers.prev,
        onOpen: handlers.open,
        onRefresh: handlers.refresh,
        onClose: handlers.close,
      })
    },
    render() {
      return h('div', { tabindex: 0 }, 'host')
    },
  })
}

function makeHandlers(): Handlers {
  return {
    next: vi.fn(),
    prev: vi.fn(),
    open: vi.fn(),
    refresh: vi.fn(),
    close: vi.fn(),
  }
}

function fireKey(key: string, options: Partial<KeyboardEventInit> = {}): void {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...options })
  window.dispatchEvent(event)
}

describe('useSchedulerHotkeys', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('вызывает onNext на "j"', () => {
    const handlers = makeHandlers()
    const wrapper = mount(createHarness(handlers))

    fireKey('j')

    expect(handlers.next).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('вызывает onPrev на "k"', () => {
    const handlers = makeHandlers()
    const wrapper = mount(createHarness(handlers))

    fireKey('K')

    expect(handlers.prev).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('вызывает onOpen на Enter и onClose на Escape', () => {
    const handlers = makeHandlers()
    const wrapper = mount(createHarness(handlers))

    fireKey('Enter')
    fireKey('Escape')

    expect(handlers.open).toHaveBeenCalledTimes(1)
    expect(handlers.close).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('вызывает onRefresh на "r"', () => {
    const handlers = makeHandlers()
    const wrapper = mount(createHarness(handlers))

    fireKey('r')

    expect(handlers.refresh).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('игнорирует хоткеи при активной модификации (Ctrl)', () => {
    const handlers = makeHandlers()
    const wrapper = mount(createHarness(handlers))

    fireKey('r', { ctrlKey: true })
    fireKey('j', { metaKey: true })
    fireKey('k', { altKey: true })

    expect(handlers.refresh).not.toHaveBeenCalled()
    expect(handlers.next).not.toHaveBeenCalled()
    expect(handlers.prev).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('игнорирует хоткеи внутри input/textarea', () => {
    const handlers = makeHandlers()
    const wrapper = mount(createHarness(handlers))

    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()

    const event = new KeyboardEvent('keydown', { key: 'j', bubbles: true, cancelable: true })
    Object.defineProperty(event, 'target', { value: input })
    window.dispatchEvent(event)

    expect(handlers.next).not.toHaveBeenCalled()
    document.body.removeChild(input)
    wrapper.unmount()
  })

  it('отключает слушатель при unmount', () => {
    const handlers = makeHandlers()
    const wrapper = mount(createHarness(handlers))
    wrapper.unmount()

    fireKey('r')

    expect(handlers.refresh).not.toHaveBeenCalled()
  })
})
