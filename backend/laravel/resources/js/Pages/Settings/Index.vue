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
              class="flex h-9 w-9 items-center justify-center rounded-full bg-[color:var(--status-ok)]/15 text-sm font-semibold text-[color:var(--status-ok)]"
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
            <div class="settings-rows max-w-xl">
              <SettingsFieldRow
                label="Не повторять одинаковые тревоги чаще"
                description="Одинаковые тосты на странице тревог не будут показываться чаще указанного интервала."
                unit="сек"
                field-id="settings-alert-suppression-input"
                test-id="settings-notifications-suppression-card"
              >
                <TextField
                  id="settings-alert-suppression-input"
                  v-model.number="notificationSettings.alertToastSuppressionSec"
                  type="number"
                  min="0"
                  max="600"
                  step="5"
                  data-testid="settings-alert-suppression-input"
                  input-class="settings-control--num text-right"
                />
              </SettingsFieldRow>
            </div>
            <template #footer>
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
            </template>
          </SettingsSectionShell>

          <template v-if="canEditAutomationEngineSettings">
            <SettingsSectionShell
              v-show="activeSection === 'automation'"
              title="Планировщик задач и AE3"
              description="Общие параметры запуска задач, связи с движком и восстановления расписаний. Настройки раствора и PID находятся на странице зоны."
              icon="⚙️"
              test-id="settings-automation-engine-card"
            >
              <template #actions>
                <Button
                  size="sm"
                  data-testid="settings-automation-engine-save"
                  :disabled="!canSaveAutomationSettings"
                  @click="saveAutomationEngineSettings"
                >
                  {{ automationSettingsSaving ? 'Сохраняем...' : automationSettingsDirtyCount ? `Сохранить (${automationSettingsDirtyCount})` : 'Сохранить' }}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  data-testid="settings-automation-engine-refresh"
                  :disabled="automationSettingsBusy || automationSettingsDirtyCount > 0"
                  @click="loadAutomationEngineSettings"
                >
                  {{ automationSettingsLoading ? 'Обновляем...' : 'Обновить' }}
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  data-testid="settings-automation-engine-reset"
                  :disabled="automationSettingsBusy"
                  @click="resetConfirmOpen = true"
                >
                  {{ automationSettingsResetting ? 'Сбрасываем...' : 'Сбросить' }}
                </Button>
              </template>

              <p class="mb-3 text-sm text-[color:var(--text-muted)]">
                Сохранение не запускает задачи. Новые параметры учитываются следующими запусками планировщика;
                параметры уже выполняющейся задачи не пересчитываются.
              </p>
              <p v-if="automationSettingsError" role="alert" class="mb-3 text-sm text-status-critical">{{ automationSettingsError }}</p>
              <div v-if="automationSettingsDirtyCount" class="mb-3 flex flex-wrap items-center gap-3 rounded-xl border border-[color:var(--status-warning)] p-3" role="status">
                <span class="text-sm">Несохранённых изменений: {{ automationSettingsDirtyCount }}</span>
                <Button size="sm" variant="ghost" :disabled="automationSettingsBusy" data-testid="settings-automation-engine-discard" @click="discardAutomationSettings">Отменить изменения</Button>
              </div>
              <div
                v-if="automationEngineSettingsSections.length === 0"
                class="text-sm text-[color:var(--text-dim)]"
              >
                Параметры runtime пока не загружены.
              </div>

              <AutomationRuntimeFieldsForm
                v-else
                v-model="automationSettingsDraft"
                :sections="automationEngineSettingsSections"
                :errors="automationSettingsErrors"
                :disabled="automationSettingsBusy"
              />
            </SettingsSectionShell>

            <SettingsSectionShell
              v-show="activeSection === 'automation'"
              title="Закрытие тревог автоматики"
              description="Закрывать ли тревоги автоматически, когда причина устранена, или всегда требовать подтверждения оператора."
              icon="🛡️"
              test-id="settings-alert-policies-card"
            >
              <div class="settings-rows max-w-xl">
                <SettingsFieldRow
                  label="Как закрывать тревоги"
                  description="Даже в режиме автозакрытия тревоги, требующие ручной проверки, остаются активными до подтверждения оператором."
                  field-id="settings-alert-policy-input"
                  test-id="settings-alert-policy-card"
                >
                  <SelectField
                    id="settings-alert-policy-input"
                    v-model="alertPolicyDraft.ae3_operational_resolution_mode"
                    data-testid="settings-alert-policy-input-ae3-operational-resolution-mode"
                    input-class="settings-control--select"
                  >
                    <option value="manual_ack">
                      Только вручную
                    </option>
                    <option value="auto_resolve_on_recovery">
                      Автоматически, когда причина устранена
                    </option>
                  </SelectField>
                </SettingsFieldRow>
              </div>
              <template #footer>
                <Button
                  size="sm"
                  data-testid="settings-alert-policy-save"
                  :disabled="alertPoliciesLoading || alertPoliciesSaving || alertPoliciesResetting"
                  @click="saveAlertPolicies"
                >
                  {{ alertPoliciesSaving ? 'Сохраняем...' : 'Сохранить' }}
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
              </template>
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
import SelectField from '@/Components/SelectField.vue'

import TextField from '@/Components/TextField.vue'

import { computed, reactive, ref, watch, onMounted } from 'vue'
import { usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import SettingsSectionShell from '@/Components/Settings/SettingsSectionShell.vue'
import SettingsFieldRow from '@/Components/Settings/SettingsFieldRow.vue'
import AutomationRuntimeFieldsForm from '@/Components/Settings/AutomationRuntimeFieldsForm.vue'
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
import { useAutomationRuntimeSettings } from '@/composables/useAutomationRuntimeSettings'
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

const alertPoliciesState = ref(null)
const alertPolicyDraft = reactive({
  ae3_operational_resolution_mode: 'manual_ack',
})

const { showToast } = useToast()
const automationConfig = useAutomationConfig(showToast)

const preferencesLoading = ref(false)
const preferencesSaving = ref(false)
const alertPoliciesLoading = ref(false)
const alertPoliciesSaving = ref(false)
const alertPoliciesResetting = ref(false)

const notificationSettings = reactive({
  alertToastSuppressionSec: 30,
})

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

const applyAlertPoliciesSnapshot = (document) => {
  alertPoliciesState.value = document || null
  const mode = document?.payload?.ae3_operational_resolution_mode
  alertPolicyDraft.ae3_operational_resolution_mode =
    typeof mode === 'string' && mode.trim() !== ''
      ? mode
      : 'manual_ack'
}

const runtimeSettings = useAutomationRuntimeSettings(showToast)
const {
  sections: automationEngineSettingsSections,
  draft: automationSettingsDraft,
  loading: automationSettingsLoading,
  saving: automationSettingsSaving,
  resetting: automationSettingsResetting,
  busy: automationSettingsBusy,
  dirtyCount: automationSettingsDirtyCount,
  canSave: canSaveAutomationSettings,
  errors: automationSettingsErrors,
  error: automationSettingsError,
  load: loadAutomationEngineSettings,
  save: saveAutomationEngineSettings,
  discard: discardAutomationSettings,
} = runtimeSettings
const resetConfirmOpen = ref(false)
const confirmResetAutomationEngineSettings = async () => {
  if (await runtimeSettings.reset()) resetConfirmOpen.value = false
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
