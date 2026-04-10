<template>
  <Card data-testid="correction-config-form">
    <div class="space-y-5">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div class="text-sm font-semibold">
            Correction Config
          </div>
          <div class="text-xs text-[color:var(--text-dim)] mt-1">
            Единый контракт для PID, таймингов, retry windows, safety и hot-reload.
          </div>
        </div>
        <div class="flex flex-wrap gap-3 text-xs text-[color:var(--text-dim)]">
          <span v-if="version !== null">Версия: {{ version }}</span>
          <span v-if="updatedAt">Обновлено: {{ formatDate(updatedAt) }}</span>
          <span v-if="lastAppliedVersion !== null">AE version: {{ lastAppliedVersion }}</span>
          <span v-if="lastAppliedAt">AE применил: {{ formatDate(lastAppliedAt) }}</span>
        </div>
      </div>

      <div class="grid gap-4 xl:grid-cols-[280px,1fr]">
        <aside class="space-y-4">
          <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
            <div>
              <label class="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
                Preset
              </label>
              <select
                v-model="selectedPresetId"
                class="input-select w-full"
                data-testid="correction-config-preset-select"
              >
                <option :value="null">
                  System default
                </option>
                <option
                  v-for="preset in presets"
                  :key="preset.id"
                  :value="preset.id"
                >
                  {{ preset.name }} ({{ preset.scope }})
                </option>
              </select>
            </div>

            <div class="text-[11px] text-[color:var(--text-dim)] min-h-[36px]">
              {{ selectedPreset?.description || 'Используется system default без preset overlay.' }}
            </div>

            <div class="space-y-2">
              <Button
                size="sm"
                variant="outline"
                class="w-full"
                data-testid="correction-config-apply-preset"
                @click="applySelectedPreset"
              >
                Применить preset в форму
              </Button>
              <Button
                size="sm"
                variant="outline"
                class="w-full"
                data-testid="correction-config-reset-defaults"
                @click="resetToDefaults"
              >
                Сбросить к system default
              </Button>
              <Button
                v-if="selectedPreset?.scope === 'custom'"
                size="sm"
                variant="outline"
                class="w-full"
                data-testid="correction-config-update-preset"
                :disabled="loading"
                @click="updateSelectedPreset"
              >
                Обновить custom preset
              </Button>
              <Button
                v-if="selectedPreset?.scope === 'custom'"
                size="sm"
                variant="danger"
                class="w-full"
                data-testid="correction-config-delete-preset"
                :disabled="loading"
                @click="deleteSelectedPreset"
              >
                Удалить custom preset
              </Button>
            </div>
          </div>

          <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
            <label class="flex items-center gap-2 text-sm">
              <input
                v-model="advancedMode"
                type="checkbox"
              />
              Advanced mode
            </label>

            <div>
              <div class="text-xs font-medium text-[color:var(--text-muted)] mb-2">
                Phase override
              </div>
              <div class="grid gap-2">
                <Button
                  v-for="phase in phases"
                  :key="phase"
                  size="sm"
                  variant="outline"
                  :data-testid="`correction-config-phase-select-${phase}`"
                  :class="{ 'bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)] border-[color:var(--badge-info-border)]': selectedPhase === phase }"
                  @click="selectedPhase = phase"
                >
                  {{ phase }}
                </Button>
              </div>
            </div>
          </div>

          <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
            <div class="text-xs font-medium text-[color:var(--text-muted)]">
              Сохранить как custom preset
            </div>
            <input
              v-model="newPresetName"
              type="text"
              class="input-field w-full"
              placeholder="Название preset"
              data-testid="correction-config-new-preset-name"
            />
            <textarea
              v-model="newPresetDescription"
              class="input-field w-full min-h-[88px]"
              placeholder="Описание"
              data-testid="correction-config-new-preset-description"
            ></textarea>
            <Button
              size="sm"
              class="w-full"
              data-testid="correction-config-save-preset"
              :disabled="loading || !newPresetName.trim()"
              @click="saveAsPreset"
            >
              Сохранить текущий config как preset
            </Button>
          </div>

          <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
            <div class="text-xs font-medium text-[color:var(--text-muted)]">
              History
            </div>
            <div
              v-if="history.length === 0"
              class="text-xs text-[color:var(--text-dim)]"
            >
              Нет ревизий.
            </div>
            <ul
              v-else
              class="space-y-2"
            >
              <li
                v-for="item in history.slice(0, 6)"
                :key="item.id"
                class="rounded-lg bg-[color:var(--surface-muted)] px-3 py-2"
              >
                <div class="text-xs font-medium">
                  v{{ item.version }} · {{ item.change_type }}
                </div>
                <div class="text-[11px] text-[color:var(--text-dim)]">
                  {{ item.preset?.name || 'System default' }} · {{ formatDate(item.changed_at) }}
                </div>
              </li>
            </ul>
          </div>
        </aside>

        <div class="space-y-5">
          <section class="space-y-4">
            <div>
              <div class="text-sm font-semibold">
                Base config
              </div>
              <div class="text-xs text-[color:var(--text-dim)] mt-1">
                Общие параметры коррекции для всех режимов до применения phase-specific overrides.
              </div>
            </div>

            <div
              v-for="section in visibleSections"
              :key="`base-${section.key}`"
              class="rounded-xl border border-[color:var(--border-muted)] p-4 space-y-4"
            >
              <div>
                <div class="text-sm font-medium">
                  {{ section.label }}
                </div>
                <div class="text-xs text-[color:var(--text-dim)] mt-1">
                  {{ section.description }}
                </div>
              </div>
              <div
                v-if="sectionRuntimeNote(section.key, baseForm)"
                class="rounded-lg border border-[color:var(--badge-info-border)] bg-[color:var(--badge-info-bg)] px-3 py-2 text-[11px] text-[color:var(--badge-info-text)]"
              >
                {{ sectionRuntimeNote(section.key, baseForm) }}
              </div>
              <div class="grid gap-4 md:grid-cols-2">
                <div
                  v-for="field in visibleFields(section.fields)"
                  :key="`base-${field.path}`"
                  class="space-y-1.5"
                >
                  <label class="block text-xs font-medium text-[color:var(--text-muted)]">{{ field.label }}</label>

                  <label
                    v-if="field.type === 'boolean'"
                    class="flex items-center gap-2 text-sm"
                  >
                    <input
                      :checked="Boolean(getByPath(baseForm, field.path))"
                      :data-testid="`correction-config-base-${field.path}`"
                      type="checkbox"
                      @change="setByPath(baseForm, field.path, ($event.target as HTMLInputElement).checked)"
                    />
                    <span>{{ field.description }}</span>
                  </label>

                  <select
                    v-else-if="field.type === 'enum'"
                    :value="String(getByPath(baseForm, field.path) ?? '')"
                    :data-testid="`correction-config-base-${field.path}`"
                    class="input-select w-full"
                    :disabled="Boolean(field.readonly)"
                    @change="setByPath(baseForm, field.path, ($event.target as HTMLSelectElement).value)"
                  >
                    <option
                      v-for="option in field.options || []"
                      :key="option"
                      :value="option"
                    >
                      {{ option }}
                    </option>
                  </select>

                  <input
                    v-else
                    :value="String(getByPath(baseForm, field.path) ?? '')"
                    :data-testid="`correction-config-base-${field.path}`"
                    :type="field.type === 'string' ? 'text' : 'number'"
                    :step="field.step ?? (field.type === 'integer' ? 1 : 'any')"
                    :min="field.min"
                    :max="field.max"
                    :disabled="Boolean(field.readonly)"
                    class="input-field w-full"
                    @input="handleScalarInput(baseForm, field, $event)"
                  />

                  <div
                    v-if="field.type !== 'boolean'"
                    class="text-[11px] text-[color:var(--text-dim)]"
                  >
                    {{ field.description }}
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section class="space-y-4">
            <div>
              <div class="text-sm font-semibold">
                Phase config: {{ selectedPhase }}
              </div>
              <div class="text-xs text-[color:var(--text-dim)] mt-1">
                Effective-конфигурация для выбранной фазы. На сохранении backend преобразует её в phase override diff.
              </div>
            </div>

            <div
              class="rounded-xl border border-[color:var(--border-muted)] p-4 space-y-4"
              data-testid="phase-effective-preview"
            >
              <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div class="text-sm font-medium">
                    Effective preview: {{ selectedPhase }}
                  </div>
                  <div class="text-xs text-[color:var(--text-dim)] mt-1">
                    Что реально уходит в runtime для выбранной фазы и где phase config отходит от base.
                  </div>
                </div>
                <div class="flex flex-wrap gap-2 text-[11px]">
                  <span class="rounded-full bg-[color:var(--surface-muted)] px-2.5 py-1">
                    Overrides: {{ phaseOverrideStats.overrideCount }}
                  </span>
                  <span class="rounded-full bg-[color:var(--surface-muted)] px-2.5 py-1">
                    Sections: {{ phaseOverrideStats.sectionCount }}
                  </span>
                  <span
                    v-if="phaseOverrideStats.hiddenOverrideCount > 0"
                    class="rounded-full border border-[color:var(--border-muted)] px-2.5 py-1 text-[color:var(--text-dim)]"
                  >
                    Hidden advanced: {{ phaseOverrideStats.hiddenOverrideCount }}
                  </span>
                </div>
              </div>

              <div class="grid gap-3 xl:grid-cols-3">
                <div
                  v-for="group in effectivePreviewGroups"
                  :key="group.key"
                  class="rounded-xl bg-[color:var(--surface-muted)] px-3 py-3"
                >
                  <div class="text-xs font-medium text-[color:var(--text-muted)]">
                    {{ group.label }}
                  </div>
                  <dl class="mt-3 space-y-2">
                    <div
                      v-for="item in group.items"
                      :key="item.path"
                      class="flex items-start justify-between gap-3 text-sm"
                    >
                      <dt class="text-[color:var(--text-dim)]">
                        {{ item.label }}
                      </dt>
                      <dd class="text-right font-medium">
                        <div>{{ item.value }}</div>
                        <div
                          v-if="item.overridden"
                          class="text-[11px] font-normal text-[color:var(--text-dim)]"
                        >
                          base {{ item.baseValue }}
                        </div>
                      </dd>
                    </div>
                  </dl>
                </div>
              </div>

              <div
                v-if="phaseOverrideSections.length === 0"
                class="rounded-lg border border-dashed border-[color:var(--border-muted)] px-3 py-3 text-xs text-[color:var(--text-dim)]"
              >
                Для этой фазы используется base config без phase override diff.
              </div>

              <div
                v-else
                class="space-y-3"
              >
                <div
                  v-for="section in phaseOverrideSections"
                  :key="section.key"
                  class="rounded-xl border border-[color:var(--border-muted)] px-3 py-3"
                >
                  <div class="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                    <div class="text-xs font-medium">
                      {{ section.label }}
                    </div>
                    <div class="text-[11px] text-[color:var(--text-dim)]">
                      {{ section.totalOverrideCount }} override
                      <span v-if="section.totalOverrideCount !== 1">s</span>
                    </div>
                  </div>

                  <ul class="mt-3 space-y-2 text-sm">
                    <li
                      v-for="field in section.fields"
                      :key="field.path"
                      class="rounded-lg bg-[color:var(--surface-muted)] px-3 py-2"
                    >
                      <span class="font-medium">{{ field.label }}:</span>
                      {{ field.effectiveValue }}
                      <span class="text-[11px] text-[color:var(--text-dim)]"> · base {{ field.baseValue }}</span>
                    </li>
                  </ul>

                  <div
                    v-if="section.hiddenOverrideCount > 0"
                    class="mt-3 text-[11px] text-[color:var(--text-dim)]"
                  >
                    И ещё {{ section.hiddenOverrideCount }} hidden advanced override.
                  </div>
                </div>
              </div>
            </div>

            <div
              v-for="section in visibleSections"
              :key="`phase-${selectedPhase}-${section.key}`"
              class="rounded-xl border border-[color:var(--border-muted)] p-4 space-y-4"
            >
              <div>
                <div class="text-sm font-medium">
                  {{ section.label }}
                </div>
                <div class="text-xs text-[color:var(--text-dim)] mt-1">
                  {{ section.description }}
                </div>
              </div>
              <div
                v-if="sectionRuntimeNote(section.key, activePhaseForm)"
                class="rounded-lg border border-[color:var(--badge-info-border)] bg-[color:var(--badge-info-bg)] px-3 py-2 text-[11px] text-[color:var(--badge-info-text)]"
              >
                {{ sectionRuntimeNote(section.key, activePhaseForm) }}
              </div>
              <div class="grid gap-4 md:grid-cols-2">
                <div
                  v-for="field in visibleFields(section.fields)"
                  :key="`phase-${selectedPhase}-${field.path}`"
                  class="space-y-1.5"
                >
                  <label class="block text-xs font-medium text-[color:var(--text-muted)]">{{ field.label }}</label>

                  <label
                    v-if="field.type === 'boolean'"
                    class="flex items-center gap-2 text-sm"
                  >
                    <input
                      :checked="Boolean(getByPath(activePhaseForm, field.path))"
                      :data-testid="`correction-config-phase-${selectedPhase}-${field.path}`"
                      type="checkbox"
                      @change="setByPath(activePhaseForm, field.path, ($event.target as HTMLInputElement).checked)"
                    />
                    <span>{{ field.description }}</span>
                  </label>

                  <select
                    v-else-if="field.type === 'enum'"
                    :value="String(getByPath(activePhaseForm, field.path) ?? '')"
                    :data-testid="`correction-config-phase-${selectedPhase}-${field.path}`"
                    class="input-select w-full"
                    :disabled="Boolean(field.readonly)"
                    @change="setByPath(activePhaseForm, field.path, ($event.target as HTMLSelectElement).value)"
                  >
                    <option
                      v-for="option in field.options || []"
                      :key="option"
                      :value="option"
                    >
                      {{ option }}
                    </option>
                  </select>

                  <input
                    v-else
                    :value="String(getByPath(activePhaseForm, field.path) ?? '')"
                    :data-testid="`correction-config-phase-${selectedPhase}-${field.path}`"
                    :type="field.type === 'string' ? 'text' : 'number'"
                    :step="field.step ?? (field.type === 'integer' ? 1 : 'any')"
                    :min="field.min"
                    :max="field.max"
                    :disabled="Boolean(field.readonly)"
                    class="input-field w-full"
                    @input="handleScalarInput(activePhaseForm, field, $event)"
                  />

                  <div
                    v-if="field.type !== 'boolean'"
                    class="text-[11px] text-[color:var(--text-dim)]"
                  >
                    {{ field.description }}
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>

      <div class="flex justify-end gap-2 border-t border-[color:var(--border-muted)] pt-4">
        <Button
          type="button"
          variant="outline"
          size="sm"
          data-testid="correction-config-reload"
          @click="reload"
        >
          Перезагрузить
        </Button>
        <Button
          type="button"
          size="sm"
          data-testid="correction-config-save"
          :disabled="loading"
          @click="save"
        >
          {{ loading ? 'Сохранение...' : 'Сохранить correction config' }}
        </Button>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import type { AutomationPreset } from '@/composables/useAutomationConfig'
