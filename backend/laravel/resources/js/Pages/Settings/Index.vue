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
              Профиль, уведомления, параметры automation-engine и управление пользователями.
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
            <span class="settings-kpi-chip__label">Runtime AE</span>
            <span class="settings-kpi-chip__value settings-kpi-chip__value--sm">{{ automationEngineSettingsGeneratedAtLabel }}</span>
          </div>
          <div
            v-if="canEditAutomationEngineSettings"
            class="settings-kpi-chip"
            title="Политика auto-resolve"
          >
            <span class="settings-kpi-chip__label">AE3 alerts</span>
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
          <SettingsSectionShell
            v-show="activeSection === 'profile'"
            title="Профиль"
            description="Основные данные вашей учётной записи. Редактирование имени и email — через администратора."
            icon="👤"
            test-id="settings-section-profile"
          >
            <dl class="grid gap-3 sm:grid-cols-2">
              <div class="settings-field-card">
                <dt class="settings-field-card__label">
                  Имя
                </dt>
                <dd class="mt-2 text-sm font-medium text-[color:var(--text-primary)]">
                  {{ currentUser?.name }}
                </dd>
              </div>
              <div class="settings-field-card">
                <dt class="settings-field-card__label">
                  Email
                </dt>
                <dd class="mt-2 text-sm font-medium text-[color:var(--text-primary)] break-all">
                  {{ currentUser?.email }}
                </dd>
              </div>
              <div class="settings-field-card sm:col-span-2">
                <dt class="settings-field-card__label">
                  Роль в системе
                </dt>
                <dd class="mt-2">
                  <Badge :variant="roleBadgeVariant">
                    {{ translateRole(currentUser?.role) }}
                  </Badge>
                </dd>
              </div>
            </dl>
          </SettingsSectionShell>

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
                  @click="resetAutomationEngineSettings"
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

            <SettingsSectionShell
              v-show="activeSection === 'automation'"
              title="Системные настройки автоматики"
              description="Калибровки, дефолты автоматики, шаблоны команд и пороги observability — отдельная страница authority."
              icon="📊"
              test-id="settings-system-authority-card"
            >
              <Link href="/system/settings">
                <Button
                  size="sm"
                  variant="secondary"
                  data-testid="settings-open-system-authority"
                >
                  Открыть системные настройки →
                </Button>
              </Link>
            </SettingsSectionShell>
          </template>

          <SettingsSectionShell
            v-if="isAdmin"
            v-show="activeSection === 'users'"
            title="Управление пользователями"
            description="Создание учётных записей и назначение ролей операторов платформы."
            icon="👥"
            test-id="settings-section-users"
          >
            <template #actions>
              <Button
                size="sm"
                variant="secondary"
                @click="loadUsers"
              >
                Обновить
              </Button>
              <Button
                size="sm"
                @click="openCreateModal()"
              >
                Создать пользователя
              </Button>
            </template>

            <div class="mb-4 flex flex-wrap items-center gap-2">
              <input
                v-model="searchQuery"
                placeholder="Поиск по имени или email..."
                class="input-field w-full sm:w-72"
                autocomplete="off"
              />
              <select
                v-model="roleFilter"
                class="input-select"
              >
                <option value="">
                  Все роли
                </option>
                <option value="admin">
                  Администратор
                </option>
                <option value="operator">
                  Оператор
                </option>
                <option value="viewer">
                  Наблюдатель
                </option>
              </select>
            </div>

            <div class="settings-group-card overflow-hidden">
              <div class="max-h-[560px] overflow-auto">
                <table class="min-w-full text-sm">
                  <thead class="sticky top-0 z-10 bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]">
                    <tr>
                      <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">
                        Пользователь
                      </th>
                      <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">
                        Роль
                      </th>
                      <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)] hidden md:table-cell">
                        Создан
                      </th>
                      <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">
                        Действия
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="u in paginatedUsers"
                      :key="u.id"
                      class="odd:bg-[color:var(--bg-surface-strong)] even:bg-[color:var(--bg-surface)]"
                    >
                      <td class="px-3 py-3 border-b border-[color:var(--border-muted)]">
                        <div class="font-medium text-[color:var(--text-primary)]">
                          {{ u.name }}
                        </div>
                        <div class="text-xs text-[color:var(--text-dim)]">
                          {{ u.email }}
                        </div>
                      </td>
                      <td class="px-3 py-3 border-b border-[color:var(--border-muted)]">
                        <Badge :variant="userRoleBadgeVariant(u.role)">
                          {{ translateRole(u.role) }}
                        </Badge>
                      </td>
                      <td class="px-3 py-3 border-b border-[color:var(--border-muted)] text-xs text-[color:var(--text-muted)] hidden md:table-cell">
                        {{ new Date(u.created_at).toLocaleDateString() }}
                      </td>
                      <td class="px-3 py-3 border-b border-[color:var(--border-muted)]">
                        <div class="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            variant="secondary"
                            @click="editUser(u)"
                          >
                            Изменить
                          </Button>
                          <Button
                            size="sm"
                            variant="danger"
                            :disabled="u.id === currentUserId"
                            @click="confirmDelete(u)"
                          >
                            Удалить
                          </Button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
                <div
                  v-if="!paginatedUsers.length"
                  class="text-sm text-[color:var(--text-dim)] px-3 py-10 text-center"
                >
                  Нет пользователей по выбранным фильтрам
                </div>
              </div>
              <div class="border-t border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-3 py-2">
                <Pagination
                  v-model:current-page="currentPage"
                  v-model:per-page="perPage"
                  :total="filteredUsers.length"
                />
              </div>
            </div>
          </SettingsSectionShell>
        </div>
      </div>
    </div>

    <Modal
      :open="showCreateModal || editingUser !== null"
      title="Пользователь"
      @close="closeModal"
    >
      <div class="space-y-3">
        <div>
          <label class="text-sm text-[color:var(--text-muted)]">Имя</label>
          <input
            v-model="userForm.name"
            class="input-field mt-1"
            autocomplete="name"
          />
        </div>
        <div>
          <label class="text-sm text-[color:var(--text-muted)]">Email</label>
          <input
            v-model="userForm.email"
            type="email"
            class="input-field mt-1"
            autocomplete="email"
          />
        </div>
        <div>
          <label
            for="user-form-password"
            class="text-sm text-[color:var(--text-muted)]"
          >Пароль</label>
          <input
            id="user-form-password"
            v-model="userForm.password"
            name="password"
            type="password"
            class="input-field mt-1"
            :placeholder="editingUser ? 'Оставьте пустым, чтобы не менять' : ''"
            :autocomplete="editingUser ? 'new-password' : 'new-password'"
          />
        </div>
        <div>
          <label
            for="user-form-role"
            class="text-sm text-[color:var(--text-muted)]"
          >Роль</label>
          <select
            id="user-form-role"
            v-model="userForm.role"
            name="role"
            class="input-select mt-1"
          >
            <option value="viewer">
              Наблюдатель
            </option>
            <option value="operator">
              Оператор
            </option>
            <option value="admin">
              Администратор
            </option>
          </select>
        </div>
      </div>
      <template #footer>
        <Button
          size="sm"
          variant="secondary"
          @click="closeModal"
        >
          Отмена
        </Button>
        <Button
          size="sm"
          @click="saveUser"
        >
          Сохранить
        </Button>
      </template>
    </Modal>

    <Modal
      :open="deletingUser !== null"
      title="Удалить пользователя?"
      @close="deletingUser = null"
    >
      <div class="text-sm text-[color:var(--text-muted)]">
        Вы уверены, что хотите удалить пользователя <strong>{{ deletingUser?.name }}</strong>?
      </div>
      <template #footer>
        <Button
          size="sm"
          variant="secondary"
          @click="deletingUser = null"
        >
          Отмена
        </Button>
        <Button
          size="sm"
          variant="danger"
          @click="doDelete"
        >
          Удалить
        </Button>
      </template>
    </Modal>
  </AppLayout>
