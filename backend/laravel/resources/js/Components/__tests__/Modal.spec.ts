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
})
