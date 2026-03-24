<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">
      Настройки
    </h1>

    <div
      v-if="isAdmin"
      class="mb-6"
    >
      <h2 class="text-md font-semibold mb-3 text-[color:var(--text-primary)]">
        Управление пользователями
      </h2>
      <Card class="mb-4">
        <div class="mb-3 flex flex-wrap items-center gap-2">
          <input
            v-model="searchQuery"
            placeholder="Поиск по имени/email..."
            class="input-field w-64"
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
          <Button
            size="sm"
            @click="loadUsers"
          >
            Обновить
          </Button>
          <Button
            size="sm"
            variant="secondary"
            @click="openCreateModal()"
          >
            Создать пользователя
          </Button>
        </div>

        <div class="rounded-xl border border-[color:var(--border-muted)] overflow-hidden max-h-[600px] overflow-y-auto">
          <table class="min-w-full text-sm">
            <thead class="bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]">
              <tr>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">
                  ID
                </th>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">
                  Имя
                </th>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">
                  Email
                </th>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">
                  Роль
                </th>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">
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
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">
                  {{ u.id }}
                </td>
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">
                  {{ u.name }}
                </td>
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">
                  {{ u.email }}
                </td>
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">
                  <Badge
                    :variant="u.role === 'admin' ? 'danger' : u.role === 'operator' ? 'warning' : 'info'"
                  >
                    {{ translateRole(u.role) }}
                  </Badge>
                </td>
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)] text-xs text-[color:var(--text-muted)]">
                  {{ new Date(u.created_at).toLocaleDateString() }}
                </td>
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">
                  <div class="flex gap-2">
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
          <Pagination
            v-model:current-page="currentPage"
            v-model:per-page="perPage"
            :total="filteredUsers.length"
          />
          <div
            v-if="!paginatedUsers.length"
            class="text-sm text-[color:var(--text-dim)] px-3 py-6 text-center"
          >
            Нет пользователей
          </div>
        </div>
      </Card>
    </div>

    <Card>
      <h2 class="text-md font-semibold mb-3 text-[color:var(--text-primary)]">
        Профиль
      </h2>
      <div class="space-y-3">
        <div>
          <label class="text-sm text-[color:var(--text-muted)]">Имя</label>
          <div class="text-sm text-[color:var(--text-primary)]">
            {{ currentUser?.name }}
          </div>
        </div>
        <div>
          <label class="text-sm text-[color:var(--text-muted)]">Email</label>
          <div class="text-sm text-[color:var(--text-primary)]">
            {{ currentUser?.email }}
          </div>
        </div>
        <div>
          <label class="text-sm text-[color:var(--text-muted)]">Роль</label>
          <div>
            <Badge
              :variant="currentUser?.role === 'admin' ? 'danger' : currentUser?.role === 'operator' ? 'warning' : 'info'"
            >
              {{ translateRole(currentUser?.role) }}
            </Badge>
          </div>
        </div>
      </div>
    </Card>

    <Card class="mt-4">
      <h2 class="text-md font-semibold mb-3 text-[color:var(--text-primary)]">
        Уведомления
      </h2>
      <div class="space-y-3 max-w-md">
        <div>
          <label class="text-sm text-[color:var(--text-muted)]">
            Окно подавления повторов алертов (сек)
          </label>
          <input
            v-model.number="notificationSettings.alertToastSuppressionSec"
            type="number"
            min="0"
            max="600"
            step="5"
            class="input-field mt-1"
            data-testid="settings-alert-suppression-input"
          />
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            Используется в тостах на странице алертов, по умолчанию 30 сек.
          </div>
        </div>
        <div class="flex items-center gap-2">
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
    </Card>

    <Card
      v-if="automationEngineSettingsSections.length > 0"
      class="mt-4"
      data-testid="settings-automation-engine-card"
    >
      <div class="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
        <h2 class="text-md font-semibold text-[color:var(--text-primary)]">
          Automation Engine
        </h2>
        <div class="text-xs text-[color:var(--text-muted)]">
          Снимок: {{ automationEngineSettingsGeneratedAtLabel }}
        </div>
      </div>
      <p class="mt-1 text-xs text-[color:var(--text-dim)]">
        Фактические runtime-параметры Laravel scheduler и интеграции с automation-engine (timeouts, retries, limits).
      </p>
      <div
        v-if="canEditAutomationEngineSettings"
        class="mt-3 flex flex-wrap items-center gap-2"
      >
        <Button
          size="sm"
          data-testid="settings-automation-engine-save"
          :disabled="automationSettingsSaving || automationSettingsLoading || automationSettingsResetting"
          @click="saveAutomationEngineSettings"
        >
          {{ automationSettingsSaving ? 'Сохраняем...' : 'Сохранить параметры' }}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          data-testid="settings-automation-engine-refresh"
          :disabled="automationSettingsSaving || automationSettingsLoading || automationSettingsResetting"
          @click="loadAutomationEngineSettings"
        >
          {{ automationSettingsLoading ? 'Обновляем...' : 'Обновить из runtime' }}
        </Button>
        <Button
          size="sm"
          variant="danger"
          data-testid="settings-automation-engine-reset"
          :disabled="automationSettingsSaving || automationSettingsLoading || automationSettingsResetting"
          @click="resetAutomationEngineSettings"
        >
          {{ automationSettingsResetting ? 'Сбрасываем...' : 'Сбросить override' }}
        </Button>
      </div>

      <div class="mt-4 space-y-3">
        <section
          v-for="section in automationEngineSettingsSections"
          :key="section.key"
          class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3"
        >
          <h3 class="text-sm font-medium text-[color:var(--text-primary)]">
            {{ section.title }}
          </h3>
          <dl class="mt-2 grid grid-cols-1 gap-x-4 gap-y-2 md:grid-cols-2">
            <template
              v-for="item in section.items"
              :key="`${section.key}-${item.key}`"
            >
              <dt class="text-xs text-[color:var(--text-muted)]">
                {{ item.label }}
              </dt>
              <dd class="text-sm font-mono text-[color:var(--text-primary)] break-all">
                <template v-if="canEditAutomationEngineSettings && item.editable">
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
                    class="input-field w-full"
                    type="number"
                    :step="item.step || 1"
                    :min="item.min"
                    :max="item.max"
                  />
                  <input
                    v-else
                    v-model="automationSettingsDraft[item.key]"
                    :data-testid="`settings-automation-engine-input-${item.key}`"
                    class="input-field w-full"
                    type="text"
                  />
                </template>
                <template v-else>
                  {{ formatAutomationSettingValue(item.value, item.unit) }}
                </template>
                <div
                  v-if="item.description"
                  class="mt-1 text-xs text-[color:var(--text-dim)] font-normal"
                >
                  {{ item.description }}
                </div>
                <div class="mt-1 text-[10px] text-[color:var(--text-muted)] uppercase tracking-wide font-normal">
                  source: {{ item.source || 'default' }}
                </div>
              </dd>
            </template>
          </dl>
        </section>
      </div>
    </Card>

    <!-- Create/Edit User Modal -->
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

    <!-- Delete Confirmation Modal -->
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
import { usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import Modal from '@/Components/Modal.vue'
import Pagination from '@/Components/Pagination.vue'
import { translateRole } from '@/utils/i18n'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
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

const { showToast } = useToast()
const automationConfig = useAutomationConfig(showToast)

// Инициализация API с Toast
const { api } = useApi(showToast)

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
    const response = await api.get('/settings/preferences')
    applyPreferences(response?.data?.data)
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
    const response = await api.patch('/settings/preferences', {
      alert_toast_suppression_sec: normalized,
    })
    applyPreferences(response?.data?.data)
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
  try {
    await api.delete(`/settings/users/${deletingUser.value.id}`)
    showToast('Пользователь успешно удален', 'success', TOAST_TIMEOUT.NORMAL)

    // Обновляем локальный список пользователей без reload
    users.value = users.value.filter((u) => u.id !== deletingUser.value.id)
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
      const response = await api.patch(`/settings/users/${editingUser.value.id}`, payload)
      const updatedUser = response.data?.data || response.data

      // Обновляем пользователя в локальном списке без reload
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
      const response = await api.post('/settings/users', payload)
      const newUser = response.data?.data || response.data

      // Добавляем нового пользователя в локальный список без reload
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
    void loadAutomationEngineSettings({ silent: true })
  }
})

// Сбрасываем на первую страницу при изменении фильтров
watch([searchQuery, roleFilter], () => {
  currentPage.value = 1
})
</script>
