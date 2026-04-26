import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CalibrationBreadcrumb from '../CalibrationBreadcrumb.vue'

describe('CalibrationBreadcrumb', () => {
  it('renders sub, title, description', () => {
    const w = mount(CalibrationBreadcrumb, {
      props: {
        sub: 'pumps',
        title: 'Дозирующие насосы',
        description: 'Калибровка ml/sec.',
      },
    })
    expect(w.text()).toContain('/ зона / калибровка / pumps')
    expect(w.text()).toContain('Дозирующие насосы')
    expect(w.text()).toContain('Калибровка ml/sec.')
  })
})
