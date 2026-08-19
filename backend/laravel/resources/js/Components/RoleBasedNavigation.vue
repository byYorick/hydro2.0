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

<script lang="ts">
export interface RoleNavItem {
  href: string
  label: string
  icon: string
}

const ICONS = {
  home: '<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><path d="M9 22V12h6v10"/>',
  launch: '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>',
  zones: '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>',
  recipes: '<path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>',
  docs: '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8M16 17H8M10 9H8"/>',
  devices: '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
  alerts: '<path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/>',
  analytics: '<path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/>',
  monitoring: '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
  logs: '<path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 12h6M9 16h4"/>',
  audit: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/>',
  users: '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/>',
  settings: '<path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>',
}

const HOME_LABELS: Record<string, string> = {
  operator: 'Сегодня',
  agronomist: 'Обзор',
  engineer: 'Обзор',
  admin: 'Система',
  viewer: 'Обзор',
}

function navItem(href: string, label: string, icon: string): RoleNavItem {
  return { href, label, icon }
}

export function homeNavLabel(role: string): string {
  return HOME_LABELS[role] ?? 'Обзор'
}

export function getRoleNavigationItems(role: string): RoleNavItem[] {
  const home = navItem('/', homeNavLabel(role), ICONS.home)
  const zones = navItem('/zones', 'Зоны', ICONS.zones)
  const alerts = navItem('/alerts', 'Тревоги', ICONS.alerts)
  const settings = navItem(
    '/settings',
    role === 'operator' ? 'Профиль' : 'Настройки',
    ICONS.settings,
  )
  const recipes = navItem('/recipes', 'Рецепты', ICONS.recipes)
  const analytics = navItem('/analytics', 'Аналитика', ICONS.analytics)
  const launch = navItem('/launch', 'Запуск', ICONS.launch)
  const docs = navItem('/documentation/fertigation', 'Справочник', ICONS.docs)
  const devices = navItem('/devices', 'Узлы', ICONS.devices)
  const monitoring = navItem('/monitoring', 'Здоровье системы', ICONS.monitoring)
  const logs = navItem('/logs', 'Логи', ICONS.logs)
  const journal = navItem('/audit', 'Журнал', ICONS.audit)
  const users = navItem('/users', 'Пользователи', ICONS.users)

  switch (role) {
    case 'operator':
      return [home, zones, alerts, docs, settings]
    case 'agronomist':
      return [home, zones, recipes, analytics, alerts, launch]
    case 'engineer':
      return [devices, home, zones, alerts, monitoring, logs]
    case 'admin':
      return [home, alerts, monitoring, users, journal, zones, devices, settings]
    case 'viewer':
    default:
      return [home, zones, alerts, settings]
  }
}
</script>

<script setup lang="ts">
import { computed } from 'vue'
import { usePage } from '@inertiajs/vue3'
import NavLink from '@/Components/NavLink.vue'

defineProps<{ collapsed?: boolean }>()

const page = usePage()
const role = computed(() => (page.props.auth as { user?: { role?: string } })?.user?.role || 'viewer')
const visibleItems = computed(() => getRoleNavigationItems(role.value))
</script>
