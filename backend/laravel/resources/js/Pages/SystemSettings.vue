<template>
  <AppLayout>
    <div class="space-y-4">
      <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
        <h1 class="text-lg font-semibold">
          Системные настройки автоматики
        </h1>
        <p class="text-sm text-[color:var(--text-dim)] mt-1">
          Системный source of truth для calibration и automation defaults.
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

      <Card
        v-if="activePayload"
        class="space-y-4"
      >
        <div class="grid gap-4 md:grid-cols-2">
          <div
            v-for="field in activeFields"
            :key="field.path"
            class="space-y-1.5"
          >
            <label class="block text-xs font-medium text-[color:var(--text-muted)]">
              {{ field.label }}
            </label>
            <label
              v-if="field.type === 'boolean'"
              class="flex items-center gap-2 rounded-xl border border-[color:var(--border-muted)] px-3 py-2 text-sm"
            >
              <input
                v-model="draft[field.path]"
                type="checkbox"
              />
              <span>{{ field.description }}</span>
            </label>
            <textarea
              v-else-if="field.type === 'json'"
              v-model="draft[field.path]"
              rows="8"
              class="input-field w-full font-mono text-xs"
            ></textarea>
            <input
              v-else
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
import { useAutomationConfig, type AutomationDocument } from '@/composables/useAutomationConfig'
import { useToast } from '@/composables/useToast'
import type { SettingsNamespacePayload, SystemSettingsField } from '@/types/SystemSettings'

const SYSTEM_NAMESPACE_MAP: Record<string, string> = {
  automation_defaults: 'system.automation_defaults',
  automation_command_templates: 'system.command_templates',
  process_calibration_defaults: 'system.process_calibration_defaults',
  pump_calibration: 'system.pump_calibration_policy',
  sensor_calibration: 'system.sensor_calibration_policy',
}

type SystemAuthorityDocument = AutomationDocument<Record<string, unknown>, {
  defaults?: Record<string, unknown>
  field_catalog?: Array<{
    key: string
    label: string
    description: string
    fields: SystemSettingsField[]
  }>
}>
type SystemAuthorityMeta = SystemAuthorityDocument['meta']

const automationConfig = useAutomationConfig()
const { showToast } = useToast()

const payloads = ref<Record<string, SettingsNamespacePayload>>({})
const activeNamespace = ref<string>('pump_calibration')
const loading = ref(false)
const draft = ref<Record<string, string | number | boolean | undefined>>({})

const namespaces = computed<string[]>(() => Object.keys(payloads.value))
const activePayload = computed(() => payloads.value[activeNamespace.value] || null)
const activeFields = computed<SystemSettingsField[]>(() => activePayload.value?.meta.field_catalog.flatMap((section) => section.fields) || [])

function documentToPayload(namespace: string, document: SystemAuthorityDocument): SettingsNamespacePayload {
  return {
    namespace,
    config: document.payload ?? {},
    meta: {
      defaults: document.meta?.defaults ?? {},
      field_catalog: Array.isArray(document.meta?.field_catalog) ? document.meta.field_catalog : [],
    },
  }
}

function syncDraft(): void {
  if (!activePayload.value) return
  const current = activePayload.value.config as Record<string, unknown>
  const nextDraft: Record<string, string | number | boolean | undefined> = {}
  activeFields.value.forEach((field) => {
    const raw = current[field.path]
    nextDraft[field.path] = field.type === 'json'
      ? JSON.stringify(raw ?? [], null, 2)
      : raw as string | number | boolean | undefined
  })
  draft.value = nextDraft
}

function normalizeDraft(): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  activeFields.value.forEach((field) => {
    const raw = draft.value[field.path]
    if (field.type === 'boolean') {
      result[field.path] = Boolean(raw)
      return
    }
    if (field.type === 'json') {
      result[field.path] = JSON.parse(String(raw ?? '[]'))
      return
    }
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
  const entries = await Promise.all(
    Object.entries(SYSTEM_NAMESPACE_MAP).map(async ([legacyNamespace, authorityNamespace]) => {
      const document = await automationConfig.getDocument<Record<string, unknown>, NonNullable<SystemAuthorityMeta>>('system', 0, authorityNamespace)
      return [legacyNamespace, documentToPayload(legacyNamespace, document)] as const
    })
  )

  payloads.value = Object.fromEntries(entries) as Record<string, SettingsNamespacePayload>
  syncDraft()
}

async function save(): Promise<void> {
  loading.value = true
  try {
    const authorityNamespace = SYSTEM_NAMESPACE_MAP[activeNamespace.value] ?? activeNamespace.value
    const document = await automationConfig.updateDocument<Record<string, unknown>, NonNullable<SystemAuthorityMeta>>(
      'system',
      0,
      authorityNamespace,
      normalizeDraft()
    )
    payloads.value[activeNamespace.value] = documentToPayload(activeNamespace.value, document)
    syncDraft()
    showToast('Настройки сохранены', 'success')
  } catch (error) {
    showToast(error instanceof Error ? error.message : 'Не удалось сохранить настройки', 'error')
  } finally {
    loading.value = false
  }
}

async function reset(): Promise<void> {
  loading.value = true
  try {
    const authorityNamespace = SYSTEM_NAMESPACE_MAP[activeNamespace.value] ?? activeNamespace.value
    const document = await automationConfig.resetDocument<Record<string, unknown>, NonNullable<SystemAuthorityMeta>>('system', 0, authorityNamespace)
    payloads.value[activeNamespace.value] = documentToPayload(activeNamespace.value, document)
    syncDraft()
    showToast('Настройки сброшены', 'success')
  } catch (error) {
    showToast(error instanceof Error ? error.message : 'Не удалось сбросить настройки', 'error')
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
