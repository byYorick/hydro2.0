<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center p-4"
  >
    <div
      class="absolute inset-0 bg-[color:var(--bg-main)] opacity-80"
      @click="$emit('close')"
    ></div>
    <div 
      class="relative w-full rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-4 max-h-[90vh] overflow-y-auto shadow-[var(--shadow-card)]"
      :class="size === 'large' ? 'max-w-4xl' : 'max-w-lg'"
      :data-testid="$attrs['data-testid']"
    >
      <div class="mb-2 text-base font-semibold text-[color:var(--text-primary)]">
        {{ title }}
      </div>
      <div class="mb-4 text-sm text-[color:var(--text-muted)]">
        <slot></slot>
      </div>
      <div class="flex justify-end gap-2">
        <Button
          variant="secondary"
          @click="$emit('close')"
        >
          Отмена
        </Button>
        <slot name="footer"></slot>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Button from './Button.vue'

interface Props {
  open?: boolean
  title?: string
  size?: 'default' | 'large'
}

withDefaults(defineProps<Props>(), {
  open: false,
  title: '',
  size: 'default'
})

defineEmits<{
  close: []
}>()
</script>
