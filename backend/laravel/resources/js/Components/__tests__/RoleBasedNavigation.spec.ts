import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import RoleBasedNavigation from '../RoleBasedNavigation.vue'
// @ts-ignore
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

function mountForRole(role: string) {
  mockPage.mockReturnValue({
    props: {
      auth: {
        user: { role }
      }
    }
  })

  return mount(RoleBasedNavigation)
}

function hrefs(wrapper: ReturnType<typeof mount>) {
  return wrapper.findAllComponents(NavLink).map((link) => link.props('href'))
}

function labels(wrapper: ReturnType<typeof mount>) {
  return wrapper.findAllComponents(NavLink).map((link) => link.props('label'))
}

describe('RoleBasedNavigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a simple read-only menu for viewer', () => {
    const wrapper = mountForRole('viewer')

    expect(labels(wrapper)).toEqual(['Обзор', 'Зоны', 'Тревоги', 'Настройки'])
    expect(wrapper.text()).not.toContain('Рецепты')
    expect(wrapper.text()).not.toContain('Запуск')
    expect(wrapper.text()).not.toContain('Пользователи')
    expect(wrapper.text()).not.toContain('Аудит')
    expect(wrapper.text()).not.toContain('Логи')
    expect(wrapper.text()).not.toContain('Узлы')
    expect(wrapper.text()).not.toContain('Аналитика')
    expect(wrapper.text()).not.toContain('Здоровье системы')
  })

  it('renders exactly five operator items in order', () => {
    const wrapper = mountForRole('operator')

    expect(hrefs(wrapper)).toEqual([
      '/',
      '/zones',
      '/alerts',
      '/documentation/fertigation',
      '/settings',
    ])
    expect(labels(wrapper)).toEqual([
      'Сегодня',
      'Зоны',
      'Тревоги',
      'Справочник',
      'Профиль',
    ])
    expect(wrapper.text()).not.toContain('Рецепты')
    expect(wrapper.text()).not.toContain('Узлы')
    expect(wrapper.text()).not.toContain('Устройства')
    expect(wrapper.text()).not.toContain('Здоровье системы')
    expect(wrapper.text()).not.toContain('Сервисы')
    expect(wrapper.text()).not.toContain('Запуск')
    expect(wrapper.text()).not.toContain('Аналитика')
  })

  it('renders agronomist items without devices or system tools', () => {
    const wrapper = mountForRole('agronomist')

    expect(hrefs(wrapper)).toEqual([
      '/',
      '/zones',
      '/recipes',
      '/analytics',
      '/alerts',
      '/launch',
      '/documentation/fertigation',
    ])
    expect(labels(wrapper)).toEqual([
      'Обзор',
      'Зоны',
      'Рецепты',
      'Аналитика',
      'Тревоги',
      'Запуск',
      'Справочник',
    ])
    expect(wrapper.text()).not.toContain('Узлы')
    expect(wrapper.text()).not.toContain('Устройства')
    expect(wrapper.text()).not.toContain('Здоровье системы')
    expect(wrapper.text()).not.toContain('Логи')
    expect(wrapper.text()).not.toContain('Аудит')
    expect(wrapper.text()).not.toContain('Пользователи')
    expect(wrapper.text()).not.toContain('Культуры')
  })

  it('renders engineer items with nodes first', () => {
    const wrapper = mountForRole('engineer')

    expect(hrefs(wrapper)).toEqual([
      '/devices',
      '/',
      '/zones',
      '/alerts',
      '/monitoring',
      '/logs',
    ])
    expect(labels(wrapper)[0]).toBe('Узлы')
    expect(wrapper.text()).toContain('Обзор')
    expect(wrapper.text()).toContain('Здоровье системы')
    expect(wrapper.text()).not.toContain('Рецепты')
    expect(wrapper.text()).not.toContain('Запуск')
    expect(wrapper.text()).not.toContain('Аналитика')
    expect(wrapper.text()).not.toContain('Пользователи')
    expect(wrapper.text()).not.toContain('Аудит')
  })

  it('renders admin items with users instead of operators', () => {
    const wrapper = mountForRole('admin')

    expect(hrefs(wrapper)).toEqual([
      '/',
      '/alerts',
      '/monitoring',
      '/users',
      '/audit',
      '/zones',
      '/devices',
      '/settings',
    ])
    expect(labels(wrapper)[0]).toBe('Система')
    expect(wrapper.text()).toContain('Пользователи')
    expect(wrapper.text()).not.toContain('Операторы')
    expect(wrapper.text()).toContain('Журнал')
    expect(wrapper.text()).not.toContain('Аудит')
    expect(wrapper.text()).not.toContain('Логи')
    expect(wrapper.text()).toContain('Здоровье системы')
    expect(wrapper.text()).toContain('Узлы')
    expect(wrapper.text()).not.toContain('Рецепты')
    expect(wrapper.text()).not.toContain('Культуры')
    expect(wrapper.text()).not.toContain('Запуск')
  })

  it('renders NavLink components for visible items', () => {
    const wrapper = mountForRole('viewer')
    const navLinks = wrapper.findAllComponents(NavLink)

    expect(navLinks.length).toBeGreaterThan(0)
  })
})
