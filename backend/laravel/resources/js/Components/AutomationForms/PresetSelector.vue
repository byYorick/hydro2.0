<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <h4 class="text-sm font-medium text-[color:var(--text-primary)]">
        Профиль автоматики
      </h4>
      <span
        v-if="selectedPreset && isModified"
        class="rounded-full bg-[color:var(--badge-warning-bg)] px-2 py-0.5 text-[10px] font-medium text-[color:var(--badge-warning-text)]"
      >
        Изменено
      </span>
      <span
        v-else-if="selectedPreset"
        class="rounded-full bg-[color:var(--badge-success-bg)] px-2 py-0.5 text-[10px] font-medium text-[color:var(--badge-success-text)]"
      >
        {{ selectedPreset.name }}
      </span>
    </div>

    <p class="text-xs text-[color:var(--text-muted)]">
      Выберите готовый профиль для быстрой настройки или начните с нуля.
      После выбора профиля все параметры ниже будут заполнены — вы можете подкрутить их под свои нужды.
    </p>

    <div v-if="loading" class="flex items-center gap-2 py-4 text-xs text-[color:var(--text-muted)]">
      <span class="inline-block h-4 w-4 animate-spin rounded-full border-2 border-[color:var(--accent-cyan)] border-t-transparent"></span>
      Загрузка профилей...
    </div>

    <div v-else-if="filteredPresets.length === 0" class="rounded-lg border border-dashed border-[color:var(--border-muted)] p-4 text-center text-xs text-[color:var(--text-muted)]">
      Нет доступных профилей для выбранной конфигурации системы.
    </div>

    <div v-else class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <button
        v-for="preset in filteredPresets"
        :key="preset.id"
        type="button"
        class="group relative rounded-xl border p-3 text-left transition-all duration-150"
        :class="[
          selectedPreset?.id === preset.id
            ? 'border-[color:var(--accent-cyan)] bg-[color:var(--accent-cyan)]/5 ring-1 ring-[color:var(--accent-cyan)]/30'
            : 'border-[color:var(--border-muted)] hover:border-[color:var(--accent-cyan)]/50 hover:bg-[color:var(--bg-surface-strong)]',
        ]"
        :disabled="!canConfigure"
        @click="selectPreset(preset)"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5">
              <span class="text-sm font-medium text-[color:var(--text-primary)]">
                {{ preset.name }}
              </span>
              <span
                v-if="preset.scope === 'system'"
                class="rounded bg-[color:var(--badge-info-bg)] px-1 py-px text-[9px] font-medium text-[color:var(--badge-info-text)]"
              >
                Системный
              </span>
            </div>

            <span
              v-if="preset.correction_profile"
              class="mt-1 inline-block rounded-full px-1.5 py-px text-[10px] font-medium"
              :class="correctionProfileClass(preset.correction_profile)"
            >
              {{ correctionProfileLabel(preset.correction_profile) }}
            </span>
          </div>

          <div
            v-if="selectedPreset?.id === preset.id"
            class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[color:var(--accent-cyan)] text-white"
          >
            <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
        </div>

        <p
          v-if="preset.description"
          class="mt-2 line-clamp-3 text-[11px] leading-relaxed text-[color:var(--text-muted)]"
        >
          {{ preset.description }}
        </p>

        <div class="mt-2 flex flex-wrap gap-1">
          <span class="rounded bg-[color:var(--bg-surface-strong)] px-1.5 py-px text-[10px] text-[color:var(--text-dim)]">
            {{ preset.irrigation_system_type }}
          </span>
          <span class="rounded bg-[color:var(--bg-surface-strong)] px-1.5 py-px text-[10px] text-[color:var(--text-dim)]">
            {{ preset.tanks_count }} бака
          </span>
          <span class="rounded bg-[color:var(--bg-surface-strong)] px-1.5 py-px text-[10px] text-[color:var(--text-dim)]">
            Полив: {{ Math.round(preset.config.irrigation.interval_sec / 60) }} мин
          </span>
        </div>
      </button>

      <button
        type="button"
        class="group rounded-xl border border-dashed p-3 text-left transition-all duration-150"
        :class="[
          selectedPreset === null
            ? 'border-[color:var(--accent-cyan)] bg-[color:var(--accent-cyan)]/5'
            : 'border-[color:var(--border-muted)] hover:border-[color:var(--accent-cyan)]/50',
        ]"
        :disabled="!canConfigure"
        @click="clearPreset"
      >
        <div class="flex items-center gap-2">
          <svg class="h-5 w-5 text-[color:var(--text-muted)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          <span class="text-sm font-medium text-[color:var(--text-primary)]">Настроить с нуля</span>
        </div>
        <p class="mt-1 text-[11px] text-[color:var(--text-muted)]">
          Ручная настройка всех параметров автоматики без шаблона.
        </p>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import type { ZoneAutomationPreset, IrrigationSystemType, CorrectionProfile } from '@/types/ZoneAutomationPreset'
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

const filteredPresets = computed(() => {
  return presets.value.filter(p => {
    if (props.tanksCount !== undefined && p.tanks_count !== props.tanksCount) return false
    return true
  })
})

const isModified = computed(() => {
  if (!selectedPreset.value) return false
  return isPresetModified(selectedPreset.value, props.waterForm)
})

function selectPreset(preset: ZoneAutomationPreset) {
  selectedPreset.value = preset
  const updated = applyPresetToWaterForm(preset, props.waterForm)
  emit('update:waterForm', updated)
  emit('presetApplied', preset)
}

function clearPreset() {
  selectedPreset.value = null
  emit('presetCleared')
}

function correctionProfileLabel(profile: string): string {
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
</script>
