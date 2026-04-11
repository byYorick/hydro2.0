<template>
  <section class="rounded-xl border border-[color:var(--border-muted)]">
    <details
      :open="showEnableToggle ? zoneClimateForm.enabled : true"
      class="group"
    >
      <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
        <div>
          <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Климат зоны
          </h4>
          <p class="mt-1 text-xs text-[color:var(--text-dim)]">
            Отдельная зональная подсистема для CO2 и прикорневой вентиляции.
          </p>
        </div>
        <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
          Опционально
        </span>
      </summary>

      <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">
        <div
          v-if="showEnableToggle"
          class="flex items-center justify-end"
        >
          <label
            class="inline-flex items-center gap-2 text-xs text-[color:var(--text-muted)]"
            :title="zoneAutomationFieldHelp('zoneClimate.enabled')"
          >
            <input
              v-model="zoneClimateForm.enabled"
              type="checkbox"
              :disabled="!ctx.canConfigure.value"
            />
            Управлять климатом зоны
          </label>
        </div>

        <div
          v-else-if="!zoneClimateForm.enabled"
          class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
        >
          Включите климат зоны, чтобы открыть привязку CO2/root-vent нод и настройки этого блока.
        </div>

        <div
          v-if="zoneClimateForm.enabled && ctx.showNodeBindings.value && assignments"
          class="grid grid-cols-1 gap-3 xl:grid-cols-3"
        >
          <div class="grid grid-cols-1 gap-2 items-end">
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('device.co2_sensor')"
            >
              Датчик CO2
              <select
                v-model.number="assignments.co2_sensor"
                class="input-select mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
                data-test="co2-sensor-select"
              >
                <option :value="null">
                  Выберите датчик CO2
                </option>
                <option
                  v-for="node in co2SensorCandidates"
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
                :disabled="!ctx.canBindSelected(assignments?.co2_sensor)"
                @click="ctx.emitBindDevices(['co2_sensor'])"
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
              :title="zoneAutomationFieldHelp('device.co2_actuator')"
            >
              CO2 actuator
              <select
                v-model.number="assignments.co2_actuator"
                class="input-select mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              >
                <option :value="null">
                  Выберите CO2 actuator
                </option>
                <option
                  v-for="node in co2ActuatorCandidates"
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
                :disabled="!ctx.canBindSelected(assignments?.co2_actuator)"
                @click="ctx.emitBindDevices(['co2_actuator'])"
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
              :title="zoneAutomationFieldHelp('device.root_vent_actuator')"
            >
              Прикорневая вентиляция
              <select
                v-model.number="assignments.root_vent_actuator"
                class="input-select mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              >
                <option :value="null">
                  Выберите ноду прикорневой вентиляции
                </option>
                <option
                  v-for="node in rootVentCandidates"
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
                :disabled="!ctx.canBindSelected(assignments?.root_vent_actuator)"
                @click="ctx.emitBindDevices(['root_vent_actuator'])"
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

        <div
          v-if="ctx.showSectionSaveButtons.value"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
        >
          <span>
            {{ ctx.isZoneBlockLayout.value
              ? 'Сохраняет блок климата зоны: switch, привязку нод и параметры подсистемы.'
              : (showConfigFields
                ? 'Сохраняет изменения этой секции в общем профиле зоны.'
                : 'Сохраняет binding устройств для секции климата зоны.') }}
          </span>
          <Button
            size="sm"
            :disabled="!saveAllowed"
            data-test="save-section-zone-climate"
            @click="ctx.emitSaveSection('zone_climate')"
          >
            {{ ctx.savingSection.value === 'zone_climate' ? 'Сохранение...' : (ctx.isZoneBlockLayout.value ? 'Сохранить блок' : 'Сохранить секцию') }}
          </Button>
        </div>
      </div>
    </details>
  </section>
</template>

<script setup lang="ts">
import Button from '@/Components/Button.vue'
import type { Node as SetupWizardNode } from '@/types/SetupWizard'
import type {
  ZoneAutomationSectionAssignments,
  ZoneClimateFormState,
} from '@/composables/zoneAutomationTypes'
import { nodeLabel } from '@/composables/zoneAutomationNodeMatching'
import { useZoneAutomationSectionContext } from '@/composables/useZoneAutomationSectionContext'
import { zoneAutomationFieldHelp } from '@/constants/zoneAutomationFieldHelp'

defineProps<{
  co2SensorCandidates: SetupWizardNode[]
  co2ActuatorCandidates: SetupWizardNode[]
  rootVentCandidates: SetupWizardNode[]
  saveAllowed: boolean
  showEnableToggle?: boolean
  showConfigFields?: boolean
}>()

const zoneClimateForm = defineModel<ZoneClimateFormState>('zoneClimateForm', { required: true })
const assignments = defineModel<ZoneAutomationSectionAssignments | null>('assignments', { default: null })

const ctx = useZoneAutomationSectionContext()
</script>
