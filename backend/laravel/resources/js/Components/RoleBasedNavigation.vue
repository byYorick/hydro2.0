<template>
  <nav class="space-y-1">
    <NavLink
      v-for="item in visibleItems"
      :key="item.href"
      :href="item.href"
      :label="item.label"
    />
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePage } from '@inertiajs/vue3'
// @ts-ignore
import NavLink from '@/Components/NavLink.vue'

interface NavItem {
  href: string
  label: string
  roles?: string[]
}

const navigationItems: NavItem[] = [
  { href: '/', label: 'Дашборд' },
  { href: '/cycles', label: 'Центр циклов' },
  { href: '/setup/wizard', label: 'Мастер запуска', roles: ['admin', 'agronomist'] },
  { href: '/zones', label: 'Зоны' },
  { href: '/greenhouses', label: 'Теплицы' },
  { href: '/recipes', label: 'Рецепты', roles: ['admin', 'agronomist'] },
  { href: '/plants', label: 'Культуры', roles: ['admin', 'agronomist'] },
  { href: '/devices', label: 'Устройства' },
  { href: '/alerts', label: 'Алерты' },
  { href: '/analytics', label: 'Аналитика' },
  { href: '/monitoring', label: 'Сервисы' },
  { href: '/logs', label: 'Логи', roles: ['admin', 'operator', 'engineer'] },
  { href: '/audit', label: 'Аудит', roles: ['admin'] },
  { href: '/users', label: 'Операторы', roles: ['admin'] },
  { href: '/settings', label: 'Настройки' },
]

const page = usePage()
const role = computed(() => (page.props.auth as any)?.user?.role || 'viewer')

const visibleItems = computed(() =>
  navigationItems.filter((item) => !item.roles || item.roles.includes(role.value))
)
</script>
