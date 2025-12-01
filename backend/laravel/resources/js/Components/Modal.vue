<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <div class="absolute inset-0 bg-black/70" @click="$emit('close')"></div>
    <div 
      class="relative w-full rounded-xl border border-neutral-800 bg-neutral-925 p-4 max-h-[90vh] overflow-y-auto"
      :class="size === 'large' ? 'max-w-4xl' : 'max-w-lg'"
    >
      <div class="mb-2 text-base font-semibold">{{ title }}</div>
      <div class="mb-4 text-sm text-neutral-300"><slot /></div>
      <div class="flex justify-end gap-2">
        <Button variant="secondary" @click="$emit('close')">Отмена</Button>
        <slot name="footer" />
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
