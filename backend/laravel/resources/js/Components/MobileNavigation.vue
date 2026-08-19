<template>
  <nav
    v-if="isMobile"
    class="fixed bottom-0 left-0 right-0 z-40 bg-[color:var(--bg-surface-strong)] border-t border-[color:var(--border-muted)] lg:hidden"
  >
    <div class="flex items-center justify-around h-16">
      <NavLink
        v-for="item in visibleItems"
        :key="item.href"
        :href="item.href"
        :label="item.label"
        class="flex flex-col items-center justify-center flex-1 h-full"
        :mobile="true"
      >
        <svg
          class="w-6 h-6 mb-1"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          v-html="item.icon"
        />
        <span>{{ item.label }}</span>
      </NavLink>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { usePage } from '@inertiajs/vue3'
import NavLink from '@/Components/NavLink.vue'
import { getRoleNavigationItems } from '@/Components/RoleBasedNavigation.vue'

const page = usePage()
const role = computed(() => (page.props.auth as { user?: { role?: string } })?.user?.role || 'viewer')
const visibleItems = computed(() => getRoleNavigationItems(role.value))

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

<style scoped>
nav {
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
</style>
