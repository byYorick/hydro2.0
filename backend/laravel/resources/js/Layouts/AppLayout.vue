<template>
  <ErrorBoundary>
    <div class="app-shell">
      <div class="app-frame">
        <aside
          class="app-sidebar hidden shrink-0 flex-col border-r border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] lg:flex"
          :class="collapsed ? 'w-16' : 'w-56'"
        >
          <div
            class="flex h-16 shrink-0 items-center border-b border-[color:var(--border-muted)]"
            :class="collapsed ? 'justify-center px-2' : 'gap-3 px-4'"
          >
            <div
              class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[color:var(--btn-primary-bg)] text-xl font-semibold text-[color:var(--btn-primary-text)]"
              aria-hidden="true"
            >
              h
            </div>
            <div
              v-if="!collapsed"
              class="min-w-0"
            >
              <div class="text-base font-semibold leading-tight tracking-tight">
                hydro 2.0
              </div>
              <div class="mt-0.5 text-[11px] text-[color:var(--text-muted)]">
                Управление выращиванием
              </div>
            </div>
          </div>

          <nav
            id="app-sidebar-nav"
            class="min-h-0 flex-1 overflow-y-auto overflow-x-hidden py-5 scrollbar-thin"
            :class="collapsed ? 'px-2' : 'px-3'"
            aria-label="Разделы"
          >
            <RoleBasedNavigation :collapsed="collapsed" />
          </nav>

          <div class="shrink-0 space-y-2 border-t border-[color:var(--border-muted)] p-2">
            <UserMenu :collapsed="collapsed" />
            <div :class="collapsed ? 'flex justify-center' : 'flex justify-end'">
              <button
                type="button"
                class="app-icon-button"
                :aria-expanded="!collapsed"
                aria-controls="app-sidebar-nav"
                :aria-label="collapsed ? 'Развернуть меню' : 'Свернуть меню'"
                :title="collapsed ? 'Развернуть меню' : 'Свернуть меню'"
                @click="toggleSidebar"
              >
                <svg
                  class="h-4 w-4"
                  :class="collapsed ? 'rotate-180' : ''"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                  aria-hidden="true"
                >
                  <path d="m15 18-6-6 6-6" />
                </svg>
              </button>
            </div>
          </div>
        </aside>

        <main class="relative z-10 flex min-h-0 min-w-0 flex-1 flex-col">
          <div class="shrink-0">
            <HeaderStatusBar />
          </div>
          <header class="app-topbar">
            <div class="flex min-w-0 items-center gap-3">
              <button
                type="button"
                class="app-icon-button lg:hidden"
                aria-label="Открыть меню"
                :aria-expanded="showMobileMenu"
                aria-controls="mobile-nav"
                @click="showMobileMenu = true"
              >
                <svg
                  class="h-5 w-5"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
              <span class="text-base font-semibold lg:hidden">hydro 2.0</span>
              <div
                v-if="showBreadcrumbs"
                class="hidden min-w-0 lg:block"
              >
                <Breadcrumbs />
              </div>
              <span
                v-else
                class="hidden text-sm text-[color:var(--text-muted)] lg:inline"
              >Запуск выращивания</span>
            </div>
            <div class="flex shrink-0 items-center gap-2">
              <button
                type="button"
                class="app-icon-button sm:w-auto sm:gap-2 sm:px-3"
                aria-label="Открыть поиск и командную палитру"
                title="Поиск и команды (Ctrl+K)"
                @click="commandPalette?.open()"
              >
                <svg
                  class="h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                  aria-hidden="true"
                >
                  <circle
                    cx="10.5"
                    cy="10.5"
                    r="6.5"
                  /><path d="m16 16 5 5" />
                </svg>
                <span class="hidden text-xs sm:inline">Поиск</span>
                <kbd class="hidden rounded border border-[color:var(--border-muted)] px-1 text-[11px] text-[color:var(--text-muted)] md:inline">Ctrl K</kbd>
              </button>
              <button
                type="button"
                class="app-icon-button sm:w-auto sm:gap-2 sm:px-3"
                :aria-label="eventsCollapsed ? contextLabel : 'Закрыть панель'"
                :title="contextLabel"
                :aria-expanded="!eventsCollapsed"
                aria-controls="events-rail-body"
                data-testid="events-rail-toggle"
                @click="toggleEventsRail"
              >
                <svg
                  class="h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                  aria-hidden="true"
                >
                  <path d="M4 5h16v14H4zM15 5v14M7 9h4M7 13h4" />
                </svg>
                <span class="hidden text-xs sm:inline">{{ hasContext ? 'События' : 'Избранное' }}</span>
              </button>
            </div>
          </header>

          <div class="app-page min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain">
            <Transition
              name="page"
              mode="out-in"
            >
              <div
                :key="page.url"
                class="min-w-0"
              >
                <slot></slot>
              </div>
            </Transition>
          </div>
          <CommandPalette ref="commandPalette" />
          <ToastContainer />
          <MobileNavigation
            :menu-open="showMobileMenu"
            @open-menu="showMobileMenu = true"
          />
        </main>
      </div>

      <Modal
        id="mobile-nav"
        :open="showMobileMenu"
        title="Разделы"
        placement="left"
        hide-default-cancel
        @close="showMobileMenu = false"
      >
        <nav
          aria-label="Все разделы"
          @click="showMobileMenu = false"
        >
          <RoleBasedNavigation />
        </nav>
      </Modal>
      <Modal
        id="events-rail-body"
        :open="!eventsCollapsed"
        :title="contextLabel"
        placement="right"
        hide-default-cancel
        data-testid="events-rail"
        @close="closeEventsRail"
      >
        <div class="flex min-h-full flex-col gap-6">
          <FavoritesWidget />
          <HistoryWidget />
          <div
            v-if="hasContext"
            class="flex min-h-0 flex-1 flex-col"
          >
            <slot name="context"></slot>
          </div>
        </div>
      </Modal>
    </div>
  </ErrorBoundary>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, useSlots, watch } from 'vue'
