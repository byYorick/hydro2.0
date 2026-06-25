<template>
  <div
    class="space-y-3"
    data-testid="authority-field-catalog-form"
  >
    <section
      v-for="section in sections"
      :key="section.key"
      class="settings-group-card"
    >
      <button
        type="button"
        class="settings-group-card__toggle"
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
          <SettingsFieldHelp
            v-if="section.description || section.help"
            :title="section.label"
            :summary="section.description"
            :help="section.help"
            :test-id="`authority-section-help-${section.key}`"
          />
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
        class="settings-group-card__body"
      >
        <div class="grid gap-3 md:grid-cols-2">
          <SettingsFieldCard
            v-for="field in section.fields"
            :key="field.path"
            :label="field.label"
            :description="field.description"
            :help="field.help"
            :unit="field.unit"
            :field-id="fieldInputId(field.path)"
            :test-id="`authority-field-card-${field.path}`"
            :help-test-id="`authority-field-help-${field.path}`"
            :show-description="field.type !== 'boolean'"
          >
            <label
              v-if="field.type === 'boolean'"
              class="flex items-center gap-2 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] px-3 py-2.5 text-sm"
            >
              <input
                :id="fieldInputId(field.path)"
                v-model="draft[field.path]"
                type="checkbox"
                :data-testid="`authority-field-${field.path}`"
              />
              <span class="text-[color:var(--text-primary)]">{{ field.description }}</span>
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
          </SettingsFieldCard>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import SettingsFieldCard from '@/Components/Settings/SettingsFieldCard.vue'
import SettingsFieldHelp from '@/Components/Settings/SettingsFieldHelp.vue'
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
