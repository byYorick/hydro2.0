<template>
  <section class="rounded-xl border border-[color:var(--border-muted)]">
    <details
      open
      class="group"
    >
      <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
        <div>
          <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Обязательные устройства
          </h4>
          <p class="mt-1 text-xs text-[color:var(--text-dim)]">
            Базовые ноды, без которых зона не сможет работать: полив, pH и EC.
          </p>
        </div>
        <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
          Обязательно
        </span>
      </summary>

      <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">
        <div
          v-if="ctx.showNodeBindings.value && assignments"
          class="grid grid-cols-1 gap-3 xl:grid-cols-3"
        >
          <div class="grid grid-cols-1 gap-2 items-end">
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('device.irrigation')"
            >
              Узел полива
              <select
                v-model.number="assignments.irrigation"
                class="input-select mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              >
                <option :value="null">
                  Выберите узел полива
                </option>
                <option
                  v-for="node in irrigationCandidates"
                  :key="node.id"
                  :value="node.id"
                >
                  {{ nodeLabel(node) }}
                </option>
              </select>
            </label>
            <div
              v-if="ctx.showBindButtons.value || ctx.showRefreshButtons.value"
              class="flex items-center gap-2"
            >
              <Button
                v-if="ctx.showBindButtons.value"
                size="sm"
                variant="secondary"
                :disabled="!ctx.canBindSelected(assignments?.irrigation)"
                @click="ctx.emitBindDevices(['irrigation'])"
              >
                {{ ctx.bindingInProgress.value ? 'Привязка...' : 'Привязать' }}
              </Button>
              <Button
                v-if="ctx.showRefreshButtons.value"
                size="sm"
                variant="ghost"
                :disabled="!ctx.canRefreshNodes.value"
                @click="ctx.emitRefreshNodes()"
              >
                {{ ctx.refreshingNodes.value ? 'Обновление...' : 'Обновить' }}
              </Button>
            </div>
          </div>

          <div class="grid grid-cols-1 gap-2 items-end">
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('device.ph_correction')"
            >
              Узел коррекции pH
              <select
                v-model.number="assignments.ph_correction"
                class="input-select mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              >
                <option :value="null">
                  Выберите узел pH
                </option>
                <option
                  v-for="node in phCandidates"
                  :key="node.id"
                  :value="node.id"
                >
                  {{ nodeLabel(node) }}
                </option>
              </select>
            </label>
            <div
              v-if="ctx.showBindButtons.value || ctx.showRefreshButtons.value"
              class="flex items-center gap-2"
            >
              <Button
                v-if="ctx.showBindButtons.value"
                size="sm"
                variant="secondary"
                :disabled="!ctx.canBindSelected(assignments?.ph_correction)"
                @click="ctx.emitBindDevices(['ph_correction'])"
              >
                {{ ctx.bindingInProgress.value ? 'Привязка...' : 'Привязать' }}
              </Button>
              <Button
                v-if="ctx.showRefreshButtons.value"
                size="sm"
                variant="ghost"
                :disabled="!ctx.canRefreshNodes.value"
                @click="ctx.emitRefreshNodes()"
              >
                {{ ctx.refreshingNodes.value ? 'Обновление...' : 'Обновить' }}
              </Button>
            </div>
          </div>

          <div class="grid grid-cols-1 gap-2 items-end">
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('device.ec_correction')"
            >
              Узел коррекции EC
              <select
                v-model.number="assignments.ec_correction"
                class="input-select mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              >
                <option :value="null">
                  Выберите узел EC
                </option>
                <option
                  v-for="node in ecCandidates"
                  :key="node.id"
                  :value="node.id"
                >
                  {{ nodeLabel(node) }}
                </option>
              </select>
            </label>
            <div
              v-if="ctx.showBindButtons.value || ctx.showRefreshButtons.value"
              class="flex items-center gap-2"
            >
              <Button
                v-if="ctx.showBindButtons.value"
                size="sm"
                variant="secondary"
                :disabled="!ctx.canBindSelected(assignments?.ec_correction)"
                @click="ctx.emitBindDevices(['ec_correction'])"
              >
                {{ ctx.bindingInProgress.value ? 'Привязка...' : 'Привязать' }}
              </Button>
              <Button
                v-if="ctx.showRefreshButtons.value"
                size="sm"
                variant="ghost"
                :disabled="!ctx.canRefreshNodes.value"
                @click="ctx.emitRefreshNodes()"
              >
                {{ ctx.refreshingNodes.value ? 'Обновление...' : 'Обновить' }}
              </Button>
            </div>
          </div>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]">
          <span>
            {{ selectedCount }}/3 обязательных устройства выбрано.
          </span>
          <div
            v-if="ctx.showSectionSaveButtons.value"
            class="flex items-center gap-3"
          >
            <span>Сохраняет устройства и привязки этой секции.</span>
            <Button
              size="sm"
              :disabled="!saveAllowed"
              data-test="save-section-required-devices"
              @click="ctx.emitSaveSection('required_devices')"
            >
              {{ ctx.savingSection.value === 'required_devices' ? 'Сохранение...' : 'Сохранить секцию' }}
            </Button>
          </div>
        </div>
      </div>
    </details>
  </section>
</template>

<script setup lang="ts">
import Button from '@/Components/Button.vue'
import type { AutomationNode as SetupWizardNode } from '@/types/AutomationNode'
import type { ZoneAutomationSectionAssignments } from '@/composables/zoneAutomationTypes'
import { nodeLabel } from '@/composables/zoneAutomationNodeMatching'
import { useZoneAutomationSectionContext } from '@/composables/useZoneAutomationSectionContext'
import { zoneAutomationFieldHelp } from '@/constants/zoneAutomationFieldHelp'

defineProps<{
  irrigationCandidates: SetupWizardNode[]
  phCandidates: SetupWizardNode[]
  ecCandidates: SetupWizardNode[]
  selectedCount: number
  saveAllowed: boolean
}>()

const assignments = defineModel<ZoneAutomationSectionAssignments | null>('assignments', { default: null })

const ctx = useZoneAutomationSectionContext()
</script>
