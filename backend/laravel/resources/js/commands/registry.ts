import type { Zone, Device, Recipe } from '@/types'
import type { UserRole } from '@/types/User'

export type CommandItemType = 'nav' | 'zone' | 'node' | 'recipe' | 'action'
export type CommandActionType =
  | 'pause'
  | 'resume'
  | 'next-phase'
  | 'irrigate'
  | 'ph-control'
  | 'ec-control'
  | 'open-cycle-wizard'
export type CommandCycleType = 'IRRIGATION' | 'PH_CONTROL' | 'EC_CONTROL'

export type CommandGroupId =
  | 'history'
  | 'navigation'
  | 'zone'
  | 'device'
  | 'recipe'
  | 'action'
  | 'cycle'
  | 'create'
  | 'management'
  | 'admin'
  | 'analytics'
  | 'system'
  | 'other'

export interface CommandGroup {
  id: CommandGroupId
  label: string
  order: number
}

export interface CommandItem {
  id: string
  type: CommandItemType
  label: string
  icon?: string
  category: string
  groupId: CommandGroupId
  shortcut?: string
  action?: () => void
  actionFn?: () => void | Promise<void>
  requiresConfirm?: boolean
  actionType?: CommandActionType
  cycleType?: CommandCycleType
  route?: string
  zoneId?: number
  zoneName?: string
  recipeId?: number
  recipeName?: string
}

export interface GroupedResult {
  category: string
  groupId: CommandGroupId
  items: CommandItem[]
}

export interface CommandHistoryItem {
  label: string
  timestamp: number
  action: string
}

export interface CommandSearchResults {
  zones: Zone[]
  nodes: Device[]
  recipes: Recipe[]
}

export interface CommandHandlers {
  navigate: (route: string) => void
  zoneAction: (zoneId: number, actionType: CommandActionType, zoneName: string) => void | Promise<void>
  zoneCycle: (zoneId: number, cycleType: CommandCycleType, zoneName: string) => void | Promise<void>
  openGrowCycleWizard: (zoneId: number, recipeId: number, zoneName: string, recipeName: string) => void
}

export interface BuildContext {
  query: string
  role?: UserRole
  searchResults: CommandSearchResults
  history: CommandHistoryItem[]
  handlers: CommandHandlers
}

interface CommandDefinition {
  id: string
  label: string
  groupId: CommandGroupId
  icon?: string
  route: string
  roles?: UserRole[]
  shortcut?: string
}

interface EntityTemplate<T> {
  id: string
  type: CommandItemType
  label: string
  groupId: CommandGroupId
  icon?: string
  route?: string
  actionType?: CommandActionType
  cycleType?: CommandCycleType
  requiresConfirm?: boolean
  when?: (entity: T) => boolean
}

interface RecipeZoneTemplate {
  id: string
  type: CommandItemType
  label: string
  groupId: CommandGroupId
  icon?: string
  actionType: CommandActionType
  requiresConfirm?: boolean
  when?: (recipe: Recipe, zone: Zone, query: string) => boolean
}

export const commandGroups: CommandGroup[] = [
  { id: 'history', label: 'История', order: 0 },
  { id: 'navigation', label: 'Навигация', order: 1 },
  { id: 'zone', label: 'Зона', order: 2 },
  { id: 'device', label: 'Устройство', order: 3 },
  { id: 'recipe', label: 'Рецепт', order: 4 },
  { id: 'action', label: 'Действие', order: 5 },
  { id: 'cycle', label: 'Цикл', order: 6 },
  { id: 'create', label: 'Создание', order: 7 },
  { id: 'management', label: 'Управление', order: 8 },
  { id: 'admin', label: 'Администрирование', order: 9 },
  { id: 'analytics', label: 'Аналитика', order: 10 },
  { id: 'system', label: 'Система', order: 11 },
  { id: 'other', label: 'Другое', order: 99 },
]

const groupLabelMap = new Map(commandGroups.map((group) => [group.id, group.label]))
const groupOrderMap = new Map(commandGroups.map((group) => [group.id, group.order]))

