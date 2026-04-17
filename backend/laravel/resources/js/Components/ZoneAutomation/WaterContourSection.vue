<template>
  <section class="rounded-xl border border-[color:var(--border-muted)]">
    <details
      open
      class="group"
    >
      <summary class="flex cursor-pointer list-none items-start justify-between gap-3 p-4">
        <div>
          <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Водный контур
          </h4>
          <p class="mt-1 text-xs text-[color:var(--text-dim)]">
            {{ ctx.isZoneBlockLayout.value
              ? 'Обязательные ноды зоны и вся логика water runtime: topology, irrigation и correction.'
              : 'Тип системы, баковая схема и базовая гидравлическая конфигурация.' }}
          </p>
        </div>
        <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
          {{ ctx.isZoneBlockLayout.value ? 'Основной блок' : 'Базовая схема' }}
        </span>
      </summary>

      <div class="space-y-4 border-t border-[color:var(--border-muted)] p-4">
        <div
          v-if="ctx.isZoneBlockLayout.value && ctx.showNodeBindings.value && assignments"
          class="rounded-xl border border-[color:var(--border-muted)] p-3"
        >
          <div class="mb-3 flex items-center justify-between gap-3">
            <div>
              <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
                Привязка обязательных нод
              </h5>
              <p class="mt-1 text-xs text-[color:var(--text-dim)]">
                Полив, pH и EC обязательны. Без них water runtime не считается готовым.
              </p>
            </div>
            <span class="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
              {{ requiredDevicesSelectedCount }}/3
            </span>
          </div>

          <div class="grid grid-cols-1 gap-3 xl:grid-cols-3">
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
        </div>

        <div class="grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs">
          <div class="text-[color:var(--text-muted)]">Тип системы</div>
          <div class="text-[color:var(--text-primary)] font-medium">
            {{ systemTypeLabel }}
            <span v-if="isSystemTypeLocked" class="ml-1 text-[10px] font-normal text-[color:var(--text-dim)]">(из рецепта)</span>
          </div>

          <div class="text-[color:var(--text-muted)]">Количество баков</div>
          <div class="text-[color:var(--text-primary)]">{{ waterForm.tanksCount }}</div>
        </div>

        <div
          v-if="ctx.isZoneBlockLayout.value"
          class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3"
        >
          <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Полив и коррекция
          </h5>

          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
              <div class="text-[10px] font-medium uppercase tracking-wide text-[color:var(--text-dim)]">Режим полива</div>
              <div class="mt-1 text-sm font-medium text-[color:var(--text-primary)]">{{ irrigationModeLabel }}</div>
              <div class="mt-0.5 text-[10px] text-[color:var(--text-dim)]">{{ irrigationModeDescription }}</div>
            </div>

            <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
              <div class="text-[10px] font-medium uppercase tracking-wide text-[color:var(--text-dim)]">Цели из рецепта</div>
              <div class="mt-1 text-sm font-medium text-[color:var(--text-primary)]">pH {{ waterForm.targetPh }} · EC {{ waterForm.targetEc }}</div>
              <div class="mt-0.5 text-[10px] text-[color:var(--text-dim)]">
                pH {{ recipeChemistrySummary.phMin ?? '—' }}..{{ recipeChemistrySummary.phMax ?? '—' }} · EC {{ recipeChemistrySummary.ecMin ?? '—' }}..{{ recipeChemistrySummary.ecMax ?? '—' }}
              </div>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs">
            <div class="text-[color:var(--text-muted)]">Расписание полива</div>
            <div class="text-[color:var(--text-primary)]">каждые {{ waterForm.intervalMinutes }} мин на {{ waterForm.durationSeconds }} сек</div>

            <div class="text-[color:var(--text-muted)]">Порция полива</div>
            <div class="text-[color:var(--text-primary)]">{{ waterForm.irrigationBatchL }} л</div>

            <div class="text-[color:var(--text-muted)]">Объём чистого бака</div>
            <div class="text-[color:var(--text-primary)]">{{ waterForm.cleanTankFillL }} л</div>

            <div class="text-[color:var(--text-muted)]">Объём бака раствора</div>
            <div class="text-[color:var(--text-primary)]">{{ waterForm.nutrientTankTargetL }} л</div>

            <div class="text-[color:var(--text-muted)]">Температура набора</div>
            <div class="text-[color:var(--text-primary)]">{{ waterForm.fillTemperatureC }} °C</div>

            <div class="text-[color:var(--text-muted)]">Окно набора воды</div>
            <div class="text-[color:var(--text-primary)]">{{ waterForm.fillWindowStart }} — {{ waterForm.fillWindowEnd }}</div>

            <div class="text-[color:var(--text-muted)]">Коррекция при поливе</div>
            <div class="text-[color:var(--text-primary)]">{{ waterForm.correctionDuringIrrigation ? 'Да' : 'Нет' }}</div>
          </div>

          <div class="text-[11px] text-[color:var(--text-dim)]">
            Параметры полива и коррекции задаются через профиль автоматики. Цели pH/EC берутся из рецепта.
          </div>
        </div>

        <div
          v-if="ctx.showSectionSaveButtons.value"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
        >
          <span>
            {{ ctx.isZoneBlockLayout.value
              ? 'Сохраняет блок целиком: обязательные ноды и логику водного контура.'
              : 'Сохраняет изменения этой секции в общем профиле зоны.' }}
          </span>
          <Button
            size="sm"
            :disabled="!saveAllowed"
            data-test="save-section-water-contour"
            @click="ctx.emitSaveSection('water_contour')"
          >
            {{ ctx.savingSection.value === 'water_contour' ? 'Сохранение...' : (ctx.isZoneBlockLayout.value ? 'Сохранить блок' : 'Сохранить секцию') }}
          </Button>
        </div>
      </div>
    </details>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import type { Node as SetupWizardNode } from '@/types/SetupWizard'
