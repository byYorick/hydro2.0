import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MobileNavigation from '@/Components/MobileNavigation.vue'

const mockPage = vi.fn()
vi.mock('@inertiajs/vue3', () => ({
  usePage: () => mockPage()
}))

vi.mock('@/Components/NavLink.vue', () => ({
  default: {
    name: 'NavLink',
    props: ['href', 'label', 'mobile'],
    template: '<a :href="href" :class="{ mobile }"><slot>{{ label }}</slot></a>'
  }
}))

let currentInnerWidth = 768
Object.defineProperty(window, 'innerWidth', {
  configurable: true,
  get: () => currentInnerWidth,
})

function mountForRole(role: string, innerWidth = 768) {
  currentInnerWidth = innerWidth
  mockPage.mockReturnValue({
    props: {
      auth: {
        user: { role }
      }
    }
  })

  return mount(MobileNavigation)
}

function hrefs(wrapper: ReturnType<typeof mount>) {
  return wrapper.findAll('a').map((link) => link.attributes('href'))
}

describe('MobileNavigation', () => {
  let wrapper: ReturnType<typeof mount>

  beforeEach(() => {
    wrapper = mountForRole('operator')
  })

  describe('Отображение', () => {
    it('скрывает навигацию на десктопе', () => {
      wrapper = mountForRole('operator', 1920)

      expect(wrapper.find('nav').exists()).toBe(false)
    })

    it('показывает навигацию на мобильных устройствах', () => {
      wrapper = mountForRole('operator', 768)

      expect(wrapper.find('nav').exists()).toBe(true)
    })
  })

  describe('Навигационные ссылки', () => {
    it('для operator показывает ровно 5 пунктов смены', () => {
      expect(hrefs(wrapper)).toEqual([
        '/',
        '/zones',
        '/alerts',
        '/documentation/fertigation',
        '/settings',
      ])
      expect(hrefs(wrapper)).not.toContain('/plants')
      expect(hrefs(wrapper)).not.toContain('/nutrients')
      expect(wrapper.text()).toContain('Сегодня')
      expect(wrapper.text()).toContain('Справочник')
      expect(wrapper.text()).toContain('Профиль')
      expect(wrapper.text()).not.toContain('Рецепты')
      expect(wrapper.text()).not.toContain('Узлы')
      expect(wrapper.text()).not.toContain('Аналитика')
      expect(wrapper.text()).not.toContain('Логи')
      expect(wrapper.text()).not.toContain('Культуры')
    })

    it('для agronomist показывает рецепты и скрывает устройства', () => {
      wrapper = mountForRole('agronomist')

      expect(hrefs(wrapper)).toEqual([
        '/',
        '/zones',
        '/recipes',
        '/analytics',
        '/alerts',
        '/launch',
        '/documentation/fertigation',
      ])
      expect(hrefs(wrapper)).not.toContain('/plants')
      expect(hrefs(wrapper)).not.toContain('/nutrients')
      expect(wrapper.text()).toContain('Рецепты')
      expect(wrapper.text()).toContain('Справочник')
      expect(wrapper.text()).not.toContain('Узлы')
      expect(wrapper.text()).not.toContain('Культуры')
      expect(wrapper.text()).not.toContain('Удобрения')
    })

    it('для engineer ставит узлы первым пунктом', () => {
      wrapper = mountForRole('engineer')

      expect(hrefs(wrapper)[0]).toBe('/devices')
      expect(wrapper.text()).toContain('Узлы')
      expect(wrapper.text()).toContain('Обзор')
      expect(wrapper.text()).not.toContain('Рецепты')
    })

    it('для admin показывает пользователей, а не операторов', () => {
      wrapper = mountForRole('admin')

      expect(hrefs(wrapper)).toContain('/users')
      expect(hrefs(wrapper)).toContain('/audit')
      expect(hrefs(wrapper)).not.toContain('/logs')
      expect(wrapper.text()).toContain('Пользователи')
      expect(wrapper.text()).toContain('Журнал')
      expect(wrapper.text()).not.toContain('Операторы')
      expect(wrapper.text()).not.toContain('Логи')
    })

    it('для viewer не показывает устройства, аналитику и сервисы', () => {
      wrapper = mountForRole('viewer')

      expect(hrefs(wrapper)).toEqual(['/', '/zones', '/alerts', '/settings'])
      expect(wrapper.text()).not.toContain('Рецепты')
      expect(wrapper.text()).not.toContain('Узлы')
      expect(wrapper.text()).not.toContain('Аналитика')
      expect(wrapper.text()).not.toContain('Здоровье системы')
    })
  })

  describe('Иконки', () => {
    it('показывает иконки для каждой ссылки', () => {
      const icons = wrapper.findAll('svg')
      expect(icons.length).toBe(5)
    })
  })

  describe('Стили', () => {
    it('применяет стили для мобильной навигации', () => {
      const nav = wrapper.find('nav')
      expect(nav.exists()).toBe(true)
      const classes = nav.classes()
      expect(classes.length).toBeGreaterThan(0)
    })

    it('применяет фиксированное позиционирование', () => {
      const nav = wrapper.find('nav')
      expect(nav.classes()).toContain('fixed')
      expect(nav.classes()).toContain('bottom-0')
    })
  })

  describe('Адаптивность', () => {
    it('скрывается на больших экранах', () => {
      const nav = wrapper.find('nav')
      expect(nav.classes()).toContain('lg:hidden')
    })
  })
})