const staticCommandDefinitions: CommandDefinition[] = [
  {
    id: 'nav-dashboard',
    label: 'Открыть Dashboard',
    icon: '📊',
    groupId: 'navigation',
    route: '/',
  },
  {
    id: 'nav-zones',
    label: 'Открыть Zones',
    icon: '🌱',
    groupId: 'navigation',
    route: '/zones',
  },
  {
    id: 'nav-devices',
    label: 'Открыть Devices',
    icon: '📱',
    groupId: 'navigation',
    route: '/devices',
  },
  {
    id: 'nav-recipes',
    label: 'Открыть Recipes',
    icon: '📋',
    groupId: 'navigation',
    route: '/recipes',
  },
  {
    id: 'nav-alerts',
    label: 'Открыть Alerts',
    icon: '⚠️',
    groupId: 'navigation',
    route: '/alerts',
  },
  {
    id: 'admin-users',
    label: 'Управление пользователями',
    icon: '👥',
    groupId: 'admin',
    route: '/users',
    roles: ['admin'],
  },
  {
    id: 'admin-settings',
    label: 'Системные настройки',
    icon: '⚙️',
    groupId: 'admin',
    route: '/settings',
    roles: ['admin'],
  },
  {
    id: 'admin-audit',
    label: 'Аудит',
    icon: '📝',
    groupId: 'admin',
    route: '/audit',
    roles: ['admin'],
  },
  {
    id: 'agro-analytics',
    label: 'Аналитика',
    icon: '📈',
    groupId: 'analytics',
    route: '/analytics',
    roles: ['agronomist'],
  },
  {
    id: 'agro-create-recipe',
    label: 'Создать рецепт',
    icon: '➕',
    groupId: 'create',
    route: '/recipes/create',
    roles: ['agronomist'],
  },
  {
    id: 'engineer-system',
    label: 'Системные метрики',
    icon: '📊',
    groupId: 'system',
    route: '/system',
    roles: ['engineer'],
  },
  {
    id: 'engineer-logs',
    label: 'Логи',
    icon: '📋',
    groupId: 'system',
    route: '/logs',
    roles: ['engineer'],
  },
  {
    id: 'operator-greenhouses',
    label: 'Теплицы',
    icon: '🏠',
    groupId: 'management',
    route: '/greenhouses',
    roles: ['operator', 'admin'],
  },
]

const zoneTemplates: Array<EntityTemplate<Zone>> = [
  {
    id: 'zone-open',
    type: 'zone',
    label: '{{zoneName}}',
    icon: '🌱',
    groupId: 'zone',
    route: '/zones/{{zoneId}}',
  },
  {
    id: 'zone-resume',
    type: 'action',
    label: 'Возобновить зону "{{zoneName}}"',
    icon: '▶️',
    groupId: 'action',
    actionType: 'resume',
    requiresConfirm: false,
    when: (zone) => zone.status === 'PAUSED',
  },
  {
    id: 'zone-pause',
    type: 'action',
    label: 'Приостановить зону "{{zoneName}}"',
    icon: '⏸️',
    groupId: 'action',
    actionType: 'pause',
    requiresConfirm: true,
    when: (zone) => zone.status === 'RUNNING',
  },
  {
    id: 'zone-irrigate',
    type: 'action',
    label: 'Полить зону "{{zoneName}}"',
    icon: '💧',
    groupId: 'cycle',
    actionType: 'irrigate',
    cycleType: 'IRRIGATION',
    requiresConfirm: true,
    when: (zone) => zone.status === 'RUNNING',
  },
  {
    id: 'zone-ph-control',
    type: 'action',
    label: 'Коррекция pH в зоне "{{zoneName}}"',
    icon: '🧪',
    groupId: 'cycle',
    actionType: 'ph-control',
    cycleType: 'PH_CONTROL',
    requiresConfirm: true,
    when: (zone) => zone.status === 'RUNNING',
  },
  {
    id: 'zone-ec-control',
    type: 'action',
    label: 'Коррекция EC в зоне "{{zoneName}}"',
    icon: '⚡',
    groupId: 'cycle',
    actionType: 'ec-control',
    cycleType: 'EC_CONTROL',
    requiresConfirm: true,
    when: (zone) => zone.status === 'RUNNING',
  },
  {
    id: 'zone-next-phase',
    type: 'action',
    label: 'Следующая фаза в зоне "{{zoneName}}"',
    icon: '⏭️',
    groupId: 'action',
    actionType: 'next-phase',
    requiresConfirm: true,
    when: (zone) => zone.status === 'RUNNING',
  },
]

