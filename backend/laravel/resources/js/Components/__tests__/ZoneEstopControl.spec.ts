import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import ZoneEstopControl from '@/Components/ZoneEstopControl.vue'

function mountControl(props: Record<string, unknown> = {}) {
  return mount(ZoneEstopControl, {
    attachTo: document.body,
    props: {
      active: false,
      canEngage: true,
      canRelease: true,
      ...props,
    },
  })
}

function bodyButton(testId: string): HTMLButtonElement {
  const element = document.body.querySelector(`[data-testid="${testId}"]`)
  if (!(element instanceof HTMLButtonElement)) {
    throw new Error(`Кнопка ${testId} не найдена`)
  }
  return element
}

describe('ZoneEstopControl', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('просит одно подтверждение перед включением', async () => {
    const wrapper = mountControl()

    expect(wrapper.get('[data-testid="zone-estop-engage"]').text()).toBe('Аварийная остановка')
    await wrapper.get('[data-testid="zone-estop-engage"]').trigger('click')
    await nextTick()

    expect(document.body.textContent).toContain('Включающие команды зоны будут заблокированы')
    expect(wrapper.emitted('engage')).toBeUndefined()

    bodyButton('zone-estop-confirm').click()
    await nextTick()
    expect(wrapper.emitted('engage')).toHaveLength(1)
    wrapper.unmount()
  })

  it('не включает остановку, если подтверждение закрыли', async () => {
    const wrapper = mountControl()
    await wrapper.get('[data-testid="zone-estop-engage"]').trigger('click')
    await nextTick()

    const cancel = [...document.body.querySelectorAll('button')].find((button) => button.textContent?.trim() === 'Отмена')
    expect(cancel).toBeDefined()
    cancel?.click()
    await nextTick()

    expect(wrapper.emitted('engage')).toBeUndefined()
    wrapper.unmount()
  })

  it('снимает остановку только с причиной не короче 3 символов', async () => {
    const wrapper = mountControl({ active: true })

    expect(wrapper.find('[data-testid="zone-estop-engage"]').exists()).toBe(false)
    await wrapper.get('[data-testid="zone-estop-release"]').trigger('click')
    await nextTick()

    const reason = document.body.querySelector('[data-testid="zone-estop-release-reason"]')
    expect(reason).toBeInstanceOf(HTMLTextAreaElement)
    const confirm = bodyButton('zone-estop-release-confirm')
    expect(confirm.disabled).toBe(true)

    const field = reason as HTMLTextAreaElement
    field.value = 'ок'
    field.dispatchEvent(new Event('input'))
    await nextTick()
    expect(document.body.textContent).toContain('3')
    expect(confirm.disabled).toBe(true)
    confirm.click()
    await nextTick()
    expect(wrapper.emitted('release')).toBeUndefined()

    field.value = 'дым устранён'
    field.dispatchEvent(new Event('input'))
    await nextTick()
    expect(confirm.disabled).toBe(false)
    confirm.click()
    await nextTick()
    expect(wrapper.emitted('release')?.[0]).toEqual(['дым устранён'])
    wrapper.unmount()
  })

  it('скрывает кнопки без права на остановку', () => {
    const wrapper = mountControl({ canEngage: false, canRelease: false, active: true })
    expect(wrapper.find('[data-testid="zone-estop-control"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