</template>

<script setup>
import { computed, reactive, ref, watch, onMounted } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import SettingsSectionShell from '@/Components/Settings/SettingsSectionShell.vue'
import SettingsFieldCard from '@/Components/Settings/SettingsFieldCard.vue'
import Tabs from '@/Components/Tabs.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import Modal from '@/Components/Modal.vue'
import Pagination from '@/Components/Pagination.vue'
import { translateRole } from '@/utils/i18n'
import { logger } from '@/utils/logger'
import { api } from '@/services/api'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import { useToast } from '@/composables/useToast'
import { useSimpleModal } from '@/composables/useModal'
import { ERROR_MESSAGES } from '@/constants/messages'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

const page = usePage()
const currentUser = computed(() => page.props.auth?.user)
const currentUserId = computed(() => currentUser.value?.id)
const isAdmin = computed(() => currentUser.value?.role === 'admin')
const canEditAutomationEngineSettings = computed(() => {
  const role = String(currentUser.value?.role || 'viewer')
  return ['admin', 'engineer', 'operator', 'agronomist'].includes(role)
})

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

function userRoleBadgeVariant(role) {
  if (role === 'admin') return 'danger'
  if (role === 'operator') return 'warning'
  return 'info'
}

const sectionCatalog = [
  { id: 'profile', label: 'Профиль', hint: 'Имя, email, роль', icon: '👤' },
  { id: 'notifications', label: 'Уведомления', hint: 'Тосты и алерты', icon: '🔔' },
  { id: 'automation', label: 'Автоматика', hint: 'AE3 и runtime', icon: '⚙️', requiresAutomation: true },
  { id: 'users', label: 'Пользователи', hint: 'Администрирование', icon: '👥', requiresAdmin: true },
]

