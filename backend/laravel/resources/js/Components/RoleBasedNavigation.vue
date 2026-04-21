<template>
  <nav class="space-y-0.5">
    <NavLink
      v-for="item in visibleItems"
      :key="item.href"
      :href="item.href"
      :label="item.label"
      :icon="item.icon"
      :collapsed="collapsed"
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
  icon: string
  roles?: string[]
}

defineProps<{ collapsed?: boolean }>()

const navigationItems: NavItem[] = [
  {
    href: '/',
    label: 'Операционный центр',
    icon: '<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><path d="M9 22V12h6v10"/>',
  },
  {
    href: '/launch',
    label: 'Мастер запуска',
    roles: ['admin', 'agronomist', 'engineer'],
    icon: '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>',
  },
  {
    href: '/zones',
    label: 'Зоны',
    icon: '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>',
  },
  {
    href: '/greenhouses',
    label: 'Теплицы',
    icon: '<path d="M3 21V9l9-7 9 7v12"/><path d="M9 21v-6a3 3 0 016 0v6"/>',
  },
  {
    href: '/recipes',
    label: 'Рецепты',
    roles: ['admin', 'agronomist'],
    icon: '<path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>',
  },
  {
    href: '/nutrients',
    label: 'Удобрения',
    roles: ['admin', 'agronomist', 'operator'],
    icon: '<path d="M12 2.69l5.66 5.66a8 8 0 11-11.31 0z"/>',
  },
  {
    href: '/documentation/fertigation',
    label: 'Документация',
    roles: ['admin', 'agronomist', 'operator'],
    icon: '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8M16 17H8M10 9H8"/>',
  },
  {
    href: '/plants',
    label: 'Культуры',
    roles: ['admin', 'agronomist'],
    icon: '<path d="M17 8C8 10 5.9 16.17 3.82 22c3.17-3.17 7.5-4.5 8.18-8.5C12.41 9.5 15 7 17 8z"/>',
  },
  {
    href: '/devices',
    label: 'Устройства',
    icon: '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
  },
  {
    href: '/alerts',
    label: 'Алерты',
    icon: '<path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/>',
  },
  {
    href: '/analytics',
    label: 'Аналитика',
    icon: '<path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/>',
  },
  {
    href: '/monitoring',
    label: 'Сервисы',
    icon: '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
  },
  {
    href: '/logs',
    label: 'Логи',
    roles: ['admin', 'operator', 'engineer'],
    icon: '<path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 12h6M9 16h4"/>',
  },
  {
    href: '/audit',
    label: 'Аудит',
    roles: ['admin'],
    icon: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/>',
  },
  {
    href: '/users',
    label: 'Операторы',
    roles: ['admin'],
    icon: '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/>',
  },
  {
    href: '/settings',
    label: 'Настройки',
    icon: '<path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>',
  },
]

const page = usePage()
const role = computed(() => (page.props.auth as any)?.user?.role || 'viewer')

const visibleItems = computed(() =>
  navigationItems.filter((item) => !item.roles || item.roles.includes(role.value))
)
</script>
