import { onMounted, watch } from 'vue'
import { useCommands } from '@/composables/useCommands'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useZoneAutomationState } from '@/composables/useZoneAutomationState'
import { useZoneAutomationApi } from '@/composables/useZoneAutomationApi'
import { useZoneAutomationScheduler } from '@/composables/useZoneAutomationScheduler'

import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'

export function useZoneAutomationTab(props: ZoneAutomationTabProps) {
  const { showToast } = useToast()
  const { sendZoneCommand } = useCommands(showToast)
  const { get, post } = useApi(showToast)

  const state = useZoneAutomationState(props, { sendZoneCommand, showToast })
  const api = useZoneAutomationApi(props, state, { get, post, showToast, sendZoneCommand })
  const scheduler = useZoneAutomationScheduler(props, { get, post, showToast })

  // ─── Lifecycle ─────────────────────────────────────────────────────────────

  onMounted(() => {
    void api.hydrateAutomationProfileFromCurrentZone({ includeTargets: true })
    void scheduler.fetchAutomationControlMode()
  })
  // ─── Zone change coordination ──────────────────────────────────────────────

  watch(
    () => props.zoneId,
    () => {
      state.pendingTargetsSyncForZoneChange.value = true
      scheduler.resetForZoneChange()
      void api.hydrateAutomationProfileFromCurrentZone({ includeTargets: false })
      void scheduler.fetchAutomationControlMode()
    }
  )

  return {
    // State
    role: state.role,
    canConfigureAutomation: state.canConfigureAutomation,
    canOperateAutomation: state.canOperateAutomation,
    isSystemTypeLocked: state.isSystemTypeLocked,
    climateForm: state.climateForm,
    waterForm: state.waterForm,
    lightingForm: state.lightingForm,
    zoneClimateForm: state.zoneClimateForm,
    quickActions: state.quickActions,
    isApplyingProfile: state.isApplyingProfile,
    isSyncingAutomationLogicProfile: state.isSyncingAutomationLogicProfile,
    lastAppliedAt: state.lastAppliedAt,
    automationLogicMode: state.automationLogicMode,
    lastAutomationLogicSyncAt: state.lastAutomationLogicSyncAt,
    predictionTargets: state.predictionTargets,
    telemetryLabel: state.telemetryLabel,
    waterTopologyLabel: state.waterTopologyLabel,
    resetToRecommended: state.resetToRecommended,
    runManualIrrigation: state.runManualIrrigation,
    runManualClimate: state.runManualClimate,
    runManualLighting: state.runManualLighting,
    runManualPh: state.runManualPh,
    runManualEc: state.runManualEc,
    // Api
    applyAutomationProfile: api.applyAutomationProfile,
    // Scheduler
    automationControlMode: scheduler.automationControlMode,
    allowedManualSteps: scheduler.allowedManualSteps,
    automationControlModeLoading: scheduler.automationControlModeLoading,
    automationControlModeSaving: scheduler.automationControlModeSaving,
    manualStepLoading: scheduler.manualStepLoading,
    setAutomationControlMode: scheduler.setAutomationControlMode,
    syncControlModeFromAutomationState: scheduler.syncControlModeFromAutomationState,
    runManualStep: scheduler.runManualStep,
    formatDateTime: scheduler.formatDateTime,
  }
}
