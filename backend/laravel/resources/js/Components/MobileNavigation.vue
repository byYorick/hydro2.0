<template>
  <!-- Bottom Navigation для мобильных устройств -->
  <nav
    v-if="isMobile"
    class="fixed bottom-0 left-0 right-0 z-40 bg-neutral-925 border-t border-neutral-800 lg:hidden"
  >
    <div class="flex items-center justify-around h-16">
      <NavLink
        href="/"
        :label="'Панель'"
        class="flex flex-col items-center justify-center flex-1 h-full"
        :mobile="true"
      >
        <svg class="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
        </svg>
      </NavLink>
      
      <NavLink
        v-if="canViewZones"
        href="/zones"
        :label="'Зоны'"
        class="flex flex-col items-center justify-center flex-1 h-full"
        :mobile="true"
      >
        <svg class="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
        </svg>
      </NavLink>
      
      <NavLink
        v-if="canViewDevices"
        href="/devices"
        :label="'Устройства'"
        class="flex flex-col items-center justify-center flex-1 h-full"
        :mobile="true"
      >
        <svg class="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m-2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
        </svg>
      </NavLink>
      
      <NavLink
        v-if="canViewRecipes"
        href="/recipes"
        :label="'Рецепты'"
        class="flex flex-col items-center justify-center flex-1 h-full"
        :mobile="true"
      >
        <svg class="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
      </NavLink>
      
      <NavLink
        href="/alerts"
        :label="'Алерты'"
        class="flex flex-col items-center justify-center flex-1 h-full"
        :mobile="true"
      >
        <svg class="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      </NavLink>
      
      <NavLink
        v-if="!isViewer"
        href="/settings"
        :label="'Настройки'"
        class="flex flex-col items-center justify-center flex-1 h-full"
        :mobile="true"
      >
        <svg class="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </NavLink>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRole } from '@/composables/useRole'
import NavLink from '@/Components/NavLink.vue'

const { isViewer, canEdit } = useRole()

const isMobile = ref(false)

const canViewZones = computed(() => true) // Все роли могут видеть зоны
const canViewDevices = computed(() => true) // Все роли могут видеть устройства
const canViewRecipes = computed(() => true) // Все роли могут видеть рецепты

function checkMobile() {
  isMobile.value = window.innerWidth < 1024 // lg breakpoint
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
/* Дополнительные стили для мобильной навигации */
nav {
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
</style>

