<template>
  <section
    class="surface-card rounded-2xl border border-[color:var(--border-muted)] p-4 md:p-5"
    data-testid="dashboard-shift-queue"
  >
    <div class="space-y-3">
      <div class="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
        <h2 class="text-sm font-semibold text-[color:var(--text-primary)]">
          Очередь смены
        </h2>
        <p
          v-if="items.length > 0"
          class="text-xs text-[color:var(--text-muted)]"
        >
          {{ items.length }} дел
        </p>
      </div>

      <p
        v-if="items.length === 0"
        class="text-sm text-[color:var(--text-primary)]"
        data-testid="dashboard-shift-empty"
      >
        Сегодня действий не требуется
      </p>

      <ul
        v-else
        class="space-y-2"
      >
        <li
          v-for="item in items"
          :key="item.zoneId"
          class="flex flex-col gap-2 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 sm:flex-row sm:items-center sm:justify-between"
        >
          <div class="min-w-0 space-y-0.5">
            <div class="truncate text-sm font-medium text-[color:var(--text-primary)]">
              {{ item.zoneName }}
            </div>
            <div class="text-xs text-[color:var(--text-muted)]">
              {{ item.reason }}
            </div>
          </div>
          <div class="flex flex-wrap gap-2">
            <Link
              :href="item.openHref"
              class="text-xs text-[color:var(--accent-cyan)] hover:underline"
            >
              Открыть зону
            </Link>
            <Link
              :href="item.alertsHref"
              class="text-xs text-[color:var(--accent-cyan)] hover:underline"
            >
              Тревоги
            </Link>
          </div>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Link } from '@inertiajs/vue3'
import type { ShiftQueueItem } from './dashboardRoleView'

defineProps<{
  items: ShiftQueueItem[]
}>()
</script>
