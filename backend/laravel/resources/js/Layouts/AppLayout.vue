<template>
  <ErrorBoundary>
    <div class="app-shell">
      <div class="min-h-screen text-[color:var(--text-primary)]">
        <div class="flex h-screen overflow-hidden">

          <!-- Desktop Sidebar -->
          <aside
            class="hidden lg:flex shrink-0 flex-col border-r border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] backdrop-blur-xl glass-panel transition-all duration-300 relative z-20"
            :class="collapsed ? 'w-16' : 'w-64'"
          >
            <!-- Logo -->
            <div
              class="h-14 flex items-center border-b border-[color:var(--border-muted)] shrink-0 transition-all duration-300"
              :class="collapsed ? 'justify-center px-2' : 'px-4 gap-3'"
            >
              <div class="h-7 w-7 shrink-0 rounded-lg bg-[linear-gradient(135deg,var(--accent-green),var(--accent-cyan))] shadow-[0_0_0_1px_var(--badge-success-border)]"></div>
              <Transition name="fade-slide">
                <div v-if="!collapsed" class="min-w-0">
                  <div class="text-sm font-semibold tracking-tight leading-none">hydro 2.0</div>
                  <div class="text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-dim)] mt-0.5">agronomy deck</div>
                </div>
              </Transition>
            </div>

            <!-- Nav -->
            <nav
              class="flex-1 py-2 overflow-y-auto overflow-x-hidden scrollbar-glow transition-all duration-300"
              :class="collapsed ? 'px-2' : 'px-3'"
            >
              <RoleBasedNavigation :collapsed="collapsed" />
            </nav>

            <!-- User + Toggle -->
            <div class="shrink-0 border-t border-[color:var(--border-muted)] p-2 space-y-1">
              <UserMenu :collapsed="collapsed" />
              <div :class="collapsed ? 'flex justify-center' : 'flex justify-end'">
                <button
                  class="p-1.5 rounded-lg text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)] transition-colors"
                  :title="collapsed ? 'Развернуть меню' : 'Свернуть меню'"
                  @click="toggleSidebar"
                >
                  <svg
                    class="h-4 w-4 transition-transform duration-300"
                    :class="collapsed ? 'rotate-180' : ''"
                    viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
                  >
                    <path d="M15 18l-6-6 6-6"/>
                  </svg>
                </button>
              </div>
            </div>
          </aside>

          <!-- Mobile Navigation Menu -->
          <div
            v-if="showMobileMenu"
            class="fixed inset-0 z-50 lg:hidden"
            @click="showMobileMenu = false"
          >
            <div class="fixed inset-0 bg-[color:var(--bg-main)] opacity-80 backdrop-blur-sm"></div>
            <div
              class="fixed left-0 top-0 bottom-0 w-72 bg-[color:var(--bg-surface-strong)] border-r border-[color:var(--border-muted)] glass-panel"
              @click.stop
            >
              <div class="h-16 flex items-center justify-between px-4 border-b border-[color:var(--border-muted)]">
                <span class="text-base font-semibold">hydro 2.0</span>
                <button
                  class="p-2 rounded-md text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)]"
                  @click="showMobileMenu = false"
                >
                  <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                  </svg>
                </button>
              </div>
              <nav class="p-4 space-y-1 overflow-y-auto" @click="showMobileMenu = false">
                <RoleBasedNavigation />
              </nav>
            </div>
          </div>

          <main class="flex-1 flex flex-col min-h-0 relative z-10">
            <!-- Header Status Bar -->
            <div class="shrink-0">
              <HeaderStatusBar />
            </div>

            <!-- Mobile header -->
            <header class="h-16 flex items-center justify-between px-4 border-b border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] lg:hidden backdrop-blur-xl shrink-0">
              <div class="flex items-center gap-3">
                <button
                  class="p-2 rounded-md text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)]"
                  @click="showMobileMenu = !showMobileMenu"
                >
                  <svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
                  </svg>
                </button>
                <span class="text-base font-semibold">hydro 2.0</span>
              </div>
              <span class="text-xs text-[color:var(--text-dim)] hidden sm:inline">Ctrl+K — Командная палитра</span>
            </header>

            <div class="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 py-3 pb-20 lg:pb-6 space-y-2">
              <div class="glass-panel border border-[color:var(--border-muted)] px-3 py-1.5 rounded-xl shadow-[var(--shadow-card)]">
                <Breadcrumbs />
              </div>
              <Transition name="page" mode="out-in">
                <div :key="$page.url">
                  <slot></slot>
                </div>
              </Transition>
            </div>
            <CommandPalette />
            <ToastContainer />
            <MobileNavigation />

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
                <slot name="context"></slot>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  </ErrorBoundary>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
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
const collapsed = ref(false)

function toggleSidebar() {
  collapsed.value = !collapsed.value
  localStorage.setItem('sidebar-collapsed', String(collapsed.value))
}

onMounted(() => {
  collapsed.value = localStorage.getItem('sidebar-collapsed') === 'true'
  useKeyboardShortcuts()
})

watch(showMobileMenu, (val) => {
  if (val) document.body.style.overflow = 'hidden'
  else document.body.style.overflow = ''
})
</script>

<style>
.bg-neutral-925 { background-color: var(--bg-surface-strong); }
.bg-neutral-850 { background-color: var(--bg-elevated); }

.fade-slide-enter-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.fade-slide-leave-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.fade-slide-enter-from { opacity: 0; transform: translateX(-6px); }
.fade-slide-leave-to { opacity: 0; transform: translateX(-6px); }

.page-enter-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.page-leave-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.page-enter-from { opacity: 0; transform: translateY(4px); }
.page-enter-to { opacity: 1; transform: translateY(0); }
.page-leave-from { opacity: 1; transform: translateY(0); }
.page-leave-to { opacity: 0; transform: translateY(-4px); }

.scrollbar-thin::-webkit-scrollbar { width: 6px; }
.scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
.scrollbar-thin::-webkit-scrollbar-thumb { background-color: var(--border-muted); border-radius: 3px; }
.scrollbar-thin::-webkit-scrollbar-thumb:hover { background-color: var(--border-strong); }
</style>
