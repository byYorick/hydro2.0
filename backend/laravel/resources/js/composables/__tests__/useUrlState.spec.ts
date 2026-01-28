import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { useUrlState } from '../useUrlState'

const makeComponent = (options: Parameters<typeof useUrlState>[0]) => {
  return defineComponent({
    setup() {
      const state = useUrlState(options)
      return { state }
    },
    template: '<div />',
  })
}

describe('useUrlState', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    window.history.replaceState({}, '', '/test')
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  it('reads initial value from URL', async () => {
    window.history.replaceState({}, '', '/test?q=hello')
    const wrapper = mount(makeComponent({ key: 'q', defaultValue: '' }))

    await nextTick()

    expect(wrapper.vm.state).toBe('hello')
  })

  it('writes to URL when state changes', async () => {
    const wrapper = mount(makeComponent({ key: 'q', defaultValue: '' }))

    wrapper.vm.state = 'updated'
    await nextTick()

    expect(window.location.search).toContain('q=updated')
  })

  it('clears URL param when returning to default', async () => {
    window.history.replaceState({}, '', '/test?q=hello')
    const wrapper = mount(makeComponent({ key: 'q', defaultValue: '' }))

    wrapper.vm.state = ''
    await nextTick()

    expect(window.location.search).not.toContain('q=')
  })

  it('debounces URL updates', async () => {
    const wrapper = mount(makeComponent({ key: 'q', defaultValue: '', debounceMs: 200 }))

    wrapper.vm.state = 'slow'
    await nextTick()

    expect(window.location.search).not.toContain('q=slow')
    await vi.advanceTimersByTimeAsync(210)

    expect(window.location.search).toContain('q=slow')
  })

  it('syncs state on popstate', async () => {
    const wrapper = mount(makeComponent({ key: 'q', defaultValue: '' }))

    window.history.replaceState({}, '', '/test?q=next')
    window.dispatchEvent(new PopStateEvent('popstate'))
    await nextTick()

    expect(wrapper.vm.state).toBe('next')
  })
})
