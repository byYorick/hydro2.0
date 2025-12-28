import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import RoleBasedNavigation from '../RoleBasedNavigation.vue'
import NavLink from '../NavLink.vue'

const mockPage = vi.fn()
vi.mock('@inertiajs/vue3', () => ({
  usePage: () => mockPage()
}))

vi.mock('../NavLink.vue', () => ({
  default: {
    name: 'NavLink',
    props: ['href', 'label'],
    template: '<a :href="href">{{ label }}</a>'
  }
}))

describe('RoleBasedNavigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders dashboard and common items for viewer', () => {
    mockPage.mockReturnValue({
      props: {
        auth: {
          user: { role: 'viewer' }
        }
      }
    })

    const wrapper = mount(RoleBasedNavigation)

    expect(wrapper.text()).toContain('Дашборд')
    expect(wrapper.text()).toContain('Центр циклов')
    expect(wrapper.text()).toContain('Зоны')
    expect(wrapper.text()).toContain('Теплицы')
    expect(wrapper.text()).toContain('Устройства')
    expect(wrapper.text()).toContain('Алерты')
    expect(wrapper.text()).toContain('Аналитика')
    expect(wrapper.text()).toContain('Сервисы')
    expect(wrapper.text()).toContain('Настройки')
    expect(wrapper.text()).not.toContain('Рецепты')
    expect(wrapper.text()).not.toContain('Культуры')
    expect(wrapper.text()).not.toContain('Операторы')
    expect(wrapper.text()).not.toContain('Логи')
    expect(wrapper.text()).not.toContain('Аудит')
  })

  it('renders agronomist-only items', () => {
    mockPage.mockReturnValue({
      props: {
        auth: {
          user: { role: 'agronomist' }
        }
      }
    })

    const wrapper = mount(RoleBasedNavigation)

    expect(wrapper.text()).toContain('Рецепты')
    expect(wrapper.text()).toContain('Культуры')
    expect(wrapper.text()).toContain('Аналитика')
    expect(wrapper.text()).not.toContain('Операторы')
    expect(wrapper.text()).not.toContain('Логи')
    expect(wrapper.text()).not.toContain('Аудит')
  })

  it('renders admin-only items', () => {
    mockPage.mockReturnValue({
      props: {
        auth: {
          user: { role: 'admin' }
        }
      }
    })

    const wrapper = mount(RoleBasedNavigation)

    expect(wrapper.text()).toContain('Рецепты')
    expect(wrapper.text()).toContain('Культуры')
    expect(wrapper.text()).toContain('Аналитика')
    expect(wrapper.text()).toContain('Операторы')
    expect(wrapper.text()).toContain('Логи')
    expect(wrapper.text()).toContain('Аудит')
  })

  it('renders NavLink components for visible items', () => {
    mockPage.mockReturnValue({
      props: {
        auth: {
          user: { role: 'viewer' }
        }
      }
    })

    const wrapper = mount(RoleBasedNavigation)
    const navLinks = wrapper.findAllComponents(NavLink)

    expect(navLinks.length).toBeGreaterThan(0)
  })
})
