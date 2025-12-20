<template>
  <ErrorBoundary>
    <div class="app-shell">
      <div class="min-h-screen text-[color:var(--text-primary)]">
        <div class="flex h-screen overflow-hidden">
          <aside class="hidden lg:flex w-72 shrink-0 flex-col border-r border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] backdrop-blur-xl glass-panel">
            <div class="h-16 flex items-center px-5 border-b border-[color:var(--border-muted)]">
              <div class="flex items-center gap-3">
                <div class="h-8 w-8 rounded-xl bg-[linear-gradient(135deg,var(--accent-green),var(--accent-cyan))] shadow-[0_0_0_1px_var(--badge-success-border)]" />
                <div>
                  <div class="text-lg font-semibold tracking-tight">hydro 2.0</div>
                  <div class="text-[11px] uppercase tracking-[0.2em] text-[color:var(--text-dim)]">agronomy deck</div>
                </div>
              </div>
            </div>
            <nav class="p-4 space-y-2 overflow-y-auto scrollbar-glow">
              <RoleBasedNavigation />
            </nav>
          </aside>

          <!-- Mobile Navigation Menu -->
          <div
            v-if="showMobileMenu"
            class="fixed inset-0 z-50 lg:hidden"
            @click="showMobileMenu = false"
          >
            <div class="fixed inset-0 bg-[color:var(--bg-main)] opacity-80 backdrop-blur-sm" />
            <div
              class="fixed left-0 top-0 bottom-0 w-72 bg-[color:var(--bg-surface-strong)] border-r border-[color:var(--border-muted)] glass-panel"
              @click.stop
            >
              <div class="h-16 flex items-center justify-between px-4 border-b border-[color:var(--border-muted)]">
                <span class="text-base font-semibold">hydro 2.0</span>
                <button
                  @click="showMobileMenu = false"
                  class="p-2 rounded-md text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)]"
                >
                  <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <nav class="p-4 space-y-1 overflow-y-auto" @click="showMobileMenu = false">
                <RoleBasedNavigation />
              </nav>
            </div>
          </div>

          <main class="flex-1 flex flex-col min-h-0 overflow-hidden relative z-10">
            <!-- Header Status Bar (всегда видимый) -->
            <div class="shrink-0">
              <HeaderStatusBar />
            </div>

            <header class="h-16 flex items-center justify-between px-4 border-b border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] lg:hidden backdrop-blur-xl shrink-0">
              <div class="flex items-center gap-3">
                <button
                  @click="showMobileMenu = !showMobileMenu"
                  class="p-2 rounded-md text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)]"
                >
                  <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
                  </svg>
                </button>
                <span class="text-base font-semibold">hydro 2.0</span>
              </div>
              <span class="text-xs text-[color:var(--text-dim)] hidden sm:inline">Ctrl+K — Командная палитра</span>
            </header>

            <div class="flex-1 min-h-0 overflow-y-auto px-4 py-4 pb-20 lg:pb-6 space-y-4">
              <div class="glass-panel border border-[color:var(--border-muted)] px-4 py-3 rounded-2xl shadow-[var(--shadow-card)]">
                <Breadcrumbs />
              </div>
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

          <aside class="hidden xl:flex w-80 shrink-0 border-l border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] glass-panel flex-col h-screen">
            <div class="h-16 flex items-center px-4 border-b border-[color:var(--border-muted)] shrink-0">
              <span class="text-sm text-[color:var(--text-dim)] uppercase tracking-[0.2em]">события</span>
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
    </div>
  </ErrorBoundary>
</template>
  
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import CommandPalette from '@/Components/CommandPalette.vue'
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

// Инициализируем keyboard shortcuts
onMounted(() => {
  useKeyboardShortcuts()
})
</script>
  
<style>
.bg-neutral-925 { background-color: var(--bg-surface-strong); }
.bg-neutral-850 { background-color: var(--bg-elevated); }

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
  background-color: var(--border-muted);
  border-radius: 3px;
}

.scrollbar-thin::-webkit-scrollbar-thumb:hover {
  background-color: var(--border-strong);
}
</style>
