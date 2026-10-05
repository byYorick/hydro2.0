import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { reactive } from 'vue'
import GreenhouseClimateConfiguration from '@/Components/GreenhouseClimateConfiguration.vue'
import IrrigationSubview from '@/Components/Launch/Automation/Subviews/IrrigationSubview.vue'
import {
  buildRecipePhasePayload,
  createDefaultRecipePhase,
  hydrateRecipePhaseForm,
  nullableDraftNumber,
} from '@/composables/recipeEditorShared'
import { greenhouseClimateSavePayload } from '@/composables/zoneAutomationProfilePayload'
import { applyAutomationFromRecipe } from '@/composables/zoneAutomationTargetsParser'
import {
  createDefaultClimateForm,
  createDefaultLightingForm,
  createDefaultWaterForm,
  FALLBACK_AUTOMATION_DEFAULTS,
} from '@/composables/useAutomationDefaults'

function climateForm() {
  return createDefaultClimateForm(FALLBACK_AUTOMATION_DEFAULTS)
}

function greenhouseTargets(payload: Record<string, unknown> | null): Record<string, unknown> {
  const climate = payload?.climate as Record<string, unknown>
  const execution = climate.execution as Record<string, unknown>
  return execution.greenhouse_targets as Record<string, unknown>
}

describe('пустой DLI', () => {
  it('не становится 0', () => {
    const phase = createDefaultRecipePhase(0)
    phase.dli_target = nullableDraftNumber('')
    expect(buildRecipePhasePayload(phase).dli_target).toBeNull()

    phase.dli_target = nullableDraftNumber('   ')
    expect(buildRecipePhasePayload(phase).dli_target).toBeNull()

    const sneaky = createDefaultRecipePhase(0)
    ;(sneaky as { dli_target: unknown }).dli_target = ''
    expect(buildRecipePhasePayload(sneaky).dli_target).toBeNull()
    expect(buildRecipePhasePayload(sneaky).dli_target).not.toBe(0)

    const hydrated = hydrateRecipePhaseForm({
      phase_index: 1,
      name: 'Вега',
      dli_target: null,
      solution_temp_min: null,
      solution_temp_max: null,
      extensions: {
        solution_max_age_days: null,
        solution_refresh_after_topup_ml: '',
        solution_health: { required: false, breach_hold_sec: '' },
      },
    })
    const payload = buildRecipePhasePayload(hydrated)
    const extensions = payload.extensions as Record<string, unknown>
    const health = extensions.solution_health as Record<string, unknown>
    expect(payload.dli_target).toBeNull()
    expect(payload.solution_temp_min).toBeNull()
    expect(payload.solution_temp_max).toBeNull()
    expect(extensions.solution_max_age_days).toBeNull()
    expect(extensions.solution_refresh_after_topup_ml).toBeNull()
    expect(health.breach_hold_sec).toBeNull()
    expect(health.breach_hold_sec).not.toBe(0)
  })
})

describe('VPD воздуха', () => {
  it('min больше max не уходит в запрос', () => {
    const form = climateForm()
    form.vpdMinKpa = 1.6
    form.vpdMaxKpa = 0.8
    const save = greenhouseClimateSavePayload(form, true)

    expect(save.payload).toBeNull()
    expect(save.error).toMatch(/минимум/)
    expect(JSON.stringify(save)).not.toContain('vpd_min_kpa')
    expect(JSON.stringify(save)).not.toContain('1.6')
  })

  it('пустая пара уходит как null, не как 0', () => {
    const form = climateForm()
    form.vpdMinKpa = nullableDraftNumber('')
    form.vpdMaxKpa = nullableDraftNumber('  ')
    const save = greenhouseClimateSavePayload(form, true)

    expect(save.error).toBeNull()
    expect(save.payload).not.toBeNull()
    const targets = greenhouseTargets(save.payload)
    expect(targets.vpd_min_kpa).toBeNull()
    expect(targets.vpd_max_kpa).toBeNull()
    expect(targets.vpd_min_kpa).not.toBe(0)
  })

  it('читает сохранённую пару и не затирает её чужой подсистемой', () => {
    const forms = {
      climateForm: climateForm(),
      waterForm: createDefaultWaterForm(FALLBACK_AUTOMATION_DEFAULTS),
      lightingForm: createDefaultLightingForm(FALLBACK_AUTOMATION_DEFAULTS),
      zoneClimateForm: { enabled: false },
    }
    applyAutomationFromRecipe({
      extensions: {
        subsystems: {
          climate: {
            execution: {
              greenhouse_targets: { vpd_min_kpa: 0.8, vpd_max_kpa: 1.4 },
            },
          },
        },
      },
    }, forms)
    expect(forms.climateForm.vpdMinKpa).toBe(0.8)
    expect(forms.climateForm.vpdMaxKpa).toBe(1.4)

    applyAutomationFromRecipe({
      extensions: { subsystems: { irrigation: { targets: { duration_sec: 180 } } } },
    }, forms)
    expect(forms.climateForm.vpdMinKpa).toBe(0.8)
    expect(forms.climateForm.vpdMaxKpa).toBe(1.4)
  })

  it('canConfigure=false оставляет поля только для чтения', async () => {
    const form = reactive(climateForm())
    form.vpdMinKpa = 0.8
    form.vpdMaxKpa = 1.2
    const wrapper = mount(GreenhouseClimateConfiguration, {
      props: {
        enabled: true,
        climateForm: form,
        bindings: {
          climate_sensors: [],
          weather_station_sensors: [],
          vent_actuators: [],
          fan_actuators: [],
        },
        canConfigure: false,
      },
    })

    const profile = wrapper.findAll('button').find((button) => button.text() === 'Профиль')
    expect(profile).toBeTruthy()
    await profile!.trigger('click')

    expect(wrapper.text()).toContain('VPD воздуха, не листа')
    expect(wrapper.get('[data-testid="greenhouse-climate-vpd-min"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="greenhouse-climate-vpd-max"]').attributes('disabled')).toBeDefined()
  })
})

describe('стратегия smart_soil_v1', () => {
  it('показывает текст про пропуск без датчика и не прячет окно влажности', () => {
    const waterForm = {
      ...createDefaultWaterForm(FALLBACK_AUTOMATION_DEFAULTS),
      irrigationDecisionStrategy: 'smart_soil_v1' as const,
    }
    const wrapper = mount(IrrigationSubview, { props: { waterForm } })

    expect(wrapper.get('[data-testid="irrigation-strategy-caption"]').text()).toContain('без свежей влажности пропускает полив')
    expect(wrapper.text()).toContain('не помечает задачу сбоем')
    expect(wrapper.find('[data-testid="irrigation-decision-lookback"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="irrigation-decision-stale"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="irrigation-decision-hysteresis"]').exists()).toBe(true)
  })

  it('при task тоже показывает lookback, stale и hysteresis', () => {
    const waterForm = {
      ...createDefaultWaterForm(FALLBACK_AUTOMATION_DEFAULTS),
      irrigationDecisionStrategy: 'task' as const,
    }
    const wrapper = mount(IrrigationSubview, { props: { waterForm } })

    expect(wrapper.find('[data-testid="irrigation-decision-lookback"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="irrigation-decision-stale"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="irrigation-decision-hysteresis"]').exists()).toBe(true)
  })
})
