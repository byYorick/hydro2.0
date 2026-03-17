<template>
  <Card>
    <div class="space-y-5">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div class="text-sm font-semibold">Correction Config</div>
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
              <select v-model="selectedPresetId" class="input-select w-full">
                <option :value="null">System default</option>
                <option v-for="preset in presets" :key="preset.id" :value="preset.id">
                  {{ preset.name }} ({{ preset.scope }})
                </option>
              </select>
            </div>

            <div class="text-[11px] text-[color:var(--text-dim)] min-h-[36px]">
              {{ selectedPreset?.description || 'Используется system default без preset overlay.' }}
            </div>

            <div class="space-y-2">
              <Button size="sm" variant="outline" class="w-full" @click="applySelectedPreset">
                Применить preset в форму
              </Button>
              <Button size="sm" variant="outline" class="w-full" @click="resetToDefaults">
                Сбросить к system default
              </Button>
              <Button
                v-if="selectedPreset?.scope === 'custom'"
                size="sm"
                variant="danger"
                class="w-full"
                :disabled="loading"
                @click="deleteSelectedPreset"
              >
                Удалить custom preset
              </Button>
            </div>
          </div>

          <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
            <label class="flex items-center gap-2 text-sm">
              <input v-model="advancedMode" type="checkbox" />
              Advanced mode
            </label>

            <div>
              <div class="text-xs font-medium text-[color:var(--text-muted)] mb-2">Phase override</div>
              <div class="grid gap-2">
                <Button
                  v-for="phase in phases"
                  :key="phase"
                  size="sm"
                  variant="outline"
                  :class="{ 'bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)] border-[color:var(--badge-info-border)]': selectedPhase === phase }"
                  @click="selectedPhase = phase"
                >
                  {{ phase }}
                </Button>
              </div>
            </div>
          </div>

          <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
            <div class="text-xs font-medium text-[color:var(--text-muted)]">Сохранить как custom preset</div>
            <input v-model="newPresetName" type="text" class="input-field w-full" placeholder="Название preset" />
            <textarea v-model="newPresetDescription" class="input-field w-full min-h-[88px]" placeholder="Описание"></textarea>
            <Button size="sm" class="w-full" :disabled="loading || !newPresetName.trim()" @click="saveAsPreset">
              Сохранить текущий config как preset
            </Button>
          </div>

          <div class="rounded-xl border border-[color:var(--border-muted)] p-3 space-y-3">
            <div class="text-xs font-medium text-[color:var(--text-muted)]">History</div>
            <div v-if="history.length === 0" class="text-xs text-[color:var(--text-dim)]">
              Нет ревизий.
            </div>
            <ul v-else class="space-y-2">
              <li
                v-for="item in history.slice(0, 6)"
                :key="item.id"
                class="rounded-lg bg-[color:var(--surface-muted)] px-3 py-2"
              >
                <div class="text-xs font-medium">v{{ item.version }} · {{ item.change_type }}</div>
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
              <div class="text-sm font-semibold">Base config</div>
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
                <div class="text-sm font-medium">{{ section.label }}</div>
                <div class="text-xs text-[color:var(--text-dim)] mt-1">{{ section.description }}</div>
              </div>
              <div class="grid gap-4 md:grid-cols-2">
                <div v-for="field in visibleFields(section.fields)" :key="`base-${field.path}`" class="space-y-1.5">
                  <label class="block text-xs font-medium text-[color:var(--text-muted)]">{{ field.label }}</label>

                  <label v-if="field.type === 'boolean'" class="flex items-center gap-2 text-sm">
                    <input
                      :checked="Boolean(getByPath(baseForm, field.path))"
                      type="checkbox"
                      @change="setByPath(baseForm, field.path, ($event.target as HTMLInputElement).checked)"
                    />
                    <span>{{ field.description }}</span>
                  </label>

                  <select
                    v-else-if="field.type === 'enum'"
                    :value="String(getByPath(baseForm, field.path) ?? '')"
                    class="input-select w-full"
                    :disabled="Boolean(field.readonly)"
                    @change="setByPath(baseForm, field.path, ($event.target as HTMLSelectElement).value)"
                  >
                    <option v-for="option in field.options || []" :key="option" :value="option">{{ option }}</option>
                  </select>

                  <input
                    v-else
                    :value="String(getByPath(baseForm, field.path) ?? '')"
                    :type="field.type === 'string' ? 'text' : 'number'"
                    :step="field.step ?? (field.type === 'integer' ? 1 : 'any')"
                    :min="field.min"
                    :max="field.max"
                    :disabled="Boolean(field.readonly)"
                    class="input-field w-full"
                    @input="handleScalarInput(baseForm, field, $event)"
                  />

                  <div v-if="field.type !== 'boolean'" class="text-[11px] text-[color:var(--text-dim)]">
                    {{ field.description }}
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section class="space-y-4">
            <div>
              <div class="text-sm font-semibold">Phase config: {{ selectedPhase }}</div>
              <div class="text-xs text-[color:var(--text-dim)] mt-1">
                Effective-конфигурация для выбранной фазы. На сохранении backend преобразует её в phase override diff.
              </div>
            </div>

            <div
              v-for="section in visibleSections"
              :key="`phase-${selectedPhase}-${section.key}`"
              class="rounded-xl border border-[color:var(--border-muted)] p-4 space-y-4"
            >
              <div>
                <div class="text-sm font-medium">{{ section.label }}</div>
                <div class="text-xs text-[color:var(--text-dim)] mt-1">{{ section.description }}</div>
              </div>
              <div class="grid gap-4 md:grid-cols-2">
                <div v-for="field in visibleFields(section.fields)" :key="`phase-${selectedPhase}-${field.path}`" class="space-y-1.5">
                  <label class="block text-xs font-medium text-[color:var(--text-muted)]">{{ field.label }}</label>

                  <label v-if="field.type === 'boolean'" class="flex items-center gap-2 text-sm">
                    <input
                      :checked="Boolean(getByPath(activePhaseForm, field.path))"
                      type="checkbox"
                      @change="setByPath(activePhaseForm, field.path, ($event.target as HTMLInputElement).checked)"
                    />
                    <span>{{ field.description }}</span>
                  </label>

                  <select
                    v-else-if="field.type === 'enum'"
                    :value="String(getByPath(activePhaseForm, field.path) ?? '')"
                    class="input-select w-full"
                    :disabled="Boolean(field.readonly)"
                    @change="setByPath(activePhaseForm, field.path, ($event.target as HTMLSelectElement).value)"
                  >
                    <option v-for="option in field.options || []" :key="option" :value="option">{{ option }}</option>
                  </select>

                  <input
                    v-else
                    :value="String(getByPath(activePhaseForm, field.path) ?? '')"
                    :type="field.type === 'string' ? 'text' : 'number'"
                    :step="field.step ?? (field.type === 'integer' ? 1 : 'any')"
                    :min="field.min"
                    :max="field.max"
                    :disabled="Boolean(field.readonly)"
                    class="input-field w-full"
                    @input="handleScalarInput(activePhaseForm, field, $event)"
                  />

                  <div v-if="field.type !== 'boolean'" class="text-[11px] text-[color:var(--text-dim)]">
                    {{ field.description }}
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>

      <div class="flex justify-end gap-2 border-t border-[color:var(--border-muted)] pt-4">
        <Button type="button" variant="outline" size="sm" @click="reload">
          Перезагрузить
        </Button>
        <Button type="button" size="sm" :disabled="loading" @click="save">
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
import { useCorrectionConfig } from '@/composables/useCorrectionConfig'
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

