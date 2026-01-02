// @ts-nocheck
import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import { nextTick } from 'vue'
import ZoneActionModal from '../ZoneActionModal.vue'

describe('ZoneActionModal - Validation (P3-2)', () => {
  const defaultProps = {
    show: true,
    actionType: 'FORCE_IRRIGATION',
    zoneId: 1
  }

  it('should validate duration_sec for FORCE_IRRIGATION', async () => {
    const wrapper = mount(ZoneActionModal, {
      props: defaultProps
    })

    // Устанавливаем невалидное значение
    ;(wrapper.vm as any).form.duration_sec = 0
    await nextTick()

    wrapper.vm.onSubmit()
    await nextTick()

    expect(wrapper.vm.error).toContain('Длительность должна быть от 1 до 3600 секунд')
  })

  it('should validate target_ph for FORCE_PH_CONTROL', async () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        ...defaultProps,
        actionType: 'FORCE_PH_CONTROL'
      }
    })

    wrapper.vm.form.target_ph = 3.0 // Ниже минимума
    await nextTick()

    wrapper.vm.onSubmit()
    await nextTick()

    expect(wrapper.vm.error).toContain('pH должен быть от 4.0 до 9.0')
  })

  it('should validate target_ec for FORCE_EC_CONTROL', async () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        ...defaultProps,
        actionType: 'FORCE_EC_CONTROL'
      }
    })

    wrapper.vm.form.target_ec = 11.0 // Выше максимума
    await nextTick()

    wrapper.vm.onSubmit()
    await nextTick()

    expect(wrapper.vm.error).toContain('EC должен быть от 0.1 до 10.0')
  })

  it('should validate target_temp and target_humidity for FORCE_CLIMATE', async () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        ...defaultProps,
        actionType: 'FORCE_CLIMATE'
      }
    })

    wrapper.vm.form.target_temp = 5 // Ниже минимума
    await nextTick()

    wrapper.vm.onSubmit()
    await nextTick()

    expect(wrapper.vm.error).toContain('Температура должна быть от 10 до 35°C')

    // Исправляем температуру, но делаем невалидную влажность
    wrapper.vm.form.target_temp = 22
    wrapper.vm.form.target_humidity = 20 // Ниже минимума
    await nextTick()

    wrapper.vm.onSubmit()
    await nextTick()

    expect(wrapper.vm.error).toContain('Влажность должна быть от 30 до 90%')
  })

  it('should validate intensity and duration_hours for FORCE_LIGHTING', async () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        ...defaultProps,
        actionType: 'FORCE_LIGHTING'
      }
    })

    wrapper.vm.form.intensity = 150 // Выше максимума
    await nextTick()

    wrapper.vm.onSubmit()
    await nextTick()

    expect(wrapper.vm.error).toContain('Интенсивность должна быть от 0 до 100%')

    // Исправляем интенсивность, но делаем невалидную длительность
    wrapper.vm.form.intensity = 80
    wrapper.vm.form.duration_hours = 30 // Выше максимума
    await nextTick()

    wrapper.vm.onSubmit()
    await nextTick()

    expect(wrapper.vm.error).toContain('Длительность должна быть от 0.5 до 24 часов')
  })

  it('should pass validation with valid values', async () => {
    const wrapper = mount(ZoneActionModal, {
      props: defaultProps
    })

    wrapper.vm.form.duration_sec = 10
    await nextTick()

    wrapper.vm.onSubmit()
    await nextTick()

    expect(wrapper.vm.error).toBeNull()
    // Проверяем, что событие submit было эмитировано
    expect(wrapper.emitted('submit')).toBeTruthy()
    expect(wrapper.emitted('submit')?.[0]?.[0]).toEqual({
      actionType: 'FORCE_IRRIGATION',
      params: { duration_sec: 10 }
    })
  })

  it('should reset form when modal opens', async () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        ...defaultProps,
        show: false
      }
    })

    wrapper.vm.form.duration_sec = 999
    await nextTick()

    // Открываем модальное окно
    await wrapper.setProps({ show: true })
    await nextTick()

    // Форма должна сброситься к значениям по умолчанию
    expect(wrapper.vm.form.duration_sec).toBe(10)
  })
})