const visibleSections = computed(() => sectionCatalog.filter((section) => {
  if (section.requiresAdmin && !isAdmin.value) return false
  if (section.requiresAutomation && !canEditAutomationEngineSettings.value) return false
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

const users = ref([])
const searchQuery = ref('')
const roleFilter = ref('')
const currentPage = ref(1)
const perPage = ref(25)
const preferencesLoading = ref(false)
const preferencesSaving = ref(false)
const automationSettingsLoading = ref(false)
const automationSettingsSaving = ref(false)
const automationSettingsResetting = ref(false)
const alertPoliciesLoading = ref(false)
const alertPoliciesSaving = ref(false)
const alertPoliciesResetting = ref(false)
const { isOpen: showCreateModal, open: openCreateModal, close: closeCreateModal } = useSimpleModal()
const editingUser = ref(null)
const deletingUser = ref(null)
const automationSettingsDraft = reactive({})

const userForm = reactive({
  name: '',
  email: '',
  password: '',
  role: 'operator',
})

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

const filteredUsers = computed(() => {
  return users.value.filter((u) => {
    const matchSearch =
      !searchQuery.value ||
      u.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      u.email.toLowerCase().includes(searchQuery.value.toLowerCase())
    const matchRole = !roleFilter.value || u.role === roleFilter.value
    return matchSearch && matchRole
  })
})

const clampCurrentPage = (total) => {
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  if (validPage !== currentPage.value) {
    currentPage.value = validPage
  }
  return validPage
}

watch([filteredUsers, perPage], () => {
  if (filteredUsers.value.length > 0) {
    clampCurrentPage(filteredUsers.value.length)
  } else {
    currentPage.value = 1
  }
})

const paginatedUsers = computed(() => {
  const total = filteredUsers.value.length
  if (total === 0) return []

  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  const start = (validPage - 1) * perPage.value
  const end = start + perPage.value
  return filteredUsers.value.slice(start, end)
})

const loadUsers = () => {
  if (!isAdmin.value) return
  const propsUsers = page.props.users || []
  users.value = propsUsers.map((u) => ({
    ...u,
    created_at: u.created_at,
  }))
}

const editUser = (user) => {
  editingUser.value = user
  userForm.name = user.name
  userForm.email = user.email
  userForm.password = ''
  userForm.role = user.role
}

const confirmDelete = (user) => {
  deletingUser.value = user
}

const doDelete = async () => {
  if (!deletingUser.value) return
  const idToDelete = deletingUser.value.id
  try {
    await api.users.delete(idToDelete)
    showToast('Пользователь успешно удален', 'success', TOAST_TIMEOUT.NORMAL)

    users.value = users.value.filter((u) => u.id !== idToDelete)
    deletingUser.value = null
  } catch (err) {
    logger.error('Failed to delete user:', err)
    const errorMsg = err.response?.data?.message || err.message || ERROR_MESSAGES.UNKNOWN
    showToast(`Ошибка: ${errorMsg}`, 'error', TOAST_TIMEOUT.LONG)
    deletingUser.value = null
  }
}

const saveUser = async () => {
  try {
    const payload = { ...userForm }
    if (editingUser.value) {
      if (!payload.password) {
        delete payload.password
      }
      const updatedUser = await api.users.update(editingUser.value.id, payload)

      if (updatedUser?.id) {
        const index = users.value.findIndex((u) => u.id === updatedUser.id)
        if (index !== -1) {
          users.value[index] = {
            ...updatedUser,
            created_at: updatedUser.created_at || users.value[index].created_at,
          }
        } else {
          users.value.push({ ...updatedUser, created_at: updatedUser.created_at })
        }
      }
    } else {
      const newUser = await api.users.create(payload)

      if (newUser?.id) {
        users.value.push({ ...newUser, created_at: newUser.created_at })
      }
    }
    showToast(
      editingUser.value ? 'Пользователь успешно обновлен' : 'Пользователь успешно создан',
      'success',
      TOAST_TIMEOUT.NORMAL
    )
    closeModal()
  } catch (err) {
    logger.error('Failed to save user:', err)
    const errorMsg = err.response?.data?.message || err.message || ERROR_MESSAGES.UNKNOWN
    showToast(`Ошибка: ${errorMsg}`, 'error', TOAST_TIMEOUT.LONG)
  }
}

const closeModal = () => {
  closeCreateModal()
  editingUser.value = null
  userForm.name = ''
  userForm.email = ''
  userForm.password = ''
  userForm.role = 'operator'
}

onMounted(() => {
  if (isAdmin.value) {
    loadUsers()
  }
  applyPreferences(currentUser.value?.preferences || null)
  loadPreferences()
  if (canEditAutomationEngineSettings.value) {
    activeSection.value = 'automation'
    void loadAutomationEngineSettings({ silent: true })
    void loadAlertPolicies({ silent: true })
  }
})

watch([searchQuery, roleFilter], () => {
  currentPage.value = 1
})
</script>
