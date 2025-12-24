<template>
  <nav class="space-y-1">
    <NavLink
      v-for="item in navigationItems"
      :key="item.href"
      :href="item.href"
      :label="item.label"
    />
  </nav>
</template>

<script setup lang="ts">
import NavLink from '@/Components/NavLink.vue'

interface NavItem {
  href: string
  label: string
}

const navigationItems: NavItem[] = [
  { href: '/', label: 'Мониторинг' },
  { href: '/greenhouses', label: 'Теплицы' },
  { href: '/zones', label: 'Зоны' },
  { href: '/recipes', label: 'Рецепты' },
  { href: '/devices', label: 'Устройства' },
  { href: '/alerts', label: 'Алерты' },
  { href: '/services', label: 'Сервисы' },
  { href: '/settings', label: 'Настройки' },
]
</script>