const {
  loading,
  getZoneCorrectionConfig,
  updateZoneCorrectionConfig,
  getZoneCorrectionConfigHistory,
  createCorrectionPreset,
  deleteCorrectionPreset,
} = useCorrectionConfig()

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

async function reload(): Promise<void> {
  try {
    const [payload, historyItems] = await Promise.all([
      getZoneCorrectionConfig(props.zoneId),
      getZoneCorrectionConfigHistory(props.zoneId),
    ])
    applyPayload(payload)
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
    const payload = await updateZoneCorrectionConfig(props.zoneId, {
      preset_id: selectedPresetId.value,
      base_config: clone(baseForm.value),
      phase_overrides: clone(phaseForms.value),
    })
    applyPayload(payload)
    history.value = await getZoneCorrectionConfigHistory(props.zoneId)
  } catch (error) {
    logger.error('[CorrectionConfigForm] Failed to save correction config', error)
  }
}

async function saveAsPreset(): Promise<void> {
  try {
    const result = await createCorrectionPreset({
      name: newPresetName.value.trim(),
      description: newPresetDescription.value.trim() || null,
      config: {
        base: clone(baseForm.value),
        phases: clone(phaseForms.value),
      },
    })
    presets.value = result.data
    selectedPresetId.value = result.selected
    newPresetName.value = ''
    newPresetDescription.value = ''
  } catch (error) {
    logger.error('[CorrectionConfigForm] Failed to create custom preset', error)
  }
}

async function deleteSelectedPreset(): Promise<void> {
  if (!selectedPreset.value || selectedPreset.value.scope !== 'custom') {
    return
  }

  try {
    presets.value = await deleteCorrectionPreset(selectedPreset.value.id)
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
