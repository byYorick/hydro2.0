<template>
  <AppLayout>
    <div
      class="space-y-2"
      data-testid="zone-detail-page"
    >
      <ZoneAutomationBlockBanner
        :block="automationBlock"
        @open-alerts="activeTab = 'alerts'"
      />
      <ZonePageHeader
        :zone-name="zone.name"
        :crop-label="headerCropLabel"
        :phase-label="headerPhaseLabel"
        :phase-days-elapsed="computedPhaseDaysElapsed"
        :phase-days-total="computedPhaseDaysTotal"
        :status-label="headerStatusLabel"
        :status-variant="headerStatusVariant"
        :cycle-status="activeGrowCycle?.status ?? null"
        :can-operate-zone="canOperateZone"
        :can-manage-cycle="canManageCycle"
        :pause-loading="loading.cyclePause"
        :next-phase-loading="loading.nextPhase"
        @water="openActionModal('START_IRRIGATION')"
        @pause="onCyclePause"
        @next-phase="onNextPhase"
        @open-actions="activeTab = 'automation'"
        @diagnose="activeTab = 'devices'"
      />
      <div class="surface-card flex flex-wrap items-center gap-1 rounded-xl border border-[color:var(--border-muted)] p-1.5">
        <Tabs
          v-model="activeTab"
          :tabs="zoneTabs"
          aria-label="Разделы зоны"
          class="min-w-0 flex-1"
        />
        <Dropdown
          v-if="moreZoneTabs.length > 0"
          align="right"
          width="48"
        >
          <template #trigger>
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-lg border border-transparent px-3 py-1.5 text-[13px] font-semibold text-[color:var(--text-dim)] transition-colors hover:bg-[color:var(--bg-elevated)] hover:text-[color:var(--text-primary)]"
              data-testid="zone-more-tabs"
            >
              Ещё
              <svg
                class="h-3 w-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </button>
          </template>
          <template #content>
            <button
              v-for="tab in moreZoneTabs"
              :key="tab.id"
              type="button"
              class="block w-full px-4 py-2 text-start text-sm text-[color:var(--text-primary)] transition-colors hover:bg-[color:var(--bg-elevated)]"
              :data-testid="`zone-more-tab-${tab.id}`"
              @click="activeTab = tab.id"
            >
              {{ tab.label }}
            </button>
          </template>
        </Dropdown>
      </div>
      <ZoneTelemetryTab
        v-if="activeTab === 'telemetry'"
        :zone-id="zoneId"
        :chart-time-range="chartTimeRange"
        :chart-data-ph="chartDataPh"
        :chart-data-ec="chartDataEc"
        :chart-data-soil-moisture="chartDataSoilMoisture"
        :loading="isChartLoading"
        :has-soil-moisture="hasSoilMoisture"
        :devices="devices"
        :telemetry="telemetry"
        :targets="targets"
        @time-range-change="onChartTimeRangeChange"
      />
      <ZoneCycleTab
        v-else-if="activeTab === 'cycle'"
        :zone="zone"
        :variant="variant"
        :active-grow-cycle="activeGrowCycle"
        :can-operate-zone="canOperateZone"
        :targets="targets"
        :telemetry="telemetry"
        :computed-phase-progress="computedPhaseProgress"
        :computed-phase-days-elapsed="computedPhaseDaysElapsed"
        :computed-phase-days-total="computedPhaseDaysTotal"
        :cycle-status-label="cycleStatusLabel"
        :cycle-status-variant="cycleStatusVariant"
        :phase-time-left-label="phaseTimeLeftLabel"
        :can-manage-recipe="canManageRecipe"
        :can-manage-cycle="canManageCycle"
        :control-mode="zone?.control_mode ?? null"
        :phase-duration-complete="phaseDurationComplete"
        :loading="{
          cyclePause: loading.cyclePause,
          cycleResume: loading.cycleResume,
          cycleHarvest: loading.cycleHarvest,
          cycleAbort: loading.cycleAbort,
          nextPhase: loading.nextPhase,
        }"
        @run-cycle="onRunCycle"
        @refresh-cycle="refreshZoneState"
        @change-recipe="onCycleChangeRecipe"
        @pause="onCyclePause"
        @resume="onCycleResume"
        @harvest="onCycleHarvest"
        @abort="onCycleAbort"
        @next-phase="onNextPhase"
      />
      <ZoneAutomationTab
        v-else-if="activeTab === 'automation'"
        :zone-id="zoneId"
        :zone-control-mode="zone?.control_mode ?? null"
        :targets="targets"
        :telemetry="telemetry"
        :active-grow-cycle="activeGrowCycle"
        :current-recipe-phase="activeGrowCycle?.currentPhase ?? null"
        :pump-calibration-save-seq="pumpCalibrationSaveSeq"
        :pump-calibration-run-seq="pumpCalibrationRunSeq"
        :automation-state-refresh-seq="automationStateRefreshSeq"
        :irrigation-action-loading="loading.actionSubmit && (currentActionType === 'START_IRRIGATION' || currentActionType === 'FORCE_IRRIGATION')"
        @open-pump-calibration="openPumpCalibrationModal"
        @refresh-automation-state="onPolicyAlertResolved"
        @start-irrigation="openActionModal('START_IRRIGATION')"
        @force-irrigation="openActionModal('FORCE_IRRIGATION')"
      />
      <ZoneSchedulerTab
        v-else-if="activeTab === 'scheduler'"
        :zone-id="zoneId"
        :zone-control-mode="zone?.control_mode ?? null"
        :targets="targets"
        :telemetry="telemetry"
        :active-grow-cycle="activeGrowCycle"
        :current-recipe-phase="activeGrowCycle?.currentPhase ?? null"
        :pump-calibration-save-seq="pumpCalibrationSaveSeq"
        :pump-calibration-run-seq="pumpCalibrationRunSeq"
      />
      <ZoneEventsTab
        v-else-if="activeTab === 'events'"
        :events="events"
        :zone-id="zoneId"
      />
      <ZoneAlertsTab
        v-else-if="activeTab === 'alerts'"
        :alerts="alerts"
        :zone-id="zoneId"
        @policy-alert-resolved="onPolicyAlertResolved"
      />
      <ZoneDevicesTab
        v-else-if="activeTab === 'devices'"
        :zone="zone"
        :devices="devices"
        :can-manage-devices="canManageDevices"
        :can-operate-zone="canOperateZone"
        @attach="modals.open('attachNodes')"
        @configure="(device) => openNodeConfig(device.id, device)"
        @open-pump-calibration="openPumpCalibrationModal"
      />
    </div>
    <ZoneDetailModals
      :show-action-modal="showActionModal"
      :show-pump-calibration-modal="showPumpCalibrationModal"
      :show-attach-nodes-modal="showAttachNodesModal"
      :show-node-config-modal="showNodeConfigModal"
      :zone-id="zoneId"
      :zone-name="zone.name"
      :devices="devices"
      :current-phase-targets="currentPhase?.targets || null"
      :active-cycle="activeCycle"
      :selected-node-id="selectedNodeId"
      :selected-node="selectedNode"
      :current-action-type="currentActionType"
      :harvest-modal="harvestModal"
      :abort-modal="abortModal"
      :change-recipe-modal="changeRecipeModal"
      :loading="loading"
      :pump-calibration-save-seq="pumpCalibrationSaveSeq"
      :pump-calibration-run-seq="pumpCalibrationRunSeq"
      :pump-calibration-last-run-token="pumpCalibrationLastRunToken"
      :irrigation-correction-summary="irrigationCorrectionSummary"
      @close-action="modals.close('action')"
      @submit-action="onActionSubmit"
      @close-pump-calibration="modals.close('pumpCalibration')"
      @start-pump-calibration="onPumpCalibrationRun"
      @save-pump-calibration="onPumpCalibrationSave"
      @close-attach-nodes="modals.close('attachNodes')"
      @nodes-attached="onNodesAttached"
      @close-node-config="modals.close('nodeConfig')"
      @close-harvest="closeHarvestModal"
      @confirm-harvest="confirmHarvest"
      @close-abort="closeAbortModal"
      @confirm-abort="confirmAbort"
      @close-change-recipe="closeChangeRecipeModal"
      @confirm-change-recipe="confirmChangeRecipe"
      @update-harvest-batch-label="harvestModal.batchLabel = $event"
      @update-harvest-yield-kg="harvestModal.yieldKg = String($event ?? '')"
      @update-abort-notes="abortModal.notes = $event"
      @update-change-recipe-revision-id="changeRecipeModal.recipeRevisionId = $event"
      @update-change-recipe-apply-mode="changeRecipeModal.applyMode = $event"
    />
  </AppLayout>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue';