import { usePage } from '@inertiajs/vue3'
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
import Modal from '@/Components/Modal.vue'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'

const page = usePage()
const slots = useSlots()
const showBreadcrumbs = computed(() => !String(page.url || '').startsWith('/launch'))
const hasContext = computed(() => Boolean(slots.context))
const contextLabel = computed(() => hasContext.value ? 'События и избранное' : 'Избранное и история')
const showMobileMenu = ref(false)
const collapsed = ref(false)
const eventsCollapsed = ref(true)
const commandPalette = ref<InstanceType<typeof CommandPalette> | null>(null)
const EVENTS_RAIL_STORAGE_KEY = 'events-rail-collapsed'

function toggleSidebar() {
  collapsed.value = !collapsed.value
  localStorage.setItem('sidebar-collapsed', String(collapsed.value))
}

function toggleEventsRail() {
  eventsCollapsed.value = !eventsCollapsed.value
  localStorage.setItem(EVENTS_RAIL_STORAGE_KEY, String(eventsCollapsed.value))
}

function closeEventsRail() {
  eventsCollapsed.value = true
  localStorage.setItem(EVENTS_RAIL_STORAGE_KEY, 'true')
}

onMounted(() => {
  collapsed.value = localStorage.getItem('sidebar-collapsed') === 'true'
  eventsCollapsed.value = localStorage.getItem(EVENTS_RAIL_STORAGE_KEY) !== 'false'
  useKeyboardShortcuts()
})

watch(() => page.url, () => {
  showMobileMenu.value = false
  closeEventsRail()
})
</script>

<style>
.page-enter-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.page-leave-active { transition: opacity 0.1s ease; }
.page-enter-from { opacity: 0; transform: translateY(3px); }
.page-leave-to { opacity: 0; }

.scrollbar-thin::-webkit-scrollbar { width: 6px; }
.scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
.scrollbar-thin::-webkit-scrollbar-thumb { background-color: var(--border-muted); border-radius: 3px; }
.scrollbar-thin::-webkit-scrollbar-thumb:hover { background-color: var(--border-strong); }

@media (prefers-reduced-motion: reduce) {
  .page-enter-active,
  .page-leave-active { transition: none; }
  .page-enter-from { transform: none; }
}
</style>
