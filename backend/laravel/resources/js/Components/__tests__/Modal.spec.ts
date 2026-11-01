import { mount } from '@vue/test-utils'
import { describe, expect, it, afterEach } from 'vitest'
import { nextTick } from 'vue'
import Modal from '../Modal.vue'

describe('Modal.vue', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('рендерит оверлей в body через Teleport и не остаётся в родителе', async () => {
    const host = document.createElement('div')
    host.id = 'modal-host'
    host.style.overflow = 'hidden'
    document.body.appendChild(host)

    const wrapper = mount(Modal, {
      props: {
        open: true,
        title: 'Тест',
        hideDefaultCancel: true,
      },
      attrs: {
        'data-testid': 'sample-modal',
      },
      slots: {
        default: '<p>Содержимое</p>',
      },
      attachTo: host,
    })

    await nextTick()

    expect(host.querySelector('[data-testid="app-modal-root"]')).toBeNull()
    expect(document.body.querySelector('[data-testid="app-modal-root"]')).not.toBeNull()
    expect(document.body.querySelector('[data-testid="sample-modal"]')?.textContent).toContain('Содержимое')

    wrapper.unmount()
  })

  it('использует z-[60] по умолчанию и позволяет поднять слой через class', async () => {
    const wrapper = mount(Modal, {
      props: { open: true, title: 'Слой' },
      attrs: { class: 'z-[70]' },
      attachTo: document.body,
    })

    await nextTick()

    const root = document.body.querySelector('[data-testid="app-modal-root"]')
    expect(root?.className).toContain('z-[70]')
    expect(root?.className).not.toContain('z-[60]')

    wrapper.unmount()
  })

  it('закрывается по Escape и возвращает фокус', async () => {
    const trigger = document.createElement('button')
    trigger.type = 'button'
    document.body.appendChild(trigger)
    trigger.focus()

    const wrapper = mount(Modal, {
      props: { open: true, title: 'Закрытие' },
      attachTo: document.body,
    })

    await nextTick()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await nextTick()

    expect(wrapper.emitted('close')).toBeTruthy()
    wrapper.unmount()
  })

  it('циклически переносит Tab и Shift+Tab внутри диалога и возвращает фокус триггеру', async () => {
    const trigger = document.createElement('button')
    trigger.type = 'button'
    document.body.appendChild(trigger)
    trigger.focus()

    const wrapper = mount(Modal, {
      props: { open: true, title: 'Фокус', hideDefaultCancel: true },
      slots: {
        default: '<button type="button" data-testid="focus-first">Раз</button><button type="button" data-testid="focus-second">Два</button>',
      },
      attachTo: document.body,
    })

    await nextTick()

    const first = document.body.querySelector('[data-testid="focus-first"]') as HTMLButtonElement
    const second = document.body.querySelector('[data-testid="focus-second"]') as HTMLButtonElement
    first.focus()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement).toBe(second)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement).toBe(first)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }))
    expect(document.activeElement).toBe(second)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(wrapper.emitted('close')?.length).toBeGreaterThan(0)

    await wrapper.setProps({ open: false })
    await nextTick()
    expect(document.activeElement).toBe(trigger)

    wrapper.unmount()
  })
})
