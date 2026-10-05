import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { AutomationState } from '@/types/Automation'
import { normalizeDayBalance } from '@/utils/cropDayView'
import CropDaySection from '../CropDaySection.vue'

function buildState(overrides: Partial<AutomationState> = {}): AutomationState {
  return {
    zone_id: 7,
    state: 'READY',
    state_label: 'Раствор готов',
    state_details: {
      started_at: null,
      elapsed_sec: 0,
      progress_percent: 0,
      failed: false,
    },
    system_config: {
      tanks_count: 2,
      system_type: 'drip',
      clean_tank_capacity_l: null,
      nutrient_tank_capacity_l: null,
    },
    current_levels: {
      clean_tank_level_percent: 0,
      nutrient_tank_level_percent: 0,
      ph: null,
      ec: null,
    },
    active_processes: {
      pump_in: false,
      circulation_pump: false,
      ph_correction: false,
      ec_correction: false,
      active_doses: [],
    },
    timeline: [],
    next_state: null,
    estimated_completion_sec: null,
    observability: {
      hang_hints: [],
      runtime: { zone_id: 7, task_is_active: false },
    },
    ...overrides,
  }
}

describe('CropDaySection', () => {
  it('пусто: первые сутки без команд не рисуют нулевые миллилитры', () => {
    const wrapper = mount(CropDaySection, {
      props: {
        automationState: buildState({
          day_balance: {
            local_date: '2026-10-04',
            timezone_fallback: true,
            irrigation_commands: 0,
            commanded_sec: 0,
            commanded_ml: 0,
            commanded_ml_status: 'ok',
            dli_mol: null,
            dli_status: 'not_configured',
          },
        }),
      },
    })

    expect(wrapper.get('[data-testid="crop-day-section"]').text()).toContain('Сутки')
    expect(wrapper.get('[data-testid="crop-day-date"]').text()).toContain('2026-10-04')
    expect(wrapper.get('[data-testid="crop-day-timezone"]').text()).toContain('UTC, пояс не задан')
    expect(wrapper.get('[data-testid="crop-day-irrigation-commands"]').text()).toBe('0')
    expect(wrapper.get('[data-testid="crop-day-commanded-sec"]').text()).toBe('0 с')
    expect(wrapper.get('[data-testid="crop-day-commanded-ml"]').text()).toBe('нет команд')
    expect(wrapper.get('[data-testid="crop-day-commanded-ml"]').text()).not.toContain('0')
    expect(wrapper.get('[data-testid="crop-day-light"]').text()).toContain('не задано')
    expect(wrapper.get('[data-testid="crop-day-light"]').text()).not.toContain('0')
    expect(wrapper.get('[data-testid="crop-day-climate"]').text()).toContain('нет снимка климата')
    expect(wrapper.get('[data-testid="crop-day-solution-temp"]').text()).toBe('нет температуры')
    expect(wrapper.get('[data-testid="crop-day-solution-gate"]').text()).toBe('нет данных')
    expect(wrapper.get('[data-testid="crop-day-solution-refresh"]').text()).toBe('рекомендации подмены нет')
  })

  it('нет калибровки: миллилитры не становятся нулём', () => {
    const wrapper = mount(CropDaySection, {
      props: {
        automationState: buildState({
          day_balance: {
            local_date: '2026-10-04',
            timezone_fallback: false,
            irrigation_commands: 2,
            commanded_sec: 45,
            commanded_ml: null,
            commanded_ml_status: 'calibration_missing',
            dli_mol: 1.5,
            dli_status: 'within_target',
            solution_temp_c: 19.2,
          },
        }),
      },
    })

    expect(wrapper.get('[data-testid="crop-day-irrigation-commands"]').text()).toBe('2')
    expect(wrapper.get('[data-testid="crop-day-commanded-sec"]').text()).toBe('45 с')
    expect(wrapper.get('[data-testid="crop-day-commanded-ml"]').text()).toBe('нет калибровки канала')
    expect(wrapper.get('[data-testid="crop-day-commanded-ml"]').text()).not.toContain('0')
    expect(wrapper.get('[data-testid="crop-day-light"]').text()).toContain('1.5 моль/м²')
    expect(wrapper.get('[data-testid="crop-day-solution-temp"]').text()).toBe('19.2 °C')
    expect(wrapper.text()).not.toContain('0 мл')
  })

  it('DLI недоступен не рисуется нулём', () => {
    const wrapper = mount(CropDaySection, {
      props: {
        automationState: buildState({
          day_balance: {
            irrigation_commands: 1,
            commanded_sec: 12,
            commanded_ml: 30,
            commanded_ml_status: 'ok',
            dli_mol: null,
            dli_status: 'sensor_unavailable',
          },
        }),
      },
    })

    const light = wrapper.get('[data-testid="crop-day-light"]')
    expect(light.text()).toContain('датчик недоступен')
    expect(light.text()).not.toContain('0')
    expect(light.text()).not.toContain('sensor_unavailable')
  })

  it('блокировка полива показывается текстом подсказки, не сырым reason', () => {
    const wrapper = mount(CropDaySection, {
      props: {
        automationState: buildState({
          day_balance: {
            local_date: '2026-10-04',
            irrigation_commands: 0,
            commanded_sec: 0,
            commanded_ml: null,
            commanded_ml_status: 'ok',
            dli_status: 'gap',
            dli_mol: null,
          },
          observability: {
            hang_hints: [
              {
                code: 'irrigation_sensor_blocked',
                severity: 'critical',
                message: 'Полив пропущен: нет свежего измерения влажности. Насос не запускался.',
                recommendation: 'Проверьте датчик влажности и цель в профиле зоны. Это успешный пропуск, не сбой задачи.',
                details: { reason_code: 'smart_soil_telemetry_missing_or_stale' },
              },
              {
                code: 'solution_temp_blocked',
                severity: 'critical',
                message: 'Полив пропущен: температура раствора вне пределов фазы. Насос не запускался.',
                recommendation: 'Проверьте датчик раствора и пределы фазы. Уже идущая доза не обрывается. Это не сбой задачи.',
                details: { reason_code: 'solution_temp_out_of_band' },
              },
              {
                code: 'waiting_command_stuck',
                severity: 'warning',
                message: 'Задача ждёт ответа по команде дольше ожидаемого',
                recommendation: 'Проверьте MQTT.',
              },
            ],
            runtime: { zone_id: 7, task_is_active: false },
          },
        }),
        recipePhase: {
          extensions: {
            solution_health: { required: true },
          },
        },
      },
    })

    const irrigation = wrapper.get('[data-testid="crop-day-hint-irrigation_sensor_blocked"]')
    expect(irrigation.text()).toContain('Полив пропущен: нет свежего измерения влажности. Насос не запускался.')
    expect(irrigation.text()).toContain('Проверьте датчик влажности и цель в профиле зоны.')
    expect(irrigation.text()).not.toContain('smart_soil_telemetry_missing_or_stale')

    const solution = wrapper.get('[data-testid="crop-day-hint-solution_temp_blocked"]')
    expect(solution.text()).toContain('Полив пропущен: температура раствора вне пределов фазы. Насос не запускался.')
    expect(solution.text()).not.toContain('solution_temp_out_of_band')

    expect(wrapper.text()).not.toContain('waiting_command_stuck')
    expect(wrapper.text()).not.toContain('Задача ждёт ответа по команде')
    expect(wrapper.get('[data-testid="crop-day-solution-gate"]').text()).toBe('включён')
    expect(wrapper.get('[data-testid="crop-day-light"]').text()).toContain('разрыв ряда')
    expect(wrapper.get('[data-testid="crop-day-commanded-ml"]').text()).toBe('нет калибровки канала')
  })

  it('нормализатор не подменяет пустые миллилитры нулём', () => {
    const balance = normalizeDayBalance({
      irrigation_commands: 1,
      commanded_sec: 10,
      commanded_ml: null,
      commanded_ml_status: 'calibration_missing',
      dli_mol: null,
      dli_status: 'sensor_unavailable',
    })

    expect(balance?.commanded_ml).toBeNull()
    expect(balance?.irrigation_commands).toBe(1)
    expect(balance?.dli_mol).toBeNull()
  })
})
