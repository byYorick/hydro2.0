import type { AutomationNode as SetupWizardNode } from '@/types/AutomationNode'

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
