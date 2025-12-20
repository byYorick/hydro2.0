<script setup lang="ts">
import { computed } from 'vue'
import { usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import DeleteUserForm from './Partials/DeleteUserForm.vue'
import UpdatePasswordForm from './Partials/UpdatePasswordForm.vue'
import UpdateProfileInformationForm from './Partials/UpdateProfileInformationForm.vue'
import { Head } from '@inertiajs/vue3'
import { translateRole } from '@/utils/i18n.js'
import type { User } from '@/types/User'

defineProps({
    mustVerifyEmail: {
        type: Boolean,
    },
    status: {
        type: String,
    },
})

const page = usePage()
const user = computed(() => page.props.auth?.user as User | undefined)

const getRoleBadgeVariant = (role?: string): 'danger' | 'warning' | 'info' | 'success' | 'neutral' => {
  switch (role) {
    case 'admin':
      return 'danger'
    case 'operator':
      return 'warning'
    case 'agronomist':
      return 'success'
    case 'engineer':
      return 'info'
    default:
      return 'neutral'
  }
}

const formatDate = (dateString?: string | null): string => {
  if (!dateString) return 'Не указано'
  return new Date(dateString).toLocaleDateString('ru-RU', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script>

<template>
  <Head title="Профиль" />

  <AppLayout>
    <div class="max-w-4xl mx-auto space-y-4">
      <!-- Информация о пользователе -->
      <Card>
        <h2 class="text-base font-semibold text-[color:var(--text-primary)] mb-4">Информация о пользователе</h2>
        <div class="space-y-4">
          <div class="flex items-center gap-4">
            <div class="w-16 h-16 rounded-full bg-[color:var(--bg-surface-strong)] flex items-center justify-center text-xl font-medium text-[color:var(--text-muted)]">
              {{ user?.name ? user.name.substring(0, 2).toUpperCase() : '?' }}
            </div>
            <div class="flex-1">
              <div class="text-lg font-semibold text-[color:var(--text-primary)]">{{ user?.name }}</div>
              <div class="text-sm text-[color:var(--text-muted)]">{{ user?.email }}</div>
            </div>
            <div v-if="user?.role">
              <Badge
                :variant="getRoleBadgeVariant(user.role)"
                size="sm"
              >
                {{ translateRole(user.role) }}
              </Badge>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-[color:var(--border-muted)]">
            <div>
              <div class="text-xs text-[color:var(--text-dim)] mb-1">Роль</div>
              <div class="text-sm text-[color:var(--text-primary)]">
                <Badge
                  :variant="getRoleBadgeVariant(user?.role)"
                  size="xs"
                >
                  {{ translateRole(user?.role) }}
                </Badge>
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-dim)] mb-1">Email подтвержден</div>
              <div class="text-sm text-[color:var(--text-primary)]">
                <Badge
                  :variant="user?.email_verified_at ? 'success' : 'warning'"
                  size="xs"
                >
                  {{ user?.email_verified_at ? 'Да' : 'Нет' }}
                </Badge>
              </div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-dim)] mb-1">Дата регистрации</div>
              <div class="text-sm text-[color:var(--text-primary)]">{{ formatDate(user?.created_at) }}</div>
            </div>
            <div>
              <div class="text-xs text-[color:var(--text-dim)] mb-1">Последнее обновление</div>
              <div class="text-sm text-[color:var(--text-primary)]">{{ formatDate(user?.updated_at) }}</div>
            </div>
          </div>
        </div>
      </Card>

      <!-- Общая информация -->
      <Card>
        <h2 class="text-base font-semibold text-[color:var(--text-primary)] mb-4">Общая информация</h2>
        <UpdateProfileInformationForm
          :must-verify-email="mustVerifyEmail"
          :status="status"
          class="max-w-xl"
        />
      </Card>

      <!-- Безопасность -->
      <Card>
        <h2 class="text-base font-semibold text-[color:var(--text-primary)] mb-4">Безопасность</h2>
        <UpdatePasswordForm class="max-w-xl" />
      </Card>

      <!-- Опасная зона -->
      <Card>
        <h2 class="text-base font-semibold text-[color:var(--text-primary)] mb-4">Опасная зона</h2>
        <DeleteUserForm class="max-w-xl" />
      </Card>
    </div>
  </AppLayout>
</template>
