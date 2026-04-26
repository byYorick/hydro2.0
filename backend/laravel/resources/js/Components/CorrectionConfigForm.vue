<template>
  <div
    class="flex flex-col gap-3"
    data-testid="correction-config-form"
  >
    <!-- ACTION BAR -->
    <div class="flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)]">
      <div class="flex flex-wrap items-center gap-1.5 min-w-0">
        <Chip
          v-if="isDirty"
          tone="brand"
        >
          <template #icon>
            <span class="inline-block w-1.5 h-1.5 rounded-full bg-brand" />
          </template>
          изменено в форме
        </Chip>
        <Chip tone="brand">
          <span class="font-mono">{{ phaseOverrideStats.overrideCount }} переопределений фазы</span>
        </Chip>
        <Chip tone="neutral">
          пресет: <span class="font-mono ml-1">{{ selectedPreset?.name || 'Системный пресет' }}</span>
        </Chip>
        <span
          v-if="version !== null"
          class="text-[11px] font-mono text-[var(--text-dim)] ml-1"
        >
          версия #{{ version }}
        </span>
        <span
          v-if="updatedAt"
          class="text-[11px] font-mono text-[var(--text-dim)]"
        >
          обновлено {{ formatDate(updatedAt) }}
        </span>
        <span
          v-if="lastAppliedVersion !== null"
          class="text-[11px] font-mono text-[var(--text-dim)]"
        >
          AE применил v{{ lastAppliedVersion }}
        </span>
      </div>
      <div class="flex items-center gap-1.5 flex-wrap">
        <Button
          size="sm"
          variant="secondary"
          data-testid="correction-config-history-open"
          @click="historyDrawerOpen = true"
        >
          История версий
          <Chip tone="neutral">
            <span class="font-mono">{{ history.length }}</span>
          </Chip>
        </Button>
        <Button
          size="sm"
          variant="secondary"
          data-testid="correction-config-reload"
          :disabled="loading"
          @click="reload"
        >
          Откатить изменения
        </Button>
        <Button
          size="sm"
          variant="primary"
          data-testid="correction-config-save"
          :disabled="loading"
          @click="save"
        >
          {{ loading ? 'Сохранение…' : `Сохранить · v${(version ?? 0) + 1}` }}
        </Button>
      </div>
    </div>

    <!-- PRESET STRIP -->
    <div class="flex flex-wrap items-center gap-1.5 px-3 py-2 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)]">
      <span class="text-[10px] uppercase tracking-wider text-[var(--text-dim)] font-semibold pr-1">
        Пресет
      </span>

      <button
        type="button"
        :class="presetPillClass(selectedPresetId === null)"
        @click="onPresetPillClick(null)"
      >
        Системный пресет
        <span class="text-[10px] font-mono opacity-65">system</span>
        <span class="text-[10px]">🔒</span>
      </button>

      <button
        v-for="preset in presets"
        :key="preset.id"
        type="button"
        :class="presetPillClass(selectedPresetId === preset.id)"
        :data-testid="`correction-config-preset-${preset.id}`"
        @click="onPresetPillClick(preset.id)"
      >
        {{ preset.name }}
        <span class="text-[10px] font-mono opacity-65">{{ preset.scope }}</span>
      </button>

      <button
        type="button"
        class="px-2.5 py-1 rounded-full border border-dashed border-[var(--border-muted)] text-[12px] text-[var(--text-muted)] cursor-pointer hover:bg-[var(--bg-surface-strong)]"
        data-testid="correction-config-new-preset"
        @click="newPresetModalOpen = true"
      >
        + новый пресет
      </button>

      <div class="ml-auto flex items-center gap-1.5">
        <Button
          size="sm"
          variant="secondary"
          data-testid="correction-config-apply-preset"
          @click="applySelectedPresetSafe"
        >
          Применить в форму
        </Button>
        <Button
          v-if="selectedPreset?.scope === 'custom'"
          size="sm"
          variant="secondary"
          data-testid="correction-config-update-preset"
          :disabled="loading"
          @click="updateSelectedPreset"
        >
          Обновить пресет
        </Button>
        <Button
          size="sm"
          variant="secondary"
          data-testid="correction-config-reset-defaults"
          @click="resetToDefaults"
        >
          Сбросить к стандартным
        </Button>
        <div class="relative">
          <Button
            size="sm"
            variant="secondary"
            data-testid="correction-config-preset-menu"
            @click.stop="presetMenuOpen = !presetMenuOpen"
          >
            ⋯
          </Button>
          <div
            v-if="presetMenuOpen"
            v-click-outside="() => (presetMenuOpen = false)"
            class="absolute right-0 top-full mt-1 z-10 min-w-[200px] rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface-strong)] shadow-lg overflow-hidden"
          >
            <div class="px-3 py-2 text-[11px] font-mono text-[var(--text-dim)] border-b border-[var(--border-muted)]">
              {{ selectedPreset?.name || 'Системный пресет' }}
            </div>
            <button
              type="button"
              :class="menuItemClass"
              :disabled="!selectedPreset || selectedPreset.scope !== 'custom'"
              @click="onMenuRename"
            >
              Переименовать
            </button>
            <button
              type="button"
              :class="menuItemClass"
              @click="onMenuDuplicate"
            >
              Дублировать
            </button>
            <button
              type="button"
              :class="menuItemClass"
              @click="onMenuExport('json')"
            >
              Экспорт JSON
            </button>
            <button
              type="button"
              :class="menuItemClass"
              @click="onMenuExport('yaml')"
            >
              Экспорт YAML
            </button>
            <div class="h-px bg-[var(--border-muted)]" />
            <button
              type="button"
              :class="[menuItemClass, 'text-alert hover:bg-alert-soft']"
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

    <!-- PHASE TABS -->
    <div class="flex flex-wrap items-end gap-1 border-b border-[var(--border-muted)]">
      <button
        type="button"
        :class="phaseTabClass(currentTab === 'base')"
        data-testid="correction-config-tab-base"
        @click="currentTab = 'base'"
      >
        <span class="text-sm font-medium">Базовая конфигурация</span>
        <span class="text-[11px] font-mono opacity-65">общие параметры</span>
        <span class="text-[11px] font-mono opacity-80">{{ baseFieldCount }} полей</span>
      </button>

      <button
        v-for="phase in phases"
        :key="phase"
        type="button"
        :class="phaseTabClass(currentTab === phase)"
        :data-testid="`correction-config-tab-${phase}`"
        @click="currentTab = phase"
      >
        <span class="text-sm font-medium">{{ phaseLabel(phase) }}</span>
        <span class="text-[11px] font-mono opacity-65">{{ phase }}</span>
        <span
          class="text-[11px] font-mono"
          :class="overrideCountByPhase[phase] > 0 ? 'text-brand' : 'opacity-65'"
        >
          {{ overrideCountByPhase[phase] }} переопределений
        </span>
      </button>

      <label class="ml-auto flex items-center gap-1.5 px-2 py-1.5 text-[12px] text-[var(--text-muted)] cursor-pointer">
        <input
          v-model="advancedMode"
          type="checkbox"
          data-testid="correction-config-advanced-mode"
          class="accent-brand"
        />
        расширенный режим
      </label>
    </div>

    <!-- MAIN (form + preview) -->
    <div class="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-3">
      <div class="flex flex-col gap-2 min-w-0">
        <div
          v-if="currentTab !== 'base'"
          class="flex flex-wrap items-center gap-2 px-3 py-2 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)]"
        >
          <Chip tone="brand">
            <template #icon>
              <Ic name="edit" />
            </template>
            фаза
          </Chip>
          <div class="text-[12px] text-[var(--text-muted)] flex-1 min-w-[200px]">
            Редактирование фазы <b class="text-[var(--text-primary)]">«{{ phaseLabel(currentTab as CorrectionPhase) }}»</b>
            · {{ overrideCountByPhase[currentTab as CorrectionPhase] }} параметров
            отличаются от базовой конфигурации
          </div>
          <Button
            size="sm"
            variant="secondary"
            @click="copyBaseToPhase(currentTab as CorrectionPhase)"
          >
            Скопировать из базовой
          </Button>
          <Button
            size="sm"
            variant="secondary"
            @click="resetPhaseOverride(currentTab as CorrectionPhase)"
          >
            Сбросить переопределение
          </Button>
        </div>

        <div
          v-for="section in visibleSections"
          :key="section.key"
          class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] overflow-hidden"
        >
          <button
            type="button"
            class="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[var(--bg-surface-strong)] transition-colors"
            :data-testid="`correction-config-section-${section.key}`"
            @click="toggleSection(section.key)"
          >
            <span :class="['inline-block transition-transform', openSections.has(section.key) ? 'rotate-90' : '']">▸</span>
            <span class="text-sm font-medium text-[var(--text-primary)]">{{ section.label }}</span>
            <span class="text-[11px] font-mono text-[var(--text-dim)]">{{ section.key }}</span>
            <span class="ml-auto">
              <Chip
                v-if="sectionOverrideCount(section) > 0"
                tone="brand"
              >
                {{ sectionOverrideCount(section) }} переопределений
              </Chip>
              <Chip
                v-else
                tone="neutral"
              >
                без переопределений
              </Chip>
            </span>
          </button>

          <div
            v-if="openSections.has(section.key)"
            class="border-t border-[var(--border-muted)] px-3 py-3 flex flex-col gap-3"
          >
            <div
              v-if="sectionRuntimeNote(section.key, currentForm)"
              class="text-[11px] text-[var(--text-muted)] leading-relaxed px-2.5 py-1.5 rounded-md bg-[var(--bg-surface-strong)] border border-[var(--border-muted)]"
            >
              {{ sectionRuntimeNote(section.key, currentForm) }}
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div
                v-for="field in visibleFields(section.fields)"
                :key="field.path"
                :class="['flex flex-col gap-1', isFieldOverridden(field) ? 'cc-field--overridden' : '']"
              >
                <span class="text-xs font-medium text-[var(--text-muted)]">
                  {{ field.label }}
                  <span
                    v-if="field.unit"
                    class="text-[10px] text-[var(--text-dim)] ml-1"
                  >{{ field.unit }}</span>
                </span>

                <label
                  v-if="field.type === 'boolean'"
                  class="flex items-center gap-2 text-sm cursor-pointer"
                >
                  <input
                    :checked="Boolean(getByPath(currentForm, field.path))"
                    :data-testid="`correction-config-${currentTab}-${field.path}`"
                    type="checkbox"
                    class="accent-brand"
                    @change="setByPath(currentForm, field.path, ($event.target as HTMLInputElement).checked)"
                  />
                  {{ Boolean(getByPath(currentForm, field.path)) ? 'включено' : 'выключено' }}
                </label>

                <select
                  v-else-if="field.type === 'enum'"
                  :value="String(getByPath(currentForm, field.path) ?? '')"
                  :data-testid="`correction-config-${currentTab}-${field.path}`"
                  :class="inputCls"
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
                  :class="inputCls"
                  @input="handleScalarInput(currentForm, field, $event)"
                />

                <div
                  v-if="field.type !== 'boolean'"
                  class="text-[11px] text-[var(--text-dim)] leading-snug"
                >
                  {{ field.description }}
                  <span
                    v-if="isFieldOverridden(field) && currentTab !== 'base'"
                    class="text-brand ml-1 font-mono"
                  >
                    базовое: {{ formatFieldValue(field, getByPath(baseForm, field.path)) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- PREVIEW -->
      <aside
        class="min-w-0"
        data-testid="phase-effective-preview"
      >
        <div class="sticky top-0 flex flex-col gap-2 px-3 py-3 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)]">
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-sm font-semibold text-[var(--text-primary)]">
              Итоговое состояние runtime
            </h3>
            <Chip tone="neutral">
              <span class="font-mono">фаза: {{ currentTab }}</span>
            </Chip>
          </div>
          <div class="flex flex-wrap gap-1.5">
            <Chip tone="brand">
              <span class="font-mono">{{ phaseOverrideStats.overrideCount }} переопределений</span>
            </Chip>
            <Chip tone="neutral">
              <span class="font-mono">{{ phaseOverrideStats.sectionCount }} секций затронуто</span>
            </Chip>
            <Chip
              v-if="phaseOverrideStats.hiddenOverrideCount > 0"
              tone="neutral"
            >
              <span class="font-mono">скрыто в расширенных: {{ phaseOverrideStats.hiddenOverrideCount }}</span>
            </Chip>
          </div>

          <div
            v-for="group in effectivePreviewGroups"
            :key="group.key"
            class="flex flex-col gap-1 mt-1 pt-2 border-t border-[var(--border-muted)]"
          >
            <h5 class="text-[11px] uppercase tracking-wider text-[var(--text-dim)] font-semibold">
              {{ group.label }}
            </h5>
            <div
              v-for="item in group.items"
              :key="item.path"
              :class="['cc-preview__row flex items-baseline justify-between gap-2 text-[12px]', item.overridden ? 'cc-preview__row--overridden' : '']"
            >
              <span class="text-[var(--text-muted)]">{{ item.label }}</span>
              <span class="font-mono text-[var(--text-primary)]">
                {{ item.value }}
                <span
                  v-if="item.overridden"
                  class="cc-preview__base text-[10px] text-[var(--text-dim)] ml-1"
                >{{ item.baseValue }}</span>
              </span>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <!-- CONFLICT BANNER -->
    <teleport to="body">
      <div
        v-if="conflictOpen"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-sm"
        data-testid="correction-config-conflict-banner"
      >
        <div class="w-[min(540px,95vw)] rounded-lg border border-[var(--border-muted)] bg-[var(--bg-surface-strong)] shadow-2xl p-4 flex flex-col gap-3">
          <div class="flex items-start gap-3">
            <span class="text-warn text-2xl leading-none">⚠</span>
            <div class="flex-1">
              <h4 class="text-base font-semibold text-[var(--text-primary)]">
                Применить пресет «{{ pendingPresetName }}»?
              </h4>
              <p class="text-[12px] text-[var(--text-muted)] leading-relaxed mt-1">
                В форме есть <b>{{ pendingPresetDiffs.length }} несохранённых</b> переопределений,
                которые будут затёрты значениями пресета. Несохранённые изменения
                нельзя будет восстановить.
              </p>
              <div class="flex flex-wrap gap-1 mt-2">
                <Chip
                  v-for="d in pendingPresetDiffs.slice(0, 6)"
                  :key="d.path"
                  tone="warn"
                >
                  <span class="font-mono">{{ d.label }}: {{ d.oldVal }} → {{ d.newVal }}</span>
                </Chip>
                <Chip
                  v-if="pendingPresetDiffs.length > 6"
                  tone="neutral"
                >
                  +{{ pendingPresetDiffs.length - 6 }} ещё
                </Chip>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2 justify-end">
            <Button
              size="sm"
              variant="secondary"
              @click="cancelPendingPreset"
            >
              Отмена
            </Button>
            <Button
              size="sm"
              variant="secondary"
              @click="openPresetCompareDiff"
            >
              Сравнить diff
            </Button>
            <Button
              size="sm"
              variant="primary"
              @click="confirmApplyPendingPreset"
            >
              Применить и затереть
            </Button>
          </div>
        </div>
      </div>
    </teleport>

    <!-- HISTORY DRAWER -->
    <teleport to="body">
      <div
        v-if="historyDrawerOpen"
        class="fixed inset-0 z-50 flex justify-end bg-black/45 backdrop-blur-sm"
        @click.self="historyDrawerOpen = false"
      >
        <aside
          class="w-[min(440px,95vw)] h-screen flex flex-col bg-[var(--bg-surface-strong)] border-l border-[var(--border-muted)] shadow-2xl"
          role="dialog"
          aria-label="История версий"
        >
          <header class="flex items-center gap-2 px-4 py-3 border-b border-[var(--border-muted)]">
            <h3 class="text-sm font-semibold text-[var(--text-primary)]">
              История версий
            </h3>
            <Chip tone="neutral">
              <span class="font-mono">{{ history.length }} ревизий</span>
            </Chip>
            <button
              type="button"
              class="ml-auto w-7 h-7 inline-flex items-center justify-center rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]"
              @click="historyDrawerOpen = false"
            >
              <Ic name="x" />
            </button>
          </header>
          <div class="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-2">
            <div
              v-if="history.length === 0"
              class="text-sm text-[var(--text-dim)] py-6 text-center"
            >
              Нет ревизий.
            </div>
            <div
              v-for="item in history"
              :key="item.id"
              class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] px-3 py-2 flex flex-col gap-1 cursor-pointer hover:border-brand transition-colors"
              @click="openHistoryDiff(item)"
            >
              <div class="flex items-center gap-2">
                <span class="text-sm font-mono font-semibold text-brand">v{{ item.version }}</span>
                <Chip :tone="historyChipTone(item.change_type)">
                  {{ item.change_type }}
                </Chip>
                <span class="ml-auto text-[11px] font-mono text-[var(--text-dim)]">
                  {{ formatDate(item.changed_at) }}
                </span>
              </div>
              <div class="text-[12px] text-[var(--text-primary)]">
                {{ item.preset?.name || 'Системный пресет' }}
              </div>
              <div
                v-if="item.changed_by_name"
                class="text-[11px] font-mono text-[var(--text-dim)]"
              >
                {{ item.changed_by_name }}
              </div>
              <div class="flex gap-1.5 mt-1">
                <Button
                  size="sm"
                  variant="secondary"
                  @click.stop="openHistoryDiff(item)"
                >
                  показать diff
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  :disabled="loading"
                  @click.stop="restoreRevision(item)"
                >
                  восстановить
                </Button>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </teleport>

    <!-- DIFF MODAL -->
    <teleport to="body">
      <div
        v-if="diffModalOpen"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-sm p-4"
        data-testid="correction-config-diff-modal"
        @click.self="diffModalOpen = false"
      >
        <div class="w-[min(960px,95vw)] max-h-[90vh] flex flex-col rounded-lg border border-[var(--border-muted)] bg-[var(--bg-surface-strong)] shadow-2xl overflow-hidden">
          <header class="flex items-center gap-3 px-4 py-3 border-b border-[var(--border-muted)]">
            <h3 class="text-sm font-semibold text-[var(--text-primary)]">{{ diffTitle }}</h3>
            <span class="text-[11px] font-mono text-[var(--text-dim)]">{{ diffCrumb }}</span>
            <button
              type="button"
              class="ml-auto w-7 h-7 inline-flex items-center justify-center rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]"
              @click="diffModalOpen = false"
            >
              <Ic name="x" />
            </button>
          </header>
          <div class="flex gap-1 px-4 pt-2 border-b border-[var(--border-muted)]">
            <button
              v-for="fmt in (['yaml', 'json', 'fields'] as const)"
              :key="fmt"
              type="button"
              :class="diffTabClass(diffFormat === fmt)"
              @click="diffFormat = fmt"
            >
              {{ fmt === 'fields' ? 'По полям' : fmt.toUpperCase() }}
            </button>
          </div>
          <div class="flex-1 overflow-hidden grid grid-cols-1 md:grid-cols-2 gap-px bg-[var(--border-muted)]">
            <div class="flex flex-col bg-[var(--bg-elevated)] overflow-hidden">
              <div class="flex items-center gap-2 px-3 py-1.5 text-[11px] font-mono text-[var(--text-dim)] border-b border-[var(--border-muted)]">
                <b class="text-[var(--text-primary)]">было</b>
                <span class="ml-auto">{{ diffFormat }}</span>
              </div>
              <div class="flex-1 overflow-auto font-mono text-[11px]">
                <div
                  v-for="(line, i) in diffRender.before"
                  :key="`b-${i}`"
                  :class="['flex gap-2 px-2 py-0.5', diffLineClass(line.t)]"
                >
                  <div class="w-8 text-right text-[var(--text-dim)] flex-shrink-0">{{ line.n }}</div>
                  <pre class="flex-1 whitespace-pre-wrap break-all">{{ line.c }}</pre>
                </div>
              </div>
            </div>
            <div class="flex flex-col bg-[var(--bg-elevated)] overflow-hidden">
              <div class="flex items-center gap-2 px-3 py-1.5 text-[11px] font-mono text-[var(--text-dim)] border-b border-[var(--border-muted)]">
                <b class="text-[var(--text-primary)]">стало</b>
                <span class="ml-auto">{{ diffFormat }}</span>
              </div>
              <div class="flex-1 overflow-auto font-mono text-[11px]">
                <div
                  v-for="(line, i) in diffRender.after"
                  :key="`a-${i}`"
                  :class="['flex gap-2 px-2 py-0.5', diffLineClass(line.t)]"
                >
                  <div class="w-8 text-right text-[var(--text-dim)] flex-shrink-0">{{ line.n }}</div>
                  <pre class="flex-1 whitespace-pre-wrap break-all">{{ line.c }}</pre>
                </div>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-3 px-4 py-2 text-[11px] font-mono text-[var(--text-dim)] border-t border-[var(--border-muted)] bg-[var(--bg-elevated)]">
            <span><span class="text-growth">+{{ diffStats.add }}</span> добавлено</span>
            <span><span class="text-alert">−{{ diffStats.del }}</span> удалено</span>
            <span>{{ diffStats.sections }} секций</span>
            <span class="ml-auto">{{ diffMeta }}</span>
          </div>
          <footer class="flex items-center gap-2 px-4 py-3 border-t border-[var(--border-muted)]">
            <Button
              variant="secondary"
              @click="diffModalOpen = false"
            >
              Закрыть
            </Button>
            <div class="flex-1" />
            <Button
              variant="secondary"
              @click="copyDiffText"
            >
              Скопировать diff
            </Button>
            <Button
              v-if="diffContext?.kind === 'history'"
              variant="primary"
              :disabled="loading"
              @click="restoreDiffRevision"
            >
              Восстановить v{{ diffContext.item.version }}
            </Button>
          </footer>
        </div>
      </div>
    </teleport>

    <!-- NEW PRESET MODAL -->
    <teleport to="body">
      <div
        v-if="newPresetModalOpen"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-sm p-4"
        @click.self="newPresetModalOpen = false"
      >
        <div class="w-[min(560px,95vw)] flex flex-col rounded-lg border border-[var(--border-muted)] bg-[var(--bg-surface-strong)] shadow-2xl overflow-hidden">
          <header class="flex items-center gap-3 px-4 py-3 border-b border-[var(--border-muted)]">
            <h3 class="text-sm font-semibold text-[var(--text-primary)]">
              Сохранить как пользовательский пресет
            </h3>
            <button
              type="button"
              class="ml-auto w-7 h-7 inline-flex items-center justify-center rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]"
              @click="newPresetModalOpen = false"
            >
              <Ic name="x" />
            </button>
          </header>
          <div class="px-4 py-3 flex flex-col gap-3">
            <Field label="Название">
              <input
                v-model="newPresetName"
                type="text"
                :class="inputCls"
                placeholder="Hydro · Tomato · v3"
                data-testid="correction-config-new-preset-name"
              />
            </Field>
            <Field label="Описание">
              <textarea
                v-model="newPresetDescription"
                :class="[inputCls, 'min-h-[80px] resize-y']"
                placeholder="Когда использовать этот пресет, какие цели"
                data-testid="correction-config-new-preset-description"
              />
            </Field>
          </div>
          <footer class="flex items-center gap-2 px-4 py-3 border-t border-[var(--border-muted)] justify-end">
            <Button
              variant="secondary"
              @click="newPresetModalOpen = false"
            >
              Отмена
            </Button>
            <Button
              variant="primary"
              :disabled="loading || !newPresetName.trim()"
              data-testid="correction-config-save-preset"
              @click="onSaveAsPreset"
            >
              Сохранить пресет
            </Button>
          </footer>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import { Chip, Field } from '@/Components/Shared/Primitives'
import type { ChipTone } from '@/Components/Shared/Primitives'
import Ic from '@/Components/Icons/Ic.vue'
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

const inputCls =
  'w-full px-2.5 py-1.5 rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] text-sm text-[var(--text-primary)] focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand/40 disabled:opacity-55'

const menuItemClass =
  'block w-full text-left px-3 py-1.5 text-[12px] text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] disabled:opacity-45 disabled:cursor-not-allowed'

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

/* ================== UI-ONLY STATE ================== */
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
  return `${controller} observe-loop: после дозы runtime ждёт окно из Process Calibration (transport_delay_sec + settle_sec), затем набирает decision window ${dw} сек и повторяет observe-check каждые ${op} сек. Эффект ниже ${mef} считается no-effect; после ${nel} подряд no-effect correction идёт в fail-closed при включённом safety guard.`
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

function historyChipTone(ct: string): ChipTone {
  if (ct === 'ae_rollback') return 'warn'
  if (ct === 'preset_apply') return 'brand'
  if (ct === 'update') return 'brand'
  return 'neutral'
}

function presetPillClass(active: boolean): string {
  return [
    'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[12px] cursor-pointer transition-colors',
    active
      ? 'bg-brand-soft border-brand text-brand-ink font-semibold'
      : 'border-[var(--border-muted)] text-[var(--text-muted)] hover:bg-[var(--bg-surface-strong)]',
  ].join(' ')
}

function phaseTabClass(active: boolean): string {
  return [
    'flex flex-col items-start gap-0.5 px-3 py-2 -mb-px border-b-2 cursor-pointer transition-colors min-w-[160px]',
    active
      ? 'border-brand text-[var(--text-primary)]'
      : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]',
  ].join(' ')
}

function diffTabClass(active: boolean): string {
  return [
    'px-3 py-1.5 -mb-px text-[12px] font-medium border-b-2 transition-colors cursor-pointer',
    active
      ? 'border-brand text-brand'
      : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]',
  ].join(' ')
}

function diffLineClass(t: 'ctx' | 'add' | 'del' | 'hdr'): string {
  if (t === 'add') return 'bg-growth-soft/20 text-growth'
  if (t === 'del') return 'bg-alert-soft/20 text-alert'
  if (t === 'hdr') return 'text-[var(--text-dim)] font-semibold'
  return 'text-[var(--text-muted)]'
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

/* ================== API CALLS ================== */
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

/* ================== PRESET MENU ACTIONS ================== */
function onMenuRename(): void {
  presetMenuOpen.value = false
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
  if (s.length && openSections.value.size === 0) {
    const initial = new Set<string>([s[0].key])
    for (const section of s) {
      if (section.key === 'controllers.ph' || section.key === 'controllers.ec') {
        initial.add(section.key)
      }
    }
    openSections.value = initial
  }
})

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
