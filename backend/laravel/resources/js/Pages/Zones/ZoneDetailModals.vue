<template>
  <div>
    <!-- Модальное окно для действий с параметрами -->
    <ZoneActionModal
      v-if="showActionModal"
      :show="showActionModal"
      :action-type="currentActionType"
      :zone-id="zoneId"
      @close="$emit('close-action')"
      @submit="$emit('submit-action', $event)"
    />

    <PumpCalibrationModal
      v-if="showPumpCalibrationModal"
      :show="showPumpCalibrationModal"
      :zone-id="zoneId"
      :devices="devices"
      :loading-run="loading.pumpCalibrationRun"
      :loading-save="loading.pumpCalibrationSave"
      :save-success-seq="pumpCalibrationSaveSeq"
      @close="$emit('close-pump-calibration')"
      @start="$emit('start-pump-calibration', $event)"
      @save="$emit('save-pump-calibration', $event)"
    />

    <!-- Модальное окно привязки узлов -->
    <AttachNodesModal
      v-if="showAttachNodesModal"
      :show="showAttachNodesModal"
      :zone-id="zoneId"
      @close="$emit('close-attach-nodes')"
      @attached="$emit('nodes-attached', $event)"
    />

    <!-- Модальное окно настройки узла -->
    <NodeConfigModal
      v-if="showNodeConfigModal && selectedNodeId"
      :show="showNodeConfigModal"
      :node-id="selectedNodeId"
      :node="selectedNode"
      @close="$emit('close-node-config')"
    />

    <!-- Модальное окно запуска/корректировки цикла выращивания -->
    <GrowthCycleWizard
      v-if="showGrowthCycleModal && zoneId"
      :show="showGrowthCycleModal"
      :zone-id="zoneId"
      :zone-name="zoneName"
      :current-phase-targets="currentPhaseTargets"
      :active-cycle="activeCycle"
      :initial-data="growthCycleInitialData"
      @close="$emit('close-growth-cycle')"
      @submit="$emit('submit-growth-cycle', $event)"
    />

    <ConfirmModal
      :open="harvestModal.open"
      title="Зафиксировать сбор"
      message=" "
      confirm-text="Подтвердить"
      :loading="loading.cycleHarvest"
      @close="$emit('close-harvest')"
      @confirm="$emit('confirm-harvest')"
    >
      <div class="space-y-3 text-sm text-[color:var(--text-muted)]">
        <div>Зафиксировать сбор урожая и завершить цикл?</div>
        <div>
          <label class="text-xs text-[color:var(--text-dim)]">Метка партии (опционально)</label>
          <input
            v-model="harvestBatchLabel"
            class="input-field mt-1 w-full"
            placeholder="Например: Batch-042"
          />
        </div>
      </div>
    </ConfirmModal>

    <ConfirmModal
      :open="abortModal.open"
      title="Аварийная остановка"
      message=" "
      confirm-text="Остановить"
      confirm-variant="danger"
      :loading="loading.cycleAbort"
      @close="$emit('close-abort')"
      @confirm="$emit('confirm-abort')"
    >
      <div class="space-y-3 text-sm text-[color:var(--text-muted)]">
        <div>Остановить цикл? Это действие нельзя отменить.</div>
        <div>
          <label class="text-xs text-[color:var(--text-dim)]">Причина (опционально)</label>
          <textarea
            v-model="abortNotes"
            class="input-field mt-1 w-full h-20 resize-none"
            placeholder="Короткое описание причины"
          ></textarea>
        </div>
      </div>
    </ConfirmModal>

    <ConfirmModal
      :open="changeRecipeModal.open"
      title="Сменить рецепт"
      message=" "
      confirm-text="Подтвердить"
      :confirm-disabled="!changeRecipeModal.recipeRevisionId"
      :loading="loading.cycleChangeRecipe"
      @close="$emit('close-change-recipe')"
      @confirm="$emit('confirm-change-recipe')"
    >
      <div class="space-y-3 text-sm text-[color:var(--text-muted)]">
        <div>Введите ID ревизии рецепта и выберите режим применения.</div>
        <div>
          <label class="text-xs text-[color:var(--text-dim)]">ID ревизии рецепта</label>
          <input
            v-model="changeRecipeRevisionId"
            class="input-field mt-1 w-full"
            placeholder="Например: 42"
          />
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="btn btn-outline h-9 px-3 text-xs"
            :class="changeRecipeApplyMode === 'now' ? 'border-[color:var(--accent-green)]' : ''"
            @click="changeRecipeApplyMode = 'now'"
          >
            Применить сейчас
          </button>
          <button
            type="button"
            class="btn btn-outline h-9 px-3 text-xs"
            :class="changeRecipeApplyMode === 'next_phase' ? 'border-[color:var(--accent-green)]' : ''"
            @click="changeRecipeApplyMode = 'next_phase'"
          >
            Со следующей фазы
          </button>
        </div>
      </div>
    </ConfirmModal>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CommandType, Device } from '@/types'
