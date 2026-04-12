<template>
  <!-- Collapsed: icon only + tooltip (Teleport → position:fixed, не режется overflow:hidden сайдбара) -->
  <div v-if="collapsed" class="relative">
    <Link
      ref="linkEl"
      :href="href"
      :prefetch="true"
      class="flex items-center justify-center w-10 h-10 rounded-xl transition-colors"
      :class="isActive
        ? 'nav-link--active text-[color:var(--nav-active-text)]'
        : 'text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)]'"
      @mouseenter="onTipEnter"
      @mouseleave="showTip = false"
    >
      <svg
        v-if="icon"
        class="h-5 w-5 shrink-0"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
        v-html="icon"
      />
    </Link>
    <Teleport to="body">
      <div
        v-if="showTip"
        class="fixed z-[200] pointer-events-none whitespace-nowrap rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-2.5 py-1.5 text-xs font-medium text-[color:var(--text-primary)] shadow-lg"
        :style="{ top: `${tipTop}px`, left: `${tipLeft}px`, transform: 'translateY(-50%)' }"
      >
        {{ label }}
        <span class="absolute right-full top-1/2 -translate-y-1/2 border-4 border-transparent border-r-[color:var(--border-muted)]"></span>
      </div>
    </Teleport>
  </div>

  <!-- Expanded: icon + label -->
  <Link
    v-else
    :href="href"
    :prefetch="true"
    :class="[
      mobile
        ? 'flex flex-col items-center justify-center text-xs transition-colors px-2 py-2'
        : 'nav-link text-sm min-w-0',
      mobile
        ? isActive ? 'text-[color:var(--text-primary)]' : 'text-[color:var(--text-dim)]'
        : isActive ? 'nav-link--active' : ''
    ]"
  >
    <svg
      v-if="icon && !mobile"
      class="h-4 w-4 shrink-0"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
      v-html="icon"
    />
    <slot><span class="truncate">{{ label }}</span></slot>
  </Link>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'

const props = defineProps<{
  href: string
  label: string
  icon?: string
  collapsed?: boolean
  mobile?: boolean
}>()

const page = usePage()
const isActive = computed(() => {
  const current = page.url || '/'
  return current === props.href || (props.href !== '/' && current.startsWith(props.href))
})

const linkEl = ref<{ $el: HTMLElement } | null>(null)
const showTip = ref(false)
const tipTop = ref(0)
const tipLeft = ref(0)

function onTipEnter() {
  const el = linkEl.value?.$el
  if (!el) return
  const r = el.getBoundingClientRect()
  tipTop.value = r.top + r.height / 2
  tipLeft.value = r.right + 12
  showTip.value = true
}
</script>
