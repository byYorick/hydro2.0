import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { router, usePage } from '@inertiajs/vue3'
import { useHistory } from '@/composables/useHistory'
import { useZonesStore } from '@/stores/zones'
import { useTelemetryBatch } from '@/composables/useOptimizedUpdates'
import { usePageProps } from '@/composables/usePageProps'
import { logger } from '@/utils/logger'
import { getCycleStatusLabel, getCycleStatusVariant } from '@/utils/growCycleStatus'
import { calculateProgressBetween } from '@/utils/growCycleProgress'
import { normalizeGrowCycle } from '@/utils/normalizeGrowCycle'
import { parseZoneUpdatePayload } from '@/ws/zoneUpdatePayload'
import type { BadgeVariant } from '@/Components/Badge.vue'
import type { Zone, Device, ZoneTelemetry, ZoneTargets as ZoneTargetsType, Cycle, GrowCycle, RecipePhase } from '@/types'
import type { CommandStatus } from '@/types/Command'
import type { ZoneEvent } from '@/types/ZoneEvent'

// ─── Private types ────────────────────────────────────────────────────────────

type ZoneExtended = Zone & {
  active_cycle?: GrowCycle
  activeCycle?: GrowCycle
  active_grow_cycle?: GrowCycle
}

interface PageProps {
  zone?: Zone
  zoneId?: number
  telemetry?: ZoneTelemetry
  targets?: ZoneTargetsType
  devices?: Device[]
  events?: ZoneEvent[]
  cycles?: Record<string, Cycle>
  current_phase?: RecipePhase | null
  active_cycle?: GrowCycle | null
  active_grow_cycle?: GrowCycle | null
  auth?: { user?: { role?: string } }
  [key: string]: unknown
}

const RELOAD_PROPS_DEBOUNCE_MS = 350
const defaultZoneReloadProps = [
  'zone', 'targets', 'current_phase', 'active_cycle', 'active_grow_cycle', 'cycles', 'events', 'devices',
]

// ─── Deps interface ───────────────────────────────────────────────────────────

export interface ZonePageStateDeps {
  reloadZoneAfterCommand: (zoneId: number, only: string[]) => void
  updateCommandStatus: (commandId: string | number, status: CommandStatus, message?: string) => void
  reloadZone: (zoneId: number, only: string[]) => void
  subscribeToZoneCommands: (
    zoneId: number,
    callback: (event: { commandId: string | number; status: CommandStatus; message?: string }) => void
  ) => () => void
}

// ─── Composable ───────────────────────────────────────────────────────────────

