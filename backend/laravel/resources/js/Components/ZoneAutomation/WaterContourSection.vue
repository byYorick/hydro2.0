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
            <label class="text-xs text-[color:var(--text-muted)]">
              Режим полива
              <select
                v-model="waterForm.irrigationDecisionStrategy"
                class="input-select mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              >
                <option value="task">По расписанию</option>
                <option value="smart_soil_v1">Умный полив (SOIL_MOISTURE)</option>
              </select>
              <span class="mt-0.5 block text-[10px] text-[color:var(--text-dim)]">{{ irrigationModeDescription }}</span>
            </label>

            <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
              <div class="text-[10px] font-medium uppercase tracking-wide text-[color:var(--text-dim)]">Цели из рецепта</div>
              <div class="mt-1 text-sm font-medium text-[color:var(--text-primary)]">pH {{ waterForm.targetPh }} · EC {{ waterForm.targetEc }}</div>
              <div class="mt-0.5 text-[10px] text-[color:var(--text-dim)]">
                pH {{ recipeChemistrySummary.phMin ?? '—' }}..{{ recipeChemistrySummary.phMax ?? '—' }} · EC {{ recipeChemistrySummary.ecMin ?? '—' }}..{{ recipeChemistrySummary.ecMax ?? '—' }}
              </div>
            </div>
          </div>

          <div
            v-if="waterForm.irrigationDecisionStrategy === 'smart_soil_v1'"
            class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 space-y-3"
          >
            <div class="text-xs font-medium text-[color:var(--text-primary)]">Настройки умного полива</div>
            <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              <label class="text-xs text-[color:var(--text-muted)]">
                Lookback (сек)
                <input
                  v-model.number="waterForm.irrigationDecisionLookbackSeconds"
                  type="number"
                  min="60"
                  max="86400"
                  class="input-field mt-1 w-full"
                  :disabled="!ctx.canConfigure.value"
                />
                <span class="mt-0.5 block text-[10px] text-[color:var(--text-dim)]">Глубина анализа телеметрии</span>
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Мин. сэмплов
                <input
                  v-model.number="waterForm.irrigationDecisionMinSamples"
                  type="number"
                  min="1"
                  max="100"
                  class="input-field mt-1 w-full"
                  :disabled="!ctx.canConfigure.value"
                />
                <span class="mt-0.5 block text-[10px] text-[color:var(--text-dim)]">Минимум точек для решения</span>
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Устаревание (сек)
                <input
                  v-model.number="waterForm.irrigationDecisionStaleAfterSeconds"
                  type="number"
                  min="30"
                  max="86400"
                  class="input-field mt-1 w-full"
                  :disabled="!ctx.canConfigure.value"
                />
                <span class="mt-0.5 block text-[10px] text-[color:var(--text-dim)]">Через сколько данные считаются устаревшими</span>
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Гистерезис (%)
                <input
                  v-model.number="waterForm.irrigationDecisionHysteresisPct"
                  type="number"
                  min="0"
                  max="50"
                  step="0.1"
                  class="input-field mt-1 w-full"
                  :disabled="!ctx.canConfigure.value"
                />
                <span class="mt-0.5 block text-[10px] text-[color:var(--text-dim)]">Зона нечувствительности</span>
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Порог алерта разброса (%)
                <input
                  v-model.number="waterForm.irrigationDecisionSpreadAlertThresholdPct"
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  class="input-field mt-1 w-full"
                  :disabled="!ctx.canConfigure.value"
                />
                <span class="mt-0.5 block text-[10px] text-[color:var(--text-dim)]">Алерт при большом разбросе показаний</span>
              </label>
              <label class="text-xs text-[color:var(--text-muted)]">
                Стоп по solution_min
                <select
                  v-model="waterForm.stopOnSolutionMin"
                  class="input-select mt-1 w-full"
                  :disabled="!ctx.canConfigure.value"
                >
                  <option :value="true">Да</option>
                  <option :value="false">Нет</option>
                </select>
                <span class="mt-0.5 block text-[10px] text-[color:var(--text-dim)]">Остановить полив при низком уровне раствора</span>
              </label>
            </div>
          </div>

          <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label class="text-xs text-[color:var(--text-muted)]">
              Интервал полива (мин)
              <input
                v-model.number="waterForm.intervalMinutes"
                type="number"
                min="5"
                max="1440"
                class="input-field mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Длительность полива (сек)
              <input
                v-model.number="waterForm.durationSeconds"
                type="number"
                min="1"
                max="3600"
                class="input-field mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Порция полива (л)
              <input
                v-model.number="waterForm.irrigationBatchL"
                type="number"
                min="1"
                max="500"
                class="input-field mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Коррекция при поливе
              <select
                v-model="waterForm.correctionDuringIrrigation"
                class="input-select mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              >
                <option :value="true">Да</option>
                <option :value="false">Нет</option>
              </select>
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Объём чистого бака (л)
              <input
                v-model.number="waterForm.cleanTankFillL"
                type="number"
                min="10"
                max="5000"
                class="input-field mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Объём бака раствора (л)
              <input
                v-model.number="waterForm.nutrientTankTargetL"
                type="number"
                min="10"
                max="5000"
                class="input-field mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Температура набора (°C)
              <input
                v-model.number="waterForm.fillTemperatureC"
                type="number"
                min="5"
                max="35"
                step="0.1"
                class="input-field mt-1 w-full"
                :disabled="!ctx.canConfigure.value"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Окно набора воды
              <div class="mt-1 flex gap-1">
                <input
                  v-model="waterForm.fillWindowStart"
                  type="time"
                  class="input-field w-full"
                  :disabled="!ctx.canConfigure.value"
                />
                <span class="self-center text-[color:var(--text-dim)]">—</span>
                <input
                  v-model="waterForm.fillWindowEnd"
                  type="time"
                  class="input-field w-full"
                  :disabled="!ctx.canConfigure.value"
                />
              </div>
            </label>
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
