import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import RoleBasedNavigation from '../RoleBasedNavigation.vue'
import NavLink from '../NavLink.vue'

// Mock useRole
const mockUseRole = vi.fn()
vi.mock('@/composables/useRole', () => ({
  useRole: () => mockUseRole()
}))

// Mock NavLink
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

  it('should render common navigation items for all roles', () => {
    mockUseRole.mockReturnValue({
      isAgronomist: { value: false },
      isAdmin: { value: false },
      isEngineer: { value: false },
      isOperator: { value: false },
      isViewer: { value: false },
    })

    const wrapper = mount(RoleBasedNavigation)
    
    expect(wrapper.text()).toContain('Панель управления')
    expect(wrapper.text()).toContain('Алерты')
  })

  it('should render agronomist navigation', () => {
    mockUseRole.mockReturnValue({
      isAgronomist: { value: true },
      isAdmin: { value: false },
      isEngineer: { value: false },
      isOperator: { value: false },
      isViewer: { value: false },
    })

    const wrapper = mount(RoleBasedNavigation)
    
    expect(wrapper.text()).toContain('Зоны')
    expect(wrapper.text()).toContain('Рецепты')
    expect(wrapper.text()).toContain('Аналитика')
    expect(wrapper.text()).toContain('Настройки')
  })

  it('should render admin navigation', () => {
    mockUseRole.mockReturnValue({
      isAgronomist: { value: false },
      isAdmin: { value: true },
      isEngineer: { value: false },
      isOperator: { value: false },
      isViewer: { value: false },
    })

    const wrapper = mount(RoleBasedNavigation)
    
    expect(wrapper.text()).toContain('Зоны')
    expect(wrapper.text()).toContain('Устройства')
    expect(wrapper.text()).toContain('Рецепты')
    expect(wrapper.text()).toContain('Пользователи')
    expect(wrapper.text()).toContain('Логи')
    expect(wrapper.text()).toContain('Настройки')
  })

  it('should render engineer navigation', () => {
    mockUseRole.mockReturnValue({
      isAgronomist: { value: false },
      isAdmin: { value: false },
      isEngineer: { value: true },
      isOperator: { value: false },
      isViewer: { value: false },
    })

    const wrapper = mount(RoleBasedNavigation)
    
    expect(wrapper.text()).toContain('Зоны')
    expect(wrapper.text()).toContain('Устройства')
    expect(wrapper.text()).toContain('Система')
    expect(wrapper.text()).toContain('Логи')
    expect(wrapper.text()).toContain('Настройки')
  })

  it('should render operator navigation', () => {
    mockUseRole.mockReturnValue({
      isAgronomist: { value: false },
      isAdmin: { value: false },
      isEngineer: { value: false },
      isOperator: { value: true },
      isViewer: { value: false },
    })

    const wrapper = mount(RoleBasedNavigation)
    
    expect(wrapper.text()).toContain('Зоны')
    expect(wrapper.text()).toContain('Устройства')
    expect(wrapper.text()).toContain('Рецепты')
    expect(wrapper.text()).toContain('Логи')
    expect(wrapper.text()).toContain('Настройки')
  })

  it('should render viewer navigation without settings', () => {
    mockUseRole.mockReturnValue({
      isAgronomist: { value: false },
      isAdmin: { value: false },
      isEngineer: { value: false },
      isOperator: { value: false },
      isViewer: { value: true },
    })

    const wrapper = mount(RoleBasedNavigation)
    
    expect(wrapper.text()).toContain('Зоны')
    expect(wrapper.text()).toContain('Устройства')
    expect(wrapper.text()).toContain('Рецепты')
    expect(wrapper.text()).not.toContain('Настройки')
  })

  it('should render all NavLink components', () => {
    mockUseRole.mockReturnValue({
      isAgronomist: { value: false },
      isAdmin: { value: true },
      isEngineer: { value: false },
      isOperator: { value: false },
      isViewer: { value: false },
    })

    const wrapper = mount(RoleBasedNavigation)
    const navLinks = wrapper.findAllComponents(NavLink)
    
    expect(navLinks.length).toBeGreaterThan(0)
  })
})

