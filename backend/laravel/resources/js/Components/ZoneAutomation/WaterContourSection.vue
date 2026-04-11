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

        <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <label
            class="text-xs text-[color:var(--text-muted)]"
            :title="zoneAutomationFieldHelp('water.systemType')"
          >
            Тип системы
            <select
              v-model="waterForm.systemType"
              class="input-select mt-1 w-full"
              :disabled="!ctx.canConfigure.value || isSystemTypeLocked"
            >
              <option value="drip">drip</option>
              <option value="substrate_trays">substrate_trays</option>
              <option
                disabled
                value="nft"
              >nft (скоро)</option>
            </select>
          </label>

          <label
            class="text-xs text-[color:var(--text-muted)]"
            :title="zoneAutomationFieldHelp('water.tanksCount')"
          >
            Количество баков
            <input
              v-model.number="waterForm.tanksCount"
              type="number"
              min="2"
              max="3"
              class="input-field mt-1 w-full"
              :disabled="!ctx.canConfigure.value || isSystemTypeLocked || waterForm.systemType === 'drip'"
            />
          </label>

          <label
            class="text-xs text-[color:var(--text-muted)]"
            :title="zoneAutomationFieldHelp('water.enableDrainControl')"
          >
            Контроль дренажа
            <select
              v-model="waterForm.enableDrainControl"
              class="input-select mt-1 w-full"
              :disabled="!ctx.canConfigure.value || waterForm.tanksCount !== 3"
            >
              <option :value="true">Включен</option>
              <option :value="false">Выключен</option>
            </select>
          </label>

          <label
            class="text-xs text-[color:var(--text-muted)]"
            :title="zoneAutomationFieldHelp('water.drainTargetPercent')"
          >
            Цель по дренажу (%)
            <input
              v-model.number="waterForm.drainTargetPercent"
              type="number"
              min="0"
              max="100"
              class="input-field mt-1 w-full"
              :disabled="!ctx.canConfigure.value || waterForm.tanksCount !== 3 || !waterForm.enableDrainControl"
            />
          </label>
        </div>

        <div
          v-if="waterForm.systemType === 'nft'"
          class="rounded-xl border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-3 text-xs text-[color:var(--badge-warning-text)]"
        >
          NFT пока не включен в основной сценарий мастера. Для агронома доступны drip и substrate_trays.
        </div>

        <details class="rounded-xl border border-[color:var(--border-muted)] p-3">
          <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
            Расширенные настройки
          </summary>

          <div class="mt-3 space-y-4">
            <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="zoneAutomationFieldHelp('water.valveSwitching')"
              >
                Переключение клапанов
                <select
                  v-model="waterForm.valveSwitching"
                  class="input-select mt-1 w-full"
                  :disabled="!ctx.canConfigure.value"
                >
                  <option :value="true">Включено</option>
                  <option :value="false">Выключено</option>
                </select>
              </label>
            </div>

            <div
              v-if="waterForm.tanksCount === 2"
              class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-dim)]"
            >
              Low-level relay plans 2-баковой топологии больше не редактируются на фронте. Командные шаги собираются backend/compiler из authority templates или уже сохранённого custom plan зоны.
            </div>
          </div>
        </details>

        <div
          v-if="ctx.isZoneBlockLayout.value"
          class="rounded-xl border border-[color:var(--border-muted)] p-3"
        >
          <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Полив
          </h5>
          <p class="mt-1 text-xs text-[color:var(--text-dim)]">
            Основной цикл полива, окна приготовления и рабочие объёмы контура.
          </p>

          <IrrigationModeSelector
            v-model:water-form="waterForm"
            :recipe-irrigation-summary="recipeIrrigationSummary"
            class="mt-3"
          />

          <IrrigationBasicFieldsGrid
            v-model:water-form="waterForm"
            class="mt-3"
          />

          <SmartIrrigationControlsGroup
            v-model:water-form="waterForm"
            v-model:assignments="assignments"
            class="mt-3"
            :recipe-soil-moisture-targets="recipeSoilMoistureTargets"
            :soil-moisture-candidates="soilMoistureCandidates"
            :collapsible="true"
            :show-soil-moisture-binding="true"
            :show-stop-on-solution-min="true"
          />
        </div>

        <div
          v-if="ctx.isZoneBlockLayout.value"
          class="rounded-xl border border-[color:var(--border-muted)] p-3"
        >
          <h5 class="text-sm font-semibold text-[color:var(--text-primary)]">
            Раствор и коррекция
          </h5>
          <p class="mt-1 text-xs text-[color:var(--text-dim)]">
            Целевые параметры раствора и ограничения correction runtime.
          </p>

          <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('water.targetPh')"
            >
              Целевой pH (из рецепта)
              <input
                v-model.number="waterForm.targetPh"
                type="number"
                min="4"
                max="9"
                step="0.1"
                class="input-field mt-1 w-full"
                disabled
              />
            </label>
            <label
              class="text-xs text-[color:var(--text-muted)]"
              :title="zoneAutomationFieldHelp('water.targetEc')"
            >
              Целевой EC (из рецепта)
              <input
                v-model.number="waterForm.targetEc"
                type="number"
                min="0.1"
                max="10"
                step="0.1"
                class="input-field mt-1 w-full"
                disabled
              />
            </label>
            <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] p-3 text-xs text-[color:var(--text-muted)] md:col-span-2">
              <div class="font-semibold text-[color:var(--text-primary)]">
                Recipe-derived chemistry summary
              </div>
              <div class="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                <div>pH window: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeChemistrySummary.phMin ?? '—' }}..{{ recipeChemistrySummary.phMax ?? '—' }}</span></div>
                <div>EC window: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeChemistrySummary.ecMin ?? '—' }}..{{ recipeChemistrySummary.ecMax ?? '—' }}</span></div>
                <div class="md:col-span-2">
                  EC strategy: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeChemistrySummary.nutrientMode ?? 'ratio_ec_pid' }}</span>
                </div>
              </div>
            </div>
          </div>

          <details class="mt-3 rounded-xl border border-[color:var(--border-muted)] p-3">
            <summary class="cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]">
              Расширенные настройки коррекции
            </summary>

            <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="zoneAutomationFieldHelp('water.correctionMaxEcCorrectionAttempts')"
              >
                Лимит попыток EC-коррекции
                <input
                  v-model.number="waterForm.correctionMaxEcCorrectionAttempts"
                  type="number"
                  min="1"
                  max="50"
                  class="input-field mt-1 w-full"
                  :disabled="!ctx.canConfigure.value"
                />
              </label>
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="zoneAutomationFieldHelp('water.correctionMaxPhCorrectionAttempts')"
              >
                Лимит попыток pH-коррекции
                <input
                  v-model.number="waterForm.correctionMaxPhCorrectionAttempts"
                  type="number"
                  min="1"
                  max="50"
                  class="input-field mt-1 w-full"
                  :disabled="!ctx.canConfigure.value"
                />
              </label>
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="zoneAutomationFieldHelp('water.correctionPrepareRecirculationMaxAttempts')"
              >
                Лимит окон рециркуляции
                <input
                  v-model.number="waterForm.correctionPrepareRecirculationMaxAttempts"
                  type="number"
                  min="1"
                  max="50"
                  class="input-field mt-1 w-full"
                  :disabled="!ctx.canConfigure.value"
                />
              </label>
              <label
                class="text-xs text-[color:var(--text-muted)]"
                :title="zoneAutomationFieldHelp('water.correctionPrepareRecirculationMaxCorrectionAttempts')"
              >
                Лимит correction-шагов
                <input
                  v-model.number="waterForm.correctionPrepareRecirculationMaxCorrectionAttempts"
                  type="number"
                  min="1"
                  max="500"
                  class="input-field mt-1 w-full"
                  :disabled="!ctx.canConfigure.value"
                />
              </label>
            </div>
          </details>
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
import Button from '@/Components/Button.vue'
import IrrigationBasicFieldsGrid from '@/Components/ZoneAutomation/IrrigationBasicFieldsGrid.vue'
import IrrigationModeSelector from '@/Components/ZoneAutomation/IrrigationModeSelector.vue'
import SmartIrrigationControlsGroup from '@/Components/ZoneAutomation/SmartIrrigationControlsGroup.vue'
import type { Node as SetupWizardNode } from '@/types/SetupWizard'
import type {
  WaterFormState,
  ZoneAutomationSectionAssignments,
} from '@/composables/zoneAutomationTypes'
import { nodeLabel } from '@/composables/zoneAutomationNodeMatching'
import { useZoneAutomationSectionContext } from '@/composables/useZoneAutomationSectionContext'
import { zoneAutomationFieldHelp } from '@/constants/zoneAutomationFieldHelp'
import type { RecipeChemistrySummary } from '@/Components/ZoneAutomation/SolutionCorrectionSection.vue'
import type {
  RecipeIrrigationSummary,
  RecipeSoilMoistureTargets,
} from '@/Components/ZoneAutomation/IrrigationSection.vue'

defineProps<{
  irrigationCandidates: SetupWizardNode[]
  phCandidates: SetupWizardNode[]
  ecCandidates: SetupWizardNode[]
  soilMoistureCandidates: SetupWizardNode[]
  requiredDevicesSelectedCount: number
  recipeIrrigationSummary: RecipeIrrigationSummary
  recipeSoilMoistureTargets: RecipeSoilMoistureTargets
  recipeChemistrySummary: RecipeChemistrySummary
  saveAllowed: boolean
  isSystemTypeLocked?: boolean
}>()

const waterForm = defineModel<WaterFormState>('waterForm', { required: true })
const assignments = defineModel<ZoneAutomationSectionAssignments | null>('assignments', { default: null })

const ctx = useZoneAutomationSectionContext()
</script>
