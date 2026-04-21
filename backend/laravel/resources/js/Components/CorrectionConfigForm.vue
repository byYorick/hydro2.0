<template>
  <div
    class="correction-config"
    data-testid="correction-config-form"
  >
    <!-- ================== ACTION BAR ================== -->
    <div class="cc-actionbar">
      <div class="cc-actionbar__lhs">
        <span
          v-if="isDirty"
          class="cc-badge cc-badge--info"
        >
          <span class="cc-badge__dot" />
          изменено в форме
        </span>
        <span class="cc-pill cc-pill--violet">
          {{ phaseOverrideStats.overrideCount }} переопределений фазы
        </span>
        <span class="cc-pill">
          пресет: {{ selectedPreset?.name || 'Системный пресет' }}
        </span>
        <span
          v-if="version !== null"
          class="cc-meta"
        >версия #{{ version }}</span>
        <span
          v-if="updatedAt"
          class="cc-meta"
        >обновлено {{ formatDate(updatedAt) }}</span>
        <span
          v-if="lastAppliedVersion !== null"
          class="cc-meta"
        >AE применил v{{ lastAppliedVersion }}</span>
      </div>
      <div class="cc-actionbar__rhs">
        <Button
          size="sm"
          variant="outline"
          data-testid="correction-config-history-open"
          @click="historyDrawerOpen = true"
        >
          История версий
          <span class="cc-pill cc-pill--sm">{{ history.length }}</span>
        </Button>
        <Button
          size="sm"
          variant="outline"
          data-testid="correction-config-reload"
          :disabled="loading"
          @click="reload"
        >
          Откатить изменения
        </Button>
        <Button
          size="sm"
          data-testid="correction-config-save"
          :disabled="loading"
          @click="save"
        >
          {{ loading ? 'Сохранение…' : `Сохранить · v${(version ?? 0) + 1}` }}
        </Button>
      </div>
    </div>

    <!-- ================== PRESET STRIP ================== -->
    <div class="cc-preset-strip">
      <span class="cc-preset-strip__label">Пресет</span>

      <button
        type="button"
        class="cc-preset-pill"
        :class="{ 'cc-preset-pill--active': selectedPresetId === null }"
        @click="onPresetPillClick(null)"
      >
        Системный пресет
        <span class="cc-preset-pill__scope">system</span>
        <span class="cc-preset-pill__lock">🔒</span>
      </button>

      <button
        v-for="preset in presets"
        :key="preset.id"
        type="button"
        class="cc-preset-pill"
        :class="{ 'cc-preset-pill--active': selectedPresetId === preset.id }"
        :data-testid="`correction-config-preset-${preset.id}`"
        @click="onPresetPillClick(preset.id)"
      >
        {{ preset.name }}
        <span class="cc-preset-pill__scope">{{ preset.scope }}</span>
      </button>

      <button
        type="button"
        class="cc-preset-pill cc-preset-pill--dashed"
        data-testid="correction-config-new-preset"
        @click="newPresetModalOpen = true"
      >
        ＋ новый пресет
      </button>

      <div class="cc-preset-strip__actions">
        <Button
          size="sm"
          variant="outline"
          data-testid="correction-config-apply-preset"
          @click="applySelectedPresetSafe"
        >
          Применить в форму
        </Button>
        <Button
          v-if="selectedPreset?.scope === 'custom'"
          size="sm"
          variant="outline"
          data-testid="correction-config-update-preset"
          :disabled="loading"
          @click="updateSelectedPreset"
        >
          Обновить пресет
        </Button>
        <Button
          size="sm"
          variant="outline"
          data-testid="correction-config-reset-defaults"
          @click="resetToDefaults"
        >
          Сбросить к стандартным
        </Button>
        <div class="cc-menu-wrap">
          <Button
            size="sm"
            variant="outline"
            class="cc-menu-trigger"
            data-testid="correction-config-preset-menu"
            @click.stop="presetMenuOpen = !presetMenuOpen"
          >
            ⋯
          </Button>
          <div
            v-if="presetMenuOpen"
            v-click-outside="() => (presetMenuOpen = false)"
            class="cc-menu"
          >
            <div class="cc-menu__header">
              {{ selectedPreset?.name || 'Системный пресет' }}
            </div>
            <button
              type="button"
              class="cc-menu__item"
              :disabled="!selectedPreset || selectedPreset.scope !== 'custom'"
              @click="onMenuRename"
            >
              Переименовать
            </button>
            <button
              type="button"
              class="cc-menu__item"
              @click="onMenuDuplicate"
            >
              Дублировать
            </button>
            <button
              type="button"
              class="cc-menu__item"
              @click="onMenuExport('json')"
            >
              Экспорт JSON
            </button>
            <button
              type="button"
              class="cc-menu__item"
              @click="onMenuExport('yaml')"
            >
              Экспорт YAML
            </button>
            <div class="cc-menu__sep" />
            <button
              type="button"
              class="cc-menu__item cc-menu__item--danger"
              :disabled="!selectedPreset || selectedPreset.scope !== 'custom' || loading"
              data-testid="correction-config-delete-preset"
              @click="deleteSelectedPreset"
            >
              Удалить пресет
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ================== PHASE TABS ================== -->
    <div class="cc-phase-tabs">
      <button
        type="button"
        class="cc-phase-tab"
        :class="{ 'cc-phase-tab--active': currentTab === 'base' }"
        data-testid="correction-config-tab-base"
        @click="currentTab = 'base'"
      >
        <span class="cc-phase-tab__title">Базовая конфигурация</span>
        <span class="cc-phase-tab__k">общие параметры</span>
        <div class="cc-phase-tab__meters">
          <span class="cc-phase-tab__n">{{ baseFieldCount }} полей</span>
        </div>
      </button>

      <button
        v-for="phase in phases"
        :key="phase"
        type="button"
        class="cc-phase-tab"
        :class="{ 'cc-phase-tab--active': currentTab === phase }"
        :data-testid="`correction-config-tab-${phase}`"
        @click="currentTab = phase"
      >
        <span class="cc-phase-tab__title">{{ phaseLabel(phase) }}</span>
        <span class="cc-phase-tab__k">{{ phase }}</span>
        <div class="cc-phase-tab__meters">
          <span
            class="cc-phase-tab__n"
            :class="{ 'cc-phase-tab__n--on': overrideCountByPhase[phase] > 0 }"
          >
            {{ overrideCountByPhase[phase] }} переопределений
          </span>
        </div>
      </button>

      <div class="cc-phase-tabs__right">
        <label class="cc-toggle">
          <input
            v-model="advancedMode"
            type="checkbox"
            data-testid="correction-config-advanced-mode"
          />
          расширенный режим
        </label>
      </div>
    </div>

    <!-- ================== MAIN (form + preview) ================== -->
    <div class="cc-main">
      <div class="cc-form-col">
        <div
          v-if="currentTab !== 'base'"
          class="cc-phase-row"
        >
          <span class="cc-phase-row__icon">⚙</span>
          <div class="cc-phase-row__text">
            Редактирование фазы <b>«{{ phaseLabel(currentTab as CorrectionPhase) }}»</b>
            · {{ overrideCountByPhase[currentTab as CorrectionPhase] }} параметров
            отличаются от базовой конфигурации
          </div>
          <div class="cc-phase-row__gap" />
          <Button
            size="sm"
            variant="outline"
            @click="copyBaseToPhase(currentTab as CorrectionPhase)"
          >
            Скопировать из базовой
          </Button>
          <Button
            size="sm"
            variant="outline"
            @click="resetPhaseOverride(currentTab as CorrectionPhase)"
          >
            Сбросить переопределение
          </Button>
        </div>

        <div
          v-for="section in visibleSections"
          :key="section.key"
          class="cc-section"
          :class="{ 'cc-section--open': openSections.has(section.key) }"
        >
          <button
            type="button"
            class="cc-section__header"
            :data-testid="`correction-config-section-${section.key}`"
            @click="toggleSection(section.key)"
          >
            <span class="cc-section__caret">▸</span>
            <span class="cc-section__title">{{ section.label }}</span>
            <span class="cc-section__sub">{{ section.key }}</span>
            <span class="cc-section__flag">
              <span
                v-if="sectionOverrideCount(section) > 0"
                class="cc-pill cc-pill--violet"
              >
                {{ sectionOverrideCount(section) }} переопределений
              </span>
              <span
                v-else
                class="cc-pill"
              >без переопределений</span>
            </span>
          </button>

          <div
            v-if="openSections.has(section.key)"
            class="cc-section__body"
          >
            <div
              v-if="sectionRuntimeNote(section.key, currentForm)"
              class="cc-section__note"
            >
              {{ sectionRuntimeNote(section.key, currentForm) }}
            </div>

            <div class="cc-fgrid">
              <div
                v-for="field in visibleFields(section.fields)"
                :key="field.path"
                class="cc-field"
                :class="{ 'cc-field--overridden': isFieldOverridden(field) }"
              >
                <label class="cc-field__label">
                  {{ field.label }}
                  <span
                    v-if="field.unit"
                    class="cc-field__hint"
                  >{{ field.unit }}</span>
                </label>

                <label
                  v-if="field.type === 'boolean'"
                  class="cc-toggle"
                  :class="{ 'cc-toggle--on': Boolean(getByPath(currentForm, field.path)) }"
                >
                  <input
                    :checked="Boolean(getByPath(currentForm, field.path))"
                    :data-testid="`correction-config-${currentTab}-${field.path}`"
                    type="checkbox"
                    @change="setByPath(currentForm, field.path, ($event.target as HTMLInputElement).checked)"
                  />
                  {{ Boolean(getByPath(currentForm, field.path)) ? 'включено' : 'выключено' }}
                </label>

                <select
                  v-else-if="field.type === 'enum'"
                  :value="String(getByPath(currentForm, field.path) ?? '')"
                  :data-testid="`correction-config-${currentTab}-${field.path}`"
                  class="cc-input cc-input--select"
                  :disabled="Boolean(field.readonly)"
                  @change="setByPath(currentForm, field.path, ($event.target as HTMLSelectElement).value)"
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
                  :value="String(getByPath(currentForm, field.path) ?? '')"
                  :data-testid="`correction-config-${currentTab}-${field.path}`"
                  :type="field.type === 'string' ? 'text' : 'number'"
                  :step="field.step ?? (field.type === 'integer' ? 1 : 'any')"
                  :min="field.min"
                  :max="field.max"
                  :disabled="Boolean(field.readonly)"
                  class="cc-input"
                  @input="handleScalarInput(currentForm, field, $event)"
                />

                <div
                  v-if="field.type !== 'boolean'"
                  class="cc-field__help"
                >
                  {{ field.description }}
                  <span
                    v-if="isFieldOverridden(field) && currentTab !== 'base'"
                    class="cc-field__base"
                  >
                    базовое: {{ formatFieldValue(field, getByPath(baseForm, field.path)) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ============== PREVIEW ============== -->
      <aside
        class="cc-preview-col"
        data-testid="phase-effective-preview"
      >
        <div class="cc-preview-stick">
          <div class="cc-preview__header">
            <h3>Итоговое состояние runtime</h3>
            <span class="cc-pill">фаза: {{ currentTab }}</span>
          </div>
          <div class="cc-preview__stats">
            <span class="cc-pill cc-pill--violet">
              {{ phaseOverrideStats.overrideCount }} переопределений
            </span>
            <span class="cc-pill">
              {{ phaseOverrideStats.sectionCount }} секций затронуто
            </span>
            <span
              v-if="phaseOverrideStats.hiddenOverrideCount > 0"
              class="cc-pill"
            >
              скрыто в расширенных: {{ phaseOverrideStats.hiddenOverrideCount }}
            </span>
          </div>

          <div
            v-for="group in effectivePreviewGroups"
            :key="group.key"
            class="cc-preview__group"
          >
            <h5>{{ group.label }}</h5>
            <div
              v-for="item in group.items"
              :key="item.path"
              class="cc-preview__row"
              :class="{ 'cc-preview__row--overridden': item.overridden }"
            >
              <span class="cc-preview__k">{{ item.label }}</span>
              <span class="cc-preview__v">
                {{ item.value }}
                <span
                  v-if="item.overridden"
                  class="cc-preview__base"
                >{{ item.baseValue }}</span>
              </span>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <!-- ================== CONFLICT BANNER ================== -->
    <teleport to="body">
      <div
        v-if="conflictOpen"
        class="cc-conflict"
        data-testid="correction-config-conflict-banner"
      >
        <span class="cc-conflict__icon">⚠</span>
        <div class="cc-conflict__body">
          <h4>
            Применить пресет «{{ pendingPresetName }}»?
          </h4>
          <p>
            В форме есть <b>{{ pendingPresetDiffs.length }} несохранённых</b> переопределений,
            которые будут затёрты значениями пресета. Несохранённые изменения
            нельзя будет восстановить.
          </p>
          <div class="cc-conflict__diffs">
            <span
              v-for="d in pendingPresetDiffs.slice(0, 6)"
              :key="d.path"
              class="cc-pill cc-pill--warn"
            >
              {{ d.label }}: {{ d.oldVal }} → {{ d.newVal }}
            </span>
            <span
              v-if="pendingPresetDiffs.length > 6"
              class="cc-pill"
            >+{{ pendingPresetDiffs.length - 6 }} ещё</span>
          </div>
          <div class="cc-conflict__actions">
            <Button
              size="sm"
              @click="confirmApplyPendingPreset"
            >
              Применить и затереть
            </Button>
            <Button
              size="sm"
              variant="outline"
              @click="openPresetCompareDiff"
            >
              Сравнить diff
            </Button>
            <Button
              size="sm"
              variant="outline"
              @click="cancelPendingPreset"
            >
              Отмена
            </Button>
          </div>
        </div>
      </div>
    </teleport>

    <!-- ================== HISTORY DRAWER ================== -->
    <teleport to="body">
      <div
        v-if="historyDrawerOpen"
        class="cc-backdrop"
        @click="historyDrawerOpen = false"
      />
      <aside
        v-if="historyDrawerOpen"
        class="cc-drawer"
        role="dialog"
        aria-label="История версий"
      >
        <div class="cc-drawer__header">
          <h3>История версий</h3>
          <span class="cc-pill">{{ history.length }} ревизий</span>
          <div class="cc-drawer__gap" />
          <button
            type="button"
            class="cc-drawer__close"
            @click="historyDrawerOpen = false"
          >
            ×
          </button>
        </div>
        <div class="cc-drawer__body">
          <div
            v-if="history.length === 0"
            class="cc-drawer__empty"
          >
            Нет ревизий.
          </div>
          <div
            v-for="item in history"
            :key="item.id"
            class="cc-hist"
            @click="openHistoryDiff(item)"
          >
            <div class="cc-hist__head">
              <span class="cc-hist__v">v{{ item.version }}</span>
              <span
                class="cc-pill"
                :class="historyTypeClass(item.change_type)"
              >{{ item.change_type }}</span>
              <span class="cc-hist__t">{{ formatDate(item.changed_at) }}</span>
            </div>
            <div class="cc-hist__s">
              {{ item.preset?.name || 'Системный пресет' }}
            </div>
            <div
              v-if="item.changed_by_name"
              class="cc-hist__preset"
            >
              {{ item.changed_by_name }}
            </div>
            <div class="cc-hist__actions">
              <Button
                size="sm"
                variant="outline"
                @click.stop="openHistoryDiff(item)"
              >
                показать diff
              </Button>
              <Button
                size="sm"
                variant="outline"
                :disabled="loading"
                @click.stop="restoreRevision(item)"
              >
                восстановить
              </Button>
            </div>
          </div>
        </div>
      </aside>
    </teleport>

    <!-- ================== DIFF MODAL ================== -->
    <teleport to="body">
      <div
        v-if="diffModalOpen"
        class="cc-diff-modal"
        data-testid="correction-config-diff-modal"
        @click.self="diffModalOpen = false"
      >
        <div class="cc-diff">
          <div class="cc-diff__header">
            <h3>{{ diffTitle }}</h3>
            <span class="cc-diff__crumb">{{ diffCrumb }}</span>
            <div class="cc-diff__gap" />
            <button
              type="button"
              class="cc-diff__close"
              @click="diffModalOpen = false"
            >
              ×
            </button>
          </div>
          <div class="cc-diff__tabs">
            <button
              v-for="fmt in (['yaml', 'json', 'fields'] as const)"
              :key="fmt"
              type="button"
              class="cc-diff__tab"
              :class="{ 'cc-diff__tab--active': diffFormat === fmt }"
              @click="diffFormat = fmt"
            >
              {{ fmt === 'fields' ? 'По полям' : fmt.toUpperCase() }}
            </button>
          </div>
          <div class="cc-diff__body">
            <div class="cc-diff__side">
              <div class="cc-diff__side-h">
                <b>было</b>
                <span class="cc-diff__fmt">{{ diffFormat }}</span>
              </div>
              <div class="cc-diff__lines">
                <div
                  v-for="(line, i) in diffRender.before"
                  :key="`b-${i}`"
                  class="cc-dl"
                  :class="[`cc-dl--${line.t}`]"
                >
                  <div class="cc-dl__n">
                    {{ line.n }}
                  </div>
                  <pre class="cc-dl__c">{{ line.c }}</pre>
                </div>
              </div>
            </div>
            <div class="cc-diff__side">
              <div class="cc-diff__side-h">
                <b>стало</b>
                <span class="cc-diff__fmt">{{ diffFormat }}</span>
              </div>
              <div class="cc-diff__lines">
                <div
                  v-for="(line, i) in diffRender.after"
                  :key="`a-${i}`"
                  class="cc-dl"
                  :class="[`cc-dl--${line.t}`]"
                >
                  <div class="cc-dl__n">
                    {{ line.n }}
                  </div>
                  <pre class="cc-dl__c">{{ line.c }}</pre>
                </div>
              </div>
            </div>
          </div>
          <div class="cc-diff__stats">
            <span><span class="cc-diff__add">+{{ diffStats.add }}</span> добавлено</span>
            <span><span class="cc-diff__del">−{{ diffStats.del }}</span> удалено</span>
            <span>{{ diffStats.sections }} секций</span>
            <div class="cc-diff__gap" />
            <span>{{ diffMeta }}</span>
          </div>
          <div class="cc-diff__footer">
            <Button
              variant="outline"
              @click="diffModalOpen = false"
            >
              Закрыть
            </Button>
            <div class="cc-diff__gap" />
            <Button
              variant="outline"
              @click="copyDiffText"
            >
              Скопировать diff
            </Button>
            <Button
              v-if="diffContext?.kind === 'history'"
              :disabled="loading"
              @click="restoreDiffRevision"
            >
              Восстановить v{{ diffContext.item.version }}
            </Button>
          </div>
        </div>
      </div>
    </teleport>

    <!-- ================== NEW PRESET MODAL ================== -->
    <teleport to="body">
      <div
        v-if="newPresetModalOpen"
        class="cc-diff-modal"
        @click.self="newPresetModalOpen = false"
      >
        <div
          class="cc-diff"
          style="width: min(560px, 100%); min-height: auto"
        >
          <div class="cc-diff__header">
            <h3>Сохранить как пользовательский пресет</h3>
            <div class="cc-diff__gap" />
            <button
              type="button"
              class="cc-diff__close"
              @click="newPresetModalOpen = false"
            >
              ×
            </button>
          </div>
          <div style="padding: 16px 20px; display: flex; flex-direction: column; gap: 12px">
            <label class="cc-field">
              <span class="cc-field__label">Название</span>
              <input
                v-model="newPresetName"
                type="text"
                class="cc-input"
                placeholder="Hydro · Tomato · v3"
                data-testid="correction-config-new-preset-name"
              />
            </label>
            <label class="cc-field">
              <span class="cc-field__label">Описание</span>
              <textarea
                v-model="newPresetDescription"
                class="cc-input cc-input--textarea"
                placeholder="Когда использовать этот пресет, какие цели"
                data-testid="correction-config-new-preset-description"
              />
            </label>
          </div>
          <div class="cc-diff__footer">
            <Button
              variant="outline"
              @click="newPresetModalOpen = false"
            >
              Отмена
            </Button>
            <div class="cc-diff__gap" />
            <Button
              :disabled="loading || !newPresetName.trim()"
              data-testid="correction-config-save-preset"
              @click="onSaveAsPreset"
            >
              Сохранить пресет
            </Button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import type { AutomationPreset } from '@/composables/useAutomationConfig'
import { useCorrectionDiff } from '@/composables/useCorrectionDiff'
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
const emit = defineEmits<{ (e: 'saved'): void }>()

const CORRECTION_NAMESPACE = 'zone.correction'
const automationConfig = useAutomationConfig()
const { loading } = automationConfig

/* ================== STATE (бизнес-логика — как в v1) ================== */
const presets = ref<CorrectionPreset[]>([])
const sections = ref<CorrectionCatalogSection[]>([])
const phases = ref<CorrectionPhase[]>(['solution_fill', 'tank_recirc', 'irrigation'])
const defaultsConfig = ref<Record<string, unknown>>({})
const history = ref<ZoneCorrectionConfigHistoryItem[]>([])
const selectedPresetId = ref<number | null>(null)
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

/* ================== UI-ONLY STATE (новое) ================== */
const currentTab = ref<'base' | CorrectionPhase>('solution_fill')
const openSections = ref<Set<string>>(new Set())
const historyDrawerOpen = ref(false)
const newPresetModalOpen = ref(false)
const presetMenuOpen = ref(false)
const conflictOpen = ref(false)
const pendingPresetId = ref<number | null>(null)
const diffModalOpen = ref(false)
const diffFormat = ref<'yaml' | 'json' | 'fields'>('yaml')
const diffContext = ref<
  | { kind: 'history'; item: ZoneCorrectionConfigHistoryItem; snapshot: ZoneCorrectionConfigPayload | null }
  | { kind: 'preset-compare'; preset: CorrectionPreset | null }
  | null
>(null)

/* snapshot последнего server-state для isDirty */
const lastServerState = ref<{
  base: Record<string, unknown>
  phases: Record<CorrectionPhase, Record<string, unknown>>
  presetId: number | null
}>({ base: {}, phases: { solution_fill: {}, tank_recirc: {}, irrigation: {} }, presetId: null })

/* ================== COMPUTED ================== */
const selectedPreset = computed(() =>
  presets.value.find((p) => p.id === selectedPresetId.value) ?? null
)

const visibleSections = computed(() =>
  sections.value.filter((s) => advancedMode.value || !s.advanced_only)
)

const currentForm = computed<Record<string, unknown>>(() =>
  currentTab.value === 'base' ? baseForm.value : phaseForms.value[currentTab.value]
)

const baseFieldCount = computed(() =>
  sections.value.reduce((sum, s) => sum + s.fields.length, 0)
)

const isDirty = computed(() => {
  return (
    JSON.stringify(baseForm.value) !== JSON.stringify(lastServerState.value.base)
    || JSON.stringify(phaseForms.value) !== JSON.stringify(lastServerState.value.phases)
    || selectedPresetId.value !== lastServerState.value.presetId
  )
})

const overrideCountByPhase = computed<Record<string, number>>(() => {
  const result: Record<string, number> = { base: 0 }
  for (const ph of phases.value) {
    result[ph] = sections.value.reduce((sum, s) => {
      return sum + s.fields.filter((f) =>
        !areLeafValuesEqual(
          getByPath(baseForm.value, f.path),
          getByPath(phaseForms.value[ph], f.path)
        )
      ).length
    }, 0)
  }
  return result
})

const phaseOverrideSections = computed(() => {
  if (currentTab.value === 'base') return []
  const phaseForm = phaseForms.value[currentTab.value as CorrectionPhase]
  return sections.value
    .map((section) => {
      const changed = section.fields.filter((f) =>
        !areLeafValuesEqual(getByPath(baseForm.value, f.path), getByPath(phaseForm, f.path))
      )
      const visibleChanged = changed.filter((f) => advancedMode.value || !f.advanced_only)
      return {
        key: section.key,
        label: section.label,
        totalOverrideCount: changed.length,
        hiddenOverrideCount: changed.length - visibleChanged.length,
        fields: visibleChanged,
      }
    })
    .filter((s) => s.totalOverrideCount > 0)
})

const phaseOverrideStats = computed(() => ({
  overrideCount: phaseOverrideSections.value.reduce((sum, s) => sum + s.totalOverrideCount, 0),
  sectionCount: phaseOverrideSections.value.length,
  hiddenOverrideCount: phaseOverrideSections.value.reduce((sum, s) => sum + s.hiddenOverrideCount, 0),
}))

const effectivePreviewGroups = computed(() => {
  return sections.value
    .filter((s) => advancedMode.value || !s.advanced_only)
    .map((section) => ({
      key: section.key,
      label: section.label,
      items: section.fields
        .filter((f) => advancedMode.value || !f.advanced_only)
        .map((f) => ({
          path: f.path,
          label: f.label,
          value: formatFieldValue(f, getByPath(currentForm.value, f.path)),
          baseValue: formatFieldValue(f, getByPath(baseForm.value, f.path)),
          overridden: currentTab.value !== 'base'
            && !areLeafValuesEqual(
              getByPath(baseForm.value, f.path),
              getByPath(currentForm.value, f.path)
            ),
        })),
    }))
})

/* ================== DIFF ================== */
const { diffConfigs, renderDiffYaml, renderDiffJson, renderDiffFields } = useCorrectionDiff()

const pendingPresetDiffs = computed(() => {
  if (pendingPresetId.value === null) return []
  const preset = presets.value.find((p) => p.id === pendingPresetId.value)
  if (!preset) return []
  const presetSplit = splitPresetConfig(preset.config as Record<string, unknown>)
  return diffConfigs(
    { base: baseForm.value, phases: phaseForms.value },
    { base: presetSplit.base, phases: presetSplit.phases },
    sections.value,
    phases.value
  )
})

const pendingPresetName = computed(() =>
  presets.value.find((p) => p.id === pendingPresetId.value)?.name || 'Системный пресет'
)

interface DiffLine { t: 'ctx' | 'add' | 'del' | 'hdr'; n: string; c: string }
const diffRender = computed<{ before: DiffLine[]; after: DiffLine[] }>(() => {
  const diffs = currentDiffs.value
  if (!diffs) return { before: [], after: [] }
  if (diffFormat.value === 'yaml') return renderDiffYaml(diffs)
  if (diffFormat.value === 'json') return renderDiffJson(diffs)
  return renderDiffFields(diffs)
})

const currentDiffs = computed(() => {
  if (!diffContext.value) return null
  if (diffContext.value.kind === 'preset-compare') {
    return pendingPresetDiffs.value
  }
  if (diffContext.value.kind === 'history' && diffContext.value.snapshot) {
    const snap = diffContext.value.snapshot
    return diffConfigs(
      { base: snap.resolved_config.base, phases: snap.resolved_config.phases as Record<CorrectionPhase, Record<string, unknown>> },
      { base: baseForm.value, phases: phaseForms.value },
      sections.value,
      phases.value
    )
  }
  return null
})

const diffTitle = computed(() => {
  if (!diffContext.value) return 'Сравнение'
  if (diffContext.value.kind === 'history') {
    return `Сравнение · v${diffContext.value.item.version - 1} → v${diffContext.value.item.version}`
  }
  return `Сравнение: текущая форма ↔ пресет «${pendingPresetName.value}»`
})
const diffCrumb = computed(() => `zone ${props.zoneId} / correction`)
const diffMeta = computed(() => {
  if (diffContext.value?.kind === 'history') {
    const i = diffContext.value.item
    return `${i.changed_by_name || 'система'} · ${formatDate(i.changed_at)}`
  }
  return 'предпросмотр применения'
})
const diffStats = computed(() => {
  const ds = currentDiffs.value || []
  const add = ds.filter((d) => d.oldVal === undefined).length + ds.filter((d) => d.oldVal !== undefined).length
  const del = ds.filter((d) => d.newVal === undefined).length + ds.filter((d) => d.newVal !== undefined).length
  const sections = new Set(ds.map((d) => d.section)).size
  return { add, del, sections }
})

/* ================== HELPERS ================== */
function clone<T>(v: T): T { return JSON.parse(JSON.stringify(v)) }
function hasKeys(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === 'object' && !Array.isArray(v) && Object.keys(v as object).length > 0
}
function formatDate(value?: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('ru-RU')
}
function visibleFields(fields: CorrectionCatalogField[]): CorrectionCatalogField[] {
  return fields.filter((f) => advancedMode.value || !f.advanced_only)
}
function areLeafValuesEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}
function formatPercent(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${Math.round(v * 100)}%` : '—'
}
function formatInteger(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? String(Math.round(v)) : '—'
}
function formatNumber(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v)
    ? new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 4 }).format(v)
    : '—'
}
function formatFieldValue(field: Pick<CorrectionCatalogField, 'type'>, value: unknown): string {
  if (field.type === 'boolean') return typeof value === 'boolean' ? (value ? 'Вкл' : 'Выкл') : '—'
  if (field.type === 'integer') return formatInteger(value)
  if (field.type === 'number') return formatNumber(value)
  if ((field.type === 'string' || field.type === 'enum') && typeof value === 'string' && value.trim() !== '') return value
  return '—'
}
function getByPath(target: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((cur, seg) => {
    if (!cur || typeof cur !== 'object' || Array.isArray(cur)) return undefined
    return (cur as Record<string, unknown>)[seg]
  }, target)
}
function setByPath(target: Record<string, unknown>, path: string, value: unknown): void {
  const segs = path.split('.')
  let cur = target
  segs.slice(0, -1).forEach((s) => {
    const n = cur[s]
    if (!n || typeof n !== 'object' || Array.isArray(n)) cur[s] = {}
    cur = cur[s] as Record<string, unknown>
  })
  cur[segs[segs.length - 1]] = value
}
function normalizeScalar(field: CorrectionCatalogField, raw: string): string | number {
  if (field.type === 'string') return raw
  const n = Number(raw)
  if (!Number.isFinite(n)) return 0
  return field.type === 'integer' ? Math.round(n) : n
}
function handleScalarInput(target: Record<string, unknown>, field: CorrectionCatalogField, ev: Event): void {
  const el = ev.target as HTMLInputElement
  setByPath(target, field.path, normalizeScalar(field, el.value))
}
function sectionRuntimeNote(sectionKey: string, target: Record<string, unknown>): string | null {
  if (sectionKey !== 'controllers.ph' && sectionKey !== 'controllers.ec') return null
  const controller = sectionKey.endsWith('.ph') ? 'pH' : 'EC'
  const prefix = `controllers.${controller === 'pH' ? 'ph' : 'ec'}.observe`
  const dw = formatInteger(getByPath(target, `${prefix}.decision_window_sec`))
  const op = formatInteger(getByPath(target, `${prefix}.observe_poll_sec`))
  const mef = formatPercent(getByPath(target, `${prefix}.min_effect_fraction`))
  const nel = formatInteger(getByPath(target, `${prefix}.no_effect_consecutive_limit`))
  return `${controller} observe-loop: после дозы runtime ждёт окно из Process Calibration (transport_delay_sec + settle_sec), затем набирает decision window ${dw} сек и повторяет observe-check каждые ${op} сек. Эффект ниже ${mef} считается no-effect; после ${nel} подряд correction идёт в fail-closed при включённом safety guard.`
}
function splitPresetConfig(raw: Record<string, unknown> | undefined) {
  if (raw && typeof raw === 'object' && 'base' in raw) {
    const t = raw as { base?: Record<string, unknown>; phases?: Partial<Record<CorrectionPhase, Record<string, unknown>>> }
    return {
      base: clone(t.base ?? {}),
      phases: {
        solution_fill: clone(t.phases?.solution_fill ?? t.base ?? {}),
        tank_recirc: clone(t.phases?.tank_recirc ?? t.base ?? {}),
        irrigation: clone(t.phases?.irrigation ?? t.base ?? {}),
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

function phaseLabel(ph: CorrectionPhase): string {
  const map: Record<CorrectionPhase, string> = {
    solution_fill: 'Набор раствора',
    tank_recirc: 'Рециркуляция',
    irrigation: 'Полив',
  }
  return map[ph] ?? ph
}

function historyTypeClass(ct: string): string {
  if (ct === 'ae_rollback') return 'cc-pill--warn'
  if (ct === 'preset_apply') return 'cc-pill--info'
  if (ct === 'update') return 'cc-pill--violet'
  return ''
}

function sectionOverrideCount(section: CorrectionCatalogSection): number {
  if (currentTab.value === 'base') return 0
  const ph = phaseForms.value[currentTab.value as CorrectionPhase]
  return section.fields.filter((f) =>
    !areLeafValuesEqual(getByPath(baseForm.value, f.path), getByPath(ph, f.path))
  ).length
}

function isFieldOverridden(field: CorrectionCatalogField): boolean {
  if (currentTab.value === 'base') return false
  const ph = phaseForms.value[currentTab.value as CorrectionPhase]
  return !areLeafValuesEqual(getByPath(baseForm.value, field.path), getByPath(ph, field.path))
}

function toggleSection(key: string): void {
  if (openSections.value.has(key)) openSections.value.delete(key)
  else openSections.value.add(key)
  openSections.value = new Set(openSections.value)
}

function copyBaseToPhase(ph: CorrectionPhase): void {
  phaseForms.value[ph] = clone(baseForm.value)
}
function resetPhaseOverride(ph: CorrectionPhase): void {
  phaseForms.value[ph] = clone(baseForm.value)
}

/* ================== API CALLS (как в v1) ================== */
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
  const rp = payload.resolved_config.phases ?? {}
  baseForm.value = clone(resolvedBase)
  phaseForms.value = {
    solution_fill: clone(hasKeys(rp.solution_fill) ? rp.solution_fill : resolvedBase),
    tank_recirc: clone(hasKeys(rp.tank_recirc) ? rp.tank_recirc : resolvedBase),
    irrigation: clone(hasKeys(rp.irrigation) ? rp.irrigation : resolvedBase),
  }

  lastServerState.value = {
    base: clone(baseForm.value),
    phases: clone(phaseForms.value),
    presetId: selectedPresetId.value,
  }
}

function applyDocument(document: unknown): void {
  if (!document || typeof document !== 'object') return
  const root = document as Record<string, unknown>
  const rp = (root.payload && typeof root.payload === 'object' && !Array.isArray(root.payload))
    ? root.payload as Record<string, unknown> : {}
  const normalized = {
    ...rp,
    ...root,
    id: Number(root.id ?? rp.id ?? 0),
    zone_id: Number(root.zone_id ?? rp.zone_id ?? props.zoneId),
    preset: (root.preset ?? rp.preset ?? null) as ZoneCorrectionConfigPayload['preset'],
    base_config: (root.base_config ?? rp.base_config ?? {}) as Record<string, unknown>,
    phase_overrides: (root.phase_overrides ?? rp.phase_overrides ?? {}) as ZoneCorrectionConfigPayload['phase_overrides'],
    resolved_config: (root.resolved_config ?? rp.resolved_config ?? { base: {}, phases: {} }) as ZoneCorrectionConfigPayload['resolved_config'],
    version: Number(root.version ?? rp.version ?? 0),
    updated_at: (root.updated_at ?? rp.updated_at ?? null) as string | null,
    updated_by: (root.updated_by ?? rp.updated_by ?? null) as number | null,
    last_applied_at: (root.last_applied_at ?? rp.last_applied_at ?? null) as string | null,
    last_applied_version: Number(root.last_applied_version ?? rp.last_applied_version ?? 0) || null,
    meta: (root.meta ?? rp.meta ?? { phases: ['solution_fill', 'tank_recirc', 'irrigation'], defaults: {}, field_catalog: [] }) as ZoneCorrectionConfigPayload['meta'],
    available_presets: (root.available_presets ?? rp.available_presets ?? []) as ZoneCorrectionConfigPayload['available_presets'],
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

function normalizeCorrectionPreset(preset: Partial<CorrectionPreset> & Record<string, unknown>): CorrectionPreset {
  return {
    id: Number(preset.id ?? 0),
    slug: String(preset.slug ?? ''),
    name: String(preset.name ?? 'Пресет'),
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
function normalizeCorrectionPresets(list: Array<Record<string, unknown> | AutomationPreset>): CorrectionPreset[] {
  return list.map((p) => normalizeCorrectionPreset(p as unknown as Partial<CorrectionPreset> & Record<string, unknown>))
}

function applySelectedPreset(): void {
  if (!selectedPreset.value) { resetToDefaults(); return }
  const n = splitPresetConfig(selectedPreset.value.config as Record<string, unknown>)
  baseForm.value = n.base
  phaseForms.value = n.phases
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
      { preset_id: number | null; base_config: Record<string, unknown>; phase_overrides: Record<CorrectionPhase, Record<string, unknown>> },
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
    logger.error('[CorrectionConfigForm] Failed to save', error)
  }
}

async function onSaveAsPreset(): Promise<void> {
  try {
    const created = await automationConfig.createPreset(CORRECTION_NAMESPACE, {
      name: newPresetName.value.trim(),
      description: newPresetDescription.value.trim() || null,
      payload: { base: clone(baseForm.value), phases: clone(phaseForms.value) },
    })
    presets.value = normalizeCorrectionPresets(await automationConfig.listPresets(CORRECTION_NAMESPACE))
    selectedPresetId.value = created.id
    newPresetName.value = ''
    newPresetDescription.value = ''
    newPresetModalOpen.value = false
  } catch (error) {
    logger.error('[CorrectionConfigForm] Failed to create preset', error)
  }
}

async function updateSelectedPreset(): Promise<void> {
  if (!selectedPreset.value || selectedPreset.value.scope !== 'custom') return
  try {
    const updated = await automationConfig.updatePreset(selectedPreset.value.id, {
      payload: { base: clone(baseForm.value), phases: clone(phaseForms.value) },
    })
    presets.value = normalizeCorrectionPresets(await automationConfig.listPresets(CORRECTION_NAMESPACE))
    selectedPresetId.value = updated.id
  } catch (error) {
    logger.error('[CorrectionConfigForm] Failed to update preset', error)
  }
}

async function deleteSelectedPreset(): Promise<void> {
  if (!selectedPreset.value || selectedPreset.value.scope !== 'custom') return
  presetMenuOpen.value = false
  try {
    await automationConfig.deletePreset(selectedPreset.value.id)
    presets.value = normalizeCorrectionPresets(await automationConfig.listPresets(CORRECTION_NAMESPACE))
    selectedPresetId.value = null
  } catch (error) {
    logger.error('[CorrectionConfigForm] Failed to delete preset', error)
  }
}

/* ================== PRESET PILL ВЗАИМОДЕЙСТВИЯ ================== */
function onPresetPillClick(id: number | null): void {
  if (id === selectedPresetId.value) return
  if (isDirty.value) {
    pendingPresetId.value = id
    conflictOpen.value = true
  } else {
    selectedPresetId.value = id
    applySelectedPreset()
  }
}

function applySelectedPresetSafe(): void {
  // кнопка "Применить в форму" — для активного preset, затирает форму
  applySelectedPreset()
}

function confirmApplyPendingPreset(): void {
  selectedPresetId.value = pendingPresetId.value
  applySelectedPreset()
  conflictOpen.value = false
  pendingPresetId.value = null
}

function cancelPendingPreset(): void {
  conflictOpen.value = false
  pendingPresetId.value = null
}

function openPresetCompareDiff(): void {
  const preset = presets.value.find((p) => p.id === pendingPresetId.value) ?? null
  diffContext.value = { kind: 'preset-compare', preset }
  diffFormat.value = 'yaml'
  diffModalOpen.value = true
}

/* ================== HISTORY DIFF ================== */
async function openHistoryDiff(item: ZoneCorrectionConfigHistoryItem): Promise<void> {
  let snapshot: ZoneCorrectionConfigPayload | null = null
  try {
    // см. handoff.md: нужен метод automationConfig.getRevision
    const raw = await automationConfig.getRevision<ZoneCorrectionConfigPayload>(
      'zone', props.zoneId, CORRECTION_NAMESPACE, item.version
    )
    snapshot = raw as unknown as ZoneCorrectionConfigPayload
  } catch (error) {
    logger.error('[CorrectionConfigForm] Failed to load revision', error)
  }
  diffContext.value = { kind: 'history', item, snapshot }
  diffFormat.value = 'yaml'
  diffModalOpen.value = true
}

async function restoreDiffRevision(): Promise<void> {
  if (diffContext.value?.kind !== 'history') return
  await restoreRevision(diffContext.value.item)
  diffModalOpen.value = false
}

async function restoreRevision(item: ZoneCorrectionConfigHistoryItem): Promise<void> {
  try {
    const payload = await automationConfig.restoreRevision<ZoneCorrectionConfigPayload>(
      'zone', props.zoneId, CORRECTION_NAMESPACE, item.version
    )
    applyDocument(payload)
    history.value = await automationConfig.getHistory<ZoneCorrectionConfigHistoryItem>(
      'zone', props.zoneId, CORRECTION_NAMESPACE
    )
    historyDrawerOpen.value = false
  } catch (error) {
    logger.error('[CorrectionConfigForm] Failed to restore revision', error)
  }
}

function copyDiffText(): void {
  const diffs = currentDiffs.value || []
  const text = diffs
    .map((d) => `${d.path}: ${JSON.stringify(d.oldVal)} → ${JSON.stringify(d.newVal)}`)
    .join('\n')
  navigator.clipboard?.writeText(text).catch(() => { /* ignore */ })
}

/* ================== PRESET MENU ACTIONS (stubs) ================== */
function onMenuRename(): void {
  presetMenuOpen.value = false
  // TODO: открыть модалку переименования; вызов automationConfig.updatePreset({ name })
}
function onMenuDuplicate(): void {
  presetMenuOpen.value = false
  newPresetName.value = `${selectedPreset.value?.name || 'Пресет'} (копия)`
  newPresetDescription.value = selectedPreset.value?.description ?? ''
  newPresetModalOpen.value = true
}
function onMenuExport(fmt: 'json' | 'yaml'): void {
  presetMenuOpen.value = false
  const data = selectedPreset.value?.config ?? { base: baseForm.value, phases: phaseForms.value }
  const text = fmt === 'json'
    ? JSON.stringify(data, null, 2)
    // yaml: минимальная сериализация без зависимости
    : jsonToYaml(data)
  const blob = new Blob([text], { type: fmt === 'json' ? 'application/json' : 'text/yaml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${selectedPreset.value?.slug || 'correction'}.${fmt}`
  a.click()
  URL.revokeObjectURL(url)
}

function jsonToYaml(obj: unknown, indent = 0): string {
  const pad = '  '.repeat(indent)
  if (obj === null || obj === undefined) return `${pad}null`
  if (typeof obj !== 'object' || Array.isArray(obj)) return `${pad}${JSON.stringify(obj)}`
  return Object.entries(obj as Record<string, unknown>)
    .map(([k, v]) => {
      if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
        return `${pad}${k}:\n${jsonToYaml(v, indent + 1)}`
      }
      return `${pad}${k}: ${typeof v === 'string' ? `"${v}"` : JSON.stringify(v)}`
    })
    .join('\n')
}

