import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import BindingsSubview from '../Subviews/BindingsSubview.vue'
import type { ZoneAutomationSectionAssignments } from '@/composables/zoneAutomationTypes'
import type { AutomationNode } from '@/types/AutomationNode'

const emptyAssignments: ZoneAutomationSectionAssignments = {
  irrigation: null,
  ph_correction: null,
  ec_correction: null,
  light: null,
  soil_moisture_sensor: null,
  co2_sensor: null,
  co2_actuator: null,
  root_vent_actuator: null,
}

describe('BindingsSubview', () => {
  it('фильтрует список нод по роли в окне выбора', () => {
    const nodes: AutomationNode[] = [
      {
        id: 10,
        uid: 'zone-node',
        type: 'pump_node',
        zone_id: 1,
        pending_zone_id: null,
      },
      {
        id: 11,
        uid: 'new-node',
        type: 'ph_node',
        zone_id: null,
        pending_zone_id: null,
      },
    ]

    const wrapper = mount(BindingsSubview, {
      props: {
        zoneId: 1,
        assignments: emptyAssignments,
        availableNodes: nodes,
      },
    })

    const selects = wrapper.findAll('select')
    const irrigationOptions = selects[0].findAll('option').map((o) => o.text())
    const phOptions = selects[1].findAll('option').map((o) => o.text())

    expect(irrigationOptions.join(' ')).toContain('zone-node')
    expect(irrigationOptions.join(' ')).not.toContain('new-node')
    expect(phOptions.join(' ')).toContain('new-node')
  })
})