import type {
  CorrectionCatalogField,
  CorrectionCatalogSection,
  CorrectionPhase,
  CorrectionPreset,
  ZoneCorrectionConfigHistoryItem,
  ZoneCorrectionConfigPayload,
} from '@/types/CorrectionConfig'
import { logger } from '@/utils/logger'

interface Props {
  zoneId: number
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'saved'): void
}>()
const CORRECTION_NAMESPACE = 'zone.correction'
const automationConfig = useAutomationConfig()
const { loading } = automationConfig

const presets = ref<CorrectionPreset[]>([])
const sections = ref<CorrectionCatalogSection[]>([])
const phases = ref<CorrectionPhase[]>(['solution_fill', 'tank_recirc', 'irrigation'])
const defaultsConfig = ref<Record<string, unknown>>({})
const history = ref<ZoneCorrectionConfigHistoryItem[]>([])
const selectedPresetId = ref<number | null>(null)
const selectedPhase = ref<CorrectionPhase>('solution_fill')
const advancedMode = ref(false)
const version = ref<number | null>(null)
const updatedAt = ref<string | null>(null)
const lastAppliedAt = ref<string | null>(null)
const lastAppliedVersion = ref<number | null>(null)
const baseForm = ref<Record<string, unknown>>({})
const phaseForms = ref<Record<CorrectionPhase, Record<string, unknown>>>({
  solution_fill: {},
  tank_recirc: {},
  irrigation: {},
})
const newPresetName = ref('')
const newPresetDescription = ref('')