/* ================== LIFECYCLE ================== */
onMounted(() => { void reload() })
watch(() => props.zoneId, () => { void reload() })
watch(sections, (s) => {
  // при первой загрузке — раскрыть первую секцию
  if (s.length && openSections.value.size === 0) {
    openSections.value = new Set([s[0].key])
  }
})

/* Escape закрывает всё */
function onEsc(e: KeyboardEvent): void {
  if (e.key !== 'Escape') return
  if (diffModalOpen.value) { diffModalOpen.value = false; return }
  if (newPresetModalOpen.value) { newPresetModalOpen.value = false; return }
  if (conflictOpen.value) { cancelPendingPreset(); return }
  if (historyDrawerOpen.value) { historyDrawerOpen.value = false; return }
  if (presetMenuOpen.value) { presetMenuOpen.value = false }
}
onMounted(() => window.addEventListener('keydown', onEsc))
</script>

<style scoped>
/*
  Стили локальные, используют существующие CSS-переменные проекта
  (--text-primary, --text-muted, --text-dim, --border-muted и т.д.).
  Только новые токены добавлены как fallback — см. handoff.md раздел "Токены".
*/
.correction-config {
  background: var(--bg-surface, #fff);
  border: 1px solid var(--border-muted);
  border-radius: 12px;
  overflow: visible;
  font-size: 13px;
  line-height: 1.45;
}

/* ========== ACTION BAR ========== */
.cc-actionbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-muted);
  background: var(--surface-muted, #fafbfc);
  flex-wrap: wrap;
}
.cc-actionbar__lhs,
.cc-actionbar__rhs { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cc-actionbar__rhs { margin-left: auto; }
.cc-meta { font-family: var(--font-mono, ui-monospace, monospace); font-size: 11px; color: var(--text-dim); }

/* ========== BADGE / PILL ========== */
.cc-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px; padding: 3px 8px; border-radius: 999px;
  border: 1px solid var(--border-muted); background: var(--surface-muted, #fafbfc);
  color: var(--text-muted);
}
.cc-badge--info {
  background: var(--badge-info-bg, #e7efff);
  border-color: var(--badge-info-border, #c6daf9);
  color: var(--badge-info-text, #1f6feb);
}
.cc-badge__dot { width: 6px; height: 6px; border-radius: 999px; background: currentColor; }
.cc-pill {
  display: inline-flex; align-items: center; gap: 5px;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px; padding: 2px 8px; border-radius: 999px;
  background: var(--surface-muted, #eef0f3);
  color: var(--text-muted); border: 1px solid var(--border-muted);
}
.cc-pill--sm { padding: 1px 6px; font-size: 10px; margin-left: 4px; }
.cc-pill--violet {
  background: var(--accent-violet-soft, #efeafe);
  border-color: #d9cffa;
  color: var(--accent-violet, #6e3bd9);
}
.cc-pill--info {
  background: var(--badge-info-bg, #e7efff);
  border-color: var(--badge-info-border, #c6daf9);
  color: var(--badge-info-text, #1f6feb);
}
.cc-pill--warn {
  background: var(--badge-warning-bg, #fdf1e4);
  border-color: var(--badge-warning-border, #f0c89b);
  color: var(--badge-warning-text, #8a5a0a);
}

/* ========== PRESET STRIP ========== */
.cc-preset-strip {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 16px; border-bottom: 1px solid var(--border-muted);
  flex-wrap: wrap;
}
.cc-preset-strip__label {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 10.5px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--text-dim); margin-right: 4px;
}
.cc-preset-pill {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 12px; border-radius: 999px;
  border: 1px solid var(--border-muted); background: var(--bg-surface, #fff);
  cursor: pointer; font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12px; color: var(--text-muted);
  transition: all .15s ease;
}
.cc-preset-pill:hover { border-color: var(--text-dim); color: var(--text-primary); }
.cc-preset-pill--active {
  background: var(--accent-blue, #1f6feb); color: #fff; border-color: var(--accent-blue, #1f6feb);
  box-shadow: 0 0 0 3px var(--accent-blue-soft, #e7efff);
}
.cc-preset-pill--active .cc-preset-pill__scope { color: rgba(255, 255, 255, .75); }
.cc-preset-pill__scope {
  color: var(--text-dim); font-size: 10px;
  letter-spacing: .04em; text-transform: uppercase;
}
.cc-preset-pill__lock { font-size: 10px; opacity: .7; }
.cc-preset-pill--dashed { border-style: dashed; color: var(--text-dim); }
.cc-preset-strip__actions {
  margin-left: auto; display: flex; gap: 6px; align-items: center; position: relative;
}

/* ========== DROPDOWN MENU ========== */
.cc-menu-wrap { position: relative; }
.cc-menu-trigger { padding: 5px 8px; font-family: var(--font-mono, ui-monospace, monospace); }
.cc-menu {
  position: absolute; right: 0; top: calc(100% + 6px);
  background: var(--bg-surface, #fff); border: 1px solid var(--border-muted);
  border-radius: 10px; box-shadow: 0 12px 28px rgba(10, 20, 40, .12);
  padding: 5px; min-width: 220px; z-index: 60;
  display: flex; flex-direction: column;
}
.cc-menu__header {
  padding: 6px 10px 4px;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 10px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--text-dim);
}
.cc-menu__item {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 10px; border-radius: 6px; cursor: pointer;
  color: var(--text-primary); background: transparent; border: none;
  font: inherit; text-align: left;
}
.cc-menu__item:hover:not(:disabled) { background: var(--surface-muted, #eef0f3); }
.cc-menu__item:disabled { color: var(--text-dim); cursor: not-allowed; opacity: .6; }
.cc-menu__item--danger { color: var(--badge-danger-text, #8a2020); }
.cc-menu__item--danger:hover:not(:disabled) { background: var(--badge-danger-bg, #fdecec); }
.cc-menu__sep { height: 1px; background: var(--border-muted); margin: 4px 2px; }

/* ========== PHASE TABS ========== */
.cc-phase-tabs {
  display: flex; align-items: stretch;
  width: 100%;
  padding: 0 16px; border-bottom: 1px solid var(--border-muted);
  background: var(--bg-surface, #fff);
}
.cc-phase-tab {
  flex: 1 1 0;
  display: flex; flex-direction: column; gap: 3px;
  padding: 12px 16px; cursor: pointer; border: none;
  border-bottom: 2px solid transparent; background: transparent;
  font-size: 13px; font-weight: 500; color: var(--text-muted);
  white-space: nowrap; min-width: 0; text-align: left;
  transition: color .15s ease, border-color .15s ease;
}
.cc-phase-tab:hover { color: var(--text-primary); }
.cc-phase-tab--active { color: var(--accent-blue, #1f6feb); border-bottom-color: var(--accent-blue, #1f6feb); }
.cc-phase-tab__k {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 10.5px; color: var(--text-dim); letter-spacing: .02em;
}
.cc-phase-tab--active .cc-phase-tab__k { color: var(--accent-blue, #1f6feb); }
.cc-phase-tab__meters {
  display: flex; gap: 6px; margin-top: 6px;
  font-family: var(--font-mono, ui-monospace, monospace); font-size: 10.5px; color: var(--text-dim);
}
.cc-phase-tab__n {
  padding: 1px 6px; border-radius: 999px;
  background: var(--surface-muted, #f0f2f5); border: 1px solid var(--border-muted);
  color: var(--text-dim); font-weight: 500;
}
.cc-phase-tab__n--on {
  background: var(--accent-violet-soft, #efeafe); border-color: #d9cffa; color: var(--accent-violet, #6e3bd9);
}
.cc-phase-tabs__right {
  flex: 0 0 auto;
  margin-left: auto; display: flex; align-items: center;
  padding: 0 6px; gap: 8px;
}

/* ========== MAIN ========== */
.cc-main { display: grid; grid-template-columns: 1fr 380px; min-height: 520px; }
.cc-form-col { padding: 16px 18px; border-right: 1px solid var(--border-muted); min-width: 0; }
.cc-preview-col { padding: 16px 18px; background: var(--surface-muted, #fbfbfc); min-width: 0; }

/* phase row */
.cc-phase-row {
  display: flex; gap: 8px; align-items: center;
  padding: 10px 14px; background: var(--accent-violet-soft, #efeafe);
  border: 1px solid #d9cffa; border-radius: 8px;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11.5px; color: var(--accent-violet, #6e3bd9);
  margin-bottom: 12px;
}
.cc-phase-row b { color: var(--accent-violet, #6e3bd9); font-family: inherit; font-size: 12.5px; font-weight: 600; }
.cc-phase-row__gap { flex: 1; }

/* section */
.cc-section {
  border: 1px solid var(--border-muted); border-radius: 10px;
  background: var(--bg-surface, #fff); overflow: hidden;
}
.cc-section + .cc-section { margin-top: 12px; }
.cc-section__header {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px; cursor: pointer; width: 100%;
  border: none; background: var(--surface-muted, #fafbfc);
  font: inherit; text-align: left; color: inherit;
  border-bottom: 1px solid transparent;
}
.cc-section--open .cc-section__header { border-bottom-color: var(--border-muted); }
.cc-section__caret {
  color: var(--text-dim); font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px; transition: transform .15s ease;
}
.cc-section--open .cc-section__caret { transform: rotate(90deg); color: var(--accent-blue, #1f6feb); }
.cc-section__title { font-size: 13px; font-weight: 600; }
.cc-section__sub {
  color: var(--text-dim); font-size: 11.5px;
  font-family: var(--font-mono, ui-monospace, monospace);
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cc-section__flag { display: flex; gap: 6px; }
.cc-section__body { padding: 14px; }
.cc-section__note {
  background: var(--badge-info-bg, #e7efff);
  border: 1px solid var(--badge-info-border, #c6daf9);
  border-radius: 7px; padding: 8px 10px;
  font-size: 11.5px; color: var(--badge-info-text, #1f6feb);
  line-height: 1.5; margin-bottom: 12px;
}

/* field grid */
.cc-fgrid { display: grid; gap: 12px 14px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.cc-field { display: flex; flex-direction: column; gap: 5px; min-width: 0; position: relative; }
.cc-field--overridden .cc-field__label::after {
  content: "override"; font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 9.5px; background: var(--accent-violet-soft, #efeafe);
  color: var(--accent-violet, #6e3bd9); padding: 1px 6px; border-radius: 999px;
  border: 1px solid #d9cffa; margin-left: 6px; letter-spacing: .04em; text-transform: uppercase;
}
.cc-field__label {
  font-size: 10.5px; color: var(--text-dim);
  letter-spacing: .04em; text-transform: uppercase;
  display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
}
.cc-field__hint { color: var(--text-dim); text-transform: none; letter-spacing: 0; font-weight: 400; }
.cc-field__help { font-size: 11px; color: var(--text-dim); line-height: 1.4; }
.cc-field__base { font-family: var(--font-mono, ui-monospace, monospace); color: var(--text-dim); margin-left: 4px; }

/* input */
.cc-input {
  height: 32px; border: 1px solid var(--border-muted); border-radius: 7px;
  background: var(--bg-surface, #fff); padding: 0 10px;
  font-family: var(--font-mono, ui-monospace, monospace); font-size: 12.5px;
  color: var(--text-primary); width: 100%; transition: border-color .15s ease, box-shadow .15s ease;
}
.cc-input:hover { border-color: var(--text-dim); }
.cc-input:focus { outline: none; border-color: var(--accent-blue, #1f6feb); box-shadow: 0 0 0 3px var(--accent-blue-soft, #e7efff); }
.cc-input--textarea { height: auto; min-height: 88px; padding: 8px 10px; font-family: inherit; }
.cc-input--select { appearance: auto; }
.cc-field--overridden .cc-input { border-color: var(--accent-violet, #6e3bd9); background: var(--accent-violet-soft, #efeafe); }

/* toggle */
.cc-toggle {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 10px; border: 1px solid var(--border-muted); border-radius: 7px;
  background: var(--bg-surface, #fff); font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11.5px; color: var(--text-muted); cursor: pointer;
}
.cc-toggle--on {
  border-color: var(--accent-blue, #1f6feb);
  background: var(--accent-blue-soft, #e7efff);
  color: var(--accent-blue, #1f6feb);
}

/* ========== PREVIEW ========== */
.cc-preview-stick { position: sticky; top: 14px; }
.cc-preview__header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.cc-preview__header h3 { margin: 0; font-size: 14px; font-weight: 600; }
.cc-preview__stats { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.cc-preview__group {
  border: 1px solid var(--border-muted); border-radius: 10px;
  background: var(--bg-surface, #fff); overflow: hidden; margin-bottom: 10px;
}
.cc-preview__group h5 {
  margin: 0; padding: 9px 12px; font-size: 11px; font-weight: 600;
  letter-spacing: .08em; text-transform: uppercase;
  color: var(--text-dim); background: var(--surface-muted, #fafbfc);
  border-bottom: 1px solid var(--border-muted);
}
.cc-preview__row {
  display: grid; grid-template-columns: 1fr auto; gap: 10px;
  align-items: baseline; padding: 7px 12px;
  border-bottom: 1px dotted var(--border-muted); font-size: 12px;
}
.cc-preview__row:last-child { border-bottom: none; }
.cc-preview__k {
  color: var(--text-dim); font-family: var(--font-mono, ui-monospace, monospace); font-size: 11px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cc-preview__v { font-family: var(--font-mono, ui-monospace, monospace); font-weight: 500; text-align: right; color: var(--text-primary); font-size: 12px; }
.cc-preview__row--overridden { background: var(--accent-violet-soft, #efeafe); }
.cc-preview__row--overridden .cc-preview__k,
.cc-preview__row--overridden .cc-preview__v { color: var(--accent-violet, #6e3bd9); }
.cc-preview__base {
  display: block; font-size: 10.5px; color: var(--text-dim);
  font-weight: 400; text-decoration: line-through;
}

/* ========== CONFLICT BANNER ========== */
.cc-conflict {
  position: fixed; left: 50%; top: 16px; transform: translateX(-50%);
  background: var(--bg-surface, #fff); border: 1px solid var(--badge-warning-border, #f0c89b);
  border-left: 4px solid var(--badge-warning-text, #8a5a0a);
  box-shadow: 0 14px 40px rgba(10, 20, 40, .14); border-radius: 10px;
  padding: 14px 18px; min-width: 480px; max-width: 620px;
  z-index: 80; display: flex; gap: 14px; align-items: flex-start;
}
.cc-conflict__icon { font-size: 18px; color: var(--badge-warning-text, #8a5a0a); }
.cc-conflict__body { flex: 1; }
.cc-conflict__body h4 { margin: 0 0 4px; font-size: 13.5px; font-weight: 600; color: var(--text-primary); }
.cc-conflict__body p { margin: 0 0 8px; font-size: 12px; color: var(--text-muted); line-height: 1.45; }
.cc-conflict__diffs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.cc-conflict__actions { display: flex; gap: 6px; flex-wrap: wrap; }

/* ========== DRAWER ========== */
.cc-backdrop {
  position: fixed; inset: 0; background: rgba(14, 17, 22, .3);
  backdrop-filter: blur(1px); z-index: 40;
}
.cc-drawer {
  position: fixed; top: 0; right: 0; bottom: 0;
  width: min(480px, 96vw); background: var(--bg-surface, #fff);
  border-left: 1px solid var(--border-muted);
  box-shadow: -10px 0 30px rgba(10, 20, 40, .08);
  z-index: 50; display: flex; flex-direction: column;
}
.cc-drawer__header {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 18px; border-bottom: 1px solid var(--border-muted);
}
.cc-drawer__header h3 { margin: 0; font-size: 15px; font-weight: 600; }
.cc-drawer__gap { flex: 1; }
.cc-drawer__close {
  width: 28px; height: 28px; border: 1px solid var(--border-muted); border-radius: 7px;
  background: var(--bg-surface, #fff); cursor: pointer; color: var(--text-dim);
  font-family: var(--font-mono, ui-monospace, monospace); font-size: 14px;
}
.cc-drawer__body { flex: 1; overflow: auto; padding: 12px 16px; }
.cc-drawer__empty { font-size: 12px; color: var(--text-dim); }

.cc-hist {
  padding: 12px; border: 1px solid var(--border-muted); border-radius: 10px;
  background: var(--bg-surface, #fff); margin-bottom: 8px; cursor: pointer;
  transition: border-color .15s ease;
}
.cc-hist:hover { border-color: var(--accent-blue, #1f6feb); background: var(--accent-blue-soft, #e7efff); }
.cc-hist__head { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.cc-hist__v {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12.5px; font-weight: 600; color: var(--text-primary);
}
.cc-hist__t {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px; color: var(--text-dim); margin-left: auto;
}
.cc-hist__s { font-size: 12px; color: var(--text-muted); }
.cc-hist__preset { font-family: var(--font-mono, ui-monospace, monospace); font-size: 11px; color: var(--text-dim); margin-top: 4px; }
.cc-hist__actions { display: flex; gap: 6px; margin-top: 8px; }

/* ========== DIFF MODAL ========== */
.cc-diff-modal {
  position: fixed; inset: 0; z-index: 90;
  display: flex; align-items: center; justify-content: center;
  padding: 24px; background: rgba(14, 17, 22, .35); backdrop-filter: blur(1px);
}
.cc-diff {
  background: var(--bg-surface, #fff); border: 1px solid var(--border-muted); border-radius: 12px;
  width: min(1040px, 100%); max-height: calc(100vh - 48px);
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 24px 60px rgba(10, 20, 40, .25);
}
.cc-diff__header {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 18px; border-bottom: 1px solid var(--border-muted);
  background: var(--surface-muted, #fafbfc);
}
.cc-diff__header h3 { margin: 0; font-size: 15px; font-weight: 600; }
.cc-diff__crumb { font-family: var(--font-mono, ui-monospace, monospace); font-size: 11.5px; color: var(--text-dim); }
.cc-diff__gap { flex: 1; }
.cc-diff__close {
  width: 28px; height: 28px; border: 1px solid var(--border-muted); border-radius: 7px;
  background: var(--bg-surface, #fff); cursor: pointer; color: var(--text-dim);
  font-family: var(--font-mono, ui-monospace, monospace); font-size: 14px;
}
.cc-diff__tabs {
  display: flex; gap: 4px; padding: 10px 18px 0;
  border-bottom: 1px solid var(--border-muted); background: var(--surface-muted, #fafbfc);
}
.cc-diff__tab {
  padding: 7px 14px; font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11.5px; color: var(--text-muted);
  border: 1px solid transparent; border-bottom: none;
  border-radius: 6px 6px 0 0; cursor: pointer;
  margin-bottom: -1px; background: transparent;
}
.cc-diff__tab--active { background: var(--bg-surface, #fff); border-color: var(--border-muted); color: var(--accent-blue, #1f6feb); }
.cc-diff__body { flex: 1; overflow: auto; display: grid; grid-template-columns: 1fr 1fr; gap: 0; }
.cc-diff__side { min-width: 0; border-right: 1px solid var(--border-muted); }
.cc-diff__side:last-child { border-right: none; }
.cc-diff__side-h {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; border-bottom: 1px solid var(--border-muted);
  background: var(--surface-muted, #fafbfc);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11.5px; color: var(--text-muted);
  position: sticky; top: 0; z-index: 1;
}
.cc-diff__side-h b { font-family: inherit; color: var(--text-primary); font-weight: 600; font-size: 12.5px; }
.cc-diff__fmt { margin-left: auto; }
.cc-diff__lines { padding: 10px 0; font-family: var(--font-mono, ui-monospace, monospace); font-size: 12px; line-height: 1.6; }
.cc-dl { display: grid; grid-template-columns: 40px 1fr; padding: 0 14px 0 0; }
.cc-dl__n {
  color: var(--text-dim); text-align: right;
  padding-right: 10px; user-select: none;
  border-right: 1px solid var(--border-muted); margin-right: 10px;
  font-size: 10.5px; padding-top: 1px;
}
.cc-dl__c { margin: 0; white-space: pre; overflow-x: auto; color: var(--text-primary); }
.cc-dl--add { background: #e7f5ec; }
.cc-dl--add .cc-dl__n, .cc-dl--add .cc-dl__c { color: #186a3b; }
.cc-dl--del { background: #fdecec; }
.cc-dl--del .cc-dl__n { color: #8a2020; }
.cc-dl--del .cc-dl__c { color: #8a2020; text-decoration: line-through; text-decoration-color: rgba(138, 32, 32, .35); }
.cc-dl--ctx { color: var(--text-muted); }
.cc-dl--hdr { color: var(--text-dim); }
.cc-diff__stats {
  padding: 8px 18px; font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px; color: var(--text-dim);
  border-top: 1px solid var(--border-muted); background: var(--surface-muted, #fafbfc);
  display: flex; gap: 14px;
}
.cc-diff__add { color: var(--accent-green, #1f8a4c); }
.cc-diff__del { color: var(--badge-danger-text, #8a2020); }
.cc-diff__footer {
  display: flex; gap: 8px; padding: 12px 18px;
  border-top: 1px solid var(--border-muted);
  background: var(--surface-muted, #fafbfc); align-items: center;
}

/* ========== RESPONSIVE ========== */
@media (max-width: 1100px) {
  .cc-main { grid-template-columns: 1fr; }
  .cc-form-col { border-right: none; border-bottom: 1px solid var(--border-muted); }
  .cc-preview-stick { position: static; }
}
@media (max-width: 720px) {
  .cc-fgrid { grid-template-columns: 1fr; }
  .cc-preset-strip__actions { margin-left: 0; width: 100%; }
}
</style>
