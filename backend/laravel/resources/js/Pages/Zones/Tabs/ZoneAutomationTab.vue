<template>
  <div class="space-y-4">
    <div
      v-if="!zoneId"
      class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 text-sm text-[color:var(--text-dim)]"
    >
      Нет данных зоны для автоматизации.
    </div>

    <template v-else>
      <section class="ui-hero p-5">
        <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div>
            <p class="text-[11px] uppercase tracking-[0.24em] text-[color:var(--text-dim)]">
              профиль управления
            </p>
            <h2 class="text-xl font-semibold mt-1 text-[color:var(--text-primary)]">
              Климат, вода и досветка
            </h2>
            <p class="text-sm text-[color:var(--text-muted)] mt-1 max-w-3xl">
              Значения на карточках берутся из активного рецепта/таргетов. Редактирование доступно через мастер.
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <Badge :variant="canConfigureAutomation ? 'success' : 'warning'">
              {{ canConfigureAutomation ? 'Режим настройки (агроном)' : 'Режим оператора' }}
            </Badge>
            <Badge variant="info">
              Телеметрия: {{ telemetryLabel }}
            </Badge>
            <Button
              v-if="canConfigureAutomation"
              size="sm"
              @click="showEditWizard = true"
            >
              Редактировать
            </Button>
          </div>
        </div>

        <div class="ui-kpi-grid md:grid-cols-2 xl:grid-cols-4 mt-4">
          <article class="ui-kpi-card">
            <div class="ui-kpi-label">Форточки</div>
            <div class="ui-kpi-value !text-lg">{{ climateForm.ventMinPercent }}-{{ climateForm.ventMaxPercent }}%</div>
            <div class="ui-kpi-hint">Диапазон открытия · каждые {{ climateForm.intervalMinutes }} мин</div>
          </article>

          <article class="ui-kpi-card">
            <div class="ui-kpi-label">Водный узел</div>
            <div class="ui-kpi-value !text-lg">{{ waterForm.tanksCount }} бака · {{ waterForm.systemType }}</div>
            <div class="ui-kpi-hint">
              {{ waterTopologyLabel }} · diag {{ waterForm.diagnosticsIntervalMinutes }} мин
            </div>
          </article>

          <article class="ui-kpi-card">
            <div class="ui-kpi-label">Коррекция pH / EC</div>
            <div class="ui-kpi-value !text-lg">pH {{ waterForm.targetPh.toFixed(1) }} · EC {{ waterForm.targetEc.toFixed(1) }}</div>
            <div class="ui-kpi-hint">Интервал {{ waterForm.intervalMinutes }} мин, {{ waterForm.durationSeconds }} сек</div>
          </article>

          <article class="ui-kpi-card">
            <div class="ui-kpi-label">Досветка</div>
            <div class="ui-kpi-value !text-lg">{{ lightingForm.luxDay }} lux</div>
            <div class="ui-kpi-hint">
              {{ lightingForm.scheduleStart }}-{{ lightingForm.scheduleEnd }} · {{ lightingForm.intervalMinutes }} мин
            </div>
          </article>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-2">
        <button
          type="button"
          class="w-full rounded-xl px-3 py-2 text-left transition-colors hover:bg-[color:var(--surface-muted)]/40"
          @click="processExpanded = !processExpanded"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0">
              <p class="text-[11px] uppercase tracking-[0.2em] text-[color:var(--text-dim)]">workflow</p>
              <div class="flex items-center gap-2 mt-1">
                <span class="text-sm md:text-base font-semibold text-[color:var(--text-primary)]">
                  Процесс выполнения автоматизации
                </span>
                <Badge
                  v-if="isProcessActive"
                  variant="info"
                  class="animate-pulse"
                >
                  Выполняется
                </Badge>
              </div>
            </div>
            <svg
              class="w-5 h-5 text-[color:var(--text-dim)] transition-transform duration-200"
              :class="{ 'rotate-180': processExpanded }"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="m6 9 6 6 6-6" />
            </svg>
          </div>
        </button>

        <div
          v-show="processExpanded"
          class="p-2 pt-3"
        >
          <AutomationProcessPanel
            :zone-id="zoneId"
            :fallback-tanks-count="waterForm.tanksCount"
            :fallback-system-type="waterForm.systemType"
            @state-change="handleProcessStateChange"
          />
        </div>
      </section>

      <section class="grid gap-4 xl:grid-cols-2">
        <article class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">Климат</h3>
          <dl class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <div>
              <dt class="text-[color:var(--text-dim)]">Температура</dt>
              <dd class="text-[color:var(--text-primary)]">{{ climateForm.dayTemp }}°C день / {{ climateForm.nightTemp }}°C ночь</dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Влажность</dt>
              <dd class="text-[color:var(--text-primary)]">{{ climateForm.dayHumidity }}% день / {{ climateForm.nightHumidity }}% ночь</dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Профиль</dt>
              <dd class="text-[color:var(--text-primary)]">{{ climateForm.enabled ? 'Автоклимат включен' : 'Автоклимат выключен' }}</dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Интервал</dt>
              <dd class="text-[color:var(--text-primary)]">{{ climateForm.intervalMinutes }} мин</dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Внешний guard</dt>
              <dd class="text-[color:var(--text-primary)]">{{ climateForm.useExternalTelemetry ? 'Включен' : 'Выключен' }}</dd>
            </div>
          </dl>
        </article>

        <article class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">Вода и узел коррекции</h3>
          <dl class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <div>
              <dt class="text-[color:var(--text-dim)]">Тип системы</dt>
              <dd class="text-[color:var(--text-primary)]">{{ waterForm.systemType }}</dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Объём баков</dt>
              <dd class="text-[color:var(--text-primary)]">{{ waterForm.cleanTankFillL }} / {{ waterForm.nutrientTankTargetL }} л</dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Полив</dt>
              <dd class="text-[color:var(--text-primary)]">Каждые {{ waterForm.intervalMinutes }} мин, {{ waterForm.durationSeconds }} сек</dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Коррекция</dt>
              <dd class="text-[color:var(--text-primary)]">pH {{ waterForm.targetPh.toFixed(1) }} · EC {{ waterForm.targetEc.toFixed(1) }}</dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Диагностика</dt>
              <dd class="text-[color:var(--text-primary)]">
                {{ waterForm.diagnosticsEnabled ? 'вкл' : 'выкл' }} · {{ waterForm.diagnosticsIntervalMinutes }} мин
              </dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Смена раствора</dt>
              <dd class="text-[color:var(--text-primary)]">
                {{ waterForm.solutionChangeEnabled ? 'вкл' : 'выкл' }} · {{ waterForm.solutionChangeIntervalMinutes }} мин / {{ waterForm.solutionChangeDurationSeconds }} сек
              </dd>
            </div>
          </dl>
          <p
            v-if="isSystemTypeLocked"
            class="text-xs text-[color:var(--text-dim)]"
          >
            Тип системы зафиксирован для активного цикла.
          </p>
        </article>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">Операционные команды</h3>
          <div class="text-xs text-[color:var(--text-muted)]">Быстрые действия оператора</div>
        </div>

        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <Button
            size="sm"
            :disabled="!canOperateAutomation || quickActions.irrigation"
            @click="runManualIrrigation"
          >
            {{ quickActions.irrigation ? 'Отправка...' : 'Запустить полив' }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :disabled="!canOperateAutomation || quickActions.climate"
            @click="runManualClimate"
          >
            {{ quickActions.climate ? 'Отправка...' : 'Применить климат' }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :disabled="!canOperateAutomation || quickActions.lighting"
            @click="runManualLighting"
          >
            {{ quickActions.lighting ? 'Отправка...' : 'Применить свет' }}
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="!canOperateAutomation || quickActions.ph"
            @click="runManualPh"
          >
            {{ quickActions.ph ? 'Отправка...' : 'Дать target pH' }}
          </Button>
          <Button
            size="sm"
            variant="outline"
            :disabled="!canOperateAutomation || quickActions.ec"
            @click="runManualEc"
          >
            {{ quickActions.ec ? 'Отправка...' : 'Дать target EC' }}
          </Button>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
          <div>
            <h3 class="text-base font-semibold text-[color:var(--text-primary)]">Применение профиля автоматики</h3>
            <p class="text-xs text-[color:var(--text-dim)] mt-1">
              Профиль сначала сохраняется в БД, затем отправляется `GROWTH_CYCLE_CONFIG` (`mode=adjust`, `profile_mode`).
            </p>
          </div>
          <div class="text-xs text-[color:var(--text-muted)]">
            <span v-if="lastAppliedAt">Последнее применение: {{ formatDateTime(lastAppliedAt) }}</span>
            <span v-else>Профиль ещё не применялся</span>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-[220px,1fr] gap-3 items-end">
          <label class="text-xs text-[color:var(--text-muted)]">
            Режим профиля
            <select
              v-model="automationLogicMode"
              class="input-select mt-1 w-full"
              :disabled="!canConfigureAutomation || isApplyingProfile || isSyncingAutomationLogicProfile"
            >
              <option value="setup">setup</option>
              <option value="working">working</option>
            </select>
          </label>
          <div class="text-xs text-[color:var(--text-muted)]">
            <span v-if="isSyncingAutomationLogicProfile">Синхронизация профиля с бэкендом...</span>
            <span v-else-if="lastAutomationLogicSyncAt">Профиль в БД обновлён: {{ formatDateTime(lastAutomationLogicSyncAt) }}</span>
            <span v-else>Профиль в БД ещё не синхронизирован</span>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            :disabled="!canConfigureAutomation || isApplyingProfile || isSyncingAutomationLogicProfile"
            @click="applyAutomationProfile"
          >
            {{ isApplyingProfile ? 'Отправка профиля...' : (isSyncingAutomationLogicProfile ? 'Сохранение профиля...' : 'Применить профиль автоматики') }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :disabled="isApplyingProfile || isSyncingAutomationLogicProfile"
            @click="resetToRecommended"
          >
            Восстановить рекомендуемые значения
          </Button>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
          <div>
            <h3 class="text-base font-semibold text-[color:var(--text-primary)]">Scheduler Task Lifecycle</h3>
            <p class="text-xs text-[color:var(--text-dim)] mt-1">
              Мониторинг статусов `accepted -> running -> completed/failed/rejected/expired` по `task_id`.
            </p>
          </div>
          <div class="text-xs text-[color:var(--text-muted)]">
            <span v-if="schedulerTasksUpdatedAt">Обновлено: {{ formatDateTime(schedulerTasksUpdatedAt) }}</span>
            <span v-else>Ожидание данных</span>
          </div>
        </div>

        <div class="flex flex-col md:flex-row gap-2">
          <input
            v-model="schedulerTaskIdInput"
            type="text"
            class="w-full md:flex-1 rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)] px-3 py-2 text-sm"
            placeholder="st-..."
          />
          <div class="flex gap-2">
            <Button
              size="sm"
              :disabled="schedulerTaskLookupLoading"
              @click="lookupSchedulerTask()"
            >
              {{ schedulerTaskLookupLoading ? 'Проверка...' : 'Проверить task_id' }}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              :disabled="schedulerTaskListLoading"
              @click="fetchRecentSchedulerTasks()"
            >
              {{ schedulerTaskListLoading ? 'Обновление...' : 'Обновить список' }}
            </Button>
          </div>
        </div>

        <p
          v-if="schedulerTaskError"
          class="text-xs text-red-500"
        >
          {{ schedulerTaskError }}
        </p>

        <article
          v-if="schedulerTaskStatus"
          class="rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--surface-muted)]/40 p-3 space-y-3"
        >
          <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
            <div class="text-sm">
              <span class="text-[color:var(--text-dim)]">task_id:</span>
              <span class="font-mono text-[color:var(--text-primary)] ml-1">{{ schedulerTaskStatus.task_id }}</span>
            </div>
            <Badge :variant="schedulerTaskStatusVariant(schedulerTaskStatus.status)">
              {{ schedulerTaskStatusLabel(schedulerTaskStatus.status) }}
            </Badge>
          </div>
          <dl class="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
            <div>
              <dt class="text-[color:var(--text-dim)]">Тип</dt>
              <dd class="text-[color:var(--text-primary)]">{{ schedulerTaskStatus.task_type || '-' }}</dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Создана</dt>
              <dd class="text-[color:var(--text-primary)]">{{ formatDateTime(schedulerTaskStatus.created_at) }}</dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Обновлена</dt>
              <dd class="text-[color:var(--text-primary)]">{{ formatDateTime(schedulerTaskStatus.updated_at) }}</dd>
            </div>
          </dl>
          <dl class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-2 text-xs">
            <div>
              <dt class="text-[color:var(--text-dim)]">Scheduled</dt>
              <dd class="text-[color:var(--text-primary)]">{{ formatDateTime(schedulerTaskStatus.scheduled_for) }}</dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Due</dt>
              <dd class="text-[color:var(--text-primary)]">{{ formatDateTime(schedulerTaskStatus.due_at || null) }}</dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Expires</dt>
              <dd class="text-[color:var(--text-primary)]">{{ formatDateTime(schedulerTaskStatus.expires_at || null) }}</dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">SLA-контроль</dt>
              <dd class="space-y-1">
                <Badge :variant="schedulerTaskSla.variant">{{ schedulerTaskSla.label }}</Badge>
                <p class="text-[color:var(--text-dim)]">{{ schedulerTaskSla.hint }}</p>
              </dd>
            </div>
          </dl>
          <dl class="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
            <div>
              <dt class="text-[color:var(--text-dim)]">Решение автоматики</dt>
              <dd class="text-[color:var(--text-primary)]">
                {{ schedulerTaskDecisionLabel(schedulerTaskStatus.decision) }}
                <span
                  v-if="schedulerTaskStatus.action_required === false"
                  class="text-[color:var(--text-dim)]"
                >
                  (действие не требуется)
                </span>
              </dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Причина</dt>
              <dd class="text-[color:var(--text-primary)]">
                {{ schedulerTaskReasonLabel(schedulerTaskStatus.reason_code, schedulerTaskStatus.reason) }}
              </dd>
            </div>
          </dl>
          <dl class="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
            <div>
              <dt class="text-[color:var(--text-dim)]">Подтверждение ноды DONE</dt>
              <dd class="space-y-1">
                <Badge :variant="schedulerTaskDone.variant">{{ schedulerTaskDone.label }}</Badge>
                <p class="text-[color:var(--text-dim)]">{{ schedulerTaskDone.hint }}</p>
              </dd>
            </div>
            <div>
              <dt class="text-[color:var(--text-dim)]">Командный итог</dt>
              <dd class="text-[color:var(--text-primary)]">
                {{ schedulerTaskStatus.commands_effect_confirmed ?? schedulerTaskStatus.result?.commands_effect_confirmed ?? '-' }}
                /
                {{ schedulerTaskStatus.commands_total ?? schedulerTaskStatus.result?.commands_total ?? '-' }}
                подтверждено DONE
              </dd>
            </div>
          </dl>
          <dl
            v-if="schedulerTaskStatus.error_code || schedulerTaskStatus.error"
            class="grid grid-cols-1 gap-2 text-xs"
          >
            <div>
              <dt class="text-[color:var(--text-dim)]">Ошибка</dt>
              <dd class="text-[color:var(--text-primary)]">
                {{ schedulerTaskErrorLabel(schedulerTaskStatus.error_code, schedulerTaskStatus.error) }}
              </dd>
            </div>
          </dl>

          <ul
            v-if="schedulerTaskStatus.timeline && schedulerTaskStatus.timeline.length > 0"
            class="space-y-1 text-xs"
          >
            <li
              v-for="(step, index) in schedulerTaskStatus.timeline"
              :key="`${schedulerTaskStatus.task_id}-timeline-${step.event_id || index}`"
              class="flex flex-col md:flex-row md:items-center md:justify-between gap-1 border-b border-[color:var(--border-muted)]/40 pb-1 last:border-0"
            >
              <div class="text-[color:var(--text-primary)]">
                {{ schedulerTaskEventLabel(step.event_type) }}
                <span
                  v-if="step.reason_code"
                  class="text-[color:var(--text-dim)]"
                >
                  · {{ schedulerTaskReasonLabel(step.reason_code, step.reason) }}
                </span>
                <span
                  v-if="step.error_code"
                  class="text-red-500"
                >
                  · {{ schedulerTaskErrorLabel(step.error_code) }}
                </span>
              </div>
              <div class="text-[color:var(--text-dim)]">
                {{ formatDateTime(step.at) }}
              </div>
            </li>
          </ul>
          <p
            v-else
            class="text-xs text-[color:var(--text-dim)]"
          >
            Timeline событий недоступен: ожидается event-contract (`event_id`, `event_type`, `at`).
          </p>
        </article>

        <div class="space-y-2">
          <h4 class="text-sm font-medium text-[color:var(--text-primary)]">Последние задачи зоны</h4>
          <div class="grid grid-cols-1 lg:grid-cols-3 gap-2">
            <input
              v-model="schedulerTaskSearch"
              type="text"
              class="w-full rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)] px-3 py-2 text-xs"
              placeholder="Поиск: task_id/status/error_code/reason_code"
            />
            <select
              v-model="schedulerTaskPreset"
              class="w-full rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)] px-3 py-2 text-xs"
            >
              <option
                v-for="preset in schedulerTaskPresetOptions"
                :key="preset.value"
                :value="preset.value"
              >
                {{ preset.label }}
              </option>
            </select>
            <Button
              size="sm"
              variant="outline"
              @click="schedulerTaskPreset = 'all'; schedulerTaskSearch = ''"
            >
              Сбросить фильтры
            </Button>
          </div>
          <ul
            v-if="filteredRecentSchedulerTasks.length > 0"
            class="space-y-2"
          >
            <li
              v-for="task in filteredRecentSchedulerTasks"
              :key="task.task_id"
              class="flex flex-col md:flex-row md:items-center md:justify-between gap-2 rounded-xl border border-[color:var(--border-muted)] px-3 py-2"
            >
              <div class="min-w-0">
                <p class="font-mono text-xs text-[color:var(--text-primary)] truncate">{{ task.task_id }}</p>
                <p class="text-xs text-[color:var(--text-dim)]">
                  {{ task.task_type || '-' }} · {{ formatDateTime(task.updated_at) }}
                </p>
              </div>
              <div class="flex items-center gap-2">
                <Badge :variant="schedulerTaskStatusVariant(task.status)">
                  {{ schedulerTaskStatusLabel(task.status) }}
                </Badge>
                <Button
                  size="sm"
                  variant="outline"
                  @click="lookupSchedulerTask(task.task_id)"
                >
                  Открыть
                </Button>
              </div>
            </li>
          </ul>
          <p
            v-else
            class="text-xs text-[color:var(--text-dim)]"
          >
            По текущим фильтрам задачи не найдены.
          </p>
        </div>
      </section>

      <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
        <AIPredictionsSection
          :zone-id="zoneId"
          :targets="predictionTargets"
          :horizon-minutes="60"
          :auto-refresh="true"
          :default-expanded="false"
        />
      </div>

      <ZoneAutomationEditWizard
        :open="showEditWizard"
        :climate-form="climateForm"
        :water-form="waterForm"
        :lighting-form="lightingForm"
        :is-applying="isApplyingProfile"
        :is-system-type-locked="isSystemTypeLocked"
        @close="showEditWizard = false"
        @apply="onApplyFromWizard"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import AIPredictionsSection from '@/Components/AIPredictionsSection.vue'
import AutomationProcessPanel from '@/Components/AutomationProcessPanel.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import ZoneAutomationEditWizard from '@/Pages/Zones/Tabs/ZoneAutomationEditWizard.vue'
import type {
  ClimateFormState,
  LightingFormState,
  WaterFormState,
} from '@/composables/zoneAutomationTypes'
import type { AutomationStateType } from '@/types/Automation'
import {
  type ZoneAutomationTabProps,
  useZoneAutomationTab,
} from '@/composables/useZoneAutomationTab'

interface ZoneAutomationWizardApplyPayload {
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
}

const props = defineProps<ZoneAutomationTabProps>()

const {
  canConfigureAutomation,
  canOperateAutomation,
  isSystemTypeLocked,
  climateForm,
  waterForm,
  lightingForm,
  quickActions,
  isApplyingProfile,
  isSyncingAutomationLogicProfile,
  lastAppliedAt,
  automationLogicMode,
  lastAutomationLogicSyncAt,
  predictionTargets,
  telemetryLabel,
  waterTopologyLabel,
  applyAutomationProfile,
  resetToRecommended,
  runManualIrrigation,
  runManualClimate,
  runManualLighting,
  runManualPh,
  runManualEc,
  schedulerTaskIdInput,
  schedulerTaskLookupLoading,
  schedulerTaskListLoading,
  schedulerTaskError,
  schedulerTaskStatus,
  filteredRecentSchedulerTasks,
  schedulerTaskSearch,
  schedulerTaskPreset,
  schedulerTaskPresetOptions,
  schedulerTasksUpdatedAt,
  fetchRecentSchedulerTasks,
  lookupSchedulerTask,
  schedulerTaskStatusVariant,
  schedulerTaskStatusLabel,
  schedulerTaskEventLabel,
  schedulerTaskDecisionLabel,
  schedulerTaskReasonLabel,
  schedulerTaskErrorLabel,
  schedulerTaskSlaMeta,
  schedulerTaskDoneMeta,
  formatDateTime,
} = useZoneAutomationTab(props)

const zoneId = toRef(props, 'zoneId')
const showEditWizard = ref(false)
const processExpanded = ref(true)
const processState = ref<AutomationStateType>('IDLE')
const schedulerTaskSla = computed(() => schedulerTaskSlaMeta(schedulerTaskStatus.value))
const schedulerTaskDone = computed(() => schedulerTaskDoneMeta(schedulerTaskStatus.value))
const isProcessActive = computed(() => processState.value !== 'IDLE' && processState.value !== 'READY')

function handleProcessStateChange(state: AutomationStateType): void {
  processState.value = state
}

async function onApplyFromWizard(payload: ZoneAutomationWizardApplyPayload): Promise<void> {
  Object.assign(climateForm, payload.climateForm)
  Object.assign(waterForm, payload.waterForm)
  Object.assign(lightingForm, payload.lightingForm)

  const success = await applyAutomationProfile()
  if (success) {
    showEditWizard.value = false
  }
}
</script>