const selectedPreset = computed(() => presets.value.find((item) => item.id === selectedPresetId.value) ?? null)
const visibleSections = computed(() => sections.value.filter((section) => advancedMode.value || !section.advanced_only))
const activePhaseForm = computed<Record<string, unknown>>(() => phaseForms.value[selectedPhase.value])
const phaseOverrideSections = computed(() => {
  return sections.value
    .map((section) => {
      const changedFields = section.fields.filter((field) => !areLeafValuesEqual(getByPath(baseForm.value, field.path), getByPath(activePhaseForm.value, field.path)))
      const visibleChangedFields = changedFields.filter((field) => advancedMode.value || !field.advanced_only)

      return {
        key: section.key,
        label: section.label,
        totalOverrideCount: changedFields.length,
        hiddenOverrideCount: changedFields.length - visibleChangedFields.length,
        fields: visibleChangedFields.map((field) => ({
          path: field.path,
          label: field.label,
          effectiveValue: formatFieldValue(field, getByPath(activePhaseForm.value, field.path)),
          baseValue: formatFieldValue(field, getByPath(baseForm.value, field.path)),
        })),
      }
    })
    .filter((section) => section.totalOverrideCount > 0)
})
const phaseOverrideStats = computed(() => ({
  overrideCount: phaseOverrideSections.value.reduce((sum, section) => sum + section.totalOverrideCount, 0),
  sectionCount: phaseOverrideSections.value.length,
  hiddenOverrideCount: phaseOverrideSections.value.reduce((sum, section) => sum + section.hiddenOverrideCount, 0),
}))
const effectivePreviewGroups = computed(() => [
  {
    key: 'controllers.ph',
    label: 'pH controller',
    items: [
      createPreviewItem('controllers.ph.kp', 'Kp', 'number'),
      createPreviewItem('controllers.ph.ki', 'Ki', 'number'),
      createPreviewItem('controllers.ph.deadband', 'Deadband', 'number'),
      createPreviewItem('controllers.ph.max_dose_ml', 'Max dose ml', 'number'),
      createPreviewItem('controllers.ph.min_interval_sec', 'Min interval sec', 'integer'),
    ],
  },
  {
    key: 'controllers.ec',
    label: 'EC controller',
    items: [
      createPreviewItem('controllers.ec.kp', 'Kp', 'number'),
      createPreviewItem('controllers.ec.ki', 'Ki', 'number'),
      createPreviewItem('controllers.ec.deadband', 'Deadband', 'number'),
      createPreviewItem('controllers.ec.max_dose_ml', 'Max dose ml', 'number'),
      createPreviewItem('controllers.ec.min_interval_sec', 'Min interval sec', 'integer'),
    ],
  },
  {
    key: 'retry',
    label: 'Retry and windows',
    items: [
      createPreviewItem('retry.telemetry_stale_retry_sec', 'Telemetry stale retry', 'integer'),
      createPreviewItem('retry.decision_window_retry_sec', 'Decision window retry', 'integer'),
      createPreviewItem('retry.low_water_retry_sec', 'Low water retry', 'integer'),
    ],
  },
])

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function hasKeys(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value) && Object.keys(value as Record<string, unknown>).length > 0
}

