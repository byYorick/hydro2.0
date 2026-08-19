<template>
  <AppLayout>
    <div class="space-y-4">
      <header class="ui-hero p-4 space-y-3">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div class="min-w-0">
            <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
              аккаунт и платформа
            </p>
            <h1 class="text-xl font-semibold tracking-tight text-[color:var(--text-primary)] mt-0.5">
              Настройки
            </h1>
            <p class="text-sm text-[color:var(--text-muted)] max-w-2xl mt-0.5">
              Мой профиль, уведомления и параметры платформы по вашей роли.
            </p>
          </div>
          <div class="flex items-center gap-2.5 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]/80 px-3 py-2 shrink-0">
            <div
              class="flex h-9 w-9 items-center justify-center rounded-full bg-[color:var(--accent-green)]/15 text-sm font-semibold text-[color:var(--accent-green)]"
              aria-hidden="true"
            >
              {{ profileInitial }}
            </div>
            <div class="min-w-0">
              <div class="truncate text-sm font-medium text-[color:var(--text-primary)]">
                {{ currentUser?.name }}
              </div>
              <div class="truncate text-xs text-[color:var(--text-dim)]">
                {{ currentUser?.email }}
              </div>
            </div>
            <Badge :variant="roleBadgeVariant">
              {{ translateRole(currentUser?.role) }}
            </Badge>
          </div>
        </div>

        <div
          class="settings-kpi-strip"
          data-testid="settings-kpi-strip"
        >
          <div
            class="settings-kpi-chip"
            title="Права в интерфейсе"
          >
            <span class="settings-kpi-chip__label">Роль</span>
            <span class="settings-kpi-chip__value">{{ translateRole(currentUser?.role) }}</span>
          </div>
          <div
            class="settings-kpi-chip"
            title="Личная настройка тостов"
          >
            <span class="settings-kpi-chip__label">Подавление алертов</span>
            <span class="settings-kpi-chip__value">{{ notificationSettings.alertToastSuppressionSec }} с</span>
          </div>
          <div
            v-if="canEditAutomationEngineSettings"
            class="settings-kpi-chip"
            title="Снимок scheduler / engine"
          >
            <span class="settings-kpi-chip__label">Снимок AE</span>
            <span class="settings-kpi-chip__value settings-kpi-chip__value--sm">{{ automationEngineSettingsGeneratedAtLabel }}</span>
          </div>
          <div
            v-if="canEditAutomationEngineSettings"
            class="settings-kpi-chip"
            title="Политика auto-resolve"
          >
            <span class="settings-kpi-chip__label">Политики алертов</span>
            <span class="settings-kpi-chip__value settings-kpi-chip__value--sm">{{ alertPolicyModeLabel }}</span>
          </div>
        </div>
      </header>

      <div class="space-y-4">
        <div
          class="surface-card border border-[color:var(--border-muted)] rounded-xl p-1.5"
          data-testid="settings-section-nav"
        >
          <Tabs
            v-model="activeSection"
            :tabs="settingsTabs"
            aria-label="Разделы настроек"
          />
        </div>

        <div class="space-y-4 min-w-0">
          <SettingsProfilePanel
            v-show="activeSection === 'profile'"
            :name="currentUser?.name"
            :email="currentUser?.email"
            :role-label="translateRole(currentUser?.role)"
            :role-badge-variant="roleBadgeVariant"
          />

          <SettingsSectionShell
            v-show="activeSection === 'notifications'"
            title="Уведомления"
            description="Персональные параметры отображения алертов в интерфейсе оператора."
            icon="🔔"
            test-id="settings-section-notifications"
          >
            <div class="max-w-xl space-y-4">
              <SettingsFieldCard
                label="Окно подавления повторов алертов"
                description="Одинаковые тосты на странице алертов не будут показываться чаще указанного интервала."
                :show-description="true"
                test-id="settings-notifications-suppression-card"
              >
                <div class="flex items-center gap-2">
                  <input
                    v-model.number="notificationSettings.alertToastSuppressionSec"
                    type="number"
                    min="0"
                    max="600"
                    step="5"
                    class="input-field w-28"
                    data-testid="settings-alert-suppression-input"
                  />
                  <span class="text-sm text-[color:var(--text-muted)]">секунд</span>
                </div>
              </SettingsFieldCard>
              <div class="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  :disabled="preferencesLoading || preferencesSaving"
                  @click="savePreferences"
                >
                  {{ preferencesSaving ? 'Сохраняем...' : 'Сохранить' }}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  :disabled="preferencesLoading || preferencesSaving"
                  @click="loadPreferences"
                >
                  {{ preferencesLoading ? 'Загружаем...' : 'Обновить' }}
                </Button>
              </div>
            </div>
          </SettingsSectionShell>

          <template v-if="canEditAutomationEngineSettings">
            <SettingsSectionShell
              v-show="activeSection === 'automation'"
              title="Automation Engine"
              description="Глобальные runtime-параметры Laravel scheduler и интеграции с automation-engine."
              icon="⚙️"
              test-id="settings-automation-engine-card"
            >
              <template #actions>
                <Button
                  size="sm"
                  data-testid="settings-automation-engine-save"
                  :disabled="automationSettingsSaving || automationSettingsLoading || automationSettingsResetting"
                  @click="saveAutomationEngineSettings"
                >
                  {{ automationSettingsSaving ? 'Сохраняем...' : 'Сохранить' }}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  data-testid="settings-automation-engine-refresh"
                  :disabled="automationSettingsSaving || automationSettingsLoading || automationSettingsResetting"
                  @click="loadAutomationEngineSettings"
                >
                  {{ automationSettingsLoading ? 'Обновляем...' : 'Обновить' }}
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  data-testid="settings-automation-engine-reset"
                  :disabled="automationSettingsSaving || automationSettingsLoading || automationSettingsResetting"
                  @click="resetConfirmOpen = true"
                >
                  {{ automationSettingsResetting ? 'Сбрасываем...' : 'Сбросить' }}
                </Button>
              </template>

              <div
                v-if="automationEngineSettingsSections.length === 0"
                class="text-sm text-[color:var(--text-dim)]"
              >
                Параметры runtime пока не загружены.
              </div>

              <div
                v-else
                class="space-y-3"
              >
                <section
                  v-for="section in automationEngineSettingsSections"
                  :key="section.key"
                  class="settings-group-card"
                >
                  <div class="settings-group-card__toggle cursor-default">
                    <h3 class="text-sm font-semibold text-[color:var(--text-primary)]">
                      {{ section.title }}
                    </h3>
                  </div>
                  <div class="settings-group-card__body">
                    <div class="settings-fields-stack">
                      <SettingsFieldCard
                        v-for="item in section.items"
                        :key="`${section.key}-${item.key}`"
                        :label="item.label"
                        :description="item.description"
                        :show-description="false"
                        :test-id="`settings-automation-field-${item.key}`"
                      >
                        <template v-if="item.editable">
                          <select
                            v-if="item.input_type === 'boolean'"
                            v-model="automationSettingsDraft[item.key]"
                            :data-testid="`settings-automation-engine-input-${item.key}`"
                            class="input-select w-full"
                          >
                            <option :value="true">
                              true
                            </option>
                            <option :value="false">
                              false
                            </option>
                          </select>
                          <select
                            v-else-if="item.input_type === 'select'"
                            v-model="automationSettingsDraft[item.key]"
                            :data-testid="`settings-automation-engine-input-${item.key}`"
                            class="input-select w-full"
                          >
                            <option
                              v-for="option in item.options || []"
                              :key="`${item.key}-option-${option}`"
                              :value="option"
                            >
                              {{ option }}
                            </option>
                          </select>
                          <input
                            v-else-if="item.input_type === 'number'"
                            v-model="automationSettingsDraft[item.key]"
                            :data-testid="`settings-automation-engine-input-${item.key}`"
                            class="input-field w-full font-mono text-sm"
                            type="number"
                            :step="item.step || 1"
                            :min="item.min"
                            :max="item.max"
                          />
                          <input
                            v-else
                            v-model="automationSettingsDraft[item.key]"
                            :data-testid="`settings-automation-engine-input-${item.key}`"
                            class="input-field w-full font-mono text-sm"
                            type="text"
                          />
                        </template>
                        <template v-else>
                          <div class="font-mono text-sm text-[color:var(--text-primary)] break-all">
                            {{ formatAutomationSettingValue(item.value, item.unit) }}
                          </div>
                        </template>
                        <template #meta>
                          source: {{ item.source || 'default' }}
                        </template>
                      </SettingsFieldCard>
                    </div>
                  </div>
                </section>
              </div>
            </SettingsSectionShell>

            <SettingsSectionShell
              v-show="activeSection === 'automation'"
              title="AE3 Alert Policies"
              description="Управляет auto-resolve для operational alerts с формализованным recovery contract."
              icon="🛡️"
              test-id="settings-alert-policies-card"
            >
              <template #actions>
                <span class="text-xs text-[color:var(--text-muted)] px-2 py-1 rounded-lg bg-[color:var(--bg-elevated)] border border-[color:var(--border-muted)]">
                  {{ alertPolicyModeLabel }}
                </span>
              </template>

              <div class="max-w-2xl settings-fields-stack">
                <SettingsFieldCard
                  label="Политика закрытия AE3 operational alerts"
                  description="Даже в режиме автозакрытия manual-only alerts остаются активными, пока для них нет формализованного recovery contract."
                  :show-description="false"
                  test-id="settings-alert-policy-card"
                >
                  <select
                    v-model="alertPolicyDraft.ae3_operational_resolution_mode"
                    data-testid="settings-alert-policy-input-ae3-operational-resolution-mode"
                    class="input-select w-full"
                  >
                    <option value="manual_ack">
                      Только ручное подтверждение
                    </option>
                    <option value="auto_resolve_on_recovery">
                      Автозакрытие после recovery
                    </option>
                  </select>
                </SettingsFieldCard>
                <div class="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    data-testid="settings-alert-policy-save"
                    :disabled="alertPoliciesLoading || alertPoliciesSaving || alertPoliciesResetting"
                    @click="saveAlertPolicies"
                  >
                    {{ alertPoliciesSaving ? 'Сохраняем...' : 'Сохранить policy' }}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    data-testid="settings-alert-policy-refresh"
                    :disabled="alertPoliciesLoading || alertPoliciesSaving || alertPoliciesResetting"
                    @click="loadAlertPolicies"
                  >
                    {{ alertPoliciesLoading ? 'Обновляем...' : 'Обновить' }}
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    data-testid="settings-alert-policy-reset"
                    :disabled="alertPoliciesLoading || alertPoliciesSaving || alertPoliciesResetting"
                    @click="resetAlertPolicies"
                  >
                    {{ alertPoliciesResetting ? 'Сбрасываем...' : 'Сбросить' }}
                  </Button>
                </div>
              </div>
            </SettingsSectionShell>
          </template>

          <SettingsSystemAuthorityCard
            v-if="canManageSystem"
            v-show="activeSection === 'system'"
          />

        </div>
      </div>
    </div>

    <ConfirmModal
      :open="resetConfirmOpen"
      title="Сбросить параметры движка?"
      message="Сброс вернёт runtime-override AE3/scheduler к значениям env/config. Активные циклы не останавливаются сразу, но следующие тики и интервалы пойдут с дефолтами. Пользовательские профили зон не меняются."
      confirm-text="Сбросить"
      confirm-variant="danger"
      :loading="automationSettingsResetting"
      data-testid="settings-automation-engine-reset-confirm"
      @close="resetConfirmOpen = false"
      @confirm="confirmResetAutomationEngineSettings"
    />
  </AppLayout>
