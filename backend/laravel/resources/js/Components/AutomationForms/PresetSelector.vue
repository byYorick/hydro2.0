<template>
  <div
    class="flex flex-col gap-2.5"
    data-testid="automation-preset-selector"
  >
    <PresetPillStrip
      :items="pillItems"
      :model-value="selectedPresetId"
      :disabled="!canConfigure || loading"
      description=""
      test-id="automation-preset-strip"
      @select="onPillSelect"
    >
      <template
        v-if="loading"
        #extra
      >
        <span class="inline-flex items-center gap-2 text-xs text-[var(--text-muted)]">
          <span class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-brand border-t-transparent"></span>
          Загрузка профилей…
        </span>
      </template>
    </PresetPillStrip>

    <div
      v-if="selectedPreset"
      class="flex flex-col gap-2 px-3 py-2 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)]"
    >
      <div class="flex flex-wrap items-center gap-1.5">
        <Chip
          v-if="isModified"
          tone="warn"
        >
          изменено относительно пресета
        </Chip>
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
      <p
        v-if="selectedPreset.description"
        class="text-[11px] leading-relaxed text-[var(--text-muted)] whitespace-pre-line"
      >
        {{ selectedPreset.description }}
      </p>
    </div>

    <p
      v-else-if="!loading"
      class="text-[11px] text-[var(--text-dim)] px-1"
    >
      Ручная настройка — заполните параметры ниже вручную.
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Chip } from '@/Components/Shared/Primitives'
import type { ChipTone } from '@/Components/Shared/Primitives/Chip.vue'
import PresetPillStrip, { type PresetPillItem, type PresetPillKey } from '@/Components/Shared/PresetPillStrip.vue'
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

const selectedPresetId = computed<PresetPillKey>(() => selectedPreset.value?.id ?? null)

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
      compatibleIrrigationTypes.value.length > 0
      && !compatibleIrrigationTypes.value.includes(p.irrigation_system_type)
    ) {
      return false
    }
    return true
  }),
)

const pillItems = computed<PresetPillItem[]>(() => {
  const items: PresetPillItem[] = [
    {
      key: null,
      label: 'Без пресета',
      meta: 'manual',
      testId: 'automation-preset-none',
    },
  ]

  for (const preset of filteredPresets.value) {
    const intervalMin = Math.round(preset.config.irrigation.interval_sec / 60)
    const durationSec = preset.config.irrigation.duration_sec
    items.push({
      key: preset.id,
      label: preset.name,
      meta: `${preset.scope} · ${intervalMin}м/${durationSec}с`,
      locked: preset.scope === 'system',
      title: [
        correctionProfileLabel(preset.correction_profile),
        `${preset.tanks_count} бака`,
        `полив ${intervalMin}м/${durationSec}с`,
      ].filter(Boolean).join(' · '),
      testId: `automation-preset-${preset.id}`,
    })
  }

  return items
})

const isModified = computed(() => {
  if (!selectedPreset.value) return false
  return isPresetModified(selectedPreset.value, props.waterForm)
})

function onPillSelect(key: PresetPillKey): void {
  if (key === null) {
    selectedPreset.value = null
    emit('presetCleared')
    return
  }
  const preset = filteredPresets.value.find((p) => p.id === Number(key))
  if (!preset) return
  selectedPreset.value = preset
  const updated = applyPresetToWaterForm(preset, props.waterForm)
  emit('update:waterForm', updated)
  emit('presetApplied', preset)
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
      preset
      && !filteredPresets.value.some((p) => p.id === preset.id)
    ) {
      selectedPreset.value = null
      emit('presetCleared')
    }
  },
)
</script>