function formatDate(value?: string | null): string {
  if (!value) {
    return '—'
  }
  return new Date(value).toLocaleString('ru-RU')
}

function visibleFields(fields: CorrectionCatalogField[]): CorrectionCatalogField[] {
  return fields.filter((field) => advancedMode.value || !field.advanced_only)
}

function formatPercent(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return '—'
  }

  return `${Math.round(value * 100)}%`
}

function formatInteger(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return '—'
  }

  return String(Math.round(value))
}

function formatNumber(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return '—'
  }

  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 4,
  }).format(value)
}

function areLeafValuesEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

function formatFieldValue(
  field: Pick<CorrectionCatalogField, 'type'>,
  value: unknown,
): string {
  if (field.type === 'boolean') {
    return typeof value === 'boolean' ? (value ? 'On' : 'Off') : '—'
  }

  if (field.type === 'integer') {
    return formatInteger(value)
  }

  if (field.type === 'number') {
    return formatNumber(value)
  }

  if (field.type === 'string' || field.type === 'enum') {
    return typeof value === 'string' && value.trim() !== '' ? value : '—'
  }

  return '—'
}

function createPreviewItem(
  path: string,
  label: string,
  type: CorrectionCatalogField['type'],
): {
  path: string
  label: string
  value: string
  baseValue: string
  overridden: boolean
} {
  const meta = sections.value.flatMap((section) => section.fields).find((field) => field.path === path)
  const field = meta ?? { path, label, description: '', type }
  const effectiveValue = getByPath(activePhaseForm.value, path)
  const baseValue = getByPath(baseForm.value, path)

  return {
    path,
    label,
    value: formatFieldValue(field, effectiveValue),
    baseValue: formatFieldValue(field, baseValue),
    overridden: !areLeafValuesEqual(effectiveValue, baseValue),
  }
}

