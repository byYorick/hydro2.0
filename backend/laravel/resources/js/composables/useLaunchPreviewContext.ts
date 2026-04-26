/**
 * Контекст PreviewStep — узлы зоны для ContourRow + AE3 status
 * для readiness-row.
 *
 * Вынесено из Pages/Launch/Index.vue, чтобы держать страницу под
 * file-size guard (≤500 строк).
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { api } from '@/services/api'
import { useServiceHealth } from '@/composables/useServiceHealth'
import type { AutomationNode as SetupWizardNode } from '@/types/AutomationNode'

export interface UseLaunchPreviewContextReturn {
  availableNodes: Ref<SetupWizardNode[]>
  ae3Online: ComputedRef<boolean>
}

export function useLaunchPreviewContext(
  zoneIdRef: ComputedRef<number | null>,
): UseLaunchPreviewContextReturn {
  const availableNodes = ref<SetupWizardNode[]>([])

  async function load(zoneId: number): Promise<void> {
    try {
      const nodes = await api.nodes.list({
        zone_id: zoneId,
        include_unassigned: true,
        per_page: 100,
      })
      const list = Array.isArray(nodes)
        ? nodes
        : Array.isArray((nodes as { data?: unknown[] })?.data)
          ? ((nodes as { data: unknown[] }).data as unknown[])
          : []
      availableNodes.value = list as SetupWizardNode[]
    } catch {
      availableNodes.value = []
    }
  }

  watch(
    zoneIdRef,
    (id) => {
      if (typeof id === 'number') load(id)
    },
    { immediate: true },
  )

  const { pills } = useServiceHealth()
  const ae3Online = computed(
    () => pills.value.find((p) => p.key === 'automation_engine')?.status === 'online',
  )

  return { availableNodes, ae3Online }
}
