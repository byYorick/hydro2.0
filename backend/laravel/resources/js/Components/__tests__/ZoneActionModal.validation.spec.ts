// @ts-expect-error - Test file with Vue component testing
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

    expect(wrapper.vm.error).toContain('Длительность (сек): допустимый диапазон 1–3600')
  })

  it('should validate duration_sec for START_IRRIGATION', async () => {
    const wrapper = mount(ZoneActionModal, {
      props: {
        ...defaultProps,
        actionType: 'START_IRRIGATION'
      }
    })

    ;(wrapper.vm as any).form.duration_sec = 0
    await nextTick()

    wrapper.vm.onSubmit()
    await nextTick()

    expect(wrapper.vm.error).toContain('Длительность (сек): допустимый диапазон 1–3600')
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

    expect(wrapper.vm.error).toContain('pH: допустимый диапазон 4–9')
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

    expect(wrapper.vm.error).toContain('EC: допустимый диапазон 0.1–10')
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

    expect(wrapper.vm.error).toContain('Температура (°C): допустимый диапазон 10–35')

    // Исправляем температуру, но делаем невалидную влажность
    wrapper.vm.form.target_temp = 22
    wrapper.vm.form.target_humidity = 20 // Ниже минимума
    await nextTick()

    wrapper.vm.onSubmit()
    await nextTick()

    expect(wrapper.vm.error).toContain('Влажность (%): допустимый диапазон 30–90')
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

    expect(wrapper.vm.error).toContain('Интенсивность (%): допустимый диапазон 0–100')

    // Исправляем интенсивность, но делаем невалидную длительность
    wrapper.vm.form.intensity = 80
    wrapper.vm.form.duration_hours = 30 // Выше максимума
    await nextTick()

    wrapper.vm.onSubmit()
    await nextTick()

    expect(wrapper.vm.error).toContain('Длительность (ч): допустимый диапазон 0.5–24')
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

    // Сброс к water_manual_irrigation_sec из FALLBACK (useAutomationDefaults)
    expect(wrapper.vm.form.duration_sec).toBe(90)
  })
})
