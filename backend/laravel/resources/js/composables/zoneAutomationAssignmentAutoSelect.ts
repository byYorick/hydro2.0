import type { ZoneAutomationSectionAssignments, ZoneAutomationBindRole } from '@/composables/zoneAutomationTypes'
import type { AutomationNode } from '@/types/AutomationNode'
import { matchesAnyBindingRole, matchesAnyChannel } from '@/composables/zoneAutomationNodeMatching'

type RoleFilterSpec = {
  typeCandidates: string[]
  channelCandidates: string[]
  bindingRoleCandidates: string[]
}

const ROLE_ORDER: ZoneAutomationBindRole[] = [
  'irrigation',
  'ph_correction',
  'ec_correction',
  'light',
  'soil_moisture_sensor',
  'co2_sensor',
  'co2_actuator',
  'root_vent_actuator',
]

const ROLE_FILTER_SPECS: Record<ZoneAutomationBindRole, RoleFilterSpec> = {
  irrigation: {
    typeCandidates: ['irrig', 'pump', 'pump_node', 'relay', 'relay_node'],
    channelCandidates: ['pump_main', 'drain', 'drain_main', 'drain_valve', 'valve_solution_supply', 'valve_solution_fill', 'valve_irrigation'],
    bindingRoleCandidates: ['pump_main', 'drain'],
  },
  ph_correction: {
    typeCandidates: ['ph', 'ph_node'],
    channelCandidates: ['pump_acid', 'pump_base', 'ph_sensor'],
    bindingRoleCandidates: ['pump_acid', 'pump_base'],
  },
  ec_correction: {
    typeCandidates: ['ec', 'ec_node'],
    channelCandidates: ['pump_a', 'pump_b', 'pump_c', 'pump_d', 'ec_sensor'],
    bindingRoleCandidates: ['pump_a', 'pump_b', 'pump_c', 'pump_d'],
  },
  light: {
    typeCandidates: ['light', 'light_node', 'relay', 'relay_node'],
    channelCandidates: ['light', 'light_main', 'white_light', 'uv_light'],
    bindingRoleCandidates: ['light', 'light_actuator'],
  },
  soil_moisture_sensor: {
    typeCandidates: ['soil', 'substrate', 'climate', 'climate_node'],
    channelCandidates: ['soil_moisture', 'soil_moisture_pct', 'substrate_moisture'],
    bindingRoleCandidates: ['soil_moisture_sensor'],
  },
  co2_sensor: {
    typeCandidates: ['climate', 'climate_node'],
    channelCandidates: ['co2_ppm'],
    bindingRoleCandidates: ['co2_sensor'],
  },
  co2_actuator: {
    typeCandidates: ['climate', 'climate_node', 'relay', 'relay_node'],
    channelCandidates: ['co2_inject'],
    bindingRoleCandidates: ['co2_actuator'],
  },
  root_vent_actuator: {
    typeCandidates: ['climate', 'climate_node', 'relay', 'relay_node'],
    channelCandidates: ['root_vent', 'fan_root'],
    bindingRoleCandidates: ['root_vent_actuator'],
  },
}

function nodeMatchesRole(node: AutomationNode, role: ZoneAutomationBindRole): boolean {
  const spec = ROLE_FILTER_SPECS[role]
  const normalizedType = String(node.type ?? '').toLowerCase()
  const typeMatched = spec.typeCandidates.includes(normalizedType)
  const channelMatched = matchesAnyChannel(node, spec.channelCandidates)
  const bindingRoleMatched = matchesAnyBindingRole(node, spec.bindingRoleCandidates)

  return typeMatched || channelMatched || bindingRoleMatched
}

export function autoSelectAssignmentsByNodeType(
  current: ZoneAutomationSectionAssignments,
  availableNodes: readonly AutomationNode[],
  zoneId: number,
): ZoneAutomationSectionAssignments {
  const next: ZoneAutomationSectionAssignments = { ...current }
  const candidateNodes = availableNodes.filter(
    (n) => n.zone_id === zoneId || n.pending_zone_id === zoneId || (n.zone_id == null && n.pending_zone_id == null),
  )
  const usedNodeIds = new Set<number>()

  for (const role of ROLE_ORDER) {
    const roleNodeId = next[role]
    if (typeof roleNodeId === 'number' && Number(roleNodeId) > 0) {
      usedNodeIds.add(roleNodeId)
    }
  }

  for (const role of ROLE_ORDER) {
    if (typeof next[role] === 'number' && Number(next[role]) > 0) {
      continue
    }

    const matchedNode = candidateNodes.find(
      (node) => !usedNodeIds.has(node.id) && nodeMatchesRole(node, role),
    )
    if (matchedNode) {
      next[role] = matchedNode.id
      usedNodeIds.add(matchedNode.id)
    }
  }

  return next
}
