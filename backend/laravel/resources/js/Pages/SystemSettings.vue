<template>
  <AppLayout>
    <div class="space-y-4">
      <header class="ui-hero p-4 space-y-3">
        <div class="min-w-0">
          <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
            система / автоматика
          </p>
          <h1 class="text-xl font-semibold tracking-tight text-[color:var(--text-primary)] mt-0.5">
            Системные настройки автоматики
          </h1>
          <p class="text-sm text-[color:var(--text-muted)] max-w-3xl mt-0.5">
            Общие для всей теплицы значения: калибровки, стартовые параметры зон и пороги предупреждений.
            Настройки конкретной зоны задаются на её странице.
          </p>
          <p
            class="text-xs text-[color:var(--text-dim)] mt-1"
            data-testid="system-settings-kpi-strip"
          >
            {{ namespaceLabel(activeNamespace) }} · {{ activeFields.length }} параметров
            <span v-if="loading"> · сохранение…</span>
          </p>
        </div>
      </header>

      <div class="space-y-4">
        <div
          class="surface-card border border-[color:var(--border-muted)] rounded-xl p-1.5"
          data-testid="system-settings-section-nav"
        >
          <Tabs
            v-model="activeNamespace"
            :tabs="systemSettingsTabs"
            aria-label="Разделы системных настроек"
          />
        </div>

        <SettingsSectionShell
          v-if="activePayload"
          :title="namespaceLabel(activeNamespace)"
          :description="namespaceDescription(activeNamespace)"
          :icon="namespaceIcon(activeNamespace)"
          test-id="system-settings-active-card"
        >
          <CommandTemplatesSettingsForm
            v-if="usesCommandTemplatesForm"
            v-model="commandTemplatesDraft"
            :fields="activeFields"
          />

          <AuthorityFieldCatalogForm
            v-else
            v-model="draft"
            :sections="activeSections"
          />

          <template #footer>
            <Button
              size="sm"
              :disabled="loading"
              data-testid="system-settings-save"
              @click="save"
            >
              {{ loading ? 'Сохранение...' : 'Сохранить' }}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              :disabled="loading"
              data-testid="system-settings-reset"
              @click="reset"
            >
              Сбросить к дефолтам
            </Button>
          </template>
        </SettingsSectionShell>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import Tabs from '@/Components/Tabs.vue'
import AuthorityFieldCatalogForm from '@/Components/Settings/AuthorityFieldCatalogForm.vue'
import CommandTemplatesSettingsForm from '@/Components/Settings/CommandTemplatesSettingsForm.vue'
import SettingsSectionShell from '@/Components/Settings/SettingsSectionShell.vue'
import { useAutomationConfig, type AutomationDocument } from '@/composables/useAutomationConfig'
import { normalizeAutomationCommandTemplates } from '@/composables/useAutomationCommandTemplates'
import { useToast } from '@/composables/useToast'
import type {
  AutomationCommandTemplateStep,
  SettingsNamespacePayload,
  SystemSettingsField,
  SystemSettingsSection,
} from '@/types/SystemSettings'

const COMMAND_TEMPLATES_NAMESPACE = 'automation_command_templates'

type DraftScalar = string | number | boolean | undefined
type SettingsDraft = Record<string, DraftScalar>

const SYSTEM_NAMESPACE_MAP: Record<string, string> = {
  automation_defaults: 'system.automation_defaults',
  automation_command_templates: 'system.command_templates',
  process_calibration_defaults: 'system.process_calibration_defaults',
  pump_calibration: 'system.pump_calibration_policy',
  sensor_calibration: 'system.sensor_calibration_policy',
  observability_thresholds: 'system.observability_thresholds',
}

const NAMESPACE_LABELS: Record<string, string> = {
  automation_defaults: 'Значения по умолчанию',
  automation_command_templates: 'Шаблоны команд',
  process_calibration_defaults: 'Калибровка процессов',
  pump_calibration: 'Калибровка насосов',
  sensor_calibration: 'Калибровка датчиков',
  observability_thresholds: 'Пороги диагностики',
}

