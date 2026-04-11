<template>
  <component
    :is="collapsible ? 'details' : 'div'"
    class="rounded-xl border border-[color:var(--border-muted)] p-3"
  >
    <component
      :is="collapsible ? 'summary' : 'h5'"
      :class="headerClass"
    >
      Умный полив (decision, recovery, safety)
    </component>

    <p class="mt-1 text-xs text-[color:var(--text-dim)]">
      {{ description }}
    </p>

    <div class="mt-3 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] p-3 text-xs text-[color:var(--text-muted)]">
      <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <label
          class="text-xs text-[color:var(--text-muted)]"
          :title="zoneAutomationFieldHelp('water.correctionDuringIrrigation')"
        >
          Коррекция во время полива
          <select
            v-model="waterForm.correctionDuringIrrigation"
            class="input-select mt-1 w-full"
            :disabled="!ctx.canConfigure.value"
          >
            <option :value="true">Включена</option>
            <option :value="false">Выключена</option>
          </select>
        </label>
        <label
          class="text-xs text-[color:var(--text-muted)]"
          :title="zoneAutomationFieldHelp('water.correctionStabilizationSec')"
        >
          Стабилизация после дозирования (сек)
          <input
            v-model.number="waterForm.correctionStabilizationSec"
            type="number"
            min="0"
            max="3600"
            class="input-field mt-1 w-full"
            :disabled="!ctx.canConfigure.value"
          />
        </label>
        <div class="md:col-span-2 xl:col-span-2">
          <div class="font-semibold text-[color:var(--text-primary)]">
            Inline correction состав
          </div>
          <div class="mt-1">
            Во время полива automation использует `Ca/Mg/Micro + pH`. `NPK` исключён и не настраивается на фронте.
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="waterForm.irrigationDecisionStrategy === 'smart_soil_v1' && waterForm.systemType === 'drip'"
      class="mt-3 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] p-3 text-xs"
      data-test="smart-irrigation-recipe-targets"
    >
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div class="font-semibold text-[color:var(--text-primary)]">
          Цели из текущей фазы (soil moisture, %)
        </div>
        <div class="text-[color:var(--text-dim)]">
          read-only
        </div>
      </div>
      <div class="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-[color:var(--text-muted)]">
        <div>
          День: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeSoilMoistureTargets.day ?? '—' }}</span>
        </div>
        <div>
          Ночь: <span class="font-mono text-[color:var(--text-primary)]">{{ recipeSoilMoistureTargets.night ?? '—' }}</span>
        </div>
      </div>
      <p class="mt-2 text-[color:var(--text-dim)]">
        Если значения пустые — открой рецепт и заполни «Умный полив (soil moisture target)» в фазе.
      </p>
    </div>

    <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
      <label
        class="text-xs text-[color:var(--text-muted)]"
        :title="zoneAutomationFieldHelp('water.irrigationDecisionStrategy')"
      >
        Decision strategy
        <select
          v-model="waterForm.irrigationDecisionStrategy"
          data-test="irrigation-decision-strategy"
          class="input-select mt-1 w-full"
          :disabled="!ctx.canConfigure.value"
        >
          <option value="task">По времени</option>
          <option value="smart_soil_v1">Умный полив</option>
        </select>
      </label>

      <label
        v-if="showSoilMoistureBinding && ctx.showNodeBindings.value && assignments"
        class="text-xs text-[color:var(--text-muted)]"
        :title="zoneAutomationFieldHelp('device.soil_moisture_sensor')"
      >
        Soil moisture sensor
        <select
          v-model.number="assignments.soil_moisture_sensor"
          class="input-select mt-1 w-full"
          :disabled="!ctx.canConfigure.value"
          data-test="soil-moisture-sensor-select"
        >
          <option :value="null">
            Выберите датчик влажности
          </option>
          <option
            v-for="node in soilMoistureCandidates"
            :key="node.id"
            :value="node.id"
          >
            {{ nodeLabel(node) }}
          </option>
        </select>
        <div
          v-if="ctx.showBindButtons.value || ctx.showRefreshButtons.value"
          class="mt-2 flex items-center gap-2"
        >
          <Button
            v-if="ctx.showBindButtons.value"
            size="sm"
            variant="secondary"
            :disabled="!ctx.canBindSelected(assignments?.soil_moisture_sensor)"
            @click="ctx.emitBindDevices(['soil_moisture_sensor'])"
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
      </label>

      <label
        class="text-xs text-[color:var(--text-muted)]"
        :title="zoneAutomationFieldHelp('water.irrigationDecisionLookbackSeconds')"
      >
        Lookback (сек)
        <input
          v-model.number="waterForm.irrigationDecisionLookbackSeconds"
          type="number"
          min="60"
          max="86400"
          class="input-field mt-1 w-full"
          :disabled="!ctx.canConfigure.value"
        />
      </label>
      <label
        class="text-xs text-[color:var(--text-muted)]"
        :title="zoneAutomationFieldHelp('water.irrigationDecisionMinSamples')"
      >
        Min samples
        <input
          v-model.number="waterForm.irrigationDecisionMinSamples"
          type="number"
          min="1"
          max="100"
          class="input-field mt-1 w-full"
          :disabled="!ctx.canConfigure.value"
        />
      </label>
      <label
        class="text-xs text-[color:var(--text-muted)]"
        :title="zoneAutomationFieldHelp('water.irrigationDecisionStaleAfterSeconds')"
      >
        Telemetry stale after (сек)
        <input
          v-model.number="waterForm.irrigationDecisionStaleAfterSeconds"
          type="number"
          min="30"
          max="86400"
          class="input-field mt-1 w-full"
          :disabled="!ctx.canConfigure.value"
        />
      </label>
      <label
        class="text-xs text-[color:var(--text-muted)]"
        :title="zoneAutomationFieldHelp('water.irrigationDecisionHysteresisPct')"
      >
        Hysteresis (%)
        <input
          v-model.number="waterForm.irrigationDecisionHysteresisPct"
          type="number"
          min="0"
          max="100"
          step="0.1"
          class="input-field mt-1 w-full"
          :disabled="!ctx.canConfigure.value"
        />
      </label>
      <label
        class="text-xs text-[color:var(--text-muted)]"
        :title="zoneAutomationFieldHelp('water.irrigationDecisionSpreadAlertThresholdPct')"
      >
        Spread alert threshold (%)
        <input
          v-model.number="waterForm.irrigationDecisionSpreadAlertThresholdPct"
          type="number"
          min="0"
          max="100"
          step="0.1"
          class="input-field mt-1 w-full"
          :disabled="!ctx.canConfigure.value"
        />
      </label>
      <label
        class="text-xs text-[color:var(--text-muted)]"
        :title="zoneAutomationFieldHelp('water.irrigationAutoReplayAfterSetup')"
      >
        Auto replay after setup
        <select
          v-model="waterForm.irrigationAutoReplayAfterSetup"
          class="input-select mt-1 w-full"
          :disabled="!ctx.canConfigure.value"
        >
          <option :value="true">Включён</option>
          <option :value="false">Выключен</option>
        </select>
      </label>
      <label
        class="text-xs text-[color:var(--text-muted)]"
        :title="zoneAutomationFieldHelp('water.irrigationMaxSetupReplays')"
      >
        Max setup replays
        <input
          v-model.number="waterForm.irrigationMaxSetupReplays"
          type="number"
          min="0"
          max="10"
          class="input-field mt-1 w-full"
          :disabled="!ctx.canConfigure.value"
        />
      </label>
      <label
        v-if="showStopOnSolutionMin"
        class="text-xs text-[color:var(--text-muted)] md:col-span-2 xl:col-span-2"
        :title="zoneAutomationFieldHelp('water.stopOnSolutionMin')"
      >
        Stop on solution min
        <select
          v-model="waterForm.stopOnSolutionMin"
          data-test="irrigation-stop-on-solution-min"
          class="input-select mt-1 w-full"
          :disabled="!ctx.canConfigure.value"
        >
          <option :value="true">Fail-closed при low solution</option>
          <option :value="false">Не останавливать irrigation workflow</option>
        </select>
      </label>
    </div>
  </component>
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
import type { RecipeSoilMoistureTargets } from '@/Components/ZoneAutomation/IrrigationSection.vue'

const props = withDefaults(defineProps<{
  recipeSoilMoistureTargets: RecipeSoilMoistureTargets
  soilMoistureCandidates?: SetupWizardNode[]
  collapsible?: boolean
  showSoilMoistureBinding?: boolean
  showStopOnSolutionMin?: boolean
}>(), {
  soilMoistureCandidates: () => [],
  collapsible: false,
  showSoilMoistureBinding: false,
  showStopOnSolutionMin: false,
})

const waterForm = defineModel<WaterFormState>('waterForm', { required: true })
const assignments = defineModel<ZoneAutomationSectionAssignments | null>('assignments', { default: null })

const ctx = useZoneAutomationSectionContext()

const description = computed(() => props.collapsible
  ? 'Настройки decision-controller штатного полива (`smart_soil_v1`) и recovery/safety политики. Цели влажности (day/night) задаются в фазе рецепта.'
  : 'Strategy обычного полива, требования к телеметрии и replay-policy после setup/recovery. Цели влажности (day/night) задаются в фазе рецепта.')

const headerClass = computed(() => props.collapsible
  ? 'cursor-pointer text-sm font-semibold text-[color:var(--text-primary)]'
  : 'text-sm font-semibold text-[color:var(--text-primary)]')
</script>
