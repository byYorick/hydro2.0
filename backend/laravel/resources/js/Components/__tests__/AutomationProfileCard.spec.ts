import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AutomationProfileCard from '../AutomationProfileCard.vue'
import { createDefaultLightingForm, createDefaultWaterForm, FALLBACK_AUTOMATION_DEFAULTS } from '@/composables/useAutomationDefaults'

const props = {
  canConfigureAutomation: false, telemetryLabel: 'Нет данных', waterTopologyLabel: 'Два бака',
  waterForm: createDefaultWaterForm(FALLBACK_AUTOMATION_DEFAULTS),
  lightingForm: createDefaultLightingForm(FALLBACK_AUTOMATION_DEFAULTS),
}

describe('AutomationProfileCard target provenance', () => {
  it('shows targets of the current recipe phase rather than profile recommendations', () => {
    const wrapper = mount(AutomationProfileCard, { props: { ...props, phaseTargets: { ph: 5.9, ec: 1.7, phaseLabel: 'Активная фаза' } } })
    expect(wrapper.text()).toContain('pH 5.90')
    expect(wrapper.text()).toContain('EC 1.70')
    expect(wrapper.text()).toContain('Активная фаза')
  })
  it('keeps absent phase targets empty instead of inventing profile defaults', () => {
    const wrapper = mount(AutomationProfileCard, { props })
    expect(wrapper.text()).toContain('pH — · EC —')
    expect(wrapper.text()).toContain('Активная фаза не загружена')
  })
})
