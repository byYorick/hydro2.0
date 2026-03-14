<template>
  <AppLayout>
    <div class="space-y-4">
      <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
        <h1 class="text-lg font-semibold">Настройки калибровки</h1>
        <p class="text-sm text-[color:var(--text-dim)] mt-1">
          Системный source of truth для `pump_calibration` и `sensor_calibration`.
        </p>
      </div>

      <div class="flex gap-2">
        <Button
          v-for="namespace in namespaces"
          :key="namespace"
          size="sm"
          :variant="activeNamespace === namespace ? 'primary' : 'secondary'"
          @click="activeNamespace = namespace"
        >
          {{ namespace }}
        </Button>
      </div>

      <Card v-if="activePayload" class="space-y-4">
        <div class="grid gap-4 md:grid-cols-2">
          <div
            v-for="field in activeFields"
            :key="field.path"
            class="space-y-1.5"
          >
            <label class="block text-xs font-medium text-[color:var(--text-muted)]">
              {{ field.label }}
            </label>
            <input
              v-model="draft[field.path]"
              :type="field.type === 'string' ? 'text' : 'number'"
              :step="field.step ?? (field.type === 'integer' ? 1 : 'any')"
              :min="field.min"
              :max="field.max"
              class="input-field w-full"
            />
            <div class="text-[11px] text-[color:var(--text-dim)]">
              {{ field.description }}
            </div>
          </div>
        </div>

        <div class="flex gap-2">
          <Button
            size="sm"
            :disabled="loading"
            @click="save"
          >
            {{ loading ? 'Сохранение...' : 'Сохранить' }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :disabled="loading"
            @click="reset"
          >
            Сбросить к дефолтам
          </Button>
        </div>
      </Card>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import { useSystemSettings } from '@/composables/useSystemSettings'
import { useToast } from '@/composables/useToast'
import type { SettingsNamespacePayload, SystemSettingsField } from '@/types/SystemSettings'

const { getAll, updateNamespace, resetNamespace } = useSystemSettings()
const { showToast } = useToast()

const payloads = ref<Record<string, SettingsNamespacePayload>>({})
const activeNamespace = ref<'pump_calibration' | 'sensor_calibration'>('pump_calibration')
const loading = ref(false)
const draft = ref<Record<string, string | number | undefined>>({})

const namespaces = computed<Array<'pump_calibration' | 'sensor_calibration'>>(
  () => Object.keys(payloads.value) as Array<'pump_calibration' | 'sensor_calibration'>,
)
const activePayload = computed(() => payloads.value[activeNamespace.value] || null)
const activeFields = computed<SystemSettingsField[]>(() => activePayload.value?.meta.field_catalog.flatMap((section) => section.fields) || [])

function syncDraft(): void {
  if (!activePayload.value) return
  draft.value = { ...(activePayload.value.config as Record<string, string | number | undefined>) }
}

function normalizeDraft(): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  activeFields.value.forEach((field) => {
    const raw = draft.value[field.path]
    if (field.type === 'integer') {
      result[field.path] = Math.trunc(Number(raw))
      return
    }
    if (field.type === 'number') {
      result[field.path] = Number(raw)
      return
    }
    result[field.path] = raw
  })
  return result
}

async function load(): Promise<void> {
  payloads.value = await getAll()
  syncDraft()
}

async function save(): Promise<void> {
  loading.value = true
  try {
    const updated = await updateNamespace(activeNamespace.value, normalizeDraft())
    payloads.value[activeNamespace.value] = updated
    syncDraft()
    showToast('Настройки сохранены', 'success')
  } finally {
    loading.value = false
  }
}

async function reset(): Promise<void> {
  loading.value = true
  try {
    const updated = await resetNamespace(activeNamespace.value)
    payloads.value[activeNamespace.value] = updated
    syncDraft()
    showToast('Настройки сброшены', 'success')
  } finally {
    loading.value = false
  }
}

watch(activeNamespace, () => {
  syncDraft()
})

onMounted(() => {
  void load()
})
</script>