function getByPath(target: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((current, segment) => {
    if (!current || typeof current !== 'object' || Array.isArray(current)) {
      return undefined
    }
    return (current as Record<string, unknown>)[segment]
  }, target)
}

function setByPath(target: Record<string, unknown>, path: string, value: unknown): void {
  const segments = path.split('.')
  let current = target
  segments.slice(0, -1).forEach((segment) => {
    const next = current[segment]
    if (!next || typeof next !== 'object' || Array.isArray(next)) {
      current[segment] = {}
    }
    current = current[segment] as Record<string, unknown>
  })
  current[segments[segments.length - 1]] = value
}

function normalizeScalar(field: CorrectionCatalogField, raw: string): string | number {
  if (field.type === 'string') {
    return raw
  }

  const numeric = Number(raw)
  if (!Number.isFinite(numeric)) {
    return field.type === 'integer' ? 0 : 0
  }

  return field.type === 'integer' ? Math.round(numeric) : numeric
}

function handleScalarInput(target: Record<string, unknown>, field: CorrectionCatalogField, event: Event): void {
  const element = event.target as HTMLInputElement
  setByPath(target, field.path, normalizeScalar(field, element.value))
}

function sectionRuntimeNote(sectionKey: string, target: Record<string, unknown>): string | null {
  if (sectionKey !== 'controllers.ph' && sectionKey !== 'controllers.ec') {
    return null
  }

  const controller = sectionKey.endsWith('.ph') ? 'pH' : 'EC'
  const prefix = `controllers.${controller === 'pH' ? 'ph' : 'ec'}.observe`
  const decisionWindow = formatInteger(getByPath(target, `${prefix}.decision_window_sec`))
  const observePoll = formatInteger(getByPath(target, `${prefix}.observe_poll_sec`))
  const minEffectFraction = formatPercent(getByPath(target, `${prefix}.min_effect_fraction`))
  const noEffectLimit = formatInteger(getByPath(target, `${prefix}.no_effect_consecutive_limit`))

  return `${controller} observe-loop: после дозы runtime сначала ждёт окно из Process Calibration (transport_delay_sec + settle_sec), затем набирает decision window ${decisionWindow} сек и повторяет observe-check каждые ${observePoll} сек. Эффект ниже ${minEffectFraction} считается no-effect; после ${noEffectLimit} подряд no-effect correction идёт в fail-closed при включённом safety guard.`
}

