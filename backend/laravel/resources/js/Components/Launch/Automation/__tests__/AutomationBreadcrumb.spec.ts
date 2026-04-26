import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AutomationBreadcrumb from '../AutomationBreadcrumb.vue'

describe('AutomationBreadcrumb', () => {
  it('renders sub, title, description', () => {
    const w = mount(AutomationBreadcrumb, {
      props: {
        sub: 'bindings',
        title: 'Привязки узлов',
        description: 'Обязательные и опциональные роли.',
      },
    })
    expect(w.text()).toContain('/ зона / автоматика / bindings')
    expect(w.text()).toContain('Привязки узлов')
    expect(w.text()).toContain('Обязательные и опциональные роли.')
  })
})
