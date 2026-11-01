import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import StatusPill from '../StatusPill.vue'

describe('StatusPill', () => {
  it('показывает подпись и тон нормы', () => {
    const wrapper = mount(StatusPill, {
      props: { tone: 'ok' },
      slots: { default: 'В норме' },
    })

    expect(wrapper.text()).toContain('В норме')
    expect(wrapper.classes()).toContain('status-chip--running')
    expect(wrapper.attributes('role')).toBe('status')
  })

  it('отличает offline от критического состояния', () => {
    const offline = mount(StatusPill, { props: { tone: 'offline' }, slots: { default: 'Нет связи' } })
    const critical = mount(StatusPill, { props: { tone: 'critical' }, slots: { default: 'Тревога' } })

    expect(offline.classes()).toContain('status-chip--offline')
    expect(critical.classes()).toContain('status-chip--alarm')
    expect(offline.classes()).not.toContain('status-chip--alarm')
  })
})
