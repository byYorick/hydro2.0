<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Пользователи</h1>

    <div v-if="isAdmin" class="mb-6">
      <Card class="mb-4">
        <div class="mb-3 flex flex-wrap items-center gap-2">
          <input
            v-model="searchQuery"
            placeholder="Поиск по имени/email..."
            class="h-9 w-64 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
          />
          <select
            v-model="roleFilter"
            class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
          >
            <option value="">Все роли</option>
            <option value="admin">Администратор</option>
            <option value="operator">Оператор</option>
            <option value="viewer">Наблюдатель</option>
          </select>
          <Button size="sm" @click="loadUsers" :disabled="loading.load">Обновить</Button>
          <Button size="sm" variant="secondary" @click="showCreateModal = true">Создать пользователя</Button>
        </div>

        <div class="rounded-xl border border-neutral-800 overflow-hidden max-h-[720px] flex flex-col">
          <div v-if="loading.load && users.length === 0" class="text-sm text-neutral-400 px-3 py-6 text-center">
            Загрузка пользователей...
          </div>
          <template v-else>
            <!-- Заголовок таблицы -->
            <div class="flex-shrink-0 grid grid-cols-6 gap-0 bg-neutral-900 text-neutral-300 text-sm border-b border-neutral-800">
              <div v-for="(h, i) in headers" :key="i" class="px-3 py-2 text-left font-medium">
                {{ h }}
              </div>
            </div>
            <!-- Виртуализированный список -->
            <div class="flex-1 overflow-hidden">
              <RecycleScroller
                :items="rows"
                :item-size="rowHeight"
                key-field="0"
                v-slot="{ item: r, index }"
                class="virtual-table-body h-full"
              >
                <div 
                  :class="index % 2 === 0 ? 'bg-neutral-950' : 'bg-neutral-925'" 
                  class="grid grid-cols-6 gap-0 text-sm border-b border-neutral-900"
                  style="height:44px"
                >
                  <div class="px-3 py-2 flex items-center">{{ r[0] }}</div>
                  <div class="px-3 py-2 flex items-center">{{ r[1] }}</div>
                  <div class="px-3 py-2 flex items-center text-xs text-neutral-400">{{ r[2] }}</div>
                  <div class="px-3 py-2 flex items-center">
                    <Badge :variant="r[3]">
                      {{ r[4] }}
                    </Badge>
                  </div>
                  <div class="px-3 py-2 flex items-center text-xs text-neutral-400">{{ r[5] }}</div>
                  <div class="px-3 py-2 flex items-center gap-2">
                    <Button size="sm" variant="secondary" @click="editUser(getUserFromRow(r))">Изменить</Button>
                    <Button
                      size="sm"
                      variant="danger"
                      @click="confirmDelete(getUserFromRow(r))"
                      :disabled="getUserFromRow(r).id === currentUserId"
                    >
                      Удалить
                    </Button>
                  </div>
                </div>
              </RecycleScroller>
              <div v-if="!rows.length && !loading.load" class="text-sm text-neutral-400 px-3 py-6 text-center">
                {{ users.length === 0 ? 'Нет пользователей' : 'Нет пользователей по текущим фильтрам' }}
              </div>
            </div>
          </template>
        </div>
      </Card>
    </div>
    <div v-else class="text-sm text-neutral-400">
      У вас нет доступа к управлению пользователями
    </div>

    <!-- Create/Edit User Modal -->
    <Modal :open="showCreateModal || editingUser !== null" title="Пользователь" @close="closeModal">
      <div class="space-y-3">
        <div>
          <label class="text-sm text-neutral-300">Имя</label>
          <input
            v-model="userForm.name"
            class="mt-1 w-full h-9 rounded-md border px-2 text-sm"
            :class="formErrors.name ? 'border-red-500 bg-neutral-900' : 'border-neutral-700 bg-neutral-900'"
          />
          <div v-if="formErrors.name" class="text-xs text-red-400 mt-1">{{ formErrors.name }}</div>
        </div>
        <div>
          <label class="text-sm text-neutral-300">Email</label>
          <input
            v-model="userForm.email"
            type="email"
            class="mt-1 w-full h-9 rounded-md border px-2 text-sm"
            :class="formErrors.email ? 'border-red-500 bg-neutral-900' : 'border-neutral-700 bg-neutral-900'"
          />
          <div v-if="formErrors.email" class="text-xs text-red-400 mt-1">{{ formErrors.email }}</div>
        </div>
        <div>
          <label class="text-sm text-neutral-300">Пароль</label>
          <input
            v-model="userForm.password"
            type="password"
            class="mt-1 w-full h-9 rounded-md border px-2 text-sm"
            :class="formErrors.password ? 'border-red-500 bg-neutral-900' : 'border-neutral-700 bg-neutral-900'"
            :placeholder="editingUser ? 'Оставьте пустым, чтобы не менять' : 'Минимум 8 символов'"
          />
          <div v-if="formErrors.password" class="text-xs text-red-400 mt-1">{{ formErrors.password }}</div>
        </div>
        <div>
          <label class="text-sm text-neutral-300">Роль</label>
          <select
            v-model="userForm.role"
            class="mt-1 w-full h-9 rounded-md border px-2 text-sm"
            :class="formErrors.role ? 'border-red-500 bg-neutral-900' : 'border-neutral-700 bg-neutral-900'"
          >
            <option value="viewer">Наблюдатель</option>
            <option value="operator">Оператор</option>
            <option value="admin">Администратор</option>
          </select>
          <div v-if="formErrors.role" class="text-xs text-red-400 mt-1">{{ formErrors.role }}</div>
        </div>
      </div>
      <template #footer>
        <Button size="sm" variant="secondary" @click="closeModal" :disabled="loading.save">Отмена</Button>
        <Button size="sm" @click="saveUser" :disabled="loading.save">
          {{ loading.save ? 'Сохранение...' : 'Сохранить' }}
        </Button>
      </template>
    </Modal>

    <!-- Delete Confirmation Modal -->
    <Modal :open="deletingUser !== null" title="Удалить пользователя?" @close="deletingUser = null">
      <div class="text-sm">
        Вы уверены, что хотите удалить пользователя <strong>{{ deletingUser?.name }}</strong>?
      </div>
      <template #footer>
        <Button size="sm" variant="secondary" @click="deletingUser = null" :disabled="loading.delete">Отмена</Button>
        <Button size="sm" variant="danger" @click="doDelete" :disabled="loading.delete">
          {{ loading.delete ? 'Удаление...' : 'Удалить' }}
        </Button>
      </template>
    </Modal>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, reactive, ref, onMounted } from 'vue'