import { router } from '@inertiajs/vue3';
import AppLayout from "@/Layouts/AppLayout.vue";
import Tabs from "@/Components/Tabs.vue";
import Dropdown from "@/Components/Dropdown.vue";
import ZonePageHeader from "@/Components/ZonePageHeader.vue";
import ZoneAutomationTab from "@/Pages/Zones/Tabs/ZoneAutomationTab.vue";
import ZoneAlertsTab from "@/Pages/Zones/Tabs/ZoneAlertsTab.vue";
import ZoneCycleTab from "@/Pages/Zones/Tabs/ZoneCycleTab.vue";
import ZoneDevicesTab from "@/Pages/Zones/Tabs/ZoneDevicesTab.vue";
import ZoneEventsTab from "@/Pages/Zones/Tabs/ZoneEventsTab.vue";

import ZoneSchedulerTab from "@/Pages/Zones/Tabs/ZoneSchedulerTab.vue";
import ZoneTelemetryTab from "@/Pages/Zones/Tabs/ZoneTelemetryTab.vue";
import ZoneDetailModals from "@/Pages/Zones/ZoneDetailModals.vue";
import ZoneAutomationBlockBanner from "@/Components/ZoneAutomationBlockBanner.vue";
import { useZoneShowPage } from "@/composables/useZoneShowPage";
import { computeAutomationBlock } from "@/utils/automationBlock";
import { normalizeDurationHours } from "@/utils/growCycleProgress";
import { translateStatus } from "@/utils/i18n";