export function useZonePageState(deps: ZonePageStateDeps) {
  const { reloadZoneAfterCommand, updateCommandStatus, reloadZone, subscribeToZoneCommands } = deps
  const page = usePage<PageProps>()
  const zonesStore = useZonesStore()

  // ─── Zone identity ────────────────────────────────────────────────────────

  const zoneId = computed(() => {
    if (page.props.zoneId) {
      const id = page.props.zoneId
      return typeof id === 'string' ? Number.parseInt(id, 10) : id
    }
    if (page.props.zone?.id) {
      const id = page.props.zone.id
      return typeof id === 'string' ? Number.parseInt(id, 10) : id
    }
    if (typeof window !== 'undefined') {
      const pathMatch = window.location.pathname.match(/\/zones\/(\d+)/)
      if (pathMatch && pathMatch[1]) return Number.parseInt(pathMatch[1], 10)
    }
    return undefined
  })

  const zone = computed<Zone>(() => {
    const zoneIdValue = zoneId.value
    const rawZoneData = (page.props.zone || {}) as Partial<Zone>
    const propsZone = rawZoneData?.id
      ? ({
          ...rawZoneData,
          id: typeof rawZoneData.id === 'string' ? Number.parseInt(rawZoneData.id, 10) : rawZoneData.id,
        } as Zone)
      : null

    const storeZone = zoneIdValue ? zonesStore.zoneById(zoneIdValue) : undefined
    if (storeZone && propsZone?.id) return { ...storeZone, ...propsZone } as Zone
    if (propsZone?.id) return propsZone
    if (zoneIdValue && storeZone && storeZone.id) return storeZone

    const zoneData = { ...rawZoneData }
    if (!zoneData.id && zoneIdValue) zoneData.id = zoneIdValue
    if (!zoneData.id) return { id: zoneIdValue || undefined } as Zone
    return zoneData as Zone
  })

  const { addToHistory } = useHistory()
  watch(
    zone,
    (newZone) => {
      if (newZone?.id) {
        addToHistory({ id: newZone.id, type: 'zone', name: newZone.name || `Зона ${newZone.id}`, url: `/zones/${newZone.id}` })
      }
    },
    { immediate: true }
  )

  // ─── Telemetry ────────────────────────────────────────────────────────────

  const telemetryRef = ref<ZoneTelemetry>(
    page.props.telemetry || ({ ph: null, ec: null, temperature: null, humidity: null } as ZoneTelemetry)
  )

  const { addUpdate, flush } = useTelemetryBatch((updates) => {
    const currentZoneId = zoneId.value
    updates.forEach((metrics, zoneIdStr) => {
      if (zoneIdStr === String(currentZoneId)) {
        const current = { ...telemetryRef.value }
        metrics.forEach((value, metric) => {
          switch (metric) {
            case 'ph': current.ph = value; break
            case 'ec': current.ec = value; break
            case 'temperature': current.temperature = value; break
            case 'humidity': current.humidity = value; break
          }
        })
        telemetryRef.value = current
      }
    })
  })

  const telemetry = computed(() => telemetryRef.value)

  // ─── Page props ───────────────────────────────────────────────────────────

  const {
    targets: targetsProp,
    devices: devicesProp,
    events: eventsProp,
    cycles: cyclesProp,
    current_phase: currentPhaseProp,
    active_cycle: activeCycleProp,
    active_grow_cycle: activeGrowCycleProp,
  } = usePageProps<PageProps>(['targets', 'devices', 'events', 'cycles', 'current_phase', 'active_cycle', 'active_grow_cycle'])

  const targets = computed(() => (targetsProp.value || {}) as ZoneTargetsType)
  const currentPhase = computed((): RecipePhase | null => currentPhaseProp.value ?? null)

  const activeCycle = computed((): GrowCycle | null => {
    const zoneExt = zone.value as ZoneExtended | undefined
    return activeCycleProp.value ?? zoneExt?.active_cycle ?? zoneExt?.activeCycle ?? null
  })

  const rawActiveGrowCycle = computed((): GrowCycle | null => {
    const zoneExt = zone.value as ZoneExtended | undefined
    return zone.value?.activeGrowCycle ?? zoneExt?.active_grow_cycle ?? activeCycle.value ?? activeGrowCycleProp.value ?? null
  })

  const activeGrowCycle = computed(() => normalizeGrowCycle(rawActiveGrowCycle.value))
  const devices = computed(() => (devicesProp.value || []) as Device[])
  const events = computed(() => (eventsProp.value || []) as ZoneEvent[])
  const cycles = computed(() => (cyclesProp.value || {}) as Record<string, Cycle>)

  // ─── Permissions ─────────────────────────────────────────────────────────

  const userRole = computed(() => page.props.auth?.user?.role || 'viewer')
  const isAgronomist = computed(() => userRole.value === 'agronomist')
  const canOperateZone = computed(() => ['admin', 'operator', 'agronomist', 'engineer'].includes(userRole.value))
  const canManageDevices = computed(() => ['admin', 'agronomist'].includes(userRole.value))
  const canManageRecipe = computed(() => isAgronomist.value || userRole.value === 'admin')
  const canManageCycle = computed(() => ['admin', 'agronomist', 'operator'].includes(userRole.value))

  // ─── Phase / cycle computeds ──────────────────────────────────────────────

  const computedPhaseProgress = computed(() => {
    const phase = currentPhase.value
    if (!phase) {
      logger.debug('[Zones/Show] computedPhaseProgress: phase is null')
      return null
    }
    if (!phase.phase_started_at || !phase.phase_ends_at) {
      logger.debug('[Zones/Show] computedPhaseProgress: missing dates', {
        phase_started_at: phase.phase_started_at,
        phase_ends_at: phase.phase_ends_at,
      })
      return null
    }
    const progress = calculateProgressBetween(phase.phase_started_at, phase.phase_ends_at)
    if (progress === null) {
      logger.debug('[Zones/Show] computedPhaseProgress: unable to calculate', {
        phase_started_at: phase.phase_started_at,
        phase_ends_at: phase.phase_ends_at,
      })
    }
    return progress
  })

  const computedPhaseDaysElapsed = computed(() => {
    const phase = currentPhase.value
    if (!phase || !phase.phase_started_at) return null
    const now = new Date()
    const phaseStart = new Date(phase.phase_started_at)
    if (Number.isNaN(phaseStart.getTime())) return null
    const elapsedMs = now.getTime() - phaseStart.getTime()
    if (elapsedMs <= 0) return 0
    return Math.floor(elapsedMs / (1000 * 60 * 60 * 24))
  })

  const computedPhaseDaysTotal = computed(() => {
    const phase = currentPhase.value
    if (!phase || !phase.duration_hours) return null
    return Math.ceil(phase.duration_hours / 24)
  })

  const cycleStatusLabel = computed(() => {
    if (activeGrowCycle.value) return getCycleStatusLabel(activeGrowCycle.value.status, 'sentence')
    if (activeCycle.value) return 'Цикл активен'
    return 'Цикл не запущен'
  })

  const cycleStatusVariant = computed<BadgeVariant>(() => {
    if (activeGrowCycle.value) return getCycleStatusVariant(activeGrowCycle.value.status)
    if (activeCycle.value) return 'success'
    return 'neutral'
  })

  const phaseTimeLeftLabel = computed(() => {
    const phase = currentPhase.value
    if (!phase || !phase.phase_ends_at) return ''
    const now = new Date()
    const endsAt = new Date(phase.phase_ends_at)
    if (Number.isNaN(endsAt.getTime())) return ''
    const diffMs = endsAt.getTime() - now.getTime()
    if (diffMs <= 0) return 'Фаза завершена'
    const minutes = Math.floor(diffMs / 60000)
    const hours = Math.floor(minutes / 60)
    const days = Math.floor(hours / 24)
    if (days > 0) return `До конца фазы: ${days} дн.`
    if (hours > 0) return `До конца фазы: ${hours} ч`
    return `До конца фазы: ${minutes} мин`
  })

  const cyclesList = computed(() => {
    const phaseTargets = currentPhase.value?.targets ?? {}
    const active = (activeCycle.value as GrowCycle & { subsystems?: Record<string, { targets?: unknown; enabled?: boolean }> })?.subsystems ?? {}
    const serverCycles = cycles.value || {}

    const base = [
      { key: 'ph', type: 'PH_CONTROL', required: true, recipeTargets: phaseTargets.ph || null, activeTargets: active.ph?.targets || null, enabled: active.ph?.enabled ?? true, strategy: serverCycles.PH_CONTROL?.strategy || 'periodic', interval: serverCycles.PH_CONTROL?.interval ?? 300, last_run: serverCycles.PH_CONTROL?.last_run || null, next_run: serverCycles.PH_CONTROL?.next_run || null },
      { key: 'ec', type: 'EC_CONTROL', required: true, recipeTargets: phaseTargets.ec || null, activeTargets: active.ec?.targets || null, enabled: active.ec?.enabled ?? true, strategy: serverCycles.EC_CONTROL?.strategy || 'periodic', interval: serverCycles.EC_CONTROL?.interval ?? 300, last_run: serverCycles.EC_CONTROL?.last_run || null, next_run: serverCycles.EC_CONTROL?.next_run || null },
      { key: 'irrigation', type: 'IRRIGATION', required: true, recipeTargets: phaseTargets.irrigation || null, activeTargets: active.irrigation?.targets || null, enabled: active.irrigation?.enabled ?? true, strategy: serverCycles.IRRIGATION?.strategy || 'periodic', interval: serverCycles.IRRIGATION?.interval ?? null, last_run: serverCycles.IRRIGATION?.last_run || null, next_run: serverCycles.IRRIGATION?.next_run || null },
      { key: 'lighting', type: 'LIGHTING', required: false, recipeTargets: phaseTargets.lighting || null, activeTargets: active.lighting?.targets || null, enabled: active.lighting?.enabled ?? false, strategy: serverCycles.LIGHTING?.strategy || 'periodic', interval: serverCycles.LIGHTING?.interval ?? null, last_run: serverCycles.LIGHTING?.last_run || null, next_run: serverCycles.LIGHTING?.next_run || null },
      { key: 'climate', type: 'CLIMATE', required: false, recipeTargets: phaseTargets.climate || null, activeTargets: active.climate?.targets || null, enabled: active.climate?.enabled ?? false, strategy: serverCycles.CLIMATE?.strategy || 'periodic', interval: serverCycles.CLIMATE?.interval ?? 300, last_run: serverCycles.CLIMATE?.last_run || null, next_run: serverCycles.CLIMATE?.next_run || null },
    ]

    return base as Array<
      {
        key: string
        type: string
        required: boolean
        recipeTargets: any
        activeTargets: any
        enabled: boolean
      } & Cycle & {
        last_run?: string | null
        next_run?: string | null
        interval?: number | null
      }
    >
  })

  // ─── Realtime / page reload ────────────────────────────────────────────────

  let unsubscribeZoneCommands: (() => void) | null = null
  let stopGrowCycleUpdatedChannel: (() => void) | null = null
  let growCycleUpdatedChannelName: string | null = null
  let propsReloadTimer: ReturnType<typeof setTimeout> | null = null

  const reloadZonePageProps = (only: string[] = defaultZoneReloadProps): void => {
    if (!zoneId.value) return
    if (propsReloadTimer) clearTimeout(propsReloadTimer)
    propsReloadTimer = setTimeout(() => {
      propsReloadTimer = null
      router.reload({ only, preserveUrl: true })
    }, RELOAD_PROPS_DEBOUNCE_MS)
  }

  const cleanupZoneRealtimeSubscriptions = (): void => {
    if (unsubscribeZoneCommands) { unsubscribeZoneCommands(); unsubscribeZoneCommands = null }
    if (stopGrowCycleUpdatedChannel) { stopGrowCycleUpdatedChannel(); stopGrowCycleUpdatedChannel = null }
    if (growCycleUpdatedChannelName && typeof window !== 'undefined' && window.Echo?.leave) {
      window.Echo.leave(growCycleUpdatedChannelName)
      growCycleUpdatedChannelName = null
    }
  }

  const subscribeZoneRealtime = (targetZoneId: number): void => {
    cleanupZoneRealtimeSubscriptions()

    unsubscribeZoneCommands = subscribeToZoneCommands(targetZoneId, (commandEvent) => {
      updateCommandStatus(commandEvent.commandId, commandEvent.status, commandEvent.message)
      const finalStatuses = ['DONE', 'NO_EFFECT', 'ERROR', 'INVALID', 'BUSY', 'TIMEOUT', 'SEND_FAILED']
      if (finalStatuses.includes(commandEvent.status)) {
        reloadZoneAfterCommand(targetZoneId, ['zone', 'cycles', 'active_grow_cycle', 'active_cycle'])
        reloadZonePageProps()
      }
    })

    const echo = typeof window !== 'undefined' ? window.Echo : null
    if (!echo) return

    const channelName = `hydro.zones.${targetZoneId}`
    const channel = echo.private(channelName)
    growCycleUpdatedChannelName = channelName
    channel.listen('.App\\Events\\GrowCycleUpdated', (event: unknown) => {
      logger.info('[Zones/Show] GrowCycleUpdated event received', event)
      reloadZone(targetZoneId, ['zone', 'active_grow_cycle', 'active_cycle'])
      reloadZonePageProps()
    })
    stopGrowCycleUpdatedChannel = () => { channel.stopListening('.App\\Events\\GrowCycleUpdated') }
  }

  // ─── Lifecycle ────────────────────────────────────────────────────────────

  onUnmounted(() => {
    cleanupZoneRealtimeSubscriptions()
    if (propsReloadTimer) { clearTimeout(propsReloadTimer); propsReloadTimer = null }
    flush()
  })

  onMounted(async () => {
    logger.info('[Show.vue] Компонент смонтирован', { zoneId: zoneId.value })

    if (zoneId.value && zone.value?.id) {
      zonesStore.upsert(zone.value, true)
      logger.debug('[Zones/Show] Zone initialized in store from props', { zoneId: zoneId.value })
    }

    if (zoneId.value) subscribeZoneRealtime(zoneId.value)

    const { useStoreEvents } = await import('@/composables/useStoreEvents')
    const { subscribeWithCleanup } = useStoreEvents()
    subscribeWithCleanup('zone:updated', (updatedZone: unknown) => {
      const parsed = parseZoneUpdatePayload(updatedZone)
      if (parsed.zoneId !== zoneId.value) return

      if (parsed.telemetry) {
        if (parsed.telemetry.ph !== undefined) addUpdate(String(zoneId.value), 'ph', parsed.telemetry.ph)
        if (parsed.telemetry.ec !== undefined) addUpdate(String(zoneId.value), 'ec', parsed.telemetry.ec)
        if (parsed.telemetry.temperature !== undefined) addUpdate(String(zoneId.value), 'temperature', parsed.telemetry.temperature)
        if (parsed.telemetry.humidity !== undefined) addUpdate(String(zoneId.value), 'humidity', parsed.telemetry.humidity)
        return
      }

      reloadZone(zoneId.value!, ['zone', 'active_grow_cycle', 'active_cycle'])
      reloadZonePageProps()
    })
  })

  watch(zoneId, (newZoneId, oldZoneId) => {
    if (newZoneId === oldZoneId) return
    if (!newZoneId) { cleanupZoneRealtimeSubscriptions(); return }
    subscribeZoneRealtime(newZoneId)
  })

  return {
    zoneId,
    zone,
    telemetry,
    targets,
    currentPhase,
    activeCycle,
    activeGrowCycle,
    devices,
    events,
    cycles,
    canOperateZone,
    canManageDevices,
    canManageRecipe,
    canManageCycle,
    computedPhaseProgress,
    computedPhaseDaysElapsed,
    computedPhaseDaysTotal,
    cycleStatusLabel,
    cycleStatusVariant,
    phaseTimeLeftLabel,
    cyclesList,
    reloadZonePageProps,
  }
}
