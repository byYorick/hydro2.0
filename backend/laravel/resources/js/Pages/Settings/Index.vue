<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Settings</h1>

    <div v-if="isAdmin" class="mb-6">
      <h2 class="text-md font-semibold mb-3 text-neutral-300">Управление пользователями</h2>
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
            <option value="admin">Admin</option>
            <option value="operator">Operator</option>
            <option value="viewer">Viewer</option>
          </select>
          <Button size="sm" @click="loadUsers">Обновить</Button>
          <Button size="sm" variant="secondary" @click="showCreateModal = true">Создать пользователя</Button>
        </div>

        <div class="rounded-xl border border-neutral-800 overflow-hidden max-h-[600px] overflow-y-auto">
          <table class="min-w-full text-sm">
            <thead class="bg-neutral-900 text-neutral-300">
              <tr>
                <th class="px-3 py-2 text-left font-medium border-b border-neutral-800">ID</th>
                <th class="px-3 py-2 text-left font-medium border-b border-neutral-800">Имя</th>
                <th class="px-3 py-2 text-left font-medium border-b border-neutral-800">Email</th>
                <th class="px-3 py-2 text-left font-medium border-b border-neutral-800">Роль</th>
                <th class="px-3 py-2 text-left font-medium border-b border-neutral-800">Создан</th>
                <th class="px-3 py-2 text-left font-medium border-b border-neutral-800">Действия</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in filteredUsers" :key="u.id" class="odd:bg-neutral-950 even:bg-neutral-925">
                <td class="px-3 py-2 border-b border-neutral-900">{{ u.id }}</td>
                <td class="px-3 py-2 border-b border-neutral-900">{{ u.name }}</td>
                <td class="px-3 py-2 border-b border-neutral-900">{{ u.email }}</td>
                <td class="px-3 py-2 border-b border-neutral-900">
                  <Badge
                    :variant="u.role === 'admin' ? 'danger' : u.role === 'operator' ? 'warning' : 'info'"
                  >
                    {{ u.role }}
                  </Badge>
                </td>
                <td class="px-3 py-2 border-b border-neutral-900 text-xs text-neutral-400">
                  {{ new Date(u.created_at).toLocaleDateString() }}
                </td>
                <td class="px-3 py-2 border-b border-neutral-900">
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
          <div v-if="!filteredUsers.length" class="text-sm text-neutral-400 px-3 py-6 text-center">
            Нет пользователей
          </div>
        </div>
      </Card>
    </div>

    <Card>
      <h2 class="text-md font-semibold mb-3 text-neutral-300">Профиль</h2>
      <div class="space-y-3">
        <div>
          <label class="text-sm text-neutral-400">Имя</label>
          <div class="text-sm text-neutral-200">{{ currentUser?.name }}</div>
        </div>
        <div>
          <label class="text-sm text-neutral-400">Email</label>
          <div class="text-sm text-neutral-200">{{ currentUser?.email }}</div>
        </div>
        <div>
          <label class="text-sm text-neutral-400">Роль</label>
          <div>
            <Badge
              :variant="currentUser?.role === 'admin' ? 'danger' : currentUser?.role === 'operator' ? 'warning' : 'info'"
            >
              {{ currentUser?.role }}
            </Badge>
          </div>
        </div>
      </div>
    </Card>

    <!-- Create/Edit User Modal -->
    <Modal :open="showCreateModal || editingUser !== null" title="Пользователь" @close="closeModal">
      <div class="space-y-3">
        <div>
          <label class="text-sm text-neutral-300">Имя</label>
          <input
            v-model="userForm.name"
            class="mt-1 w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
          />
        </div>
        <div>
          <label class="text-sm text-neutral-300">Email</label>
          <input
            v-model="userForm.email"
            type="email"
            class="mt-1 w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
          />
        </div>
        <div>
          <label class="text-sm text-neutral-300">Пароль</label>
          <input
            v-model="userForm.password"
            type="password"
            class="mt-1 w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
            :placeholder="editingUser ? 'Оставьте пустым, чтобы не менять' : ''"
          />
        </div>
        <div>
          <label class="text-sm text-neutral-300">Роль</label>
          <select
            v-model="userForm.role"
            class="mt-1 w-full h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm"
          >
            <option value="viewer">Viewer</option>
            <option value="operator">Operator</option>
            <option value="admin">Admin</option>
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
      <div class="text-sm">
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
import { computed, reactive, ref, onMounted } from 'vue'
import { usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import Modal from '@/Components/Modal.vue'
import axios from 'axios'

const page = usePage()
const currentUser = computed(() => page.props.auth?.user)
const currentUserId = computed(() => currentUser.value?.id)
const isAdmin = computed(() => currentUser.value?.role === 'admin')

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
        await axios.delete(`/settings/users/${deletingUser.value.id}`, {
          headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        })
        // Перезагрузить страницу для обновления списка пользователей
        window.location.reload()
      } catch (err) {
        console.error('Failed to delete user:', err)
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
          await axios.patch(`/settings/users/${editingUser.value.id}`, payload, {
            headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          })
        } else {
          await axios.post('/settings/users', payload, {
            headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          })
        }
        // Перезагрузить страницу для обновления списка пользователей
        window.location.reload()
      } catch (err) {
        console.error('Failed to save user:', err)
      }
    }

const closeModal = () => {
  showCreateModal.value = false
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
</script>