function splitPresetConfig(raw: Record<string, unknown> | undefined): { base: Record<string, unknown>; phases: Record<CorrectionPhase, Record<string, unknown>> } {
  if (raw && typeof raw === 'object' && !Array.isArray(raw) && 'base' in raw) {
    const typed = raw as { base?: Record<string, unknown>; phases?: Partial<Record<CorrectionPhase, Record<string, unknown>>> }
    return {
      base: clone(typed.base ?? {}),
      phases: {
        solution_fill: clone(typed.phases?.solution_fill ?? typed.base ?? {}),
        tank_recirc: clone(typed.phases?.tank_recirc ?? typed.base ?? {}),
        irrigation: clone(typed.phases?.irrigation ?? typed.base ?? {}),
      },
    }
  }

  return {
    base: clone(raw ?? {}),
    phases: {
      solution_fill: clone(raw ?? {}),
      tank_recirc: clone(raw ?? {}),
      irrigation: clone(raw ?? {}),
    },
  }
}

function normalizeCorrectionPreset(preset: Partial<CorrectionPreset> & Record<string, unknown>): CorrectionPreset {
  return {
    id: Number(preset.id ?? 0),
    slug: String(preset.slug ?? ''),
    name: String(preset.name ?? 'Preset'),
    scope: preset.scope === 'system' ? 'system' : 'custom',
    is_locked: preset.is_locked === true,
    is_active: preset.is_active === true,
    description: typeof preset.description === 'string' ? preset.description : null,
    config: (preset.config as Record<string, unknown>) ?? (preset.payload as Record<string, unknown>) ?? {},
    created_by: typeof preset.created_by === 'number' ? preset.created_by : null,
    updated_by: typeof preset.updated_by === 'number' ? preset.updated_by : null,
    updated_at: typeof preset.updated_at === 'string' ? preset.updated_at : null,
  }
}

