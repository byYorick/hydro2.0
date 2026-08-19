import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RepeatPathHint from '../RepeatPathHint.vue'

describe('RepeatPathHint', () => {
  it('renders hint and optional jump buttons', async () => {
    const w = mount(RepeatPathHint, {
      props: { showAutomation: true, showCalibration: false },
    })
    expect(w.find('[data-testid="launch-repeat-path-hint"]').exists()).toBe(true)
    expect(w.text()).toContain('вынесены в сторону')
    expect(w.text()).toContain('Автоматика')
    expect(w.text()).not.toContain('Калибровка')
    await w.findAll('button')[0].trigger('click')
    expect(w.emitted('open-automation')).toBeTruthy()
  })
})
