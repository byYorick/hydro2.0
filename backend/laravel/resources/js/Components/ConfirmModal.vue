<template>
  <Modal
    :open="open"
    :title="title"
    @close="$emit('close')"
  >
    <slot>
      <div class="text-sm text-[color:var(--text-muted)]">
        {{ message }}
      </div>
    </slot>
    <template #footer>
      <Button
        size="sm"
        variant="secondary"
        @click="$emit('close')"
      >
        {{ cancelText }}
      </Button>
      <Button 
        size="sm" 
        :variant="confirmVariant"
        :disabled="loading || confirmDisabled"
        @click="$emit('confirm')"
      >
        {{ loading ? loadingText : confirmText }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import Modal from '@/Components/Modal.vue'
import Button from '@/Components/Button.vue'
import type { ButtonVariant } from '@/Components/Button.vue'

interface Props {
  open?: boolean
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  confirmVariant?: ButtonVariant
  loading?: boolean
  confirmDisabled?: boolean
  loadingText?: string
}

withDefaults(defineProps<Props>(), {
  open: false,
  title: 'Подтверждение',
  confirmText: 'Подтвердить',
  cancelText: 'Отмена',
  confirmVariant: 'primary',
  loading: false,
  confirmDisabled: false,
  loadingText: 'Загрузка...'
})

defineEmits<{
  close: []
  confirm: []
}>()
</script>
