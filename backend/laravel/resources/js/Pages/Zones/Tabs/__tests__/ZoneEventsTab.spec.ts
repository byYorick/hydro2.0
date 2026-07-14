import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ZoneEventsTab from '../ZoneEventsTab.vue'

vi.mock('@/services/api', () => ({
  api: {
    zones: {
      eventsPage: vi.fn().mockResolvedValue({
        data: [],
        last_event_id: null,
        oldest_event_id: null,
        has_more: false,
        has_more_before: false,
      }),
    },
  },
}))

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

async function expandEngineerEvent(wrapper: ReturnType<typeof mount>) {
  const engineer = wrapper.get('[data-testid="zone-events-engineer"]')
  const clickable = engineer.findAll('.cursor-pointer')
  // [0] group header, [1] EventRow
  await clickable[1].trigger('click')
}

describe('ZoneEventsTab.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('рендерит dual-pane: оператор и инженер', () => {
    const wrapper = mount(ZoneEventsTab, {
      props: {
        zoneId: 42,
        events: [
          makeEvent(1, 'EC_DOSING', 'EC dosing', {
            task_id: 28,
            correction_window_id: 'task:28:irrigating:irrigation_check',
            dose_ml: 12,
            channel: 'A+B',
          }),
          makeEvent(2, 'IRR_STATE_SNAPSHOT', 'snapshot', { task_id: 28 }),
          makeEvent(3, 'ALERT_CREATED', 'Alert', { severity: 'critical', code: 'pump fail' }),
        ],
      },
    })

    expect(wrapper.find('[data-testid="zone-events-operator"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="zone-events-engineer"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="zone-events-operator"]').text()).not.toContain('IRR_STATE_SNAPSHOT')
    expect(wrapper.get('[data-testid="zone-events-operator"]').text()).toContain('Тревога')
    expect(wrapper.get('[data-testid="zone-events-engineer"]').text()).toContain('AE задача #28')
  })

  it('группирует связанные runtime events по задаче и correction window', () => {
    const wrapper = mount(ZoneEventsTab, {
      props: {
        zoneId: 42,
        events: [
          makeEvent(
            1,
            'EC_DOSING',
            'EC dosing',
            {
              task_id: 28,
              correction_window_id: 'task:28:irrigating:irrigation_check',
              workflow_phase: 'irrigating',
              stage: 'irrigation_check',
              snapshot_event_id: 1699,
            },
          ),
          makeEvent(
            2,
            'CORRECTION_DECISION_MADE',
            'Decision',
            {
              task_id: 28,
              correction_window_id: 'task:28:irrigating:irrigation_check',
              workflow_phase: 'irrigating',
              stage: 'irrigation_check',
              selected_action: 'ec',
              current_ec: 1.1,
            },
          ),
          makeEvent(
            3,
            'ALERT_CREATED',
            'Alert',
            {
              severity: 'critical',
            },
          ),
        ],
      },
    })

    expect(wrapper.get('[data-testid="zone-events-engineer"]').text()).toContain('AE задача #28 · Окно irrigation_check')
    expect(wrapper.get('[data-testid="zone-events-engineer"]').text()).toContain('2 события')
    expect(wrapper.get('[data-testid="zone-events-engineer"]').text()).toContain('Тревога создана')
    expect(wrapper.get('[data-testid="zone-events-operator"]').text()).toContain('Коррекция EC')
  })

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
    })

    await expandEngineerEvent(wrapper)

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
    })

    await expandEngineerEvent(wrapper)

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
    })

    await expandEngineerEvent(wrapper)

    expect(wrapper.text()).toContain('EC')
    expect(wrapper.text()).toContain('1.98')
    expect(wrapper.text()).toContain('EC gap 0.0200 <= deadband 0.0500')
  })

  it('локализует код ошибки в деталях AE task failed', async () => {
    const wrapper = mount(ZoneEventsTab, {
      props: {
        zoneId: 42,
        events: [
          makeEvent(
            4,
            'AE_TASK_FAILED',
            'Automation task failed',
            {
              task_id: 123,
              error_code: 'start_cycle_zone_busy',
              error_message: 'Intent skipped: zone busy',
              stage: 'prepare',
            },
          ),
        ],
      },
    })

    await expandEngineerEvent(wrapper)

    expect(wrapper.text()).toContain('Ошибка:')
    expect(wrapper.text()).toContain('Повторный запуск отклонён: по зоне уже есть активный intent или выполняемая задача.')
    expect(wrapper.text()).toContain('Код ошибки:')
    expect(wrapper.text()).toContain('start_cycle_zone_busy')
  })

  it('показывает trace-поля для события решения коррекции', async () => {
    const wrapper = mount(ZoneEventsTab, {
      props: {
        zoneId: 42,
        events: [
          makeEvent(
            5,
            'CORRECTION_DECISION_MADE',
            'Коррекция: решение принято',
            {
              correction_window_id: 'task:3:tank_filling:solution_fill_check',
              task_id: 3,
              workflow_phase: 'tank_filling',
              stage: 'solution_fill_check',
              selected_action: 'ph_down',
              decision_reason: 'prioritize_pending_ph_after_ec_observe',
              observe_seq: 2,
              current_ph: 6.83,
              current_ec: 0.52,
              needs_ec: true,
              needs_ph_down: true,
              needs_ph_up: false,
            },
          ),
        ],
      },
    })

    await expandEngineerEvent(wrapper)

    expect(wrapper.text()).toContain('Окно коррекции:')
    expect(wrapper.text()).toContain('task:3:tank_filling:solution_fill_check')
    expect(wrapper.text()).toContain('Выбранный контур:')
    expect(wrapper.text()).toContain('ph_down')
    expect(wrapper.text()).toContain('Причина выбора:')
    expect(wrapper.text()).toContain('prioritize_pending_ph_after_ec_observe')
    expect(wrapper.text()).toContain('Наблюдение:')
    expect(wrapper.text()).toContain('#2')
  })

  it('показывает causal-поля для события старта inline-коррекции', async () => {
    const wrapper = mount(ZoneEventsTab, {
      props: {
        zoneId: 42,
        events: [
          makeEvent(
            7,
            'IRRIGATION_CORRECTION_STARTED',
            'Inline correction started',
            {
              task_id: 28,
              correction_window_id: 'task:28:irrigating:irrigation_check',
              workflow_phase: 'irrigating',
              stage: 'irrigation_check',
              selected_action: 'ec',
              channel: 'pump_a',
              node_uid: 'nd-test-ec-1',
              snapshot_event_id: 1699,
              caused_by_event_id: 1698,
              event_schema_version: 2,
            },
          ),
        ],
      },
    })

    await expandEngineerEvent(wrapper)

    expect(wrapper.text()).toContain('Snapshot event ID:')
    expect(wrapper.text()).toContain('1699')
    expect(wrapper.text()).toContain('Причинное событие ID:')
    expect(wrapper.text()).toContain('1698')
    expect(wrapper.text()).toContain('Schema version:')
    expect(wrapper.text()).toContain('2')
    expect(wrapper.text()).toContain('Канал:')
    expect(wrapper.text()).toContain('pump_a')
  })

  it('показывает детали события решения умного полива', async () => {
    const wrapper = mount(ZoneEventsTab, {
      props: {
        zoneId: 42,
        events: [
          makeEvent(
            6,
            'IRRIGATION_DECISION_EVALUATED',
            'Decision-controller полива: разрешён деградированный полив (smart_soil_v1)',
            {
              task_id: 77,
              strategy: 'smart_soil_v1',
              outcome: 'degraded_run',
              reason_code: 'smart_soil_telemetry_missing_or_stale',
              degraded: true,
              bundle_revision: '1234567890abcdef1234567890abcdef12345678',
              details: {
                zone_average_pct: 24.55,
                sensor_count: 3,
                samples: 9,
                spread_pct: 4.2,
                target_profile: 'veg-mid',
                target_mode: 'profile',
                requested_duration_sec: 120,
              },
            },
          ),
        ],
      },
    })

    await expandEngineerEvent(wrapper)

    expect(wrapper.text()).toContain('Задача ID:')
    expect(wrapper.text()).toContain('77')
    expect(wrapper.text()).toContain('Strategy:')
    expect(wrapper.text()).toContain('smart_soil_v1')
    expect(wrapper.text()).toContain('Решение:')
    expect(wrapper.text()).toContain('degraded_run')
    expect(wrapper.text()).toContain('Причина:')
    expect(wrapper.text()).toContain('smart_soil_telemetry_missing_or_stale')
    expect(wrapper.text()).toContain('Degraded:')
    expect(wrapper.text()).toContain('да')
    expect(wrapper.text()).toContain('Bundle:')
    expect(wrapper.text()).toContain('1234567890ab')
    expect(wrapper.text()).toContain('Средняя влажность:')
    expect(wrapper.text()).toContain('24.55%')
    expect(wrapper.text()).toContain('Сенсоров:')
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('Сэмплов:')
    expect(wrapper.text()).toContain('9')
    expect(wrapper.text()).toContain('Разброс:')
    expect(wrapper.text()).toContain('4.20%')
    expect(wrapper.text()).toContain('Профиль:')
    expect(wrapper.text()).toContain('veg-mid')
    expect(wrapper.text()).toContain('Target mode:')
    expect(wrapper.text()).toContain('profile')
    expect(wrapper.text()).toContain('Запрошено:')
    expect(wrapper.text()).toContain('120 с')
  })
})
