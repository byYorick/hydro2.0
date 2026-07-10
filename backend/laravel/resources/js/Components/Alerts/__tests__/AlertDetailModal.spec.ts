import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AlertDetailModal from '../AlertDetailModal.vue'
import type { Alert } from '@/types/Alert'

function makeAlert(overrides: Partial<Alert> = {}): Alert {
  return {
    id: 42,
    type: 'AE3_ALERT',
    code: 'biz_ae3_task_failed',
    title: 'Задача AE3 завершилась ошибкой',
    status: 'active',
    severity: 'error',
    message: 'Task failed',
    details: {
      task_id: 'task-9001',
      correction_window_id: 'task:9001:irrigating:irrigation_check',
      error_code: 'ae3_timeout',
      stage: 'dose',
    },
    created_at: '2026-03-29T08:00:00Z',
    ...overrides,
  }
}

describe('AlertDetailModal.vue', () => {
  it('показывает process-stopping, task и correction window', () => {
    const wrapper = mount(AlertDetailModal, {
      props: {
        open: true,
        alert: makeAlert(),
        resolveLoading: false,
      },
      global: {
        stubs: {
          Modal: {
            props: ['open', 'title'],
            template: '<div v-if="open" data-testid="zone-alert-details-modal"><slot /><slot name="footer" /></div>',
          },
          Button: { template: '<button><slot /></button>' },
          Link: {
            props: ['href'],
            template: '<a :href="href"><slot /></a>',
          },
        },
      },
    })

    expect(wrapper.get('[data-testid="alert-details-process-stop"]').text()).toContain('Стоп: Автоматика')
    expect(wrapper.get('[data-testid="alert-details-task-id"]').text()).toBe('task-9001')
    expect(wrapper.get('[data-testid="alert-details-correction-window-id"]').text())
      .toBe('task:9001:irrigating:irrigation_check')
    expect(wrapper.text()).toContain('error: ae3_timeout · stage: dose')
  })

  it('показывает safety process-stopping для hardware кода', () => {
    const wrapper = mount(AlertDetailModal, {
      props: {
        open: true,
        alert: makeAlert({
          code: 'biz_no_flow',
          title: 'Нет потока',
          severity: 'critical',
          details: { stage: 'irrigation' },
        }),
        resolveLoading: false,
      },
      global: {
        stubs: {
          Modal: {
            props: ['open', 'title'],
            template: '<div v-if="open"><slot /></div>',
          },
          Button: { template: '<button><slot /></button>' },
          Link: {
            props: ['href'],
            template: '<a :href="href"><slot /></a>',
          },
        },
      },
    })

    expect(wrapper.get('[data-testid="alert-details-process-stop"]').text()).toContain('Стоп: Железо')
    expect(wrapper.find('[data-testid="alert-details-task-id"]').exists()).toBe(false)
  })

  it('рендерит кнопку решения только для активного алерта', () => {
    const active = mount(AlertDetailModal, {
      props: {
        open: true,
        alert: makeAlert(),
        resolveLoading: false,
      },
      global: {
        stubs: {
          Modal: {
            props: ['open'],
            template: '<div v-if="open"><slot name="footer" /></div>',
          },
          Button: { template: '<button><slot /></button>' },
        },
      },
    })

    expect(active.find('[data-testid="zone-alert-resolve-button"]').exists()).toBe(true)

    const resolved = mount(AlertDetailModal, {
      props: {
        open: true,
        alert: makeAlert({ status: 'resolved', resolved_at: '2026-03-29T09:00:00Z' }),
        resolveLoading: false,
      },
      global: {
        stubs: {
          Modal: {
            props: ['open'],
            template: '<div v-if="open"><slot name="footer" /></div>',
          },
          Button: { template: '<button><slot /></button>' },
        },
      },
    })

    expect(resolved.find('[data-testid="zone-alert-resolve-button"]').exists()).toBe(false)
  })
})
