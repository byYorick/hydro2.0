import { computed, type ComputedRef, type MaybeRefOrGetter, toValue } from 'vue'
import type { Node as SetupWizardNode } from '@/types/SetupWizard'

export function nodeLabel(node: SetupWizardNode): string {
  return node.name || node.uid || `Node #${node.id}`
}

export function nodeChannels(node: SetupWizardNode): string[] {
  return Array.isArray(node.channels)
    ? node.channels
      .map((channel) => String(channel.channel ?? '').toLowerCase())
      .filter((channel) => channel.length > 0)
    : []
}

export function nodeBindingRoles(node: SetupWizardNode): string[] {
  return Array.isArray(node.channels)
    ? node.channels
      .map((channel) => String(channel.binding_role ?? '').toLowerCase())
      .filter((role) => role.length > 0)
    : []
}

export function matchesAnyChannel(node: SetupWizardNode, candidates: string[]): boolean {
  const channels = new Set(nodeChannels(node))
  return candidates.some((candidate) => channels.has(candidate))
}

export function matchesAnyBindingRole(node: SetupWizardNode, candidates: string[]): boolean {
  const bindingRoles = new Set(nodeBindingRoles(node))
  return candidates.some((candidate) => bindingRoles.has(candidate))
}

export interface ZoneAutomationNodeCandidates {
  irrigation: ComputedRef<SetupWizardNode[]>
  ph: ComputedRef<SetupWizardNode[]>
  ec: ComputedRef<SetupWizardNode[]>
  light: ComputedRef<SetupWizardNode[]>
  soilMoisture: ComputedRef<SetupWizardNode[]>
  co2Sensor: ComputedRef<SetupWizardNode[]>
  co2Actuator: ComputedRef<SetupWizardNode[]>
  rootVent: ComputedRef<SetupWizardNode[]>
}

/**
 * Фильтрация availableNodes по ролям/каналам для zone automation секций.
 * Используется в ZoneAutomationProfileSections и её под-секциях.
 */
export function useZoneAutomationNodeCandidates(
  availableNodes: MaybeRefOrGetter<SetupWizardNode[] | undefined>,
): ZoneAutomationNodeCandidates {
  const nodes = computed<SetupWizardNode[]>(() => toValue(availableNodes) ?? [])

  const irrigation = computed(() => nodes.value.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'irrig'
      || matchesAnyBindingRole(node, ['main_pump', 'drain'])
      || matchesAnyChannel(node, [
        'pump_main',
        'main_pump',
        'pump_irrigation',
        'valve_irrigation',
        'pump_in',
      ])
  }))

  const ph = computed(() => nodes.value.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'ph'
      || matchesAnyBindingRole(node, ['ph_acid_pump', 'ph_base_pump'])
      || matchesAnyChannel(node, ['ph_sensor', 'pump_acid', 'pump_base'])
  }))

  const ec = computed(() => nodes.value.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'ec'
      || matchesAnyBindingRole(node, ['ec_npk_pump', 'ec_calcium_pump', 'ec_magnesium_pump', 'ec_micro_pump'])
      || matchesAnyChannel(node, ['ec_sensor', 'pump_a', 'pump_b', 'pump_c', 'pump_d'])
  }))

  const light = computed(() => nodes.value.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'light'
      || matchesAnyBindingRole(node, ['light'])
      || matchesAnyChannel(node, ['light', 'light_main', 'white_light', 'uv_light'])
  }))

  const soilMoisture = computed(() => nodes.value.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'soil'
      || type === 'substrate'
      || matchesAnyBindingRole(node, ['soil_moisture_sensor'])
      || matchesAnyChannel(node, ['soil_moisture', 'soil_moisture_pct', 'substrate_moisture'])
  }))

  const co2Sensor = computed(() => nodes.value.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'climate'
      || matchesAnyBindingRole(node, ['co2_sensor'])
      || matchesAnyChannel(node, ['co2_ppm'])
  }))

  const co2Actuator = computed(() => nodes.value.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'climate'
      || matchesAnyBindingRole(node, ['co2_actuator'])
      || matchesAnyChannel(node, ['co2_inject'])
  }))

  const rootVent = computed(() => nodes.value.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'climate'
      || matchesAnyBindingRole(node, ['root_vent_actuator'])
      || matchesAnyChannel(node, ['root_vent', 'fan_root'])
  }))

  return { irrigation, ph, ec, light, soilMoisture, co2Sensor, co2Actuator, rootVent }
}