const nodeTemplates: Array<EntityTemplate<Device>> = [
  {
    id: 'node-open',
    type: 'node',
    label: '{{nodeLabel}}',
    icon: '📱',
    groupId: 'device',
    route: '/devices/{{nodeId}}',
  },
]

const recipeTemplates: Array<EntityTemplate<Recipe>> = [
  {
    id: 'recipe-open',
    type: 'recipe',
    label: '{{recipeName}}',
    icon: '📋',
    groupId: 'recipe',
    route: '/recipes/{{recipeId}}',
  },
]

const recipeZoneTemplates: RecipeZoneTemplate[] = [
  {
    id: 'recipe-open-cycle-wizard',
    type: 'action',
    label: 'Открыть мастер цикла для зоны "{{zoneName}}"',
    icon: '🔄',
    groupId: 'recipe',
    actionType: 'open-cycle-wizard',
  },
]

const fuzzyMatch = (text: string, query: string): boolean => {
  if (!query) return true
  const textLower = text.toLowerCase()
  const queryLower = query.toLowerCase()
  let textIndex = 0
  let queryIndex = 0

  while (textIndex < textLower.length && queryIndex < queryLower.length) {
    if (textLower[textIndex] === queryLower[queryIndex]) {
      queryIndex++
    }
    textIndex++
  }

  return queryIndex === queryLower.length
}

const resolveTemplate = (template: string, values: Record<string, string | number | undefined | null>): string => {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key) => String(values[key] ?? ''))
}

const isRoleAllowed = (roles: UserRole[] | undefined, role?: UserRole): boolean => {
  if (!roles || roles.length === 0) return true
  if (!role) return false
  return roles.includes(role)
}

const groupLabel = (groupId: CommandGroupId): string => {
  return groupLabelMap.get(groupId) || 'Другое'
}

const buildStaticCommands = (role: UserRole | undefined, handlers: CommandHandlers): CommandItem[] => {
  return staticCommandDefinitions
    .filter((definition) => isRoleAllowed(definition.roles, role))
    .map((definition) => ({
      id: definition.id,
      type: 'nav',
      label: definition.label,
      icon: definition.icon,
      category: groupLabel(definition.groupId),
      groupId: definition.groupId,
      shortcut: definition.shortcut,
      route: definition.route,
      action: () => handlers.navigate(definition.route),
    }))
}

const buildHistoryCommands = (history: CommandHistoryItem[], staticCommands: CommandItem[]): CommandItem[] => {
  return history.map((historyItem, index) => {
    const match = staticCommands.find((command) => command.label === historyItem.label)
    return {
      id: `history-${historyItem.timestamp}-${index}`,
      type: match?.type ?? 'nav',
      label: historyItem.label,
      icon: '🕐',
      category: groupLabel('history'),
      groupId: 'history',
      shortcut: index === 0 ? 'Недавно' : undefined,
      route: match?.route,
      action: match?.action,
      actionFn: match?.actionFn,
      requiresConfirm: match?.requiresConfirm,
      actionType: match?.actionType,
      cycleType: match?.cycleType,
      zoneId: match?.zoneId,
      zoneName: match?.zoneName,
      recipeId: match?.recipeId,
      recipeName: match?.recipeName,
    }
  })
}

const buildZoneCommands = (zones: Zone[], query: string, handlers: CommandHandlers): CommandItem[] => {
  return zones.flatMap((zone) => {
    if (!fuzzyMatch(zone.name, query)) return []
    return zoneTemplates
      .filter((template) => (template.when ? template.when(zone) : true))
      .map((template) => {
        const label = resolveTemplate(template.label, { zoneName: zone.name })
        const route = template.route ? resolveTemplate(template.route, { zoneId: zone.id }) : undefined
        const actionFn = template.cycleType
          ? () => handlers.zoneCycle(zone.id, template.cycleType as CommandCycleType, zone.name)
          : template.actionType
            ? () => handlers.zoneAction(zone.id, template.actionType as CommandActionType, zone.name)
            : undefined

        return {
          id: `${template.id}-${zone.id}`,
          type: template.type,
          label,
          icon: template.icon,
          category: groupLabel(template.groupId),
          groupId: template.groupId,
          requiresConfirm: template.requiresConfirm,
          actionType: template.actionType,
          cycleType: template.cycleType,
          route,
          zoneId: zone.id,
          zoneName: zone.name,
          action: route ? () => handlers.navigate(route) : undefined,
          actionFn,
        } as CommandItem
      })
  })
}

