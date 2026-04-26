import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CorrectionProfileChooser from '../CorrectionProfileChooser.vue'
import { CORRECTION_PRESETS } from '../correctionPresets'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'

const baseWaterForm: Partial<WaterFormState> = {
  phPct: 5,
  ecPct: 5,
  correctionStabilizationSec: 45,
  correctionMaxPhCorrectionAttempts: 5,
  correctionMaxEcCorrectionAttempts: 5,
}

describe('CorrectionProfileChooser', () => {
  it('renders all 4 preset buttons with labels', () => {
    const w = mount(CorrectionProfileChooser, {
      props: { modelValue: null, waterForm: baseWaterForm as WaterFormState },
    })
    expect(w.text()).toContain('Мягкий')
    expect(w.text()).toContain('Оптимальный')
    expect(w.text()).toContain('Агрессивный')
    expect(w.text()).toContain('Тестовый')
  })

  it('shows description of selected preset', () => {
    const w = mount(CorrectionProfileChooser, {
      props: { modelValue: 'safe', waterForm: baseWaterForm as WaterFormState },
    })
    expect(w.text()).toContain(CORRECTION_PRESETS.safe.desc)
  })

  it('emits update:modelValue + apply on preset click', async () => {
    const w = mount(CorrectionProfileChooser, {
      props: { modelValue: null, waterForm: baseWaterForm as WaterFormState },
    })
    const aggressiveBtn = w.findAll('button').find((b) => b.text().startsWith('Агрессивный'))!
    await aggressiveBtn.trigger('click')

    expect(w.emitted('update:modelValue')![0]).toEqual(['aggressive'])
    const apply = w.emitted('apply')!
    expect(apply[0][0]).toMatchObject({
      phPct: 3,
      ecPct: 3,
      correctionStabilizationSec: 30,
    })
  })

  it('flags "изменено" when waterForm differs from preset', () => {
    const w = mount(CorrectionProfileChooser, {
      props: {
        modelValue: 'balanced',
        waterForm: { ...baseWaterForm, phPct: 9 } as WaterFormState,
      },
    })
    expect(w.text()).toContain('изменено')
  })

  it('does NOT show "изменено" when waterForm matches preset', () => {
    const w = mount(CorrectionProfileChooser, {
      props: {
        modelValue: 'balanced',
        waterForm: baseWaterForm as WaterFormState,
      },
    })
    expect(w.text()).not.toContain('изменено')
  })

  it('exports CORRECTION_PRESETS with all 4 keys', () => {
    expect(Object.keys(CORRECTION_PRESETS)).toEqual([
      'safe',
      'balanced',
      'aggressive',
      'test',
    ])
  })
})
