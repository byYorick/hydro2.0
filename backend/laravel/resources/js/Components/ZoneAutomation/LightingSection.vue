<template>
  <section class="rounded-xl border border-[color:var(--border-muted)]">
    <details
      :open="showEnableToggle ? lightingForm.enabled : true"
      class="group"
    >
      <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
        <div>
          <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Освещение
          </h4>
          <p class="mt-1 text-xs text-[color:var(--text-dim)]">
            Опциональная подсистема досветки для этой зоны.
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
            :title="zoneAutomationFieldHelp('lighting.enabled')"
          >
            <input
              v-model="lightingForm.enabled"
              type="checkbox"
              :disabled="!ctx.canConfigure.value"
            />
            Управлять освещением
          </label>
        </div>

        <div
          v-else-if="!lightingForm.enabled"
          class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
        >
          Включите подсистему освещения, чтобы открыть привязку ноды и настройки логики для этого блока.
        </div>

        <div
          v-if="lightingForm.enabled && ctx.showNodeBindings.value && assignments"
          class="grid grid-cols-1 gap-3 xl:grid-cols-2"
        >
          <div class="grid grid-cols-1 gap-2 items-end">
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('device.light')"
            >
              Нода света
              <select
                v-model.number="assignments.light"
                class="input-select mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              >
                <option :value="null">
                  Выберите ноду освещения
                </option>
                <option
                  v-for="node in lightCandidates"
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
                :disabled="!ctx.canBindSelected(assignments?.light)"
                @click="ctx.emitBindDevices(['light'])"
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
          v-if="lightingForm.enabled && showConfigFields"
          class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4"
        >
          <label
            class="text-xs text-[color:var(--text-muted)]"
            :title="zoneAutomationFieldHelp('lighting.luxDay')"
          >
            Освещённость днём (lux)
            <input
              v-model.number="lightingForm.luxDay"
              type="number"
              min="0"
              max="120000"
              class="input-field mt-1 w-full"
              :disabled="!ctx.canConfigure.value"
            />
          </label>
          <label
            class="text-xs text-[color:var(--text-muted)]"
            :title="zoneAutomationFieldHelp('lighting.luxNight')"
          >
            Освещённость ночью (lux)
            <input
              v-model.number="lightingForm.luxNight"
              type="number"
              min="0"
              max="120000"
              class="input-field mt-1 w-full"
              :disabled="!ctx.canConfigure.value"
            />
          </label>
          <label
            class="text-xs text-[color:var(--text-muted)]"
            :title="zoneAutomationFieldHelp('lighting.hoursOn')"
          >
            Часов света
            <input
              v-model.number="lightingForm.hoursOn"
              type="number"
              min="0"
              max="24"
              step="0.5"
              class="input-field mt-1 w-full"
              :disabled="!ctx.canConfigure.value"
            />
          </label>
          <label
            class="text-xs text-[color:var(--text-muted)]"
            :title="zoneAutomationFieldHelp('lighting.scheduleStart')"
          >
            Начало
            <input
              v-model="lightingForm.scheduleStart"
              type="time"
              class="input-field mt-1 w-full"
              :disabled="!ctx.canConfigure.value"
            />
          </label>
          <label
            class="text-xs text-[color:var(--text-muted)]"
            :title="zoneAutomationFieldHelp('lighting.scheduleEnd')"
          >
            Конец
            <input
              v-model="lightingForm.scheduleEnd"
              type="time"
              class="input-field mt-1 w-full"
              :disabled="!ctx.canConfigure.value"
            />
          </label>
        </div>

        <details
          v-if="lightingForm.enabled && showConfigFields"
          class="rounded-xl border border-[color:var(--border-muted)] p-3"
        >
          <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
            Расширенные настройки
          </summary>

          <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('lighting.intervalMinutes')"
            >
              Интервал досветки (мин)
              <input
                v-model.number="lightingForm.intervalMinutes"
                type="number"
                min="1"
                max="1440"
                class="input-field mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              />
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('lighting.manualIntensity')"
            >
              Интенсивность ручного режима (%)
              <input
                v-model.number="lightingForm.manualIntensity"
                type="number"
                min="0"
                max="100"
                class="input-field mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              />
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('lighting.manualDurationHours')"
            >
              Ручной режим (ч)
              <input
                v-model.number="lightingForm.manualDurationHours"
                type="number"
                min="0.5"
                max="24"
                step="0.5"
                class="input-field mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              />
            </label>
          </div>
        </details>

        <div
          v-if="ctx.showSectionSaveButtons.value"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
        >
          <span>
            {{ ctx.isZoneBlockLayout.value
              ? 'Сохраняет блок освещения: switch, привязку ноды и параметры досветки.'
              : (showConfigFields
                ? 'Сохраняет изменения этой секции в общем профиле зоны.'
                : 'Сохраняет binding устройств для секции освещения.') }}
          </span>
          <Button
            size="sm"
            :disabled="!saveAllowed"
            data-test="save-section-lighting"
            @click="ctx.emitSaveSection('lighting')"
          >
            {{ ctx.savingSection.value === 'lighting' ? 'Сохранение...' : (ctx.isZoneBlockLayout.value ? 'Сохранить блок' : 'Сохранить секцию') }}
          </Button>
        </div>
      </div>
    </details>
  </section>
</template>

<script setup lang="ts">
import Button from '@/Components/Button.vue'
import type { AutomationNode as SetupWizardNode } from '@/types/AutomationNode'
import type {
  LightingFormState,
  ZoneAutomationSectionAssignments,
} from '@/composables/zoneAutomationTypes'
import { nodeLabel } from '@/composables/zoneAutomationNodeMatching'
import { useZoneAutomationSectionContext } from '@/composables/useZoneAutomationSectionContext'
import { zoneAutomationFieldHelp } from '@/constants/zoneAutomationFieldHelp'

defineProps<{
  lightCandidates: SetupWizardNode[]
  saveAllowed: boolean
  showEnableToggle?: boolean
  showConfigFields?: boolean
}>()

const lightingForm = defineModel<LightingFormState>('lightingForm', { required: true })
const assignments = defineModel<ZoneAutomationSectionAssignments | null>('assignments', { default: null })

const ctx = useZoneAutomationSectionContext()
</script>
