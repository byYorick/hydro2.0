<template>
  <nav
    v-if="isMobile"
    class="mobile-navigation fixed bottom-0 left-0 right-0 z-40 border-t border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] lg:hidden"
    aria-label="Основная навигация"
  >
    <div class="grid h-16 grid-cols-4">
      <NavLink
        v-for="item in visibleItems"
        :key="item.href"
        :href="item.href"
        :label="item.label"
        class="min-w-0 h-full"
        :mobile="true"
      >
        <svg
          class="w-5 h-5 mb-1 shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <SvgNodes :nodes="item.icon" />
        </svg>
        <span class="max-w-full truncate">{{ item.label }}</span>
      </NavLink>
      <button
        type="button"
        class="mobile-nav-link"
        :class="moreActive ? 'mobile-nav-link--active' : ''"
        :aria-expanded="menuOpen"
        aria-controls="mobile-nav"
        aria-label="Ещё разделы"
        @click="$emit('open-menu')"
      >
        <svg
          class="w-5 h-5 mb-1 shrink-0"
          viewBox="0 0 24 24"
          fill="currentColor"
          aria-hidden="true"
        >
          <circle
            cx="5"
            cy="12"
            r="1.5"
          /><circle
            cx="12"
            cy="12"
            r="1.5"
          /><circle
            cx="19"
            cy="12"
            r="1.5"
          />
        </svg>
        <span>Ещё</span>
      </button>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { usePage } from '@inertiajs/vue3'
import NavLink from '@/Components/NavLink.vue'
import SvgNodes from '@/Components/Icons/SvgNodes.vue'
import { getRoleNavigationItems } from '@/Components/RoleBasedNavigation.vue'

const page = usePage()
defineProps<{ menuOpen?: boolean }>()
defineEmits<{ 'open-menu': [] }>()
const role = computed(() => (page.props.auth as { user?: { role?: string } })?.user?.role || 'viewer')

const primaryPaths: Record<string, string[]> = {
  operator: ['/', '/zones', '/alerts'],
  agronomist: ['/', '/zones', '/recipes'],
  engineer: ['/', '/devices', '/zones'],
  admin: ['/', '/alerts', '/users'],
  viewer: ['/', '/zones', '/alerts'],
}
const visibleItems = computed(() => {
  const items = getRoleNavigationItems(role.value)
  return (primaryPaths[role.value] ?? primaryPaths.viewer)
    .flatMap((href) => items.filter((item) => item.href === href))
})
const moreActive = computed(() => {
  const path = String(page.url || '/').split(/[?#]/)[0]
  return !visibleItems.value.some((item) => path === item.href || (item.href !== '/' && path.startsWith(`${item.href}/`)))
})

const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 1024)

function checkMobile() {
  isMobile.value = window.innerWidth < 1024
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})
</script>