import { usePage, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import Modal from '@/Components/Modal.vue'
import { translateRole } from '@/utils/i18n'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

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
const showCreateModal = ref(false)
const editingUser = ref(null)
const deletingUser = ref(null)

const userForm = reactive({
  name: '',
  email: '',
  password: '',
  role: 'operator',
})

const formErrors = reactive({
  name: '',
  email: '',
  password: '',
  role: '',
})

const loading = ref({
  save: false,
  delete: false,
  load: false,
})

const headers = ['ID', 'Имя', 'Email', 'Роль', 'Создан', 'Действия']

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

// Преобразуем пользователей в строки таблицы
const rows = computed(() => {
  return filteredUsers.value.map(u => [
    u.id, // r[0]
    u.name, // r[1]
    u.email, // r[2]
    u.role === 'admin' ? 'danger' : u.role === 'operator' ? 'warning' : 'info', // r[3] - variant для Badge
    translateRole(u.role), // r[4] - текст для Badge
    u.created_at ? new Date(u.created_at).toLocaleDateString('ru-RU') : '-', // r[5]
    u // r[6] - объект пользователя для удобства доступа
  ])
})

// Функция для получения объекта пользователя из строки таблицы
function getUserFromRow(row: Array<string | number | object>): any {
  // Последний элемент строки - это объект пользователя
  return row[row.length - 1] as any
}

// Виртуализация через RecycleScroller
const rowHeight = 44

const validateForm = () => {
  // Очищаем предыдущие ошибки
  formErrors.name = ''
  formErrors.email = ''
  formErrors.password = ''
  formErrors.role = ''
  
  let isValid = true
  
  if (!userForm.name.trim()) {
    formErrors.name = 'Имя обязательно'
    isValid = false
  }
  
  if (!userForm.email.trim()) {
    formErrors.email = 'Email обязателен'
    isValid = false
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(userForm.email)) {
    formErrors.email = 'Некорректный email'
    isValid = false
  }
  
  if (!editingUser.value && !userForm.password.trim()) {
    formErrors.password = 'Пароль обязателен'
    isValid = false
  } else if (userForm.password && userForm.password.length < 8) {
    formErrors.password = 'Пароль должен быть не менее 8 символов'
    isValid = false
  }
  
  if (!userForm.role) {
    formErrors.role = 'Роль обязательна'
    isValid = false
  }
  
  return isValid
}

const loadUsers = async () => {
  if (!isAdmin.value) return
  loading.value.load = true
  try {
    await router.reload({ only: ['users'] })
    const propsUsers = page.props.users || []
    users.value = propsUsers.map((u) => ({
      ...u,
      created_at: u.created_at,
    }))
  } catch (err) {
    logger.error('Failed to load users:', err)
    showToast('Ошибка загрузки пользователей', 'error', 5000)
  } finally {
    loading.value.load = false
  }
}

const editUser = (user) => {
  editingUser.value = user
  userForm.name = user.name
  userForm.email = user.email
  userForm.password = ''
  userForm.role = user.role
  // Очищаем ошибки
  Object.keys(formErrors).forEach(key => formErrors[key] = '')
}

const confirmDelete = (user) => {
  deletingUser.value = user
}

const doDelete = async () => {
  if (!deletingUser.value) return
  loading.value.delete = true
  try {
    await api.delete(`/settings/users/${deletingUser.value.id}`)
    showToast('Пользователь успешно удален', 'success', 3000)
    deletingUser.value = null
    await router.reload({ only: ['users'] })
  } catch (err) {
    logger.error('Failed to delete user:', err)
    const errorMsg = err.response?.data?.message || err.message || 'Неизвестная ошибка'
    showToast(`Ошибка: ${errorMsg}`, 'error', 5000)
    deletingUser.value = null
  } finally {
    loading.value.delete = false
  }
}

const saveUser = async () => {
  if (!validateForm()) {
    showToast('Пожалуйста, исправьте ошибки в форме', 'error', 5000)
    return
  }
  
  loading.value.save = true
  try {
    const payload = { ...userForm }
    if (editingUser.value) {
      if (!payload.password) {
        delete payload.password
      }
      await api.patch(`/settings/users/${editingUser.value.id}`, payload)
    } else {
      await api.post('/settings/users', payload)
    }
    showToast(editingUser.value ? 'Пользователь успешно обновлен' : 'Пользователь успешно создан', 'success', 3000)
    closeModal()
    await router.reload({ only: ['users'] })
  } catch (err) {
    logger.error('Failed to save user:', err)
    
    // Обработка ошибок валидации
    if (err.response?.status === 422 && err.response?.data?.errors) {
      const errors = err.response.data.errors
      if (errors.name) formErrors.name = errors.name[0]
      if (errors.email) formErrors.email = errors.email[0]
      if (errors.password) formErrors.password = errors.password[0]
      if (errors.role) formErrors.role = errors.role[0]
      showToast('Ошибки валидации', 'error', 5000)
    } else {
      const errorMsg = err.response?.data?.message || err.message || 'Неизвестная ошибка'
      showToast(`Ошибка: ${errorMsg}`, 'error', 5000)
    }
  } finally {
    loading.value.save = false
  }
}

const closeModal = () => {
  showCreateModal.value = false
  editingUser.value = null
  userForm.name = ''
  userForm.email = ''
  userForm.password = ''
  userForm.role = 'operator'
  // Очищаем ошибки
  Object.keys(formErrors).forEach(key => formErrors[key] = '')
}

onMounted(() => {
  if (isAdmin.value) {
    const propsUsers = page.props.users || []
    users.value = propsUsers.map((u) => ({
      ...u,
      created_at: u.created_at,
    }))
  }
})
</script>