</template>

<script setup>
import { computed, reactive, ref, watch, onMounted } from 'vue'
import { usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import SettingsSectionShell from '@/Components/Settings/SettingsSectionShell.vue'
import SettingsFieldCard from '@/Components/Settings/SettingsFieldCard.vue'
import SettingsProfilePanel from '@/Components/Settings/SettingsProfilePanel.vue'
import SettingsSystemAuthorityCard from '@/Components/Settings/SettingsSystemAuthorityCard.vue'
import Tabs from '@/Components/Tabs.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import { translateRole } from '@/utils/i18n'
import { logger } from '@/utils/logger'
import { api } from '@/services/api'
import { useRole } from '@/composables/useRole'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import { useToast } from '@/composables/useToast'
import { ERROR_MESSAGES } from '@/constants/messages'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

const page = usePage()
const currentUser = computed(() => page.props.auth?.user)
const { canEditAutomationEngineSettings, canManageSystem } = useRole()

const profileInitial = computed(() => {
  const name = String(currentUser.value?.name || '?').trim()
  return name.charAt(0).toUpperCase()
})

const roleBadgeVariant = computed(() => {
  const role = currentUser.value?.role
  if (role === 'admin') return 'danger'
  if (role === 'operator') return 'warning'
  return 'info'
})

const sectionCatalog = [
  { id: 'profile', label: 'Мой профиль', hint: 'Имя, email, роль', icon: '👤' },
  { id: 'notifications', label: 'Уведомления', hint: 'Тосты и алерты', icon: '🔔' },
  { id: 'automation', label: 'Параметры движка', hint: 'AE3 и runtime', icon: '⚙️', requiresAutomation: true },
  { id: 'system', label: 'Настройки системы', hint: 'Authority платформы', icon: '📊', requiresSystem: true },
]

const visibleSections = computed(() => sectionCatalog.filter((section) => {
  if (section.requiresAutomation && !canEditAutomationEngineSettings.value) return false
  if (section.requiresSystem && !canManageSystem.value) return false
  return true
}))

/** Горизонтальные табы как на странице зоны (Components/Tabs). */
const settingsTabs = computed(() =>
  visibleSections.value.map((section) => ({
    id: section.id,
    label: section.label,
  })),
)

const activeSection = ref('profile')

watch(visibleSections, (sections) => {
  if (!sections.some((section) => section.id === activeSection.value)) {
    activeSection.value = sections[0]?.id || 'profile'
  }
}, { immediate: true })

const automationEngineSettingsState = ref(null)
const automationEngineSettingsSections = computed(() => {
  const sections = automationEngineSettingsState.value?.snapshot?.sections
  if (!Array.isArray(sections)) return []

  return sections.filter((section) => {
    return (
      section &&
      typeof section === 'object' &&
      typeof section.key === 'string' &&
      typeof section.title === 'string' &&
      Array.isArray(section.items)
    )
  })
})
const automationEngineSettingsGeneratedAtLabel = computed(() => {
  const raw = automationEngineSettingsState.value?.snapshot?.generated_at
  if (typeof raw !== 'string' || raw.trim() === '') return 'неизвестно'
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return raw
  return date.toLocaleString()
})
const editableAutomationSettingsItems = computed(() => {
  return automationEngineSettingsSections.value
    .flatMap((section) => (Array.isArray(section.items) ? section.items : []))
    .filter((item) => item && item.editable === true && typeof item.key === 'string')
})
const alertPoliciesState = ref(null)
const alertPolicyDraft = reactive({
  ae3_operational_resolution_mode: 'manual_ack',
})
const alertPolicyMode = computed(() => {
  const mode = alertPoliciesState.value?.payload?.ae3_operational_resolution_mode
  if (typeof mode === 'string' && mode.trim() !== '') {
    return mode
  }
  return 'manual_ack'
})
const alertPolicyModeLabel = computed(() => {
  return alertPolicyMode.value === 'auto_resolve_on_recovery'
    ? 'Автозакрытие после recovery'
    : 'Только ручное подтверждение'
})

const { showToast } = useToast()
const automationConfig = useAutomationConfig(showToast)

const preferencesLoading = ref(false)
const preferencesSaving = ref(false)
const automationSettingsLoading = ref(false)
const automationSettingsSaving = ref(false)
const automationSettingsResetting = ref(false)
const alertPoliciesLoading = ref(false)
const alertPoliciesSaving = ref(false)
const alertPoliciesResetting = ref(false)
const automationSettingsDraft = reactive({})

const notificationSettings = reactive({
  alertToastSuppressionSec: 30,
})

const formatAutomationSettingValue = (value, unit = null) => {
  if (value === null || value === undefined) return '—'
  const suffix = unit ? ` ${unit}` : ''
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '[]'
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value) + suffix
    } catch {
      return String(value) + suffix
    }
  }
  return String(value) + suffix
}

