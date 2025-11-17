<template>
  <div class="min-h-screen bg-neutral-950 text-neutral-100">
    <div class="flex">
      <aside class="hidden lg:block w-64 shrink-0 border-r border-neutral-800 bg-neutral-925">
        <div class="h-16 flex items-center px-4 border-b border-neutral-800">
          <span class="text-base font-semibold">hydro 2.0</span>
        </div>
        <nav class="p-3 space-y-1">
          <NavLink href="/" label="Панель управления" />
          <NavLink href="/zones" label="Зоны" />
          <NavLink href="/devices" label="Устройства" />
          <NavLink href="/recipes" label="Рецепты" />
          <NavLink href="/alerts" label="Алерты" />
          <NavLink href="/settings" label="Настройки" />
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
            <NavLink href="/" label="Панель управления" />
            <NavLink href="/zones" label="Зоны" />
            <NavLink href="/devices" label="Устройства" />
            <NavLink href="/recipes" label="Рецепты" />
            <NavLink href="/alerts" label="Алерты" />
            <NavLink href="/settings" label="Настройки" />
          </nav>
        </div>
      </div>
      
      <main class="flex-1">
        <header class="h-16 flex items-center justify-between px-4 border-b border-neutral-800 bg-neutral-925 lg:hidden">
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
        <div class="px-4 py-4">
          <slot />
        </div>
        <CommandPalette />
      </main>
      <aside class="hidden xl:block w-80 shrink-0 border-l border-neutral-800 bg-neutral-925">
        <div class="h-16 flex items-center px-4 border-b border-neutral-800">
          <span class="text-sm text-neutral-400">События</span>
        </div>
        <div class="p-4 text-neutral-400 text-sm">
          <slot name="context" />
        </div>
      </aside>
    </div>
  </div>
  </template>
  
  <script setup>
  import { ref } from 'vue'
  import CommandPalette from '@/Components/CommandPalette.vue'
  import NavLink from '@/Components/NavLink.vue'
  
  const showMobileMenu = ref(false)
  </script>
  
  <style>
  :root {
    color-scheme: dark;
  }
  .bg-neutral-925 { background-color: #0f0f10; }
  .bg-neutral-850 { background-color: #1a1a1b; }
  </style>

