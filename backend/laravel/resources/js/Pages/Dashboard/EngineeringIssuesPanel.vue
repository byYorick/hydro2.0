<template>
  <section
    class="surface-card rounded-2xl border border-[color:var(--border-muted)] p-4 md:p-5"
    data-testid="dashboard-engineering-issues"
  >
    <div class="space-y-3">
      <h2 class="text-sm font-semibold text-[color:var(--text-primary)]">
        Проблемные узлы и зоны
      </h2>

      <p
        v-if="issues.length === 0"
        class="text-sm text-[color:var(--text-muted)]"
      >
        Проблемных узлов нет
      </p>

      <ul
        v-else
        class="space-y-2"
      >
        <li
          v-for="issue in issues"
          :key="issue.zoneId"
          class="rounded-xl border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-3"
        >
          <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0 space-y-1">
              <div class="truncate text-sm font-medium text-[color:var(--text-primary)]">
                {{ issue.zoneName }}
              </div>
              <ul class="space-y-0.5 text-xs text-[color:var(--text-muted)]">
                <li
                  v-for="reason in issue.reasons"
                  :key="reason"
                >
                  {{ reason }}
                </li>
              </ul>
            </div>
            <Link
              :href="issue.openHref"
              class="shrink-0 text-xs text-[color:var(--accent-cyan)] hover:underline"
            >
              Открыть зону
            </Link>
          </div>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Link } from '@inertiajs/vue3'
import type { EngineeringIssue } from './dashboardRoleView'

defineProps<{
  issues: EngineeringIssue[]
}>()
</script>
