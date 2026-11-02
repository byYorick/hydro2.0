import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAutomationRuntimeSettings } from '../useAutomationRuntimeSettings'

const api = vi.hoisted(() => ({ getDocument: vi.fn(), updateDocument: vi.fn(), resetDocument: vi.fn() }))
vi.mock('@/composables/useAutomationConfig', () => ({ useAutomationConfig: () => api }))

function snapshot(value = 15) {
  return { snapshot: { sections: [{ key: 'scheduler', title: 'Планировщик', items: [
    { key: 'grace', label: 'Допуск', type: 'int', input_type: 'number', editable: true, value, min: 1, max: 600 },
    { key: 'lock', label: 'Блокировка', type: 'string', input_type: 'text', editable: true, value: 'keep-me', source: 'override' },
  ] }] } }
}

function editor() {
  let state!: ReturnType<typeof useAutomationRuntimeSettings>
  const toast = vi.fn()
  const wrapper = mount(defineComponent({ setup() { state = useAutomationRuntimeSettings(toast); return () => null } }))
  return { state, toast, wrapper }
}

describe('useAutomationRuntimeSettings', () => {
  beforeEach(() => { vi.resetAllMocks(); api.getDocument.mockResolvedValue(snapshot()) })

  it('сохраняет только правки и не превращает загруженные значения в overrides', async () => {
    const { state, wrapper } = editor()
    await state.load({ silent: true })
    expect(state.dirtyCount.value).toBe(0)
    expect(state.canSave.value).toBe(false)
    state.draft.value.grace = '42'
    api.updateDocument.mockResolvedValue(snapshot(42))
    await state.save()
    expect(api.updateDocument).toHaveBeenCalledWith('system', 0, 'system.runtime', { grace: 42 })
    expect(state.dirtyCount.value).toBe(0)
    wrapper.unmount()
  })

  it.each(['', 'bad', 0, 601, 1.5])('не сохраняет невалидное целое значение %s', async value => {
    const { state, wrapper } = editor()
    await state.load({ silent: true })
    state.draft.value.grace = value
    expect(state.canSave.value).toBe(false)
    expect(state.errors.value.grace).toBeTruthy()
    await state.save()
    expect(api.updateDocument).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('не стирает черновик при обновлении и ошибке сохранения', async () => {
    const { state, wrapper } = editor()
    await state.load({ silent: true })
    state.draft.value.grace = 45
    await state.load()
    expect(api.getDocument).toHaveBeenCalledTimes(1)
    api.updateDocument.mockRejectedValue(new Error('Нет связи'))
    await state.save()
    expect(state.draft.value.grace).toBe(45)
    expect(state.error.value).toBe('Нет связи')
    expect(state.canSave.value).toBe(true)
    state.discard()
    expect(state.draft.value.grace).toBe(15)
    expect(state.dirtyCount.value).toBe(0)
    wrapper.unmount()
  })

  it('сохраняет черновик при неудачном сбросе', async () => {
    const { state, wrapper } = editor()
    await state.load({ silent: true })
    state.draft.value.grace = 45
    api.resetDocument.mockRejectedValue(new Error('Сервис недоступен'))
    expect(await state.reset()).toBe(false)
    expect(state.draft.value.grace).toBe(45)
    wrapper.unmount()
  })

  it('предупреждает о несохранённых правках при переходе и снимает обработчик при выходе', async () => {
    const { state, wrapper } = editor()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await state.load({ silent: true })
    const visit = () => {
      const event = new Event('inertia:before', { cancelable: true })
      document.dispatchEvent(event)
      return event.defaultPrevented
    }
    expect(visit()).toBe(false)
    state.draft.value.grace = 42
    expect(visit()).toBe(true)
    expect(state.draft.value.grace).toBe(42)
    confirm.mockReturnValue(true)
    expect(visit()).toBe(false)
    confirm.mockReturnValue(false)
    state.discard()
    expect(visit()).toBe(false)
    state.draft.value.grace = 42
    wrapper.unmount()
    expect(visit()).toBe(false)
    confirm.mockRestore()
  })
})
