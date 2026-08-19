import type { UnifiedZone } from '@/composables/useUnifiedDashboard'
import type { UserRole } from '@/types/User'

export type DashboardView = 'operations' | 'agronomy' | 'engineering' | 'admin'

export const DASHBOARD_HERO_TITLE: Record<DashboardView, string> = {
  operations: 'Сегодня',
  agronomy: 'Обзор культур',
  engineering: 'Узлы',
  admin: 'Система',
}

export const DASHBOARD_HERO_SUBTITLE: Record<DashboardView, string> = {
  operations: 'Очередь смены и зоны. Пауза автоматики — на карточке зоны.',
  agronomy: 'Культуры, коридор pH/EC и ближайшие переходы фаз.',
  engineering: 'Проблемные узлы и зоны. Карточки — диагностика.',
  admin: 'Здоровье сервисов, блокировки автоматики и инциденты.',
}

export const DASHBOARD_CONTEXT_TITLE: Record<DashboardView, string> = {
  operations: 'Последние события',
  agronomy: 'Отклонения',
  engineering: 'Инженерные события',
  admin: 'Инциденты',
}

export type DashboardEventScope = 'all' | 'warnings_alerts' | 'alerts_only'

export function resolveDashboardView(role: UserRole | string | undefined | null): DashboardView {
  if (role === 'agronomist') {
    return 'agronomy'
  }
  if (role === 'engineer') {
    return 'engineering'
  }
  if (role === 'admin') {
    return 'admin'
  }

  return 'operations'
}

export function eventScopeForView(view: DashboardView): DashboardEventScope {
  if (view === 'admin') {
    return 'alerts_only'
  }
  if (view === 'agronomy') {
    return 'warnings_alerts'
  }

  return 'all'
}

export function cropGroupLabel(zone: UnifiedZone): string {
  return zone.crop || zone.plant?.name || zone.recipe?.name || 'Без культуры'
}

export interface CropZoneGroup {
  crop: string
  zones: UnifiedZone[]
}

export function groupZonesByCrop(zones: UnifiedZone[]): CropZoneGroup[] {
  const groups = new Map<string, UnifiedZone[]>()

  for (const zone of zones) {
    const label = cropGroupLabel(zone)
    const bucket = groups.get(label)
    if (bucket) {
      bucket.push(zone)
    } else {
      groups.set(label, [zone])
    }
  }

  return Array.from(groups.entries()).map(([crop, grouped]) => ({
    crop,
    zones: grouped,
  }))
}

export interface ShiftQueueItem {
  zoneId: number
  zoneName: string
  reason: string
  openHref: string
  alertsHref: string
}

function zoneOpenHref(zoneId: number): string {
  return `/zones/${zoneId}`
}

function zoneAlertsHref(zoneId: number): string {
  return `/zones/${zoneId}?tab=alerts`
}

export function buildShiftQueue(zones: UnifiedZone[]): ShiftQueueItem[] {
  const items: ShiftQueueItem[] = []
  const seen = new Set<number>()

  const push = (zone: UnifiedZone, reason: string): void => {
    if (seen.has(zone.id)) {
      return
    }
    seen.add(zone.id)
    items.push({
      zoneId: zone.id,
      zoneName: zone.name,
      reason,
      openHref: zoneOpenHref(zone.id),
      alertsHref: zoneAlertsHref(zone.id),
    })
  }

  for (const zone of zones) {
    if (zone.automation_block?.blocked) {
      push(zone, zone.automation_block.message?.trim() || 'Автоматика остановлена')
    }
  }

  for (const zone of zones) {
    if (zone.status === 'ALARM') {
      push(zone, 'Тревога')
    }
  }

  for (const zone of zones) {
    if ((zone.alerts_count ?? 0) > 0) {
      push(zone, 'Есть тревоги')
    }
  }

  return items
}

type CorridorStatus = 'in' | 'out' | 'unknown'

function metricCorridor(
  value: number | null | undefined,
  range: { min: number | null; max: number | null } | null | undefined,
): CorridorStatus {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return 'unknown'
  }
  if (!range || range.min === null || range.max === null) {
    return 'unknown'
  }
  return value >= range.min && value <= range.max ? 'in' : 'out'
}

