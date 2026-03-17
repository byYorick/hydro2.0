import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ZoneEventsTab from '../ZoneEventsTab.vue'

function makeEvent(id: number, kind: string, message: string, payload: Record<string, unknown>) {
  return {
    id,
    kind,
    zone_id: 42,
    message,
    occurred_at: '2026-03-17T10:10:00Z',
    payload,
  }
}

describe('ZoneEventsTab.vue', () => {
  it('показывает детали correction skipped dose discarded', async () => {
    const wrapper = mount(ZoneEventsTab, {
      props: {
        zoneId: 42,
        events: [
          makeEvent(
            1,
            'CORRECTION_SKIPPED_DOSE_DISCARDED',
            'Коррекция: доза отброшена (below_min_dose_ms, 10мс < 50мс, доза 0.1000 мл, насос 10.0000 мл/с)',
            {
              reason: 'below_min_dose_ms',
              computed_duration_ms: 10,
              min_dose_ms: 50,
              dose_ml: 0.1,
              ml_per_sec: 10.0,
            },
          ),
        ],
      },
      global: {
        stubs: {
          VirtualList: {
            props: ['items'],
            template: '<div><slot v-for="item in items" :key="item.id" :item="item" /></div>',
          },
        },
      },
    })

    await wrapper.find('.cursor-pointer').trigger('click')

    expect(wrapper.text()).toContain('Причина:')
    expect(wrapper.text()).toContain('below_min_dose_ms')
    expect(wrapper.text()).toContain('Импульс:')
    expect(wrapper.text()).toContain('10 мс < 50 мс')
    expect(wrapper.text()).toContain('0.1000 мл')
    expect(wrapper.text()).toContain('10.0000 мл/с')
  })

  it('показывает детали correction skipped window not ready', async () => {
    const wrapper = mount(ZoneEventsTab, {
      props: {
        zoneId: 42,
        events: [
          makeEvent(
            2,
            'CORRECTION_SKIPPED_WINDOW_NOT_READY',
            'Коррекция: окно наблюдения не готово (observe window, EC, insufficient_samples, повтор через 2 с)',
            {
              sensor_scope: 'observe_window',
              sensor_type: 'EC',
              reason: 'insufficient_samples',
              sample_count: 2,
              retry_after_sec: 2,
            },
          ),
        ],
      },
      global: {
        stubs: {
          VirtualList: {
            props: ['items'],
            template: '<div><slot v-for="item in items" :key="item.id" :item="item" /></div>',
          },
        },
      },
    })

    await wrapper.find('.cursor-pointer').trigger('click')

    expect(wrapper.text()).toContain('Окно:')
    expect(wrapper.text()).toContain('observe_window')
    expect(wrapper.text()).toContain('Сенсор:')
    expect(wrapper.text()).toContain('EC')
    expect(wrapper.text()).toContain('Сэмплов:')
    expect(wrapper.text()).toContain('2')
    expect(wrapper.text()).toContain('Повтор через:')
    expect(wrapper.text()).toContain('2 с')
  })

  it('показывает детали correction skipped dead zone с gap/deadband', async () => {
    const wrapper = mount(ZoneEventsTab, {
      props: {
        zoneId: 42,
        events: [
          makeEvent(
            3,
            'CORRECTION_SKIPPED_DEAD_ZONE',
            'Коррекция: мёртвая зона PID (EC 1.98 мС/см, EC gap 0.0200 <= deadband 0.0500)',
            {
              current_ec: 1.98,
              ec_gap: 0.02,
              ec_deadband: 0.05,
              ph_up_gap: 0,
              ph_down_gap: 0,
              ph_deadband: 0.05,
            },
          ),
        ],
      },
      global: {
        stubs: {
          VirtualList: {
            props: ['items'],
            template: '<div><slot v-for="item in items" :key="item.id" :item="item" /></div>',
          },
        },
      },
    })

    await wrapper.find('.cursor-pointer').trigger('click')

    expect(wrapper.text()).toContain('Текущее:')
    expect(wrapper.text()).toContain('1.980')
    expect(wrapper.text()).toContain('EC gap 0.0200 <= deadband 0.0500')
  })
})
