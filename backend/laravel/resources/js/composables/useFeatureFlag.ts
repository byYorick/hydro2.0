import { computed, type ComputedRef } from 'vue'
import { usePage } from '@inertiajs/vue3'

export interface FeatureFlags {
  scheduler_cockpit_ui: boolean
}

const DEFAULTS: FeatureFlags = {
  scheduler_cockpit_ui: false,
}

interface PageWithFeatures {
  props?: {
    features?: Partial<FeatureFlags>
    [key: string]: unknown
  }
}

function safeUsePage(): PageWithFeatures | null {
  try {
    return usePage() as unknown as PageWithFeatures
  } catch {
    // Вне контекста Inertia (например, в Vitest без плагина) считаем флаги
    // выключенными — это безопасный дефолт для feature-flag.
    return null
  }
}

export function useFeatureFlags(): ComputedRef<FeatureFlags> {
  const page = safeUsePage()
  return computed<FeatureFlags>(() => {
    const raw = (page?.props?.features ?? {}) as Partial<FeatureFlags>
    return { ...DEFAULTS, ...raw }
  })
}

export function useFeatureFlag<K extends keyof FeatureFlags>(key: K): ComputedRef<FeatureFlags[K]> {
  const flags = useFeatureFlags()
  return computed(() => flags.value[key])
}
