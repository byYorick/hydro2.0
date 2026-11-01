<template>
  <nav
    v-if="items.length > 0"
    class="flex items-center gap-1.5 text-xs"
    aria-label="Breadcrumb"
  >
    <ol class="flex items-center gap-2 flex-wrap">
      <li
        v-for="(item, index) in items"
        :key="index"
        class="flex items-center gap-1.5"
      >
        <Link
          v-if="item.href && index < items.length - 1"
          :href="item.href"
          class="text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] transition-colors"
        >
          {{ item.label }}
        </Link>
        <span
          v-else
          class="text-[color:var(--text-primary)] font-medium"
          :class="{ 'text-[color:var(--text-muted)]': index < items.length - 1 }"
          :aria-current="index === items.length - 1 ? 'page' : undefined"
        >
          {{ item.label }}
        </span>
        <svg
          v-if="index < items.length - 1"
          class="w-3 h-3 text-[color:var(--text-dim)] shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M9 5l7 7-7 7"
          />
        </svg>
      </li>
    </ol>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import { buildAutoBreadcrumbs, type BreadcrumbItem } from '@/utils/breadcrumbs'

interface Props {
  items?: BreadcrumbItem[]
  autoGenerate?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  items: () => [],
  autoGenerate: true,
})

const page = usePage()

const autoItems = computed(() => {
  if (!props.autoGenerate) {
    return []
  }
  return buildAutoBreadcrumbs(String(page.url || '/'), page.props as Record<string, unknown>)
})

const items = computed(() => {
  return props.items.length > 0 ? props.items : autoItems.value
})
</script>
