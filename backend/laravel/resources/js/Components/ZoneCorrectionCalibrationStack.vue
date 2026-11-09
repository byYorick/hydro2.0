<template>
  <div
    class="space-y-4"
    data-testid="zone-correction-workspace"
  >
    <p class="text-sm text-[color:var(--text-muted)]">
      Сначала проверьте датчики и дозирование насосов, затем настройте процесс и коэффициенты PID. Цели pH и EC берутся из фазы рецепта.
    </p>
    <Tabs
      v-model="activeSection"
      :tabs="sections"
      list-role="group"
      aria-label="Настройки коррекции AE3"
    />
    <section
      v-if="loadedSections.has('readiness') && showRuntimeReadiness"
      v-show="activeSection === 'readiness'"
      class="space-y-3"
      aria-label="Готовность коррекции"
    >
      <CorrectionRuntimeReadinessCard
        :zone-id="zoneId"
        :refresh-token="readinessRefreshToken"
        @focus-process-calibration="selectSection('process')"
        @open-pump-calibration="$emit('open-pump-calibration')"
        @focus-pid-config="selectSection('pid')"
      />
    </section>
    <section
      v-if="loadedSections.has('sensors')"
      v-show="activeSection === 'sensors'"
      class="space-y-3"
      aria-label="Калибровка датчиков"
    >
      <h3 class="text-sm font-semibold">
        Калибровка датчиков pH и EC
      </h3>
      <SensorCalibrationStatus
        :zone-id="zoneId"
        :settings="sensorCalibrationSettings"
      />
    </section>
    <section
      v-if="loadedSections.has('pumps')"
      v-show="activeSection === 'pumps'"
      class="space-y-3"
      aria-label="Калибровка насосов"
    >
      <h3 class="text-sm font-semibold">
        Дозирующие насосы
      </h3>
      <PumpCalibrationsPanel
        :zone-id="zoneId"
        :save-success-seq="saveSuccessSeq"
        :run-success-seq="runSuccessSeq"
        @open-pump-calibration="$emit('open-pump-calibration')"
      />
    </section>
    <section
      v-if="loadedSections.has('process')"
      v-show="activeSection === 'process'"
      id="zone-process-calibration-panel-shared"
      class="space-y-3"
      aria-label="Калибровка процесса"
    >
      <h3 class="text-sm font-semibold">
        Отклик раствора и время стабилизации
      </h3>
      <ProcessCalibrationPanel
        :zone-id="zoneId"
        @saved="handleAuthorityUpdated"
      />
    </section>
    <section
      v-if="loadedSections.has('pid')"
      v-show="activeSection === 'pid'"
      id="zone-pid-config-panel-shared"
      aria-label="Коэффициенты PID"
    >
      <PidConfigForm
        :zone-id="zoneId"
        :phase-targets="phaseTargets"
        :disabled="!canEdit"
        @saved="handlePidConfigSaved"
      />
    </section>
    <section
      v-if="loadedSections.has('history')"
      v-show="activeSection === 'history'"
      aria-label="История PID"
    >
      <PidLogsTable :zone-id="zoneId" />
    </section>
    <section
      v-if="loadedSections.has('limits')"
      v-show="activeSection === 'limits'"
      aria-label="Параметры коррекции"
    >
      <p class="mb-3 text-sm text-[color:var(--text-muted)]">
        Лимиты доз, ожидание эффекта и профили коррекции. Коэффициенты Kp/Ki/Kd редактируются в разделе «PID».
      </p>
      <CorrectionConfigForm
        :zone-id="zoneId"
        @saved="handleAuthorityUpdated"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import Tabs from '@/Components/Tabs.vue'
import CorrectionConfigForm from '@/Components/CorrectionConfigForm.vue'
import CorrectionRuntimeReadinessCard from '@/Components/CorrectionRuntimeReadinessCard.vue'
import PidConfigForm from '@/Components/PidConfigForm.vue'
import PidLogsTable from '@/Components/PidLogsTable.vue'
import ProcessCalibrationPanel from '@/Components/ProcessCalibrationPanel.vue'
import PumpCalibrationsPanel from '@/Components/PumpCalibrationsPanel.vue'
import SensorCalibrationStatus from '@/Components/SensorCalibrationStatus.vue'
import { useRole } from '@/composables/useRole'
import type { RecipePhasePidTargets } from '@/composables/recipePhasePidTargets'
import type { PidConfigWithMeta } from '@/types/PidConfig'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'

const props = withDefaults(defineProps<{
  zoneId: number
  sensorCalibrationSettings: SensorCalibrationSettings
  phaseTargets?: RecipePhasePidTargets | null
  showRuntimeReadiness?: boolean
  saveSuccessSeq?: number
  runSuccessSeq?: number
}>(), { phaseTargets: null, showRuntimeReadiness: true, saveSuccessSeq: 0, runSuccessSeq: 0 })
const emit = defineEmits<{
  'open-pump-calibration': []
  'pid-config-saved': [config: PidConfigWithMeta]
  'authority-updated': []
}>()
const { canEdit } = useRole()
const activeSection = ref(props.showRuntimeReadiness ? 'readiness' : 'sensors')
const loadedSections = ref(new Set([activeSection.value]))
watch(activeSection, section => loadedSections.value.add(section), { flush: 'sync' })
const sections = computed(() => [
  ...(props.showRuntimeReadiness ? [{ id: 'readiness', label: 'Готовность' }] : []),
  { id: 'sensors', label: 'Датчики' }, { id: 'pumps', label: 'Насосы' },
  { id: 'process', label: 'Процесс' }, { id: 'pid', label: 'PID' },
  { id: 'history', label: 'История PID' }, { id: 'limits', label: 'Параметры коррекции' },
])
const authorityRefreshSeq = ref(0)
const readinessRefreshToken = computed(() => `${props.saveSuccessSeq}:${props.runSuccessSeq}:${authorityRefreshSeq.value}`)
function selectSection(section: string) { activeSection.value = section }
function handlePidConfigSaved(config: PidConfigWithMeta) { handleAuthorityUpdated(); emit('pid-config-saved', config) }
function handleAuthorityUpdated() { authorityRefreshSeq.value += 1; emit('authority-updated') }
onMounted(() => {
  if (window.location.hash === '#zone-pid-config-panel-shared') activeSection.value = 'pid'
})
watch(() => props.zoneId, () => {
  activeSection.value = props.showRuntimeReadiness ? 'readiness' : 'sensors'
  loadedSections.value = new Set([activeSection.value])
})
</script>