export function zonePhEcCorridor(zone: UnifiedZone): CorridorStatus {
  const ph = metricCorridor(zone.telemetry?.ph, zone.targets?.ph)
  const ec = metricCorridor(zone.telemetry?.ec, zone.targets?.ec)

  if (ph === 'out' || ec === 'out') {
    return 'out'
  }
  if (ph === 'in' || ec === 'in') {
    return 'in'
  }

  if (zone.status === 'ALARM' || zone.status === 'WARNING') {
    return 'out'
  }
  if (zone.status === 'RUNNING' || zone.status === 'OK') {
    return 'in'
  }

  return 'unknown'
}

export interface AgronomyCorridorSummary {
  inRange: number
  outOfRange: number
  unknown: number
  total: number
}

export function summarizePhEcCorridor(zones: UnifiedZone[]): AgronomyCorridorSummary {
  const summary: AgronomyCorridorSummary = {
    inRange: 0,
    outOfRange: 0,
    unknown: 0,
    total: zones.length,
  }

  for (const zone of zones) {
    const status = zonePhEcCorridor(zone)
    if (status === 'in') {
      summary.inRange += 1
    } else if (status === 'out') {
      summary.outOfRange += 1
    } else {
      summary.unknown += 1
    }
  }

  return summary
}

export interface UpcomingPhaseTransition {
  zoneId: number
  zoneName: string
  phaseName: string
  at: string
}

export function upcomingPhaseTransitions(
  zones: UnifiedZone[],
  nowMs: number = Date.now(),
  limit: number = 5,
): UpcomingPhaseTransition[] {
  const items: UpcomingPhaseTransition[] = []

  for (const zone of zones) {
    const cycle = zone.cycle
    if (!cycle) {
      continue
    }

    const stages = cycle.stages ?? []
    const active = stages.find((stage) => stage.state === 'ACTIVE')
    if (active?.to) {
      const at = new Date(active.to).getTime()
      if (Number.isFinite(at) && at >= nowMs) {
        const index = stages.indexOf(active)
        const next = stages[index + 1]
        items.push({
          zoneId: zone.id,
          zoneName: zone.name,
          phaseName: next?.name || active.name || cycle.current_stage?.name || 'Фаза',
          at: active.to,
        })
        continue
      }
    }

    const upcoming = stages.find((stage) => {
      if (stage.state === 'ACTIVE' || !stage.from) {
        return false
      }
      const at = new Date(stage.from).getTime()
      return Number.isFinite(at) && at >= nowMs
    })
    if (upcoming?.from) {
      items.push({
        zoneId: zone.id,
        zoneName: zone.name,
        phaseName: upcoming.name || 'Фаза',
        at: upcoming.from,
      })
      continue
    }

    if (cycle.expected_harvest_at) {
      const at = new Date(cycle.expected_harvest_at).getTime()
      if (Number.isFinite(at) && at >= nowMs) {
        items.push({
          zoneId: zone.id,
          zoneName: zone.name,
          phaseName: 'Урожай',
          at: cycle.expected_harvest_at,
        })
      }
    }
  }

  return items
    .sort((left, right) => new Date(left.at).getTime() - new Date(right.at).getTime())
    .slice(0, limit)
}

export interface EngineeringIssue {
  zoneId: number
  zoneName: string
  reasons: string[]
  openHref: string
}

export function buildEngineeringIssues(zones: UnifiedZone[]): EngineeringIssue[] {
  const issues: EngineeringIssue[] = []

  for (const zone of zones) {
    const reasons: string[] = []
    const online = zone.devices?.online ?? 0
    const total = zone.devices?.total ?? 0
    if (total > 0 && online < total) {
      reasons.push(`Узлы офлайн: ${online}/${total}`)
    }
    if (zone.irrig_node && zone.irrig_node.online === false) {
      reasons.push('Поливной узел не на связи')
    } else if (zone.irrig_node?.stale) {
      reasons.push('Данные полива устарели')
    }
    if (zone.automation_block?.blocked) {
      reasons.push(zone.automation_block.message?.trim() || 'Автоматика остановлена')
    }

    if (reasons.length > 0) {
      issues.push({
        zoneId: zone.id,
        zoneName: zone.name,
        reasons,
        openHref: zoneOpenHref(zone.id),
      })
    }
  }

  return issues
}
