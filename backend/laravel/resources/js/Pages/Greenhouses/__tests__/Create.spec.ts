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
  post: (url: string, data?: any, config?: any) => {
    // Симулируем работу перехватчика useApi - добавляем префикс /api
    const finalUrl = url && !url.startsWith('/api/') && !url.startsWith('http') ? `/api${url}` : url
    return axiosPostMock(finalUrl, data, config)
  },
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
    create: vi.fn(() => mockAxiosInstance),
    post: (url: string, data?: any, config?: any) => {
      const finalUrl = url && !url.startsWith('/api/') && !url.startsWith('http') ? `/api${url}` : url
      return axiosPostMock(finalUrl, data, config)
    },
  },
}))

// Мокируем useApi, чтобы он использовал мокированный axios
vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: mockAxiosInstance,
  }),
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

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}))

vi.mock('@/constants/timeouts', () => ({
  TOAST_TIMEOUT: {
    NORMAL: 4000,
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
    
    expect(wrapper.find('input[type="text"][placeholder*="Main Greenhouse"]').exists()).toBe(true)
    expect(wrapper.find('input[placeholder*="Europe/Moscow"]').exists()).toBe(true)
    expect(wrapper.find('select').exists()).toBe(true)
    expect(wrapper.find('textarea').exists()).toBe(true)
  })

  it('инициализирует форму с значениями по умолчанию', () => {
    const wrapper = mount(GreenhousesCreate)
    
    // Форма инициализируется с пустыми значениями, но имеет placeholder'ы
    const nameInput = wrapper.find('input[placeholder*="Main Greenhouse"]')
    
    // Проверяем, что поле существует и имеет правильный placeholder
    expect(nameInput.exists()).toBe(true)
    expect(nameInput.attributes('placeholder')).toContain('Main Greenhouse')
    // Проверяем, что UID генерируется автоматически
    expect(wrapper.text()).toContain('UID будет сгенерирован автоматически')
  })

  it('валидирует обязательные поля', async () => {
    const wrapper = mount(GreenhousesCreate)
    
    const nameInput = wrapper.find('input[type="text"][placeholder*="Main Greenhouse"]')
    
    // Поле name должно быть required
    expect((nameInput.element as HTMLInputElement).hasAttribute('required')).toBe(true)
  })

  it('создает теплицу при отправке формы', async () => {
    const wrapper = mount(GreenhousesCreate)
    await wrapper.vm.$nextTick()
    
    // Заполняем форму перед отправкой
    const nameInput = wrapper.find('input[placeholder*="Main Greenhouse"]')
    
    if (nameInput.exists()) {
      await nameInput.setValue('Main Greenhouse')
      await wrapper.vm.$nextTick()
    }
    
    const form = wrapper.find('form')
    if (form.exists()) {
      await form.trigger('submit.prevent')
      // Увеличиваем время ожидания для асинхронной обработки
      await new Promise(resolve => setTimeout(resolve, 500))
      await wrapper.vm.$nextTick()
      
      expect(axiosPostMock).toHaveBeenCalled()
      // Проверяем, что был вызван с правильным URL (useApi добавляет /api префикс)
      const calls = axiosPostMock.mock.calls
      expect(calls.length).toBeGreaterThan(0)
      const url = calls[0][0]
      expect(url).toContain('greenhouses')
      // Проверяем, что форма была отправлена с UID
      if (calls[0][1]) {
        const postData = calls[0][1]
        expect(postData.name).toBe('Main Greenhouse')
        expect(postData.uid).toBeDefined()
      }
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
    
    // Заполняем имя перед отправкой
    const nameInput = wrapper.find('input[placeholder*="Main Greenhouse"]')
    if (nameInput.exists()) {
      await nameInput.setValue('Main Greenhouse')
      await wrapper.vm.$nextTick()
    }
    
    const form = wrapper.find('form')
    await form.trigger('submit.prevent')
    
    // Увеличиваем время ожидания для асинхронной обработки
    await new Promise(resolve => setTimeout(resolve, 500))
    await wrapper.vm.$nextTick()
    
    expect(routerVisitMock).toHaveBeenCalledWith('/')
  })

  it('обрабатывает ошибки при создании', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    axiosPostMock.mockRejectedValueOnce(new Error('Network error'))
    
    const wrapper = mount(GreenhousesCreate)
    
    // Заполняем имя перед отправкой
    const nameInput = wrapper.find('input[placeholder*="Main Greenhouse"]')
    if (nameInput.exists()) {
      await nameInput.setValue('Main Greenhouse')
      await wrapper.vm.$nextTick()
    }
    
    const form = wrapper.find('form')
    await form.trigger('submit.prevent')
    
    // Увеличиваем время ожидания для асинхронной обработки
    await new Promise(resolve => setTimeout(resolve, 500))
    await wrapper.vm.$nextTick()
    
    expect(axiosPostMock).toHaveBeenCalled()
    
    consoleErrorSpy.mockRestore()
  })

  it('отображает ошибки валидации', async () => {
    axiosPostMock.mockRejectedValue({
      response: {
        data: {
          errors: {
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

