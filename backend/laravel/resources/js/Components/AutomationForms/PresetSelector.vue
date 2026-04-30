<template>
  <div class="p-3 border border-brand bg-brand-soft rounded-md flex flex-col gap-2.5">
    <div class="flex items-center gap-2.5 flex-wrap">
      <Ic
        name="bookmark"
        class="text-brand shrink-0"
      />
      <span class="text-xs font-semibold text-brand-ink">Профиль автоматики</span>
      <Chip
        v-if="selectedPreset && isModified"
        tone="warn"
      >
        изменено
      </Chip>
    </div>

    <div class="flex items-center gap-2 flex-wrap">
      <select
        v-if="!loading"
        class="block min-w-[300px] flex-1 h-8 rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-primary)] px-2.5 text-sm font-mono outline-none focus-visible:ring-2 focus-visible:ring-brand"
        :value="selectedPreset?.id ?? ''"
        :disabled="!canConfigure"
        @change="onSelectChange"
      >
        <option value="">
          — Настроить с нуля —
        </option>
        <optgroup
          v-if="systemPresets.length > 0"
          label="Системные"
        >
          <option
            v-for="preset in systemPresets"
            :key="preset.id"
            :value="preset.id"
          >
            {{ preset.name }} · {{ correctionProfileLabel(preset.correction_profile) }} · {{ Math.round(preset.config.irrigation.interval_sec / 60) }}мин
          </option>
        </optgroup>
        <optgroup
          v-if="customPresets.length > 0"
          label="Мои профили"
        >
          <option
            v-for="preset in customPresets"
            :key="preset.id"
            :value="preset.id"
          >
            {{ preset.name }}
          </option>
        </optgroup>
      </select>
      <div
        v-else
        class="flex items-center gap-2 text-xs text-[var(--text-muted)]"
      >
        <span class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-brand border-t-transparent"></span>
        Загрузка профилей...
      </div>
    </div>

    <div
      v-if="selectedPreset"
      class="flex flex-col gap-2 px-2.5 py-2 bg-[var(--bg-surface)] border border-[var(--border-muted)] rounded-sm"
    >
      <p
        v-if="selectedPreset.description"
        class="text-[11px] leading-relaxed text-[var(--text-muted)] whitespace-pre-line"
      >
        {{ selectedPreset.description }}
      </p>

      <div class="flex flex-wrap gap-1.5">
        <Chip
          v-if="selectedPreset.correction_profile"
          :tone="correctionProfileTone(selectedPreset.correction_profile)"
        >
          {{ correctionProfileLabel(selectedPreset.correction_profile) }}
        </Chip>
        <Chip tone="neutral">
          <span class="font-mono">{{ selectedPreset.irrigation_system_type }}</span>
        </Chip>
        <Chip tone="neutral">
          {{ selectedPreset.tanks_count }} бака
        </Chip>
        <Chip tone="neutral">
          Полив:
          <span class="font-mono ml-1">
            {{ Math.round(selectedPreset.config.irrigation.interval_sec / 60) }}м/{{ selectedPreset.config.irrigation.duration_sec }}с
          </span>
        </Chip>
        <Chip tone="neutral">
          Корр. при поливе: {{ selectedPreset.config.irrigation.correction_during_irrigation ? 'да' : 'нет' }}
        </Chip>
      </div>
    </div>

    <p
      v-else-if="!loading"
      class="text-[11px] text-[var(--text-dim)]"
    >
      Ручная настройка — заполните параметры ниже вручную.
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Chip } from '@/Components/Shared/Primitives'
import type { ChipTone } from '@/Components/Shared/Primitives/Chip.vue'
import Ic from '@/Components/Icons/Ic.vue'
import type { ZoneAutomationPreset } from '@/types/ZoneAutomationPreset'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'
import {
  useZoneAutomationPresets,
  applyPresetToWaterForm,
  isPresetModified,
} from '@/composables/useZoneAutomationPresets'

const props = defineProps<{
  waterForm: WaterFormState
  canConfigure: boolean
  tanksCount?: number
  irrigationSystemType?: string
}>()

const emit = defineEmits<{
  presetApplied: [preset: ZoneAutomationPreset]
  presetCleared: []
  'update:waterForm': [form: WaterFormState]
}>()

const { presets, loading, loadPresets } = useZoneAutomationPresets()

const selectedPreset = ref<ZoneAutomationPreset | null>(null)

const compatibleIrrigationTypes = computed<string[]>(() => {
  const st = props.waterForm.systemType
  const map: Record<string, string[]> = {
    drip: ['drip_tape', 'drip_emitter'],
    substrate_trays: ['dwc', 'ebb_flow', 'aeroponics'],
    nft: ['nft'],
  }
  return map[st] ?? []
})

const filteredPresets = computed(() =>
  presets.value.filter((p) => {
    if (props.tanksCount !== undefined && p.tanks_count !== props.tanksCount) return false
    if (
      compatibleIrrigationTypes.value.length > 0 &&
      !compatibleIrrigationTypes.value.includes(p.irrigation_system_type)
    )
      return false
    return true
  }),
)

const systemPresets = computed(() => filteredPresets.value.filter((p) => p.scope === 'system'))
const customPresets = computed(() => filteredPresets.value.filter((p) => p.scope === 'custom'))

const isModified = computed(() => {
  if (!selectedPreset.value) return false
  return isPresetModified(selectedPreset.value, props.waterForm)
})

function onSelectChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  if (!value) {
    selectedPreset.value = null
    emit('presetCleared')
    return
  }
  const preset = filteredPresets.value.find((p) => p.id === Number(value))
  if (preset) {
    selectedPreset.value = preset
    const updated = applyPresetToWaterForm(preset, props.waterForm)
    emit('update:waterForm', updated)
    emit('presetApplied', preset)
  }
}

function correctionProfileLabel(profile: string | null): string {
  if (!profile) return ''
  const labels: Record<string, string> = {
    safe: 'Мягкий',
    balanced: 'Оптимальный',
    aggressive: 'Агрессивный',
    test: 'Тестовый',
  }
  return labels[profile] ?? profile
}

function correctionProfileTone(profile: string): ChipTone {
  const map: Record<string, ChipTone> = {
    safe: 'growth',
    balanced: 'brand',
    aggressive: 'warn',
    test: 'neutral',
  }
  return map[profile] ?? 'neutral'
}

onMounted(() => {
  loadPresets()
})

watch(
  () => props.tanksCount,
  () => {
    loadPresets()
  },
)

watch(
  () => props.waterForm.systemType,
  () => {
    const preset = selectedPreset.value
    if (
      preset &&
      !filteredPresets.value.some((p) => p.id === preset.id)
    ) {
      selectedPreset.value = null
      emit('presetCleared')
    }
  },
)
</script>
