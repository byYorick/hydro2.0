import { inject, provide, type InjectionKey, type ComputedRef } from 'vue'
import type {
  ZoneAutomationBindRole,
  ZoneAutomationSectionSaveKey,
} from '@/composables/zoneAutomationTypes'

/**
 * Общий контекст для секций zone automation (provide/inject).
 * Секции получают из него UI-флаги, эмиттеры и helper-функции,
 * вместо того чтобы принимать ~15 пропсов по отдельности.
 */
export interface ZoneAutomationSectionContext {
  canConfigure: ComputedRef<boolean>
  isZoneBlockLayout: ComputedRef<boolean>

  // Node bindings UI
  showNodeBindings: ComputedRef<boolean>
  showBindButtons: ComputedRef<boolean>
  showRefreshButtons: ComputedRef<boolean>
  bindingInProgress: ComputedRef<boolean>
  refreshingNodes: ComputedRef<boolean>
  canRefreshNodes: ComputedRef<boolean>
  canBindSelected: (value: number | null | undefined) => boolean

  // Section save buttons
  showSectionSaveButtons: ComputedRef<boolean>
  savingSection: ComputedRef<ZoneAutomationSectionSaveKey | null>

  // Emitters forwarded to the shell
  emitBindDevices: (roles: ZoneAutomationBindRole[]) => void
  emitRefreshNodes: () => void
  emitSaveSection: (section: ZoneAutomationSectionSaveKey) => void
}

const ZONE_AUTOMATION_SECTION_CONTEXT_KEY: InjectionKey<ZoneAutomationSectionContext> =
  Symbol('ZoneAutomationSectionContext')

export function provideZoneAutomationSectionContext(ctx: ZoneAutomationSectionContext): void {
  provide(ZONE_AUTOMATION_SECTION_CONTEXT_KEY, ctx)
}

export function useZoneAutomationSectionContext(): ZoneAutomationSectionContext {
  const ctx = inject(ZONE_AUTOMATION_SECTION_CONTEXT_KEY)
  if (!ctx) {
    throw new Error(
      'useZoneAutomationSectionContext must be called inside <ZoneAutomationProfileSections>',
    )
  }
  return ctx
}
