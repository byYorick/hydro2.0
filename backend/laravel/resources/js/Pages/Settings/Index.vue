<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Настройки</h1>

    <div v-if="isAdmin" class="mb-6">
      <h2 class="text-md font-semibold mb-3 text-[color:var(--text-primary)]">Управление пользователями</h2>
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
            <option value="">Все роли</option>
            <option value="admin">Администратор</option>
            <option value="operator">Оператор</option>
            <option value="viewer">Наблюдатель</option>
          </select>
          <Button size="sm" @click="loadUsers">Обновить</Button>
          <Button size="sm" variant="secondary" @click="openCreateModal()">Создать пользователя</Button>
        </div>

        <div class="rounded-xl border border-[color:var(--border-muted)] overflow-hidden max-h-[600px] overflow-y-auto">
          <table class="min-w-full text-sm">
            <thead class="bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]">
              <tr>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">ID</th>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">Имя</th>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">Email</th>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">Роль</th>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">Создан</th>
                <th class="px-3 py-2 text-left font-medium border-b border-[color:var(--border-muted)]">Действия</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in paginatedUsers" :key="u.id" class="odd:bg-[color:var(--bg-surface-strong)] even:bg-[color:var(--bg-surface)]">
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">{{ u.id }}</td>
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">{{ u.name }}</td>
                <td class="px-3 py-2 border-b border-[color:var(--border-muted)]">{{ u.email }}</td>
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
                    <Button size="sm" variant="secondary" @click="editUser(u)">Изменить</Button>
                    <Button
                      size="sm"
                      variant="danger"
                      @click="confirmDelete(u)"
                      :disabled="u.id === currentUserId"
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
          <div v-if="!paginatedUsers.length" class="text-sm text-[color:var(--text-dim)] px-3 py-6 text-center">
            Нет пользователей
          </div>
        </div>
      </Card>
    </div>

    <Card>
      <h2 class="text-md font-semibold mb-3 text-[color:var(--text-primary)]">Профиль</h2>
      <div class="space-y-3">
        <div>
          <label class="text-sm text-[color:var(--text-muted)]">Имя</label>
          <div class="text-sm text-[color:var(--text-primary)]">{{ currentUser?.name }}</div>
        </div>
        <div>
          <label class="text-sm text-[color:var(--text-muted)]">Email</label>
          <div class="text-sm text-[color:var(--text-primary)]">{{ currentUser?.email }}</div>
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

    <!-- Create/Edit User Modal -->
    <Modal :open="showCreateModal || editingUser !== null" title="Пользователь" @close="closeModal">
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
          <label for="user-form-password" class="text-sm text-[color:var(--text-muted)]">Пароль</label>
          <input
            id="user-form-password"
            name="password"
            v-model="userForm.password"
            type="password"
            class="input-field mt-1"
            :placeholder="editingUser ? 'Оставьте пустым, чтобы не менять' : ''"
            :autocomplete="editingUser ? 'new-password' : 'new-password'"
          />
        </div>
        <div>
          <label for="user-form-role" class="text-sm text-[color:var(--text-muted)]">Роль</label>
          <select
            id="user-form-role"
            name="role"
            v-model="userForm.role"
            class="input-select mt-1"
          >
            <option value="viewer">Наблюдатель</option>
            <option value="operator">Оператор</option>
            <option value="admin">Администратор</option>
          </select>
        </div>
      </div>
      <template #footer>
        <Button size="sm" variant="secondary" @click="closeModal">Отмена</Button>
        <Button size="sm" @click="saveUser">Сохранить</Button>
      </template>
    </Modal>

    <!-- Delete Confirmation Modal -->
    <Modal :open="deletingUser !== null" title="Удалить пользователя?" @close="deletingUser = null">
      <div class="text-sm text-[color:var(--text-muted)]">
        Вы уверены, что хотите удалить пользователя <strong>{{ deletingUser?.name }}</strong>?
      </div>
      <template #footer>
        <Button size="sm" variant="secondary" @click="deletingUser = null">Отмена</Button>
        <Button size="sm" variant="danger" @click="doDelete">Удалить</Button>
      </template>
    </Modal>
  </AppLayout>
</template>

<script setup>
import { computed, reactive, ref, watch, onMounted } from 'vue'
import { usePage, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import Modal from '@/Components/Modal.vue'
import Pagination from '@/Components/Pagination.vue'
import { translateRole } from '@/utils/i18n'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useSimpleModal } from '@/composables/useModal'
import { ERROR_MESSAGES } from '@/constants/messages'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

const page = usePage()
const currentUser = computed(() => page.props.auth?.user)
const currentUserId = computed(() => currentUser.value?.id)
const isAdmin = computed(() => currentUser.value?.role === 'admin')

const { showToast } = useToast()

// Инициализация API с Toast
const { api } = useApi(showToast)

const users = ref([])
const searchQuery = ref('')
const roleFilter = ref('')
const currentPage = ref(1)
const perPage = ref(25)
const { isOpen: showCreateModal, open: openCreateModal, close: closeCreateModal } = useSimpleModal()
const editingUser = ref(null)
const deletingUser = ref(null)

const userForm = reactive({
  name: '',
  email: '',
  password: '',
  role: 'operator',
})

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

const paginatedUsers = computed(() => {
  const total = filteredUsers.value.length
  if (total === 0) return []
  
  // Защита от некорректных значений
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  if (validPage !== currentPage.value) {
    currentPage.value = validPage
  }
  
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
        users.value = users.value.filter(u => u.id !== deletingUser.value.id)
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
            const index = users.value.findIndex(u => u.id === updatedUser.id)
            if (index !== -1) {
              users.value[index] = { ...updatedUser, created_at: updatedUser.created_at || users.value[index].created_at }
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
        showToast(editingUser.value ? 'Пользователь успешно обновлен' : 'Пользователь успешно создан', 'success', TOAST_TIMEOUT.NORMAL)
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
})

// Сбрасываем на первую страницу при изменении фильтров
watch([searchQuery, roleFilter], () => {
  currentPage.value = 1
})
</script>
