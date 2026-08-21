<template>
  <div
    class="space-y-3"
    data-testid="authority-field-catalog-form"
  >
    <div
      v-if="totalFields > SEARCH_THRESHOLD"
      class="flex flex-wrap items-center gap-2"
    >
      <input
        v-model="search"
        type="search"
        class="input-field w-full sm:w-64"
        placeholder="Поиск параметра"
        aria-label="Поиск параметра"
        data-testid="authority-field-search"
      />
      <span class="text-xs text-[color:var(--text-dim)]">
        {{ matchedFields }} из {{ totalFields }}
      </span>
    </div>

    <p
      v-if="visibleSections.length === 0"
      class="text-sm text-[color:var(--text-dim)]"
      data-testid="authority-field-empty"
    >
      Ничего не найдено. Попробуйте изменить запрос.
    </p>

    <section
      v-for="section in visibleSections"
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
            :class="isOpen(section.key) ? 'rotate-90' : ''"
          >
            ▸
          </span>
          <span class="text-sm font-semibold text-[color:var(--text-primary)]">
            {{ section.label }}
          </span>
          <span class="text-xs text-[color:var(--text-dim)]">
            {{ section.fields.length }}
          </span>
          <SettingsFieldHelp
            v-if="section.description || section.help"
            :title="section.label"
            :summary="section.description"
            :help="section.help"
            :test-id="`authority-section-help-${section.key}`"
          />
        </div>
      </button>

      <div
        v-if="isOpen(section.key)"
        class="settings-group-card__body"
      >
        <div class="settings-rows settings-rows--split">
          <SettingsFieldRow
            v-for="field in section.fields"
            :key="field.path"
            :label="field.label"
            :description="field.description"
            :help="field.help"
            :unit="field.unit"
            :field-id="fieldInputId(field.path)"
            :stacked="field.type === 'json'"
            :test-id="`authority-field-card-${field.path}`"
            :help-test-id="`authority-field-help-${field.path}`"
          >
            <label
              v-if="field.type === 'boolean'"
              class="inline-flex items-center gap-2 text-sm text-[color:var(--text-primary)]"
            >
              <input
                :id="fieldInputId(field.path)"
                v-model="draft[field.path]"
                type="checkbox"
                :data-testid="`authority-field-${field.path}`"
              />
              <span class="text-xs text-[color:var(--text-muted)]">
                {{ draft[field.path] ? 'включено' : 'выключено' }}
              </span>
            </label>

            <textarea
              v-else-if="field.type === 'json'"
              :id="fieldInputId(field.path)"
              v-model="draft[field.path]"
              rows="6"
              class="input-field settings-control--wide font-mono text-xs"
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
              class="input-field"
              :class="field.type === 'string' ? 'settings-control--text' : 'settings-control--num text-right'"
              :data-testid="`authority-field-${field.path}`"
            />
          </SettingsFieldRow>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import SettingsFieldRow from '@/Components/Settings/SettingsFieldRow.vue'
import SettingsFieldHelp from '@/Components/Settings/SettingsFieldHelp.vue'
import { isSameSettingsDraft } from '@/utils/settingsDraft'
import type { SystemSettingsField, SystemSettingsSection } from '@/types/SystemSettings'

/** Ниже этого числа полей поиск только мешает. */
const SEARCH_THRESHOLD = 12

const props = defineProps<{
  sections: SystemSettingsSection[]
  modelValue: Record<string, string | number | boolean | undefined>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, string | number | boolean | undefined>]
}>()

const draft = ref<Record<string, string | number | boolean | undefined>>({ ...props.modelValue })
const search = ref('')
const collapsedSections = ref<Set<string>>(collapsedKeys(props.sections))

const totalFields = computed(() => props.sections.reduce((sum, section) => sum + section.fields.length, 0))

const visibleSections = computed<SystemSettingsSection[]>(() => {
  const query = search.value.trim().toLowerCase()
  if (query === '') {
    return props.sections
  }

  return props.sections
    .map((section) => ({ ...section, fields: section.fields.filter((field) => matches(field, query)) }))
    .filter((section) => section.fields.length > 0)
})

const matchedFields = computed(() => visibleSections.value.reduce((sum, section) => sum + section.fields.length, 0))

watch(
  () => props.modelValue,
  (value) => {
    if (!isSameSettingsDraft(draft.value, value)) {
      draft.value = { ...value }
    }
  },
  { deep: true },
)

watch(
  draft,
  (value) => {
    if (!isSameSettingsDraft(value, props.modelValue)) {
      emit('update:modelValue', { ...value })
    }
  },
  { deep: true },
)

watch(
  () => props.sections.map((section) => section.key).join(','),
  () => {
    collapsedSections.value = collapsedKeys(props.sections)
  },
)

/** Первая секция открыта, остальные свёрнуты — иначе 30+ полей сразу на экране. */
function collapsedKeys(sections: SystemSettingsSection[]): Set<string> {
  return new Set(sections.slice(1).map((section) => section.key))
}

function matches(field: SystemSettingsField, query: string): boolean {
  return [field.label, field.description, field.path].some(
    (candidate) => typeof candidate === 'string' && candidate.toLowerCase().includes(query),
  )
}

function isOpen(key: string): boolean {
  // При активном поиске секции раскрыты, иначе найденное поле осталось бы скрытым.
  return search.value.trim() !== '' || !collapsedSections.value.has(key)
}

function toggleSection(key: string): void {
  const next = new Set(collapsedSections.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  collapsedSections.value = next
}

function fieldInputId(path: string): string {
  return `authority-field-${path.replace(/[^a-zA-Z0-9_-]/g, '-')}`
}
</script>
