import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PhaseStrip from '../PhaseStrip.vue'

describe('PhaseStrip', () => {
  it('renders placeholder when phases are empty', () => {
    const w = mount(PhaseStrip, { props: { phases: [] } })
    expect(w.text()).toContain('Фазы появятся')
  })

  it('renders one segment per phase with name + days', () => {
    const w = mount(PhaseStrip, {
      props: {
        phases: [
          { name: 'Germination', days: 7 },
          { name: 'Vegetation', days: 21 },
          { name: 'Harvest', days: 14 },
        ],
      },
    })
    expect(w.text()).toContain('Germination')
    expect(w.text()).toContain('7д')
    expect(w.text()).toContain('Vegetation')
    expect(w.text()).toContain('21д')
    expect(w.text()).toContain('Harvest')
    expect(w.text()).toContain('14д')
  })

  it('renders pH/EC row when expanded=true', () => {
    const w = mount(PhaseStrip, {
      props: {
        phases: [{ name: 'P1', days: 10, ph: 5.8, ec: 1.2 }],
        expanded: true,
      },
    })
    expect(w.text()).toContain('pH 5.8')
    expect(w.text()).toContain('EC 1.2')
  })

  it('uses default name "Фаза N" when name missing', () => {
    const w = mount(PhaseStrip, {
      props: { phases: [{ days: 5 }, { days: 10 }] },
    })
    expect(w.text()).toContain('Фаза 1')
    expect(w.text()).toContain('Фаза 2')
  })
})
