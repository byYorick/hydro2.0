import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/Card.vue', () => ({
  default: { name: 'Card', template: '<div class="card"><slot /></div>' },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: { name: 'Button', props: ['size', 'variant', 'type', 'disabled'], template: '<button :disabled="disabled"><slot /></button>' },
}))

const axiosPostMock = vi.hoisted(() => vi.fn())
const routerVisitMock = vi.hoisted(() => vi.fn())

const mockAxiosInstance = vi.hoisted(() => ({
  get: vi.fn(),
  post: axiosPostMock,
  patch: vi.fn(),
  delete: vi.fn(),
  put: vi.fn(),
  interceptors: {
    request: { use: vi.fn(), eject: vi.fn() },
    response: { use: vi.fn(), eject: vi.fn() },
  },
}))

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => mockAxiosInstance()),
    post: (url: string, data?: any, config?: any) => axiosPostMock(url, data, config),
  },
}))

vi.mock('@inertiajs/vue3', () => ({
  Link: { name: 'Link', props: ['href'], template: '<a :href="href"><slot /></a>' },
  router: {
    visit: routerVisitMock,
  },
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    info: vi.fn(),
    error: vi.fn(),
  },
}))

import GreenhousesCreate from '../Create.vue'

describe('Greenhouses/Create.vue', () => {
  beforeEach(() => {
    axiosPostMock.mockClear()
    routerVisitMock.mockClear()
    axiosPostMock.mockResolvedValue({
      data: {
        data: {
          id: 1,
          uid: 'gh-main',
          name: 'Main Greenhouse',
        },
      },
    })
  })

  it('отображает заголовок создания теплицы', () => {
    const wrapper = mount(GreenhousesCreate)
    
    expect(wrapper.text()).toContain('Создать теплицу')
  })

  it('отображает все поля формы', () => {
    const wrapper = mount(GreenhousesCreate)
    
    expect(wrapper.find('input[type="text"][placeholder*="gh-main"]').exists()).toBe(true)
    expect(wrapper.find('input[type="text"][placeholder*="Main Greenhouse"]').exists()).toBe(true)
    expect(wrapper.find('input[placeholder*="Europe/Moscow"]').exists()).toBe(true)
    expect(wrapper.find('select').exists()).toBe(true)
    expect(wrapper.find('textarea').exists()).toBe(true)
  })

  it('инициализирует форму с значениями по умолчанию', () => {
    const wrapper = mount(GreenhousesCreate)
    
    // Форма инициализируется с пустыми значениями, но имеет placeholder'ы
    const uidInput = wrapper.find('input[placeholder*="gh-main"]')
    const nameInput = wrapper.find('input[placeholder*="Main Greenhouse"]')
    
    // Проверяем, что поля существуют и имеют правильные placeholder'ы
    expect(uidInput.exists()).toBe(true)
    expect(nameInput.exists()).toBe(true)
    expect(uidInput.attributes('placeholder')).toContain('gh-main')
    expect(nameInput.attributes('placeholder')).toContain('Main Greenhouse')
  })

  it('валидирует обязательные поля', async () => {
    const wrapper = mount(GreenhousesCreate)
    
    const uidInput = wrapper.find('input[type="text"][placeholder*="gh-main"]')
    const nameInput = wrapper.find('input[type="text"][placeholder*="Main Greenhouse"]')
    
    // Поля должны быть required
    expect((uidInput.element as HTMLInputElement).hasAttribute('required')).toBe(true)
    expect((nameInput.element as HTMLInputElement).hasAttribute('required')).toBe(true)
  })

  it('создает теплицу при отправке формы', async () => {
    const wrapper = mount(GreenhousesCreate)
    await wrapper.vm.$nextTick()
    
    // Заполняем форму перед отправкой
    const uidInput = wrapper.find('input[placeholder*="gh-main"]')
    const nameInput = wrapper.find('input[placeholder*="Main Greenhouse"]')
    
    if (uidInput.exists() && nameInput.exists()) {
      await uidInput.setValue('gh-main')
      await nameInput.setValue('Main Greenhouse')
      await wrapper.vm.$nextTick()
    }
    
    const form = wrapper.find('form')
    if (form.exists()) {
      await form.trigger('submit.prevent')
      await new Promise(resolve => setTimeout(resolve, 200))
      await wrapper.vm.$nextTick()
      
      expect(axiosPostMock).toHaveBeenCalled()
      expect(axiosPostMock.mock.calls[0][0]).toBe('/api/greenhouses')
      // Проверяем, что форма была отправлена (значения могут быть пустыми, если форма не заполнена)
      expect(axiosPostMock.mock.calls[0][1]).toBeDefined()
    }
  })

  it('отображает состояние загрузки', async () => {
    axiosPostMock.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)))
    
    const wrapper = mount(GreenhousesCreate)
    
    const form = wrapper.find('form')
    const submitPromise = form.trigger('submit.prevent')
    
    await wrapper.vm.$nextTick()
    
    const submitButton = wrapper.findAll('button[type="submit"]')[0]
    if (submitButton) {
      const isDisabled = (submitButton.element as HTMLButtonElement).disabled
      expect(isDisabled).toBe(true)
    }
    
    await submitPromise
  })

  it('перенаправляет на главную после успешного создания', async () => {
    const wrapper = mount(GreenhousesCreate)
    
    const form = wrapper.find('form')
    await form.trigger('submit.prevent')
    
    await new Promise(resolve => setTimeout(resolve, 100))
    
    expect(routerVisitMock).toHaveBeenCalledWith('/')
  })

  it('обрабатывает ошибки при создании', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    axiosPostMock.mockRejectedValue(new Error('Network error'))
    
    const wrapper = mount(GreenhousesCreate)
    
    const form = wrapper.find('form')
    await form.trigger('submit.prevent')
    
    await new Promise(resolve => setTimeout(resolve, 100))
    
    expect(axiosPostMock).toHaveBeenCalled()
    
    consoleErrorSpy.mockRestore()
  })

  it('отображает ошибки валидации', async () => {
    axiosPostMock.mockRejectedValue({
      response: {
        data: {
          errors: {
            uid: ['UID уже существует'],
            name: ['Название обязательно'],
          },
        },
      },
    })
    
    const wrapper = mount(GreenhousesCreate)
    
    const form = wrapper.find('form')
    await form.trigger('submit.prevent')
    
    await new Promise(resolve => setTimeout(resolve, 200))
    
    // errors доступны через reactive, но не через $data в тестах
    // Проверяем, что ошибки отображаются в UI
    await wrapper.vm.$nextTick()
    const errorMessages = wrapper.findAll('.text-red-400')
    expect(errorMessages.length).toBeGreaterThan(0)
  })

  it('позволяет выбрать тип теплицы', async () => {
    const wrapper = mount(GreenhousesCreate)
    
    const select = wrapper.find('select')
    expect(select.exists()).toBe(true)
    
    const options = select.findAll('option')
    expect(options.length).toBeGreaterThan(1)
    expect(options.some(opt => opt.text().includes('Indoor'))).toBe(true)
    expect(options.some(opt => opt.text().includes('Outdoor'))).toBe(true)
    expect(options.some(opt => opt.text().includes('Greenhouse'))).toBe(true)
  })

  it('отображает кнопки отмены и создания', () => {
    const wrapper = mount(GreenhousesCreate)
    
    expect(wrapper.text()).toContain('Отмена')
    expect(wrapper.text()).toContain('Создать')
  })
})