const {
    zoneTabs,
    moreZoneTabs,
    activeTab,
    modals,
    showActionModal,
    showPumpCalibrationModal,
    showAttachNodesModal,
    showNodeConfigModal,
    currentActionType,
    selectedNodeId,
    selectedNode,
    pumpCalibrationSaveSeq,
    pumpCalibrationRunSeq,
    pumpCalibrationLastRunToken,
    loading,
    zoneId,
    zone,
    telemetry,
    targets,
    currentPhase,
    activeCycle,
    activeGrowCycle,
    devices,
    irrigationCorrectionSummary,
    alerts,
    events,
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
    chartTimeRange,
    chartDataPh,
    chartDataEc,
    chartDataSoilMoisture,
    isChartLoading,
    hasSoilMoisture,
    onChartTimeRangeChange,
    onRunCycle,
    refreshZoneState,
    variant,
    openActionModal,
    openPumpCalibrationModal,
    onActionSubmit,
    onPumpCalibrationRun,
    onPumpCalibrationSave,
    openNodeConfig,
    onNodesAttached,
    harvestModal,
    abortModal,
    changeRecipeModal,
    closeHarvestModal,
    closeAbortModal,
    closeChangeRecipeModal,
    onNextPhase,
    onCyclePause,
    onCycleResume,
    onCycleHarvest,
    confirmHarvest,
    onCycleAbort,
    confirmAbort,
    onCycleChangeRecipe,
    confirmChangeRecipe,
} = useZoneShowPage();

/**
 * Признак «AE3 остановлен ACTIVE-алертом» из массива `alerts` страницы зоны.
 * См. `utils/automationBlock.ts` (whitelist синхронизирован с
 * `AlertPolicyService::POLICY_MANAGED_CODES`).
 */
const automationBlock = computed(() => computeAutomationBlock(alerts.value));

const headerCropLabel = computed(() => {
    const zoneCrop = (zone.value as { crop?: string } | null)?.crop;
    return zoneCrop
        || activeGrowCycle.value?.recipe?.name
        || activeGrowCycle.value?.recipeRevision?.recipe?.name
        || null;
});

const headerPhaseLabel = computed(() =>
    activeGrowCycle.value?.currentPhase?.name
        ?? activeGrowCycle.value?.current_phase_name
        ?? null,
);

const headerStatusLabel = computed(() => {
    if (activeGrowCycle.value) {
        return cycleStatusLabel.value;
    }
    return translateStatus(zone.value.status);
});

const headerStatusVariant = computed(() => {
    if (activeGrowCycle.value) {
        return cycleStatusVariant.value;
    }
    return variant.value;
});


const automationStateRefreshSeq = ref(0);

function onPolicyAlertResolved(): void {
  automationStateRefreshSeq.value += 1;
  router.reload({ only: ['alerts'], preserveUrl: true });
}

/**
 * true если phase_started_at + duration_hours/days < now.
 * Используется UI для показа badge "готова" и подсказок в CycleActionsDropdown.
 * См. CONTROL_MODES_SPEC.md §4.5.
 */
const phaseDurationComplete = computed<boolean>(() => {
    const phase = activeGrowCycle.value?.currentPhase;
    if (!phase || !phase.started_at) return false;
    const startedAt = new Date(phase.started_at).getTime();
    if (Number.isNaN(startedAt)) return false;
    // Match backend EffectiveTargetsService: hours OR days, never sum both.
    const hours = normalizeDurationHours(phase.duration_hours ?? null, phase.duration_days ?? null);
    if (hours == null || hours <= 0) return false;
    return Date.now() >= startedAt + hours * 3_600_000;
});
</script>
