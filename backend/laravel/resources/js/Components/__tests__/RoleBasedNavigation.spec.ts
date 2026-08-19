import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import RoleBasedNavigation, {
  getRoleNavigationGroups,
  getRoleNavigationItems,
} from '../RoleBasedNavigation.vue'
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

function mountForRole(role: string, collapsed = false) {
  mockPage.mockReturnValue({
    props: {
      auth: {
        user: { role }
      }
    }
  })

  return mount(RoleBasedNavigation, {
    props: { collapsed },
  })
}

function hrefs(wrapper: ReturnType<typeof mount>) {
  return wrapper.findAllComponents(NavLink).map((link) => link.props('href'))
}

function labels(wrapper: ReturnType<typeof mount>) {
  return wrapper.findAllComponents(NavLink).map((link) => link.props('label'))
}

function groupLabels(wrapper: ReturnType<typeof mount>) {
  return wrapper.findAll('[data-testid="nav-group-label"]').map((el) => el.text())
}

function itemHrefs(role: string) {
  return getRoleNavigationItems(role).map((item) => item.href)
}

function groupHrefs(role: string) {
  return getRoleNavigationGroups(role).flatMap((group) => group.items.map((item) => item.href))
}

describe('RoleBasedNavigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a simple read-only menu for viewer', () => {
    const wrapper = mountForRole('viewer')

    expect(labels(wrapper)).toEqual(['Обзор', 'Зоны', 'Тревоги', 'Настройки'])
    expect(groupLabels(wrapper)).toEqual(['Работа'])
    expect(wrapper.text()).not.toContain('Рецепты')
    expect(wrapper.text()).not.toContain('Запуск')
    expect(wrapper.text()).not.toContain('Пользователи')
    expect(wrapper.text()).not.toContain('Аудит')
    expect(wrapper.text()).not.toContain('Логи')
    expect(wrapper.text()).not.toContain('Узлы')
    expect(wrapper.text()).not.toContain('Аналитика')
    expect(wrapper.text()).not.toContain('Здоровье системы')
  })

  it('renders exactly five operator items in grouped desktop order', () => {
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
    expect(groupLabels(wrapper)).toEqual(['Работа', 'Помощь'])
    expect(wrapper.text()).not.toContain('Рецепты')
    expect(wrapper.text()).not.toContain('Узлы')
    expect(wrapper.text()).not.toContain('Устройства')
    expect(wrapper.text()).not.toContain('Здоровье системы')
    expect(wrapper.text()).not.toContain('Сервисы')
    expect(wrapper.text()).not.toContain('Запуск')
    expect(wrapper.text()).not.toContain('Аналитика')
    expect(wrapper.text()).not.toContain('Культуры')
  })

  it('renders agronomist desktop groups with plants and nutrients in help', () => {
    const wrapper = mountForRole('agronomist')

    expect(hrefs(wrapper)).toEqual([
      '/',
      '/zones',
      '/alerts',
      '/launch',
      '/recipes',
      '/analytics',
      '/documentation/fertigation',
      '/plants',
      '/nutrients',
    ])
    expect(labels(wrapper)).toEqual([
      'Обзор',
      'Зоны',
      'Тревоги',
      'Запуск',
      'Рецепты',
      'Аналитика',
      'Справочник',
      'Культуры',
      'Удобрения',
    ])
    expect(groupLabels(wrapper)).toEqual(['Работа', 'Объекты', 'Справочники'])
    expect(wrapper.text()).not.toContain('Узлы')
    expect(wrapper.text()).not.toContain('Устройства')
    expect(wrapper.text()).not.toContain('Здоровье системы')
    expect(wrapper.text()).not.toContain('Логи')
    expect(wrapper.text()).not.toContain('Аудит')
    expect(wrapper.text()).not.toContain('Пользователи')
  })

  it('hides group titles when collapsed', () => {
    const wrapper = mountForRole('agronomist', true)

    expect(groupLabels(wrapper)).toEqual([])
    expect(hrefs(wrapper)).toContain('/plants')
    expect(hrefs(wrapper)).toContain('/nutrients')
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
    expect(groupLabels(wrapper)).toEqual(['Работа', 'Система'])
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
      '/zones',
      '/monitoring',
      '/users',
      '/audit',
      '/devices',
      '/settings',
    ])
    expect(labels(wrapper)[0]).toBe('Система')
    expect(groupLabels(wrapper)).toEqual(['Работа', 'Система'])
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

  it('keeps agronomist mobile items without plants and nutrients', () => {
    expect(itemHrefs('agronomist')).toEqual([
      '/',
      '/zones',
      '/recipes',
      '/analytics',
      '/alerts',
      '/launch',
      '/documentation/fertigation',
    ])
    expect(itemHrefs('agronomist')).not.toContain('/plants')
    expect(itemHrefs('agronomist')).not.toContain('/nutrients')
    expect(groupHrefs('agronomist')).toContain('/plants')
    expect(groupHrefs('agronomist')).toContain('/nutrients')
  })

  it('returns only non-empty navigation groups', () => {
    for (const role of ['operator', 'agronomist', 'engineer', 'admin', 'viewer']) {
      const groups = getRoleNavigationGroups(role)
      expect(groups.length).toBeGreaterThan(0)
      expect(groups.every((group) => group.items.length > 0)).toBe(true)
    }
  })
})