const extractApiError = (error, fallback) => {
  const details = error?.response?.data?.errors
  if (details && typeof details === 'object') {
    const first = Object.values(details).flat().find((msg) => typeof msg === 'string')
    if (typeof first === 'string' && first.trim() !== '') {
      return first
    }
  }

  return error?.response?.data?.message || error?.message || fallback
}

const resetAutomationSettingsDraft = () => {
  Object.keys(automationSettingsDraft).forEach((key) => delete automationSettingsDraft[key])
}

const hydrateAutomationSettingsDraft = () => {
  resetAutomationSettingsDraft()
  editableAutomationSettingsItems.value.forEach((item) => {
    automationSettingsDraft[item.key] = item.value
  })
}

const applyAutomationSettingsSnapshot = (snapshot) => {
  automationEngineSettingsState.value = snapshot || null
  hydrateAutomationSettingsDraft()
}

const applyAlertPoliciesSnapshot = (document) => {
  alertPoliciesState.value = document || null
  const mode = document?.payload?.ae3_operational_resolution_mode
  alertPolicyDraft.ae3_operational_resolution_mode =
    typeof mode === 'string' && mode.trim() !== ''
      ? mode
      : 'manual_ack'
}

const normalizeAutomationSettingDraftValue = (item, value) => {
  if (item.type === 'bool') {
    if (typeof value === 'boolean') return value
    const lowered = String(value).trim().toLowerCase()
    return ['1', 'true', 'yes', 'on'].includes(lowered)
  }

  if (item.type === 'int') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? Math.trunc(parsed) : Number(item.value ?? 0)
  }

  if (item.type === 'float') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : Number(item.value ?? 0)
  }

  return String(value ?? '').trim()
}

