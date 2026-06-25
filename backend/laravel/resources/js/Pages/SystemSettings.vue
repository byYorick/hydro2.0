<template>
  <AppLayout>
    <div class="space-y-4">
      <header class="ui-hero p-5 space-y-4">
        <div>
          <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
            authority / system
          </p>
          <h1 class="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)] mt-1">
            Системные настройки автоматики
          </h1>
          <p class="text-sm text-[color:var(--text-muted)] max-w-3xl mt-1">
            Калибровки, дефолты, шаблоны relay-команд и пороги observability — единый source of truth для automation bundle.
          </p>
        </div>
        <div class="ui-kpi-grid grid-cols-2 xl:grid-cols-3">
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Активный раздел
            </div>
            <div class="ui-kpi-value text-base md:text-lg leading-tight">
              {{ namespaceLabel(activeNamespace) }}
            </div>
            <div class="ui-kpi-hint">
              Текущий authority namespace
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Полей в разделе
            </div>
            <div class="ui-kpi-value">
              {{ activeFields.length }}
            </div>
            <div class="ui-kpi-hint">
              Редактируемых параметров
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Статус
            </div>
            <div class="ui-kpi-value text-base md:text-lg leading-tight">
              {{ loading ? 'Сохранение...' : 'Готово' }}
            </div>
            <div class="ui-kpi-hint">
              Локальный draft формы
            </div>
          </div>
        </div>
      </header>

      <div class="grid gap-4 lg:grid-cols-[minmax(220px,260px)_minmax(0,1fr)]">
        <nav
          class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-2 h-fit lg:sticky lg:top-4"
          aria-label="Разделы системных настроек"
        >
          <button
            v-for="namespace in namespaces"
            :key="namespace"
            type="button"
            class="settings-nav-item"
            :class="{ 'settings-nav-item--active': activeNamespace === namespace }"
            :data-testid="`system-settings-tab-${namespace}`"
            @click="activeNamespace = namespace"
          >
            <span
              class="settings-nav-item__icon"
              aria-hidden="true"
            >{{ namespaceIcon(namespace) }}</span>
            <span class="min-w-0">
              <span class="block text-sm font-medium text-[color:var(--text-primary)]">
                {{ namespaceLabel(namespace) }}
              </span>
              <span class="block text-xs text-[color:var(--text-dim)] mt-0.5">
                {{ namespaceHint(namespace) }}
              </span>
            </span>
          </button>
        </nav>

        <SettingsSectionShell
          v-if="activePayload"
          :title="namespaceLabel(activeNamespace)"
          :description="namespaceDescription(activeNamespace)"
          :icon="namespaceIcon(activeNamespace)"
          test-id="system-settings-active-card"
        >
          <AuthorityFieldCatalogForm
            v-if="usesSectionedForm"
            v-model="draft"
            :sections="activeSections"
          />

          <CommandTemplatesSettingsForm
            v-else-if="usesCommandTemplatesForm"
            v-model="commandTemplatesDraft"
            :fields="activeFields"
          />

          <div
            v-else
            class="grid gap-3 md:grid-cols-2"
          >
            <SettingsFieldCard
              v-for="field in activeFields"
              :key="field.path"
              :label="field.label"
              :description="field.description"
              :help="field.help"
              :test-id="`system-settings-field-card-${field.path}`"
              :help-test-id="`system-settings-field-help-${field.path}`"
              :show-description="field.type !== 'boolean'"
            >
              <label
                v-if="field.type === 'boolean'"
                class="flex items-center gap-2 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] px-3 py-2.5 text-sm"
              >
                <input
                  v-model="draft[field.path]"
                  type="checkbox"
                />
                <span class="text-[color:var(--text-primary)]">{{ field.description }}</span>
              </label>
              <textarea
                v-else-if="field.type === 'json'"
                v-model="draft[field.path]"
                rows="8"
                class="input-field w-full font-mono text-xs"
              />
              <input
                v-else
                v-model="draft[field.path]"
                :type="field.type === 'string' ? 'text' : 'number'"
                :step="field.step ?? (field.type === 'integer' ? 1 : 'any')"
                :min="field.min"
                :max="field.max"
                class="input-field w-full"
              />
            </SettingsFieldCard>
          </div>

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
import AuthorityFieldCatalogForm from '@/Components/Settings/AuthorityFieldCatalogForm.vue'
import CommandTemplatesSettingsForm from '@/Components/Settings/CommandTemplatesSettingsForm.vue'
import SettingsFieldCard from '@/Components/Settings/SettingsFieldCard.vue'
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

const SECTIONED_NAMESPACES = new Set(['observability_thresholds'])
const COMMAND_TEMPLATES_NAMESPACE = 'automation_command_templates'

type DraftScalar = string | number | boolean | undefined
type DraftValue = DraftScalar | AutomationCommandTemplateStep[]
type SettingsDraft = Record<string, DraftValue>

const SYSTEM_NAMESPACE_MAP: Record<string, string> = {
  automation_defaults: 'system.automation_defaults',
  automation_command_templates: 'system.command_templates',
  process_calibration_defaults: 'system.process_calibration_defaults',
  pump_calibration: 'system.pump_calibration_policy',
  sensor_calibration: 'system.sensor_calibration_policy',
  observability_thresholds: 'system.observability_thresholds',
}

const NAMESPACE_LABELS: Record<string, string> = {
  automation_defaults: 'Дефолты автоматики',
  automation_command_templates: 'Шаблоны команд',
  process_calibration_defaults: 'Калибровка процессов',
  pump_calibration: 'Калибровка насосов',
  sensor_calibration: 'Калибровка сенсоров',
  observability_thresholds: 'Пороги observability',
}

const NAMESPACE_HINTS: Record<string, string> = {
  automation_defaults: 'Климат, вода, свет',
  automation_command_templates: 'Relay workflow',
  process_calibration_defaults: 'Process UI',
  pump_calibration: 'Насосы и дозы',
  sensor_calibration: 'pH / EC эталоны',
  observability_thresholds: 'Hints AE3 / Laravel',
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
  automation_defaults: 'Системные дефолты для мастера автоматики: климат, вода, освещение.',
  automation_command_templates: 'Последовательности set_relay для two-tank workflow.',
  process_calibration_defaults: 'Стартовые коэффициенты process calibration UI.',
  pump_calibration: 'Лимиты и качество калибровки насосов.',
  sensor_calibration: 'Эталоны и пороги для мастера калибровки сенсоров.',
  observability_thresholds: 'Пороги diagnostic hints для AE3 и stale fallback Laravel.',
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
const activePayload = computed(() => payloads.value[activeNamespace.value] || null)
const activeSections = computed<SystemSettingsSection[]>(() => activePayload.value?.meta.field_catalog ?? [])
const activeFields = computed<SystemSettingsField[]>(() => activeSections.value.flatMap((section) => section.fields))
const usesSectionedForm = computed(() => SECTIONED_NAMESPACES.has(activeNamespace.value))
const usesCommandTemplatesForm = computed(() => activeNamespace.value === COMMAND_TEMPLATES_NAMESPACE)

function namespaceLabel(namespace: string): string {
  return NAMESPACE_LABELS[namespace] ?? namespace
}

function namespaceHint(namespace: string): string {
  return NAMESPACE_HINTS[namespace] ?? 'Системный namespace'
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
    return normalizeAutomationCommandTemplates(commandTemplatesDraft.value)
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
