<template>
  <div class="space-y-2">
    <div class="flex items-center gap-3">
      <label class="flex-1">
        <span class="text-xs font-medium text-[color:var(--text-primary)]">Профиль автоматики</span>
        <select
          v-if="!loading"
          class="input-select mt-1 w-full"
          :value="selectedPreset?.id ?? ''"
          :disabled="!canConfigure"
          @change="onSelectChange"
        >
          <option value="">Настроить с нуля</option>
          <optgroup v-if="systemPresets.length > 0" label="Системные">
            <option
              v-for="preset in systemPresets"
              :key="preset.id"
              :value="preset.id"
            >
              {{ preset.name }} — {{ correctionProfileLabel(preset.correction_profile) }} · {{ preset.irrigation_system_type }} · {{ Math.round(preset.config.irrigation.interval_sec / 60) }} мин
            </option>
          </optgroup>
          <optgroup v-if="customPresets.length > 0" label="Мои профили">
            <option
              v-for="preset in customPresets"
              :key="preset.id"
              :value="preset.id"
            >
              {{ preset.name }}
            </option>
          </optgroup>
        </select>
        <div v-else class="mt-1 flex items-center gap-2 text-xs text-[color:var(--text-muted)]">
          <span class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-[color:var(--accent-cyan)] border-t-transparent"></span>
          Загрузка профилей...
        </div>
      </label>

      <span
        v-if="selectedPreset && isModified"
        class="mt-5 shrink-0 rounded-full bg-[color:var(--badge-warning-bg)] px-2 py-0.5 text-[10px] font-medium text-[color:var(--badge-warning-text)]"
      >
        Изменено
      </span>
    </div>

    <!-- Описание и параметры выбранного пресета -->
    <div
      v-if="selectedPreset"
      class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 space-y-2"
    >
      <p
        v-if="selectedPreset.description"
        class="text-[11px] leading-relaxed text-[color:var(--text-muted)] whitespace-pre-line"
      >
        {{ selectedPreset.description }}
      </p>

      <div class="flex flex-wrap gap-1.5">
        <span
          v-if="selectedPreset.correction_profile"
          class="rounded-full px-1.5 py-px text-[10px] font-medium"
          :class="correctionProfileClass(selectedPreset.correction_profile)"
        >
          {{ correctionProfileLabel(selectedPreset.correction_profile) }}
        </span>
        <span class="rounded bg-[color:var(--bg-main)] px-1.5 py-px text-[10px] text-[color:var(--text-dim)]">
          {{ selectedPreset.irrigation_system_type }}
        </span>
        <span class="rounded bg-[color:var(--bg-main)] px-1.5 py-px text-[10px] text-[color:var(--text-dim)]">
          {{ selectedPreset.tanks_count }} бака
        </span>
        <span class="rounded bg-[color:var(--bg-main)] px-1.5 py-px text-[10px] text-[color:var(--text-dim)]">
          Полив: {{ Math.round(selectedPreset.config.irrigation.interval_sec / 60) }} мин / {{ selectedPreset.config.irrigation.duration_sec }} сек
        </span>
        <span class="rounded bg-[color:var(--bg-main)] px-1.5 py-px text-[10px] text-[color:var(--text-dim)]">
          Коррекция при поливе: {{ selectedPreset.config.irrigation.correction_during_irrigation ? 'да' : 'нет' }}
        </span>
      </div>
    </div>

    <p v-else-if="!loading" class="text-[11px] text-[color:var(--text-dim)]">
      Ручная настройка — заполните параметры ниже вручную.
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import type { ZoneAutomationPreset } from '@/types/ZoneAutomationPreset'
import type { WaterFormState } from '@/composables/zoneAutomationTypes'
import { useZoneAutomationPresets, applyPresetToWaterForm, isPresetModified } from '@/composables/useZoneAutomationPresets'

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

/**
 * Маппинг waterForm.systemType → совместимые preset irrigation_system_type.
 * drip → drip_tape, drip_emitter
 * substrate_trays → dwc, ebb_flow, aeroponics
 * nft → nft
 */
const compatibleIrrigationTypes = computed<string[]>(() => {
  const st = props.waterForm.systemType
  const map: Record<string, string[]> = {
    drip: ['drip_tape', 'drip_emitter'],
    substrate_trays: ['dwc', 'ebb_flow', 'aeroponics'],
    nft: ['nft'],
  }
  return map[st] ?? []
})

const filteredPresets = computed(() => {
  return presets.value.filter(p => {
    if (props.tanksCount !== undefined && p.tanks_count !== props.tanksCount) return false
    if (compatibleIrrigationTypes.value.length > 0 && !compatibleIrrigationTypes.value.includes(p.irrigation_system_type)) return false
    return true
  })
})

const systemPresets = computed(() => filteredPresets.value.filter(p => p.scope === 'system'))
const customPresets = computed(() => filteredPresets.value.filter(p => p.scope === 'custom'))

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
  const preset = filteredPresets.value.find(p => p.id === Number(value))
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

function correctionProfileClass(profile: string): string {
  const classes: Record<string, string> = {
    safe: 'bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)]',
    balanced: 'bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)]',
    aggressive: 'bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]',
    test: 'bg-[color:var(--badge-neutral-bg)] text-[color:var(--badge-neutral-text)]',
  }
  return classes[profile] ?? 'bg-[color:var(--badge-neutral-bg)] text-[color:var(--badge-neutral-text)]'
}

onMounted(() => {
  loadPresets()
})

watch(() => props.tanksCount, () => {
  loadPresets()
})

watch(() => props.waterForm.systemType, () => {
  // Сбросить выбранный пресет если он больше не совместим
  if (selectedPreset.value && !filteredPresets.value.some(p => p.id === selectedPreset.value!.id)) {
    selectedPreset.value = null
    emit('presetCleared')
  }
})
</script>
