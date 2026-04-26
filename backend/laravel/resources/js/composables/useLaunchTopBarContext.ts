/**
 * Контекст LaunchTopBar — userEmail, breadcrumb-zone-name + Ziggy hrefs
 * для Dashboard / Zones / выбранной зоны.
 *
 * Вынесено из Pages/Launch/Index.vue для соблюдения file-size guard.
 */
import { computed, type ComputedRef } from 'vue'

declare function route(name: string, params?: Record<string, unknown>): string

export interface UseLaunchTopBarContextInput {
  auth?: { user?: { email?: string | null; name?: string | null } | null } | null
  zoneId: ComputedRef<number | null>
  zoneNameById: ComputedRef<Record<number, string>>
}

export interface UseLaunchTopBarContextReturn {
  userEmail: ComputedRef<string | null>
  breadcrumbZoneName: ComputedRef<string | null>
  dashboardHref: ComputedRef<string>
  zonesHref: ComputedRef<string>
}

export function useLaunchTopBarContext(
  input: UseLaunchTopBarContextInput,
): UseLaunchTopBarContextReturn {
  const userEmail = computed(
    () => input.auth?.user?.email ?? input.auth?.user?.name ?? null,
  )

  const breadcrumbZoneName = computed(() => {
    const id = input.zoneId.value
    if (!id) return null
    return input.zoneNameById.value[id] ?? `id ${id}`
  })

  function safeRoute(name: string, fallback: string): string {
    try {
      return route(name)
    } catch {
      return fallback
    }
  }

  const dashboardHref = computed(() => safeRoute('dashboard', '/'))
  const zonesHref = computed(() => safeRoute('zones.index', '/zones'))

  return { userEmail, breadcrumbZoneName, dashboardHref, zonesHref }
}
