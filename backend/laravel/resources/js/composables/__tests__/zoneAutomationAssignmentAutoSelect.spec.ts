import { describe, expect, it } from 'vitest'
import { autoSelectAssignmentsByNodeType } from '@/composables/zoneAutomationAssignmentAutoSelect'
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

describe('autoSelectAssignmentsByNodeType', () => {
  it('автоматически назначает роли по типам и каналам нод', () => {
    const nodes: AutomationNode[] = [
      { id: 1, type: 'pump_node', zone_id: 7, channels: [{ channel: 'pump_main' }] },
      { id: 2, type: 'ph_node', zone_id: 7, channels: [{ channel: 'pump_acid' }] },
      { id: 3, type: 'ec_node', zone_id: null, channels: [{ channel: 'pump_a' }] },
      { id: 4, type: 'light_node', pending_zone_id: 7, channels: [{ channel: 'light_main' }] },
    ]

    const result = autoSelectAssignmentsByNodeType(emptyAssignments, nodes, 7)

    expect(result.irrigation).toBe(1)
    expect(result.ph_correction).toBe(2)
    expect(result.ec_correction).toBe(3)
    expect(result.light).toBe(4)
  })

  it('не перезаписывает уже выбранные вручную роли', () => {
    const current: ZoneAutomationSectionAssignments = {
      ...emptyAssignments,
      irrigation: 99,
    }
    const nodes: AutomationNode[] = [
      { id: 1, type: 'pump_node', zone_id: 7, channels: [{ channel: 'pump_main' }] },
    ]

    const result = autoSelectAssignmentsByNodeType(current, nodes, 7)
    expect(result.irrigation).toBe(99)
  })

  it('не назначает одну и ту же ноду на несколько ролей', () => {
    const nodes: AutomationNode[] = [
      { id: 10, type: 'relay_node', zone_id: 7, channels: [{ channel: 'pump_main' }, { channel: 'light_main' }] },
      { id: 11, type: 'light_node', zone_id: 7, channels: [{ channel: 'light_main' }] },
    ]

    const result = autoSelectAssignmentsByNodeType(emptyAssignments, nodes, 7)

    expect(result.irrigation).toBe(10)
    expect(result.light).toBe(11)
  })
})
