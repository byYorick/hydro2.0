<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Admin</h1>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
      <Card><div class="text-sm font-semibold mb-2">Zones</div><Link href="/admin/zones" class="text-sky-400">Manage Zones</Link></Card>
      <Card><div class="text-sm font-semibold mb-2">Recipes</div><Link href="/admin/recipes" class="text-sky-400">Manage Recipes</Link></Card>
      <Card><div class="text-sm font-semibold mb-2">Users</div><div class="text-neutral-400 text-sm">Coming soon</div></Card>
    </div>
  </AppLayout>
</template>

<script setup>
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import { Link } from '@inertiajs/vue3'
</script>

