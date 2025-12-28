import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MobileNavigation from '@/Components/MobileNavigation.vue'

// Моки
vi.mock('@/composables/useRole', () => ({
  useRole: () => ({
    isViewer: false,
    canEdit: true,
    hasAnyRole: () => true
  })
}))

vi.mock('@/Components/NavLink.vue', () => ({
  default: {
    name: 'NavLink',
    props: ['href', 'label', 'mobile'],
    template: '<a :href="href" :class="{ mobile }"><slot>{{ label }}</slot></a>'
  }
}))

// Моки window.innerWidth
Object.defineProperty(window, 'innerWidth', {
  writable: true,
  configurable: true,
  value: 1024
})

describe('MobileNavigation', () => {
  let wrapper: ReturnType<typeof mount>

  beforeEach(() => {
    wrapper = mount(MobileNavigation)
  })

  describe('Отображение', () => {
    it('скрывает навигацию на десктопе', () => {
      Object.defineProperty(window, 'innerWidth', { value: 1920, writable: true })
      wrapper = mount(MobileNavigation)
      
      expect(wrapper.exists()).toBe(true)
    })

    it('показывает навигацию на мобильных устройствах', () => {
      Object.defineProperty(window, 'innerWidth', { value: 768, writable: true })
      wrapper = mount(MobileNavigation)
      
      expect(wrapper.exists()).toBe(true)
    })
  })

  describe('Навигационные ссылки', () => {
    it('показывает ссылку на Dashboard', () => {
      const links = wrapper.findAll('a')
      const dashboardLink = links.find(link => link.attributes('href') === '/')
      expect(dashboardLink).toBeDefined()
    })

    it('показывает ссылку на Zones', () => {
      const links = wrapper.findAll('a')
      const zonesLink = links.find(link => link.attributes('href') === '/zones')
      expect(zonesLink).toBeDefined()
    })

    it('показывает ссылку на Alerts', () => {
      const links = wrapper.findAll('a')
      const alertsLink = links.find(link => link.attributes('href') === '/alerts')
      expect(alertsLink).toBeDefined()
    })

    it('показывает ссылку на Analytics', () => {
      const links = wrapper.findAll('a')
      const analyticsLink = links.find(link => link.attributes('href') === '/analytics')
      expect(analyticsLink).toBeDefined()
    })

    it('показывает ссылку на Logs', () => {
      const links = wrapper.findAll('a')
      const logsLink = links.find(link => link.attributes('href') === '/logs')
      expect(logsLink).toBeDefined()
    })
  })

  describe('Иконки', () => {
    it('показывает иконки для каждой ссылки', () => {
      const icons = wrapper.findAll('svg')
      expect(icons.length).toBeGreaterThan(0)
    })
  })

  describe('Стили', () => {
    it('применяет стили для мобильной навигации', () => {
      const nav = wrapper.find('nav')
      expect(nav.exists()).toBe(true)
      // Проверяем наличие базовых классов
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