const buildNodeCommands = (nodes: Device[], query: string, handlers: CommandHandlers): CommandItem[] => {
  return nodes.flatMap((node) => {
    const label = node.name || node.uid || `Node #${node.id}`
    if (!fuzzyMatch(label, query)) return []
    return nodeTemplates.map((template) => {
      const route = template.route ? resolveTemplate(template.route, { nodeId: node.id }) : undefined
      return {
        id: `${template.id}-${node.id}`,
        type: template.type,
        label: resolveTemplate(template.label, { nodeLabel: label }),
        icon: template.icon,
        category: groupLabel(template.groupId),
        groupId: template.groupId,
        route,
        action: route ? () => handlers.navigate(route) : undefined,
      } as CommandItem
    })
  })
}

const buildRecipeCommands = (
  recipes: Recipe[],
  zones: Zone[],
  query: string,
  handlers: CommandHandlers
): CommandItem[] => {
  return recipes.flatMap((recipe) => {
    if (!fuzzyMatch(recipe.name, query)) return []

    const items: CommandItem[] = recipeTemplates.map((template) => {
      const route = template.route ? resolveTemplate(template.route, { recipeId: recipe.id }) : undefined
      return {
        id: `${template.id}-${recipe.id}`,
        type: template.type,
        label: resolveTemplate(template.label, { recipeName: recipe.name }),
        icon: template.icon,
        category: groupLabel(template.groupId),
        groupId: template.groupId,
        route,
        recipeId: recipe.id,
        recipeName: recipe.name,
        action: route ? () => handlers.navigate(route) : undefined,
      }
    })

    const zoneMatches = zones.filter((zone) => {
      const zoneName = zone.name || ''
      return fuzzyMatch(zoneName, query) || query.toLowerCase().includes(zoneName.toLowerCase())
    })

    zoneMatches.forEach((zone) => {
      recipeZoneTemplates.forEach((template) => {
        if (template.when && !template.when(recipe, zone, query)) return
        items.push({
          id: `${template.id}-${recipe.id}-${zone.id}`,
          type: template.type,
          label: resolveTemplate(template.label, { zoneName: zone.name }),
          icon: template.icon,
          category: groupLabel(template.groupId),
          groupId: template.groupId,
          requiresConfirm: template.requiresConfirm,
          actionType: template.actionType,
          zoneId: zone.id,
          zoneName: zone.name,
          recipeId: recipe.id,
          recipeName: recipe.name,
          actionFn: () => handlers.openGrowCycleWizard(zone.id, recipe.id, zone.name, recipe.name),
        })
      })
    })

    return items
  })
}

export const buildCommandItems = (context: BuildContext): CommandItem[] => {
  const { query, role, searchResults, history, handlers } = context
  const normalizedQuery = query.trim().toLowerCase()
  const staticCommands = buildStaticCommands(role, handlers)
  const historyCommands = buildHistoryCommands(history, staticCommands)

  if (!normalizedQuery) {
    return [...historyCommands, ...staticCommands]
  }

  const results: CommandItem[] = []

  results.push(...staticCommands.filter((command) => fuzzyMatch(command.label, normalizedQuery)))
  results.push(...historyCommands.filter((command) => fuzzyMatch(command.label, normalizedQuery)))
  results.push(...buildZoneCommands(searchResults.zones, normalizedQuery, handlers))
  results.push(...buildNodeCommands(searchResults.nodes, normalizedQuery, handlers))
  results.push(...buildRecipeCommands(searchResults.recipes, searchResults.zones, normalizedQuery, handlers))

  return results
}

export const groupCommandItems = (items: CommandItem[]): GroupedResult[] => {
  const grouped = new Map<CommandGroupId, GroupedResult>()

  items.forEach((item) => {
    const groupId = item.groupId || 'other'
    if (!grouped.has(groupId)) {
      grouped.set(groupId, {
        category: groupLabel(groupId),
        groupId,
        items: [],
      })
    }
    const group = grouped.get(groupId)
    if (group) {
      group.items.push(item)
    }
  })

  return Array.from(grouped.values()).sort((a, b) => {
    const aOrder = groupOrderMap.get(a.groupId) ?? 999
    const bOrder = groupOrderMap.get(b.groupId) ?? 999
    return aOrder - bOrder
  })
}
