<template>
  <Card class="zone-pump-calibration-settings-card">
    <div class="space-y-4">
      <div class="flex items-center justify-between gap-3">
        <div>
          <div class="text-sm font-semibold">Pump Calibration Override</div>
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            Переопределение системных порогов калибровки насосов только для этой зоны.
          </div>
        </div>
        <Badge :variant="hasOverrides ? 'warning' : 'info'">
          {{ hasOverrides ? 'Есть override' : 'Наследование от системы' }}
        </Badge>
      </div>

      <div
        v-if="loading"
        class="text-sm text-[color:var(--text-dim)]"
      >
        Загрузка...
      </div>

      <div
        v-else
        class="grid gap-4 md:grid-cols-2"
      >
        <div
          v-for="field in fields"
          :key="field.path"
          class="space-y-1.5"
        >
          <label class="block text-xs font-medium text-[color:var(--text-muted)]">
            {{ field.label }}
          </label>
          <input
            :value="stringValue(field.path)"
            :type="field.type === 'string' ? 'text' : 'number'"
            :step="field.step ?? (field.type === 'integer' ? 1 : 'any')"
            :min="field.min"
            :max="field.max"
            class="input-field w-full"
            :placeholder="`Система: ${resolvedSystemSettings[field.path as keyof PumpCalibrationSettings]}`"
            :title="field.description"
            @input="updateField(field.path, ($event.target as HTMLInputElement).value)"
          />
          <div class="text-[11px] text-[color:var(--text-dim)]">
            {{ field.description }}
          </div>
          <div class="text-[11px] text-[color:var(--text-muted)]">
            Effective: {{ effectiveValue(field.path) }}
          </div>
        </div>
      </div>

      <div class="flex flex-wrap gap-2">
        <Button
          size="sm"
          :disabled="loading || saving"
          @click="save"
        >
          {{ saving ? 'Сохранение...' : 'Сохранить override' }}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          :disabled="loading || saving || !hasOverrides"
          @click="resetOverrides"
        >
          Сбросить к системным
        </Button>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import { useApi } from '@/composables/useApi'
import { usePumpCalibrationSettings } from '@/composables/usePumpCalibrationSettings'
import { useToast } from '@/composables/useToast'
import type { PumpCalibrationSettings, SystemSettingsField, SystemSettingsSection } from '@/types/SystemSettings'

interface CorrectionConfigResponse {
  preset: { id: number } | null
  base_config: Record<string, unknown>
  phase_overrides: Record<string, unknown>
  meta: {
    pump_calibration_field_catalog: SystemSettingsSection[]
  }
}

const props = defineProps<{ zoneId: number }>()

const { api } = useApi()
const { showToast } = useToast()
const systemSettings = usePumpCalibrationSettings()

const loading = ref(true)
const saving = ref(false)
const baseConfig = ref<Record<string, unknown>>({})
const phaseOverrides = ref<Record<string, unknown>>({})
const presetId = ref<number | null>(null)
const overrideConfig = ref<Partial<PumpCalibrationSettings>>({})
const fields = ref<SystemSettingsField[]>([])

const resolvedSystemSettings = computed<PumpCalibrationSettings>(() => systemSettings.value)

const hasOverrides = computed(() => Object.keys(overrideConfig.value).length > 0)

function numericField(field: SystemSettingsField, value: string): number | null {
  if (value.trim() === '') return null
  const raw = Number(value)
  if (!Number.isFinite(raw)) return null
  return field.type === 'integer' ? Math.trunc(raw) : raw
}

function stringValue(path: string): string {
  const value = overrideConfig.value[path as keyof PumpCalibrationSettings]
  return value === undefined || value === null ? '' : String(value)
}

function effectiveValue(path: string): string {
  const override = overrideConfig.value[path as keyof PumpCalibrationSettings]
  return String(override ?? resolvedSystemSettings.value[path as keyof PumpCalibrationSettings])
}

function updateField(path: string, rawValue: string): void {
  const field = fields.value.find((item) => item.path === path)
  if (!field) return
  const next = { ...overrideConfig.value }
  const normalized = numericField(field, rawValue)
  if (normalized === null) {
    delete next[path as keyof PumpCalibrationSettings]
  } else {
    next[path as keyof PumpCalibrationSettings] = normalized as never
  }
  overrideConfig.value = next
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const response = await api.get(`/api/automation-configs/zone/${props.zoneId}/zone.correction`)
    const payload = response.data.data as CorrectionConfigResponse
    presetId.value = payload.preset?.id ?? null
    baseConfig.value = payload.base_config || {}
    phaseOverrides.value = payload.phase_overrides || {}
    overrideConfig.value = ((payload.base_config?.pump_calibration as Partial<PumpCalibrationSettings>) || {})
    fields.value = (payload.meta?.pump_calibration_field_catalog || []).flatMap((section) => section.fields)
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  saving.value = true
  try {
    const nextBaseConfig = {
      ...baseConfig.value,
      pump_calibration: overrideConfig.value,
    }
    await api.put(`/api/automation-configs/zone/${props.zoneId}/zone.correction`, {
      payload: {
        preset_id: presetId.value,
        base_config: nextBaseConfig,
        phase_overrides: phaseOverrides.value,
      },
    })
    showToast('Pump calibration override сохранён', 'success')
    await load()
  } finally {
    saving.value = false
  }
}

async function resetOverrides(): Promise<void> {
  overrideConfig.value = {}
  await save()
}

onMounted(() => {
  void load()
})
</script>

<style scoped>
.zone-pump-calibration-settings-card :deep(.input-field) {
  height: 2.2rem;
  padding: 0 0.7rem;
  font-size: 0.78rem;
  border-radius: 0.72rem;
}
</style>
