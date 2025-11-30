<template>
  <ErrorBoundary>
    <div class="min-h-screen bg-neutral-950 text-neutral-100">
      <div class="flex h-screen overflow-hidden">
      <aside class="hidden lg:block w-64 shrink-0 border-r border-neutral-800 bg-neutral-925">
        <div class="h-16 flex items-center px-4 border-b border-neutral-800">
          <span class="text-base font-semibold">hydro 2.0</span>
        </div>
        <nav class="p-3 space-y-1">
          <RoleBasedNavigation />
        </nav>
      </aside>
      
      <!-- Mobile Navigation Menu -->
      <div
        v-if="showMobileMenu"
        class="fixed inset-0 z-50 lg:hidden"
        @click="showMobileMenu = false"
      >
        <div class="fixed inset-0 bg-black/50" />
        <div
          class="fixed left-0 top-0 bottom-0 w-64 bg-neutral-925 border-r border-neutral-800"
          @click.stop
        >
          <div class="h-16 flex items-center justify-between px-4 border-b border-neutral-800">
            <span class="text-base font-semibold">hydro 2.0</span>
            <button
              @click="showMobileMenu = false"
              class="p-2 rounded-md text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800"
            >
              <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <nav class="p-3 space-y-1" @click="showMobileMenu = false">
            <RoleBasedNavigation />
          </nav>
        </div>
      </div>
      
      <main class="flex-1 flex flex-col min-h-0 overflow-hidden">
        <!-- Header Status Bar (всегда видимый) -->
        <div class="shrink-0">
          <HeaderStatusBar />
        </div>
        
        <header class="h-16 flex items-center justify-between px-4 border-b border-neutral-800 bg-neutral-925 lg:hidden shrink-0">
          <div class="flex items-center gap-3">
            <button
              @click="showMobileMenu = !showMobileMenu"
              class="p-2 rounded-md text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800"
            >
              <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <span class="text-base font-semibold">hydro 2.0</span>
          </div>
          <span class="text-xs text-neutral-400 hidden sm:inline">Ctrl+K — Командная палитра</span>
        </header>
        <div class="flex-1 min-h-0 overflow-y-auto px-4 py-4 pb-20 lg:pb-4">
          <Breadcrumbs />
          <Transition
            name="page"
            mode="out-in"
          >
            <div :key="$page.url">
              <slot />
            </div>
          </Transition>
        </div>
        <CommandPalette />
        <ToastContainer />
        <MobileNavigation />
        
        <!-- Меню пользователя в нижнем левом углу -->
        <!-- На мобильных устройствах выше MobileNavigation (h-16 = 4rem = 64px), на десктопе просто bottom-4 -->
        <div class="fixed bottom-20 left-4 lg:bottom-4 z-50">
          <UserMenu />
        </div>
      </main>
      <aside class="hidden xl:block w-80 shrink-0 border-l border-neutral-800 bg-neutral-925 flex flex-col h-screen">
        <div class="h-16 flex items-center px-4 border-b border-neutral-800 shrink-0">
          <span class="text-sm text-neutral-400">События</span>
        </div>
        <div class="flex-1 min-h-0 flex flex-col overflow-hidden">
          <div class="p-4 space-y-4 shrink-0">
            <FavoritesWidget />
            <HistoryWidget />
          </div>
          <div class="flex-1 min-h-0 px-4 pb-4 overflow-hidden">
            <slot name="context" />
          </div>
        </div>
      </aside>
    </div>
  </div>
  </ErrorBoundary>
</template>
  
<script setup lang="ts">
import { ref, onMounted, usePage } from 'vue'
import { usePage as useInertiaPage } from '@inertiajs/vue3'
import CommandPalette from '@/Components/CommandPalette.vue'
import NavLink from '@/Components/NavLink.vue'
import RoleBasedNavigation from '@/Components/RoleBasedNavigation.vue'
import Breadcrumbs from '@/Components/Breadcrumbs.vue'
import HeaderStatusBar from '@/Components/HeaderStatusBar.vue'
import ErrorBoundary from '@/Components/ErrorBoundary.vue'
import ToastContainer from '@/Components/ToastContainer.vue'
import MobileNavigation from '@/Components/MobileNavigation.vue'
import FavoritesWidget from '@/Components/FavoritesWidget.vue'
import HistoryWidget from '@/Components/HistoryWidget.vue'
import UserMenu from '@/Components/UserMenu.vue'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'
  
const showMobileMenu = ref(false)
const page = useInertiaPage()

// Инициализируем keyboard shortcuts
onMounted(() => {
  useKeyboardShortcuts()
})
</script>
  
<style>
:root {
  color-scheme: dark;
}
.bg-neutral-925 { background-color: #0f0f10; }
.bg-neutral-850 { background-color: #1a1a1b; }

/* Анимации переходов между страницами */
.page-enter-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.page-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.page-enter-from {
  opacity: 0;
  transform: translateY(4px);
}

.page-enter-to {
  opacity: 1;
  transform: translateY(0);
}

.page-leave-from {
  opacity: 1;
  transform: translateY(0);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* Стили для прокрутки */
.scrollbar-thin::-webkit-scrollbar {
  width: 6px;
}

.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}

.scrollbar-thin::-webkit-scrollbar-thumb {
  background-color: rgba(38, 38, 38, 0.8);
  border-radius: 3px;
}

.scrollbar-thin::-webkit-scrollbar-thumb:hover {
  background-color: rgba(38, 38, 38, 1);
}
</style>

