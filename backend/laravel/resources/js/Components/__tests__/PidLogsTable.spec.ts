import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const getPidLogsMock = vi.hoisted(() => vi.fn())

vi.mock('@/composables/usePidConfig', () => ({
  usePidConfig: () => ({
    getPidLogs: getPidLogsMock,
  }),
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}))

vi.mock('../Card.vue', () => ({
  default: {
    name: 'Card',
    template: '<div><slot /></div>',
  },
}))

vi.mock('../Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['disabled', 'size', 'variant'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
}))

vi.mock('../Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant'],
    template: '<span><slot /></span>',
  },
}))

import PidLogsTable from '../PidLogsTable.vue'

describe('PidLogsTable.vue', () => {
  beforeEach(() => {
    getPidLogsMock.mockReset()
    getPidLogsMock.mockResolvedValue({
      logs: [
        {
          id: 10,
          type: 'config_updated',
          pid_type: 'ph',
          updated_by: 7,
          old_config: {
            dead_zone: 0.08,
          },
          new_config: {
            dead_zone: 0.05,
            close_zone: 0.3,
            max_integral: 20,
          },
          created_at: '2026-03-17T12:00:00Z',
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('показывает summary для PID_CONFIG_UPDATED', async () => {
    const wrapper = mount(PidLogsTable, {
      props: { zoneId: 42 },
    })

    await flushPromises()

    expect(getPidLogsMock).toHaveBeenCalledWith(42, {
      type: undefined,
      limit: 50,
      offset: 0,
    })
    expect(wrapper.text()).toContain('Config PH')
    expect(wrapper.text()).toContain('updated_by #7')
    expect(wrapper.text()).toContain('dead zone 0.05')
    expect(wrapper.text()).toContain('close zone 0.30')
    expect(wrapper.text()).toContain('max integral 20.0')

    wrapper.unmount()
  })
})
