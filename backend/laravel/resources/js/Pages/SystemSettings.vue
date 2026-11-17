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
            <span v-if="loading"> · {{ operationLabel }}</span>
          </p>
        </div>
      </header>

      <div class="space-y-4">
        <div
          class="surface-card border border-[color:var(--border-muted)] rounded-xl p-1.5"
          data-testid="system-settings-section-nav"
        >
          <Tabs
            :model-value="activeNamespace"
            :tabs="systemSettingsTabs"
            aria-label="Разделы системных настроек"
            @update:model-value="selectNamespace"
          />
        </div>

        <SettingsSectionShell
          v-if="activePayload"
          :title="namespaceLabel(activeNamespace)"
          :description="namespaceDescription(activeNamespace)"
          :icon="namespaceIcon(activeNamespace)"
          test-id="system-settings-active-card"
        >
          <fieldset
            :disabled="loading"
            class="m-0 min-w-0 border-0 p-0"
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
              :errors="fieldErrors"
            />
          </fieldset>

          <p
            v-if="formError"
            role="alert"
            data-testid="system-settings-error"
            class="text-sm text-status-critical"
          >
            {{ formError }}
          </p>
          <p
            v-if="dirtyCount"
            role="status"
            data-testid="system-settings-dirty-count"
            class="text-xs text-status-warning"
          >
            Несохранённых параметров: {{ dirtyCount }}
          </p>
          <template #footer>
            <Button
              size="sm"
              variant="secondary"
              :disabled="loading || !dirtyCount"
              data-testid="system-settings-discard"
              @click="discard"
            >
              Отменить изменения
            </Button>
            <Button
              size="sm"
              :disabled="!canSave"
              data-testid="system-settings-save"
              @click="save"
            >
              {{ loading ? operationLabel : 'Сохранить' }}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              :disabled="loading"
              data-testid="system-settings-reset"
              @click="reset"
            >
              Восстановить значения по умолчанию
            </Button>
          </template>
        </SettingsSectionShell>
        <SkeletonBlock
          v-else-if="loading"
          class="h-48 w-full"
        />
        <div
          v-else-if="formError"
          class="space-y-3"
        >
          <EmptyState
            title="Настройки не загружены"
            :description="formError"
          />
          <Button
            size="sm"
            @click="load"
          >
            Повторить загрузку
          </Button>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import EmptyState from '@/Components/EmptyState.vue'
import SkeletonBlock from '@/Components/SkeletonBlock.vue'
import { isSettingsFieldDirty, normalizeSettingsFieldValue, settingsFieldError } from '@/utils/settingsDraft'
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
  observability_thresholds: 'Когда предупреждать о слишком долгом ожидании. Эти пороги сами по себе не останавливают оборудование.',
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
const operation = ref<'loading' | 'saving' | 'resetting' | null>(null)
const operationLabel = computed(() => operation.value === 'loading' ? 'Загрузка настроек…' : operation.value === 'resetting' ? 'Восстановление настроек…' : 'Сохранение настроек…')
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
const formError = ref<string | null>(null)
const fieldErrors = computed<Record<string, string>>(() => usesCommandTemplatesForm.value ? {} : Object.fromEntries(
  activeFields.value.flatMap(field => {
    const error = settingsFieldError(field, draft.value[field.path])
    return error ? [[field.path, error]] : []
  }),
))
const dirtyCount = computed(() => {
  const savedPayload = activePayload.value
  if (!savedPayload) return 0
  if (usesCommandTemplatesForm.value) {
    const saved = normalizeAutomationCommandTemplates(savedPayload.config as Partial<Record<string, AutomationCommandTemplateStep[]>>)
    const edited = normalizeAutomationCommandTemplates(commandTemplatesDraft.value)
    return activeFields.value.filter(field => JSON.stringify(saved[field.path as keyof typeof saved]) !== JSON.stringify(edited[field.path as keyof typeof edited])).length
  }
  return activeFields.value.filter(field => isSettingsFieldDirty(field, draft.value[field.path], savedPayload.config[field.path])).length
})
const canSave = computed(() => !loading.value && dirtyCount.value > 0 && !Object.keys(fieldErrors.value).length)

function discard() {
  syncDraft()
  formError.value = null
}
function selectNamespace(value: string) {
  if (loading.value || value === activeNamespace.value) return
  if (dirtyCount.value && !window.confirm('Изменения этого раздела не сохранены. Перейти в другой раздел и отменить правки?')) return
  activeNamespace.value = value
}
function reportError(cause: unknown, fallback: string) {
  const data = (cause as { response?: { data?: { message?: string; errors?: Record<string, string[]> } } })?.response?.data
  formError.value = (data?.errors && Object.values(data.errors).flat()[0]) || data?.message || (cause instanceof Error ? cause.message : fallback)
  showToast(formError.value, 'error')
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (!dirtyCount.value) return
  event.preventDefault()
  event.returnValue = ''
}
function beforeVisit(event: Event) {
  if (dirtyCount.value && !window.confirm('Изменения системных настроек не сохранены. Покинуть страницу?')) event.preventDefault()
}


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

  return Object.fromEntries(activeFields.value.map(field => [field.path, normalizeSettingsFieldValue(field, draft.value[field.path])]))
}

async function load(): Promise<void> {
  operation.value = 'loading'
  loading.value = true
  formError.value = null
  try {
    const entries = await Promise.all(
      Object.entries(SYSTEM_NAMESPACE_MAP).map(async ([legacyNamespace, authorityNamespace]) => {
        const document = await automationConfig.getDocument<Record<string, unknown>, NonNullable<SystemAuthorityMeta>>('system', 0, authorityNamespace)
        return [legacyNamespace, documentToPayload(legacyNamespace, document)] as const
      })
    )

    payloads.value = Object.fromEntries(entries) as Record<string, SettingsNamespacePayload>
    syncDraft()
  } catch (error) {
    reportError(error, 'Не удалось загрузить настройки. Повторите попытку.')
  } finally { loading.value = false; operation.value = null }
}

async function save(): Promise<void> {
  if (!canSave.value) return
  operation.value = 'saving'
  loading.value = true
  formError.value = null
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
    reportError(error, 'Не удалось сохранить настройки')
  } finally {
    loading.value = false
    operation.value = null
  }
}

async function reset(): Promise<void> {
  if (loading.value || !window.confirm('Восстановить значения по умолчанию для раздела «' + namespaceLabel(activeNamespace.value) + '»? Сохранённые настройки этого раздела будут заменены.')) return
  operation.value = 'resetting'
  loading.value = true
  formError.value = null
  try {
    const authorityNamespace = SYSTEM_NAMESPACE_MAP[activeNamespace.value] ?? activeNamespace.value
    const document = await automationConfig.resetDocument<Record<string, unknown>, NonNullable<SystemAuthorityMeta>>('system', 0, authorityNamespace)
    payloads.value[activeNamespace.value] = documentToPayload(activeNamespace.value, document)
    syncDraft()
    showToast('Настройки сброшены', 'success')
  } catch (error) {
    reportError(error, 'Не удалось восстановить настройки')
  } finally {
    loading.value = false
    operation.value = null
  }
}

watch(activeNamespace, () => {
  formError.value = null
  syncDraft()
})

onMounted(() => {
  window.addEventListener('beforeunload', beforeUnload)
  document.addEventListener('inertia:before', beforeVisit)
  void load()
})
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
  document.removeEventListener('inertia:before', beforeVisit)
})
</script>