function normalizeCorrectionPresets(presetsList: Array<Record<string, unknown> | AutomationPreset>): CorrectionPreset[] {
  return presetsList.map((preset) => normalizeCorrectionPreset(
    preset as unknown as Partial<CorrectionPreset> & Record<string, unknown>
  ))
}

function applyPayload(payload: ZoneCorrectionConfigPayload): void {
  presets.value = payload.available_presets ?? []
  sections.value = payload.meta.field_catalog ?? []
  phases.value = payload.meta.phases ?? ['solution_fill', 'tank_recirc', 'irrigation']
  defaultsConfig.value = clone(payload.meta.defaults ?? {})
  version.value = payload.version
  updatedAt.value = payload.updated_at ?? null
  lastAppliedAt.value = payload.last_applied_at ?? null
  lastAppliedVersion.value = payload.last_applied_version ?? null
  selectedPresetId.value = payload.preset?.id ?? null
  const resolvedBase = hasKeys(payload.resolved_config.base)
    ? payload.resolved_config.base
    : (payload.meta.defaults ?? {})
  const resolvedPhases = payload.resolved_config.phases ?? {}
  baseForm.value = clone(resolvedBase)
  phaseForms.value = {
    solution_fill: clone(hasKeys(resolvedPhases.solution_fill) ? resolvedPhases.solution_fill : resolvedBase),
    tank_recirc: clone(hasKeys(resolvedPhases.tank_recirc) ? resolvedPhases.tank_recirc : resolvedBase),
    irrigation: clone(hasKeys(resolvedPhases.irrigation) ? resolvedPhases.irrigation : resolvedBase),
  }
}

function applyDocument(document: unknown): void {
  if (!document || typeof document !== 'object') {
    return
  }

  const root = document as Record<string, unknown>
  const rawPayload = (root.payload && typeof root.payload === 'object' && !Array.isArray(root.payload))
    ? root.payload as Record<string, unknown>
    : {}

  const resolvedConfig = (
    root.resolved_config
    ?? rawPayload.resolved_config
    ?? { base: {}, phases: {} }
  ) as ZoneCorrectionConfigPayload['resolved_config']

  const normalized = {
    ...rawPayload,
    ...root,
    id: Number(root.id ?? rawPayload.id ?? 0),
    zone_id: Number(root.zone_id ?? rawPayload.zone_id ?? props.zoneId),
    preset: (root.preset ?? rawPayload.preset ?? null) as ZoneCorrectionConfigPayload['preset'],
    base_config: (root.base_config ?? rawPayload.base_config ?? {}) as Record<string, unknown>,
    phase_overrides: (root.phase_overrides ?? rawPayload.phase_overrides ?? {}) as ZoneCorrectionConfigPayload['phase_overrides'],
    resolved_config: resolvedConfig,
    version: Number(root.version ?? rawPayload.version ?? 0),
    updated_at: (root.updated_at ?? rawPayload.updated_at ?? null) as string | null,
    updated_by: (root.updated_by ?? rawPayload.updated_by ?? null) as number | null,
    last_applied_at: (root.last_applied_at ?? rawPayload.last_applied_at ?? null) as string | null,
    last_applied_version: Number(root.last_applied_version ?? rawPayload.last_applied_version ?? 0) || null,
    meta: (root.meta ?? rawPayload.meta ?? {
      phases: ['solution_fill', 'tank_recirc', 'irrigation'],
      defaults: {},
      field_catalog: [],
    }) as ZoneCorrectionConfigPayload['meta'],
    available_presets: (root.available_presets ?? rawPayload.available_presets ?? []) as ZoneCorrectionConfigPayload['available_presets'],
  } satisfies ZoneCorrectionConfigPayload

  applyPayload(normalized)
}

