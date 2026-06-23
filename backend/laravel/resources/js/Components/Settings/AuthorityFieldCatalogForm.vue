<template>
  <div
    class="space-y-3"
    data-testid="authority-field-catalog-form"
  >
    <section
      v-for="section in sections"
      :key="section.key"
      class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] overflow-hidden"
    >
      <button
        type="button"
        class="w-full flex flex-col gap-1 px-4 py-3 text-left hover:bg-[color:var(--bg-surface-strong)] transition-colors"
        :data-testid="`authority-section-toggle-${section.key}`"
        @click="toggleSection(section.key)"
      >
        <div class="flex items-center gap-2">
          <span
            class="inline-block text-[color:var(--text-muted)] transition-transform"
            :class="openSections.has(section.key) ? 'rotate-90' : ''"
          >
            ▸
          </span>
          <span class="text-sm font-semibold text-[color:var(--text-primary)]">
            {{ section.label }}
          </span>
        </div>
        <p
          v-if="section.description"
          class="text-xs text-[color:var(--text-dim)] pl-6"
        >
          {{ section.description }}
        </p>
      </button>

      <div
        v-if="openSections.has(section.key)"
        class="border-t border-[color:var(--border-muted)] px-4 py-4"
      >
        <div class="grid gap-4 md:grid-cols-2">
          <div
            v-for="field in section.fields"
            :key="field.path"
            class="space-y-1.5"
          >
            <label
              class="block text-xs font-medium text-[color:var(--text-muted)]"
              :for="fieldInputId(field.path)"
            >
              {{ field.label }}
              <span
                v-if="field.unit"
                class="text-[10px] text-[color:var(--text-dim)] ml-1"
              >
                ({{ field.unit }})
              </span>
            </label>

            <label
              v-if="field.type === 'boolean'"
              class="flex items-center gap-2 rounded-xl border border-[color:var(--border-muted)] px-3 py-2 text-sm"
            >
              <input
                :id="fieldInputId(field.path)"
                v-model="draft[field.path]"
                type="checkbox"
                :data-testid="`authority-field-${field.path}`"
              />
              <span>{{ field.description }}</span>
            </label>

            <textarea
              v-else-if="field.type === 'json'"
              :id="fieldInputId(field.path)"
              v-model="draft[field.path]"
              rows="6"
              class="input-field w-full font-mono text-xs"
              :data-testid="`authority-field-${field.path}`"
            />

            <input
              v-else
              :id="fieldInputId(field.path)"
              v-model="draft[field.path]"
              :type="field.type === 'string' ? 'text' : 'number'"
              :step="field.step ?? (field.type === 'integer' ? 1 : 'any')"
              :min="field.min"
              :max="field.max"
              class="input-field w-full"
              :data-testid="`authority-field-${field.path}`"
            />

            <p
              v-if="field.type !== 'boolean' && field.description"
              class="text-[11px] leading-relaxed text-[color:var(--text-dim)]"
            >
              {{ field.description }}
            </p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { SystemSettingsSection } from '@/types/SystemSettings'

const props = defineProps<{
  sections: SystemSettingsSection[]
  modelValue: Record<string, string | number | boolean | undefined>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, string | number | boolean | undefined>]
}>()

const draft = ref<Record<string, string | number | boolean | undefined>>({ ...props.modelValue })
const openSections = ref<Set<string>>(new Set(props.sections.map((section) => section.key)))

watch(
  () => props.modelValue,
  (value) => {
    draft.value = { ...value }
  },
  { deep: true },
)

watch(
  draft,
  (value) => {
    emit('update:modelValue', { ...value })
  },
  { deep: true },
)

watch(
  () => props.sections,
  (sections) => {
    openSections.value = new Set(sections.map((section) => section.key))
  },
)

function toggleSection(key: string): void {
  const next = new Set(openSections.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  openSections.value = next
}

function fieldInputId(path: string): string {
  return `authority-field-${path.replace(/[^a-zA-Z0-9_-]/g, '-')}`
}
</script>
