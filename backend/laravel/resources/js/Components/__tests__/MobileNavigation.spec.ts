import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MobileNavigation from '@/Components/MobileNavigation.vue'

const mockPage = vi.fn()
vi.mock('@inertiajs/vue3', () => ({ usePage: () => mockPage() }))
vi.mock('@/Components/NavLink.vue', () => ({
  default: {
    name: 'NavLink',
    props: ['href', 'label', 'mobile'],
    template: '<a :href="href"><slot>{{ label }}</slot></a>',
  },
}))

let currentInnerWidth = 768
Object.defineProperty(window, 'innerWidth', {
  configurable: true,
  get: () => currentInnerWidth,
})
const wrappers: ReturnType<typeof mount>[] = []
function mountForRole(role: string, path = '/', width = 768) {
  currentInnerWidth = width
  mockPage.mockReturnValue({ url: path, props: { auth: { user: { role } } } })
  const wrapper = mount(MobileNavigation)
  wrappers.push(wrapper)
  return wrapper
}

afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

describe('MobileNavigation', () => {
  it.each([
    ['operator', ['/', '/zones', '/alerts']],
    ['agronomist', ['/', '/zones', '/recipes']],
    ['engineer', ['/', '/devices', '/zones']],
    ['admin', ['/', '/alerts', '/users']],
    ['viewer', ['/', '/zones', '/alerts']],
    ['unknown', ['/', '/zones', '/alerts']],
  ])('оставляет три основных раздела и меню для %s', (role, expected) => {
    const wrapper = mountForRole(role as string)
    expect(wrapper.findAll('a').map((link) => link.attributes('href'))).toEqual(expected)
    expect(wrapper.findAll('button')).toHaveLength(1)
    expect(wrapper.get('button').text()).toBe('Ещё')
    expect(wrapper.findAll('svg')).toHaveLength(4)
  })

  it('открывает общее меню вместо скрытия остальных разделов', async () => {
    const wrapper = mountForRole('agronomist')
    const more = wrapper.get('button')
    expect(more.attributes('aria-controls')).toBe('mobile-nav')
    expect(more.attributes('aria-expanded')).toBe('false')
    await more.trigger('click')
    expect(wrapper.emitted('open-menu')).toHaveLength(1)
    await wrapper.setProps({ menuOpen: true })
    expect(more.attributes('aria-expanded')).toBe('true')
  })

  it('отмечает раздел из дополнительного меню как активный', () => {
    const wrapper = mountForRole('agronomist', '/analytics?period=7d')
    expect(wrapper.get('button').classes()).toContain('mobile-nav-link--active')
  })

  it('не выделяет Ещё для вложенной страницы основного раздела', () => {
    const wrapper = mountForRole('engineer', '/devices/15?tab=channels')
    expect(wrapper.get('button').classes()).not.toContain('mobile-nav-link--active')
  })

  it('считает главную страницу с фильтром основным разделом', () => {
    const wrapper = mountForRole('operator', '/?greenhouse=1')
    expect(wrapper.get('button').classes()).not.toContain('mobile-nav-link--active')
  })

  it('скрывается на десктопе и реагирует на смену ширины', async () => {
    const wrapper = mountForRole('operator', '/', 1440)
    expect(wrapper.find('nav').exists()).toBe(false)
    currentInnerWidth = 390
    window.dispatchEvent(new Event('resize'))
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('a')).toHaveLength(3)
    expect(wrapper.get('nav').classes()).toContain('fixed')
    expect(wrapper.get('nav').attributes('aria-label')).toBe('Основная навигация')
  })
})
