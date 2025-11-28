import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import LoadingState from '../LoadingState.vue'

describe('LoadingState', () => {
  it('should render spinner when loading', () => {
    const wrapper = mount(LoadingState, {
      props: {
        loading: true
      }
    })
    
    expect(wrapper.find('.animate-spin').exists()).toBe(true)
  })

  it('should not render when not loading', () => {
    const wrapper = mount(LoadingState, {
      props: {
        loading: false
      }
    })
    
    expect(wrapper.find('.animate-spin').exists()).toBe(false)
  })

  it('should render message when provided', () => {
    const wrapper = mount(LoadingState, {
      props: {
        loading: true,
        message: 'Загрузка...'
      }
    })
    
    expect(wrapper.text()).toContain('Загрузка...')
  })

  it('should apply size classes', () => {
    const sizes = ['sm', 'md', 'lg'] as const
    
    sizes.forEach(size => {
      const wrapper = mount(LoadingState, {
        props: {
          loading: true,
          size
        }
      })
      
      const spinner = wrapper.find('.animate-spin')
      expect(spinner.exists()).toBe(true)
      
      if (size === 'sm') {
        expect(spinner.classes()).toContain('h-4')
      } else if (size === 'md') {
        expect(spinner.classes()).toContain('h-8')
      } else if (size === 'lg') {
        expect(spinner.classes()).toContain('h-12')
      }
    })
  })

  it('should render full screen when fullScreen is true', () => {
    const wrapper = mount(LoadingState, {
      props: {
        loading: true,
        fullScreen: true
      }
    })
    
    expect(wrapper.classes()).toContain('fixed')
    expect(wrapper.classes()).toContain('inset-0')
    expect(wrapper.classes()).toContain('z-50')
  })

  it('should render skeleton when skeleton is true and not loading', () => {
    const wrapper = mount(LoadingState, {
      props: {
        loading: false,
        skeleton: true,
        skeletonLines: 3
      }
    })
    
    const skeletonLines = wrapper.findAll('.animate-pulse')
    expect(skeletonLines.length).toBe(3)
  })

  it('should not render skeleton when loading', () => {
    const wrapper = mount(LoadingState, {
      props: {
        loading: true,
        skeleton: true
      }
    })
    
    expect(wrapper.find('.animate-pulse').exists()).toBe(false)
  })

  it('should apply custom container class', () => {
    const wrapper = mount(LoadingState, {
      props: {
        loading: true,
        containerClass: 'custom-class'
      }
    })
    
    expect(wrapper.classes()).toContain('custom-class')
  })

  it('should apply custom color', () => {
    const wrapper = mount(LoadingState, {
      props: {
        loading: true,
        color: '#ff0000'
      }
    })
    
    const spinner = wrapper.find('.animate-spin')
    const style = spinner.attributes('style') || ''
    // Проверяем, что цвет присутствует в стиле (может быть в разных форматах)
    expect(style).toMatch(/border-color.*rgb\(255,\s*0,\s*0\)|border-color.*#ff0000|border-color.*#f00/i)
  })
})

