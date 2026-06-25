<template>
  <button
    type="button"
    class="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] text-[10px] font-semibold text-[color:var(--text-muted)] hover:border-[color:var(--accent-green)] hover:text-[color:var(--accent-green)] transition-colors"
    :aria-label="`Подробнее: ${title}`"
    :data-testid="testId"
    @click.stop="open = true"
  >
    ?
  </button>

  <Modal
    :open="open"
    :title="title"
    size="large"
    hide-default-cancel
    :data-testid="`${testId}-modal`"
    @close="open = false"
  >
    <div class="space-y-3 text-sm text-[color:var(--text-primary)]">
      <p
        v-if="summary"
        class="text-xs text-[color:var(--text-dim)]"
      >
        {{ summary }}
      </p>
      <div class="whitespace-pre-line leading-relaxed">
        {{ bodyText }}
      </div>
    </div>
    <template #footer>
      <Button
        size="sm"
        :data-testid="`${testId}-close`"
        @click="open = false"
      >
        Понятно
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from '@/Components/Button.vue'
import Modal from '@/Components/Modal.vue'
import { resolveSettingsFieldHelp } from '@/utils/settingsFieldHelp'

const props = withDefaults(defineProps<{
  title: string
  summary?: string
  help?: string
  testId?: string
}>(), {
  summary: '',
  help: '',
  testId: 'settings-field-help',
})

const open = ref(false)

const bodyText = computed(() => resolveSettingsFieldHelp({
  title: props.title,
  summary: props.summary,
  help: props.help,
}))
</script>
