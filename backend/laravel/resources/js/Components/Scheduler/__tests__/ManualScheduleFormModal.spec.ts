import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ManualScheduleFormModal from '../ManualScheduleFormModal.vue'
import type { ZoneManualSchedule } from '@/composables/zoneScheduleWorkspaceTypes'

const executableTaskTypes = ['irrigation', 'lighting', 'diagnostics']

const modalStub = {
  template: '<div data-testid="modal-stub"><p data-testid="modal-title">{{ title }}</p><slot /><slot name="footer" /></div>',
  props: ['title', 'open', 'size'],
}

describe('ManualScheduleFormModal.vue', () => {
  it('показывает заголовок создания без initial.id', () => {
    const wrapper = mount(ManualScheduleFormModal, {
      props: {
        open: true,
        initial: null,
        saving: false,
        executableTaskTypes,
      },
      global: {
        stubs: {
          Modal: modalStub,
          Button: true,
        },
      },
    })

    expect(wrapper.get('[data-testid="modal-title"]').text()).toContain('Новое расписание')
  })

  it('показывает заголовок редактирования при initial.id', () => {
    const initial: ZoneManualSchedule = {
      id: 5,
      zone_id: 1,
      task_type: 'irrigation',
      schedule_kind: 'time',
      time_at: '08:00',
      enabled: true,
      payload: { duration_sec: 60 },
    }

    const wrapper = mount(ManualScheduleFormModal, {
      props: {
        open: true,
        initial,
        saving: false,
        executableTaskTypes,
      },
      global: {
        stubs: {
          Modal: modalStub,
          Button: true,
        },
      },
    })

    expect(wrapper.get('[data-testid="modal-title"]').text()).toContain('Изменить расписание')
  })

  it('блокирует submit при невалидной форме once без run_at', async () => {
    const wrapper = mount(ManualScheduleFormModal, {
      props: {
        open: true,
        initial: null,
        saving: false,
        executableTaskTypes,
      },
      global: {
        stubs: {
          Modal: modalStub,
          Button: {
            template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
            props: ['disabled'],
          },
        },
      },
    })

    await wrapper.get('[data-testid="manual-schedule-kind-once"]').trigger('click')

    const submit = wrapper.get('[data-testid="manual-schedule-submit"]')
    expect((submit.element as HTMLButtonElement).disabled).toBe(true)
  })
})
