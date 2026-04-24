import { defineComponent, h, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useRafCountdown } from '../useRafCountdown'

describe('useRafCountdown', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  function createHarness(target: Ref<string | null>) {
    return defineComponent({
      setup() {
        const { label, remainingSeconds, expired } = useRafCountdown(target)
        return { label, remainingSeconds, expired }
      },
      render() {
        return h('div', {}, [
          h('span', { 'data-testid': 'label' }, this.label),
          h('span', { 'data-testid': 'seconds' }, String(this.remainingSeconds)),
          h('span', { 'data-testid': 'expired' }, String(this.expired)),
        ])
      },
    })
  }

  it('рендерит "—" если target=null', () => {
    vi.setSystemTime(new Date('2026-02-10T12:00:00Z'))
    const target = ref<string | null>(null)
    const wrapper = mount(createHarness(target))
    expect(wrapper.get('[data-testid="label"]').text()).toBe('—')
    expect(wrapper.get('[data-testid="seconds"]').text()).toBe('null')
    wrapper.unmount()
  })

  it('форматирует MM:SS для интервала <1 часа', () => {
    vi.setSystemTime(new Date('2026-02-10T12:00:00Z'))
    const target = ref<string | null>('2026-02-10T12:02:14Z')
    const wrapper = mount(createHarness(target))
    expect(wrapper.get('[data-testid="label"]').text()).toBe('02:14')
    expect(wrapper.get('[data-testid="expired"]').text()).toBe('false')
    wrapper.unmount()
  })

  it('форматирует HH:MM:SS для больших интервалов', () => {
    vi.setSystemTime(new Date('2026-02-10T12:00:00Z'))
    const target = ref<string | null>('2026-02-10T14:05:30Z')
    const wrapper = mount(createHarness(target))
    expect(wrapper.get('[data-testid="label"]').text()).toBe('02:05:30')
    wrapper.unmount()
  })

  it('помечает expired, если target в прошлом', () => {
    vi.setSystemTime(new Date('2026-02-10T12:00:00Z'))
    const target = ref<string | null>('2026-02-10T11:55:00Z')
    const wrapper = mount(createHarness(target))
    expect(wrapper.get('[data-testid="expired"]').text()).toBe('true')
    expect(wrapper.get('[data-testid="label"]').text()).toBe('00:00')
    wrapper.unmount()
  })

  it('отрабатывает смену target (переключение run)', async () => {
    vi.setSystemTime(new Date('2026-02-10T12:00:00Z'))
    const target = ref<string | null>('2026-02-10T12:01:00Z')
    const wrapper = mount(createHarness(target))
    expect(wrapper.get('[data-testid="label"]').text()).toBe('01:00')

    target.value = '2026-02-10T12:10:00Z'
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-testid="label"]').text()).toBe('10:00')

    target.value = null
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-testid="label"]').text()).toBe('—')
    wrapper.unmount()
  })
})
