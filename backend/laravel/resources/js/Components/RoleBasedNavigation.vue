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
import NavLink from '@/Components/NavLink.vue'

interface NavItem {
  href: string
  label: string
  roles?: string[]
}

const navigationItems: NavItem[] = [
  { href: '/cycles', label: 'Центр циклов' },
  { href: '/zones', label: 'Зоны' },
  { href: '/greenhouses', label: 'Теплицы' },
  { href: '/recipes', label: 'Рецепты', roles: ['admin', 'agronomist'] },
  { href: '/plants', label: 'Культуры', roles: ['admin', 'agronomist'] },
  { href: '/devices', label: 'Устройства' },
  { href: '/alerts', label: 'Алерты' },
  { href: '/monitoring', label: 'Сервисы' },
  { href: '/users', label: 'Операторы', roles: ['admin'] },
  { href: '/settings', label: 'Настройки' },
]

const page = usePage()
const role = computed(() => page.props.auth?.user?.role || 'viewer')

const visibleItems = computed(() =>
  navigationItems.filter((item) => !item.roles || item.roles.includes(role.value))
)
</script>