const buildAutomationSettingsPayload = () => {
  const payload = {}
  editableAutomationSettingsItems.value.forEach((item) => {
    payload[item.key] = normalizeAutomationSettingDraftValue(item, automationSettingsDraft[item.key])
  })
  return payload
}

const loadAutomationEngineSettings = async (options = {}) => {
  const silent = options.silent === true
  automationSettingsLoading.value = true
  try {
    const document = await automationConfig.getDocument('system', 0, 'system.runtime')
    applyAutomationSettingsSnapshot(document || null)
    if (!silent) {
      showToast('Параметры automation runtime обновлены', 'success', TOAST_TIMEOUT.NORMAL)
    }
  } catch (err) {
    logger.error('Failed to load automation runtime settings:', err)
    if (!silent) {
      showToast(
        `Ошибка загрузки runtime параметров: ${extractApiError(err, ERROR_MESSAGES.UNKNOWN)}`,
        'error',
        TOAST_TIMEOUT.LONG
      )
    }
  } finally {
    automationSettingsLoading.value = false
  }
}

const saveAutomationEngineSettings = async () => {
  automationSettingsSaving.value = true
  try {
    const document = await automationConfig.updateDocument(
      'system',
      0,
      'system.runtime',
      buildAutomationSettingsPayload()
    )
    applyAutomationSettingsSnapshot(document || null)
    showToast('Глобальные параметры автоматики сохранены и применены', 'success', TOAST_TIMEOUT.NORMAL)
  } catch (err) {
    logger.error('Failed to save automation runtime settings:', err)
    showToast(
      `Ошибка сохранения runtime параметров: ${extractApiError(err, ERROR_MESSAGES.UNKNOWN)}`,
      'error',
      TOAST_TIMEOUT.LONG
    )
  } finally {
    automationSettingsSaving.value = false
  }
}