const NAMESPACE_ICONS: Record<string, string> = {
  automation_defaults: '🌱',
  automation_command_templates: '🔀',
  process_calibration_defaults: '🧪',
  pump_calibration: '💧',
  sensor_calibration: '📡',
  observability_thresholds: '📊',
}

const NAMESPACE_DESCRIPTIONS: Record<string, string> = {
  automation_defaults: 'С этих значений начинается настройка новой зоны: климат, полив, освещение.',
  automation_command_templates: 'Последовательности включения реле для двухбаковой схемы.',
  process_calibration_defaults: 'Стартовые коэффициенты отклика раствора на дозирование.',
  pump_calibration: 'Допустимые пределы и оценка качества калибровки насосов.',
  sensor_calibration: 'Эталонные растворы и сроки повторной калибровки датчиков.',
  observability_thresholds: 'После какого времени система считает процесс зависшим и предупреждает оператора.',
}

type SystemAuthorityDocument = AutomationDocument<Record<string, unknown>, {
  defaults?: Record<string, unknown>
  field_catalog?: SystemSettingsSection[]
}>
type SystemAuthorityMeta = SystemAuthorityDocument['meta']

const automationConfig = useAutomationConfig()
const { showToast } = useToast()

const payloads = ref<Record<string, SettingsNamespacePayload>>({})
const activeNamespace = ref<string>('observability_thresholds')
const loading = ref(false)
const draft = ref<SettingsDraft>({})
const commandTemplatesDraft = ref<Record<string, AutomationCommandTemplateStep[]>>({})

const namespaces = computed<string[]>(() => Object.keys(payloads.value))
const systemSettingsTabs = computed(() =>
  namespaces.value.map((namespace) => ({
    id: namespace,
    label: namespaceLabel(namespace),
    testId: `system-settings-tab-${namespace}`,
  })),
)
const activePayload = computed(() => payloads.value[activeNamespace.value] || null)
const activeSections = computed<SystemSettingsSection[]>(() => activePayload.value?.meta.field_catalog ?? [])
const activeFields = computed<SystemSettingsField[]>(() => activeSections.value.flatMap((section) => section.fields))
const usesCommandTemplatesForm = computed(() => activeNamespace.value === COMMAND_TEMPLATES_NAMESPACE)

function namespaceLabel(namespace: string): string {
  return NAMESPACE_LABELS[namespace] ?? namespace
}

function namespaceIcon(namespace: string): string {
  return NAMESPACE_ICONS[namespace] ?? '⚙️'
}

function namespaceDescription(namespace: string): string {
  return NAMESPACE_DESCRIPTIONS[namespace] ?? 'Системные параметры authority.'
}

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
  if (!activePayload.value) {
    return
  }

  if (usesCommandTemplatesForm.value) {
    const normalized = normalizeAutomationCommandTemplates(
      activePayload.value.config as Partial<Record<string, AutomationCommandTemplateStep[]>>,
    )
    commandTemplatesDraft.value = Object.fromEntries(
      activeFields.value.map((field) => [field.path, normalized[field.path as keyof typeof normalized] ?? []]),
    )
    return
  }

  const current = activePayload.value.config as Record<string, unknown>
  const nextDraft: SettingsDraft = {}
  activeFields.value.forEach((field) => {
    const raw = current[field.path]
    nextDraft[field.path] = field.type === 'json'
      ? JSON.stringify(raw ?? [], null, 2)
      : raw as DraftScalar
  })
  draft.value = nextDraft
}

function normalizeDraft(): Record<string, unknown> {
  if (usesCommandTemplatesForm.value) {
    return {
      ...normalizeAutomationCommandTemplates(commandTemplatesDraft.value),
    } as Record<string, unknown>
  }

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
