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
          <!-- eslint-disable-next-line vue/no-mutating-props -->
          <input
            v-model="harvestModal.batchLabel"
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
          <!-- eslint-disable-next-line vue/no-mutating-props -->
          <textarea
            v-model="abortModal.notes"
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
          <!-- eslint-disable-next-line vue/no-mutating-props -->
          <input
            v-model="changeRecipeModal.recipeRevisionId"
            class="input-field mt-1 w-full"
            placeholder="Например: 42"
          />
        </div>
        <div class="flex flex-wrap gap-2">
          <!-- eslint-disable-next-line vue/no-mutating-props -->
          <button
            type="button"
            class="btn btn-outline h-9 px-3 text-xs"
            :class="changeRecipeModal.applyMode === 'now' ? 'border-[color:var(--accent-green)]' : ''"
            @click="changeRecipeModal.applyMode = 'now'"
          >
            Применить сейчас
          </button>
          <!-- eslint-disable-next-line vue/no-mutating-props -->
          <button
            type="button"
            class="btn btn-outline h-9 px-3 text-xs"
            :class="changeRecipeModal.applyMode === 'next_phase' ? 'border-[color:var(--accent-green)]' : ''"
            @click="changeRecipeModal.applyMode = 'next_phase'"
          >
            Со следующей фазы
          </button>
        </div>
      </div>
    </ConfirmModal>
  </div>
</template>

<script setup lang="ts">
import type { CommandType } from '@/types'
import ZoneActionModal from '@/Components/ZoneActionModal.vue'
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
}

interface Props {
  zoneId: number | null
  zoneName: string
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
  showAttachNodesModal: boolean
  showNodeConfigModal: boolean
  harvestModal: HarvestModalState
  abortModal: AbortModalState
  changeRecipeModal: ChangeRecipeModalState
  loading: LoadingState
}

defineProps<Props>()

defineEmits<{
  (e: 'close-action'): void
  (e: 'submit-action', payload: { actionType: CommandType; params: Record<string, unknown> }): void
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
}>()
</script>