const resetConfirmOpen = ref(false)

const confirmResetAutomationEngineSettings = async () => {
  await resetAutomationEngineSettings()
  resetConfirmOpen.value = false
}

const resetAutomationEngineSettings = async () => {
  automationSettingsResetting.value = true
  try {
    const document = await automationConfig.resetDocument('system', 0, 'system.runtime')
    applyAutomationSettingsSnapshot(document || null)
    showToast('Override параметры сброшены к значениям env/config', 'success', TOAST_TIMEOUT.NORMAL)
  } catch (err) {
    logger.error('Failed to reset automation runtime settings:', err)
    showToast(
      `Ошибка сброса runtime параметров: ${extractApiError(err, ERROR_MESSAGES.UNKNOWN)}`,
      'error',
      TOAST_TIMEOUT.LONG
    )
  } finally {
    automationSettingsResetting.value = false
  }
}

const loadAlertPolicies = async (options = {}) => {
  const silent = options.silent === true
  alertPoliciesLoading.value = true
  try {
    const document = await automationConfig.getDocument('system', 0, 'system.alert_policies')
    applyAlertPoliciesSnapshot(document || null)
    if (!silent) {
      showToast('Политики алертов обновлены', 'success', TOAST_TIMEOUT.NORMAL)
    }
  } catch (err) {
    logger.error('Failed to load alert policies:', err)
    if (!silent) {
      showToast(
        `Ошибка загрузки alert policy: ${extractApiError(err, ERROR_MESSAGES.UNKNOWN)}`,
        'error',
        TOAST_TIMEOUT.LONG
      )
    }
  } finally {
    alertPoliciesLoading.value = false
  }
}