async function reload(): Promise<void> {
  try {
    const [payload, historyItems] = await Promise.all([
      automationConfig.getDocument<ZoneCorrectionConfigPayload>('zone', props.zoneId, CORRECTION_NAMESPACE),
      automationConfig.getHistory<ZoneCorrectionConfigHistoryItem>('zone', props.zoneId, CORRECTION_NAMESPACE),
    ])
    applyDocument(payload)
    history.value = historyItems
  } catch (error) {
    logger.error('[CorrectionConfigForm] Failed to load correction config', error)
  }
}

function applySelectedPreset(): void {
  if (!selectedPreset.value) {
    resetToDefaults()
    return
  }

  const normalized = splitPresetConfig(selectedPreset.value.config as Record<string, unknown>)
  baseForm.value = normalized.base
  phaseForms.value = normalized.phases
}

function resetToDefaults(): void {
  selectedPresetId.value = null
  baseForm.value = clone(defaultsConfig.value)
  phaseForms.value = {
    solution_fill: clone(defaultsConfig.value),
    tank_recirc: clone(defaultsConfig.value),
    irrigation: clone(defaultsConfig.value),
  }
}

async function save(): Promise<void> {
  try {
    const payload = await automationConfig.updateDocument<
      {
        preset_id: number | null
        base_config: Record<string, unknown>
        phase_overrides: Record<CorrectionPhase, Record<string, unknown>>
      },
      ZoneCorrectionConfigPayload
    >('zone', props.zoneId, CORRECTION_NAMESPACE, {
      preset_id: selectedPresetId.value,
      base_config: clone(baseForm.value),
      phase_overrides: clone(phaseForms.value),
    })
    applyDocument(payload)
    history.value = await automationConfig.getHistory<ZoneCorrectionConfigHistoryItem>('zone', props.zoneId, CORRECTION_NAMESPACE)
    emit('saved')
  } catch (error) {
    logger.error('[CorrectionConfigForm] Failed to save correction config', error)
  }
}

async function saveAsPreset(): Promise<void> {
  try {
    const createdPreset = await automationConfig.createPreset(CORRECTION_NAMESPACE, {
      name: newPresetName.value.trim(),
      description: newPresetDescription.value.trim() || null,
      payload: {
        base: clone(baseForm.value),
        phases: clone(phaseForms.value),
      },
    })
    presets.value = normalizeCorrectionPresets(await automationConfig.listPresets(CORRECTION_NAMESPACE))
    selectedPresetId.value = createdPreset.id
    newPresetName.value = ''
    newPresetDescription.value = ''
  } catch (error) {
    logger.error('[CorrectionConfigForm] Failed to create custom preset', error)
  }
}

async function updateSelectedPreset(): Promise<void> {
  if (!selectedPreset.value || selectedPreset.value.scope !== 'custom') {
    return
  }

  try {
    const updatedPreset = await automationConfig.updatePreset(selectedPreset.value.id, {
      payload: {
        base: clone(baseForm.value),
        phases: clone(phaseForms.value),
      },
    })
    presets.value = normalizeCorrectionPresets(await automationConfig.listPresets(CORRECTION_NAMESPACE))
    selectedPresetId.value = updatedPreset.id
  } catch (error) {
    logger.error('[CorrectionConfigForm] Failed to update custom preset', error)
  }
}

async function deleteSelectedPreset(): Promise<void> {
  if (!selectedPreset.value || selectedPreset.value.scope !== 'custom') {
    return
  }

  try {
    await automationConfig.deletePreset(selectedPreset.value.id)
    presets.value = normalizeCorrectionPresets(await automationConfig.listPresets(CORRECTION_NAMESPACE))
    selectedPresetId.value = null
  } catch (error) {
    logger.error('[CorrectionConfigForm] Failed to delete custom preset', error)
  }
}

onMounted(() => {
  void reload()
})

watch(
  () => props.zoneId,
  () => {
    void reload()
  }
)
</script>