import ZoneActionModal from '@/Components/ZoneActionModal.vue'
import PumpCalibrationModal from '@/Components/PumpCalibrationModal.vue'
import GrowthCycleWizard from '@/Components/GrowCycle/GrowthCycleWizard.vue'
import AttachNodesModal from '@/Components/AttachNodesModal.vue'
import NodeConfigModal from '@/Components/NodeConfigModal.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'

interface HarvestModalState {
  open: boolean
  batchLabel: string
}

interface AbortModalState {
  open: boolean
  notes: string
}

interface ChangeRecipeModalState {
  open: boolean
  recipeRevisionId: string
  applyMode: 'now' | 'next_phase'
}

interface LoadingState {
  cycleHarvest: boolean
  cycleAbort: boolean
  cycleChangeRecipe: boolean
  pumpCalibrationRun: boolean
  pumpCalibrationSave: boolean
}

interface Props {
  zoneId: number | null
  zoneName: string
  devices: Device[]
  currentPhaseTargets: any | null
  activeCycle: any | null
  growthCycleInitialData?: {
    recipeId?: number | null
    recipeRevisionId?: number | null
    plantId?: number | null
    startedAt?: string | null
    expectedHarvestAt?: string | null
  } | null
  selectedNodeId: number | null
  selectedNode: any | null
  currentActionType: CommandType
  showActionModal: boolean
  showGrowthCycleModal: boolean
  showPumpCalibrationModal: boolean
  showAttachNodesModal: boolean
  showNodeConfigModal: boolean
  harvestModal: HarvestModalState
  abortModal: AbortModalState
  changeRecipeModal: ChangeRecipeModalState
  loading: LoadingState
  pumpCalibrationSaveSeq: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'close-action'): void
  (e: 'submit-action', payload: { actionType: CommandType; params: Record<string, unknown> }): void
  (e: 'close-pump-calibration'): void
  (e: 'start-pump-calibration', payload: { node_channel_id: number; duration_sec: number; component: 'npk' | 'calcium' | 'magnesium' | 'micro' | 'ph_up' | 'ph_down' }): void
  (e: 'save-pump-calibration', payload: { node_channel_id: number; duration_sec: number; actual_ml: number; component: 'npk' | 'calcium' | 'magnesium' | 'micro' | 'ph_up' | 'ph_down'; skip_run: true; test_volume_l?: number; ec_before_ms?: number; ec_after_ms?: number; temperature_c?: number }): void
  (e: 'close-attach-nodes'): void
  (e: 'nodes-attached', payload: number[]): void
  (e: 'close-node-config'): void
  (e: 'close-growth-cycle'): void
  (e: 'submit-growth-cycle', payload: { zoneId: number; recipeId?: number; startedAt: string; expectedHarvestAt?: string }): void
  (e: 'close-harvest'): void
  (e: 'confirm-harvest'): void
  (e: 'close-abort'): void
  (e: 'confirm-abort'): void
  (e: 'close-change-recipe'): void
  (e: 'confirm-change-recipe'): void
  (e: 'update-harvest-batch-label', value: string): void
  (e: 'update-abort-notes', value: string): void
  (e: 'update-change-recipe-revision-id', value: string): void
  (e: 'update-change-recipe-apply-mode', value: 'now' | 'next_phase'): void
}>()

const harvestBatchLabel = computed({
  get: () => props.harvestModal.batchLabel,
  set: (value: string) => {
    emit('update-harvest-batch-label', value)
  },
})

const abortNotes = computed({
  get: () => props.abortModal.notes,
  set: (value: string) => {
    emit('update-abort-notes', value)
  },
})

const changeRecipeRevisionId = computed({
  get: () => props.changeRecipeModal.recipeRevisionId,
  set: (value: string) => {
    emit('update-change-recipe-revision-id', value)
  },
})

const changeRecipeApplyMode = computed({
  get: () => props.changeRecipeModal.applyMode,
  set: (value: 'now' | 'next_phase') => {
    emit('update-change-recipe-apply-mode', value)
  },
})
</script>