const saveAlertPolicies = async () => {
  alertPoliciesSaving.value = true
  try {
    const document = await automationConfig.updateDocument(
      'system',
      0,
      'system.alert_policies',
      {
        ae3_operational_resolution_mode: alertPolicyDraft.ae3_operational_resolution_mode,
      }
    )
    applyAlertPoliciesSnapshot(document || null)
    showToast('Политика закрытия AE3 alerts сохранена', 'success', TOAST_TIMEOUT.NORMAL)
  } catch (err) {
    logger.error('Failed to save alert policies:', err)
    showToast(
      `Ошибка сохранения alert policy: ${extractApiError(err, ERROR_MESSAGES.UNKNOWN)}`,
      'error',
      TOAST_TIMEOUT.LONG
    )
  } finally {
    alertPoliciesSaving.value = false
  }
}

const resetAlertPolicies = async () => {
  alertPoliciesResetting.value = true
  try {
    const document = await automationConfig.resetDocument('system', 0, 'system.alert_policies')
    applyAlertPoliciesSnapshot(document || null)
    showToast('Политика закрытия AE3 alerts сброшена к default', 'success', TOAST_TIMEOUT.NORMAL)
  } catch (err) {
    logger.error('Failed to reset alert policies:', err)
    showToast(
      `Ошибка сброса alert policy: ${extractApiError(err, ERROR_MESSAGES.UNKNOWN)}`,
      'error',
      TOAST_TIMEOUT.LONG
    )
  } finally {
    alertPoliciesResetting.value = false
  }
}

const normalizeSuppressionSec = (value) => {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 30
  return Math.max(0, Math.min(600, Math.floor(parsed)))
}

const applyPreferences = (data) => {
  notificationSettings.alertToastSuppressionSec = normalizeSuppressionSec(
    data?.alert_toast_suppression_sec
  )
}

const loadPreferences = async () => {
  preferencesLoading.value = true
  try {
    const prefs = await api.settings.getPreferences()
    applyPreferences(prefs)
  } catch (err) {
    logger.error('Failed to load user preferences:', err)
    const errorMsg = err.response?.data?.message || err.message || ERROR_MESSAGES.UNKNOWN
    showToast(`Ошибка загрузки настроек: ${errorMsg}`, 'error', TOAST_TIMEOUT.LONG)
  } finally {
    preferencesLoading.value = false
  }
}

const savePreferences = async () => {
  const normalized = normalizeSuppressionSec(notificationSettings.alertToastSuppressionSec)
  notificationSettings.alertToastSuppressionSec = normalized
  preferencesSaving.value = true
  try {
    await api.settings.updatePreferences({
      alert_toast_suppression_sec: normalized,
    })
    applyPreferences({ alert_toast_suppression_sec: normalized })
    showToast('Настройки уведомлений сохранены', 'success', TOAST_TIMEOUT.NORMAL)
  } catch (err) {
    logger.error('Failed to save user preferences:', err)
    const errorMsg = err.response?.data?.message || err.message || ERROR_MESSAGES.UNKNOWN
    showToast(`Ошибка сохранения настроек: ${errorMsg}`, 'error', TOAST_TIMEOUT.LONG)
  } finally {
    preferencesSaving.value = false
  }
}

onMounted(() => {
  applyPreferences(currentUser.value?.preferences || null)
  loadPreferences()
  if (canEditAutomationEngineSettings.value) {
    void loadAutomationEngineSettings({ silent: true })
    void loadAlertPolicies({ silent: true })
  }
})
</script>
