<template>
  <div
    v-if="user"
    class="relative"
  >
    <button
      class="flex items-center gap-2 px-3 py-1.5 rounded-md hover:bg-[color:var(--bg-elevated)] transition-colors text-sm text-[color:var(--text-primary)]"
      :class="{ 'bg-[color:var(--bg-elevated)]': open }"
      @click="open = !open"
    >
      <div class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-full bg-[color:var(--bg-surface-strong)] flex items-center justify-center text-xs font-medium text-[color:var(--text-muted)]">
          {{ userInitials }}
        </div>
        <div class="hidden sm:flex flex-col items-start">
          <span class="text-xs font-medium text-[color:var(--text-primary)]">{{ user?.name }}</span>
          <span class="text-[10px] text-[color:var(--text-muted)]">{{ translateRole(user?.role) }}</span>
        </div>
        <svg
          class="w-4 h-4 text-[color:var(--text-muted)] transition-transform"
          :class="{ 'rotate-180': open }"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M5 15l7-7 7 7"
          />
        </svg>
      </div>
    </button>

    <!-- Overlay для закрытия меню -->
    <div
      v-show="open"
      class="fixed inset-0 z-40"
      @click="open = false"
    ></div>

    <!-- Dropdown меню -->
    <Transition
      enter-active-class="transition ease-out duration-200"
      enter-from-class="opacity-0 scale-95"
      enter-to-class="opacity-100 scale-100"
      leave-active-class="transition ease-in duration-75"
      leave-from-class="opacity-100 scale-100"
      leave-to-class="opacity-0 scale-95"
    >
      <div
        v-show="open"
        class="absolute left-0 bottom-full mb-2 w-56 rounded-md shadow-[var(--shadow-card)] bg-[color:var(--bg-surface-strong)] border border-[color:var(--border-muted)] z-50"
        @click.stop
      >
        <div class="py-1">
          <!-- Информация о пользователе -->
          <div class="px-4 py-3 border-b border-[color:var(--border-muted)]">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-full bg-[color:var(--bg-surface-strong)] flex items-center justify-center text-sm font-medium text-[color:var(--text-muted)]">
                {{ userInitials }}
              </div>
              <div class="flex-1 min-w-0">
                <div class="text-sm font-medium text-[color:var(--text-primary)] truncate">
                  {{ user?.name }}
                </div>
                <div class="text-xs text-[color:var(--text-muted)] truncate">
                  {{ user?.email }}
                </div>
                <div class="mt-1">
                  <Badge
                    :variant="getRoleBadgeVariant(user?.role)"
                    size="sm"
                  >
                    {{ translateRole(user?.role) }}
                  </Badge>
                </div>
              </div>
            </div>
          </div>

          <!-- Пункты меню -->
          <div class="py-1">
            <Link
              :href="route('profile.edit')"
              class="flex items-center gap-3 px-4 py-2 text-sm text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)] transition-colors"
              @click="open = false"
            >
              <svg
                class="w-5 h-5 text-[color:var(--text-muted)]"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                />
              </svg>
              <span>Профиль</span>
            </Link>

            <Link
              :href="route('settings.index')"
              class="flex items-center gap-3 px-4 py-2 text-sm text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)] transition-colors"
              @click="open = false"
            >
              <svg
                class="w-5 h-5 text-[color:var(--text-muted)]"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                />
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                />
              </svg>
              <span>Настройки</span>
            </Link>

            <div class="border-t border-[color:var(--border-muted)] my-1"></div>

            <button
              class="w-full flex items-center gap-3 px-4 py-2 text-sm text-[color:var(--accent-red)] hover:bg-[color:var(--badge-danger-bg)] transition-colors"
              @click="handleLogout"
            >
              <svg
                class="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                />
              </svg>
              <span>Выход</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Link, router, usePage } from '@inertiajs/vue3'
import { route } from '@/utils/route'
// @ts-ignore
import { translateRole } from '@/utils/i18n.js'
import Badge from '@/Components/Badge.vue'
import type { User } from '@/types/User'

const page = usePage()
const open = ref(false)

const user = computed(() => (page.props.auth as any)?.user as User | undefined)

const userInitials = computed(() => {
  if (!user.value?.name) return '?'
  const names = user.value.name.trim().split(/\s+/)
  if (names.length >= 2) {
    return (names[0][0] + names[names.length - 1][0]).toUpperCase()
  }
  return user.value.name.substring(0, 2).toUpperCase()
})

const handleLogout = () => {
  open.value = false
  router.post(route('logout'))
}

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

// Закрытие меню по Escape
const closeOnEscape = (e: KeyboardEvent) => {
  if (open.value && e.key === 'Escape') {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('keydown', closeOnEscape)
})

onUnmounted(() => {
  document.removeEventListener('keydown', closeOnEscape)
})
</script>
