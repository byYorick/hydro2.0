<template>
  <div class="min-h-screen bg-neutral-950 text-neutral-100">
    <div class="flex">
      <aside class="hidden lg:block w-64 shrink-0 border-r border-neutral-800 bg-neutral-925">
        <div class="h-16 flex items-center px-4 border-b border-neutral-800">
          <span class="text-base font-semibold">hydro 2.0</span>
        </div>
        <nav class="p-3 space-y-1">
          <NavLink href="/" label="Dashboard" />
          <NavLink href="/zones" label="Zones" />
          <NavLink href="/devices" label="Devices" />
          <NavLink href="/recipes" label="Recipes" />
          <NavLink href="/alerts" label="Alerts" />
          <NavLink href="/settings" label="Settings" />
        </nav>
      </aside>
      <main class="flex-1">
        <header class="h-16 flex items-center justify-between px-4 border-b border-neutral-800 bg-neutral-925 lg:hidden">
          <span class="text-base font-semibold">hydro 2.0</span>
          <span class="text-xs text-neutral-400">Ctrl+K — Command Palette</span>
        </header>
        <div class="px-4 py-4">
          <slot />
        </div>
        <CommandPalette />
      </main>
      <aside class="hidden xl:block w-80 shrink-0 border-l border-neutral-800 bg-neutral-925">
        <div class="h-16 flex items-center px-4 border-b border-neutral-800">
          <span class="text-sm text-neutral-400">Events</span>
        </div>
        <div class="p-4 text-neutral-400 text-sm">
          <slot name="context" />
        </div>
      </aside>
    </div>
  </div>
  </template>
  
  <script setup>
  import CommandPalette from '@/Components/CommandPalette.vue'
  import NavLink from '@/Components/NavLink.vue'
  </script>
  
  <style>
  :root {
    color-scheme: dark;
  }
  .bg-neutral-925 { background-color: #0f0f10; }
  .bg-neutral-850 { background-color: #1a1a1b; }
  </style>