import type {
  WaterFormState,
  ZoneAutomationSectionAssignments,
} from '@/composables/zoneAutomationTypes'
import { nodeLabel } from '@/composables/zoneAutomationNodeMatching'
import { useZoneAutomationSectionContext } from '@/composables/useZoneAutomationSectionContext'
import { zoneAutomationFieldHelp } from '@/constants/zoneAutomationFieldHelp'
import type { RecipeChemistrySummary } from '@/Components/ZoneAutomation/SolutionCorrectionSection.vue'

defineProps<{
  irrigationCandidates: SetupWizardNode[]
  phCandidates: SetupWizardNode[]
  ecCandidates: SetupWizardNode[]
  soilMoistureCandidates: SetupWizardNode[]
  requiredDevicesSelectedCount: number
  recipeChemistrySummary: RecipeChemistrySummary
  saveAllowed: boolean
  isSystemTypeLocked?: boolean
}>()

const waterForm = defineModel<WaterFormState>('waterForm', { required: true })
const assignments = defineModel<ZoneAutomationSectionAssignments | null>('assignments', { default: null })

const ctx = useZoneAutomationSectionContext()

const systemTypeLabel = computed(() => {
  const labels: Record<string, string> = {
    drip: 'Капельный полив (Drip)',
    substrate_trays: 'DWC / Субстрат',
    nft: 'NFT (Nutrient Film)',
  }
  return labels[waterForm.value.systemType] ?? waterForm.value.systemType
})

const irrigationModeLabel = computed(() =>
  waterForm.value.irrigationDecisionStrategy === 'smart_soil_v1'
    ? 'Умный полив по SOIL_MOISTURE'
    : 'Полив по расписанию',
)

const irrigationModeDescription = computed(() =>
  waterForm.value.irrigationDecisionStrategy === 'smart_soil_v1'
    ? 'Оценивает влажность субстрата перед стартом'
    : 'Запуск по временным окнам цикла',
)
</script>
