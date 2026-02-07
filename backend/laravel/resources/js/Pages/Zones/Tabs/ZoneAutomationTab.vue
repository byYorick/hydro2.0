<template>
  <!-- eslint-disable vue/singleline-html-element-content-newline -->
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
              Настройка целевых параметров и быстрых ручных действий для оператора.
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <Badge :variant="canConfigureAutomation ? 'success' : 'warning'">
              {{ canConfigureAutomation ? 'Режим настройки (агроном)' : 'Режим оператора' }}
            </Badge>
            <Badge variant="info">
              Телеметрия: {{ telemetryLabel }}
            </Badge>
          </div>
        </div>

        <div class="ui-kpi-grid md:grid-cols-2 xl:grid-cols-4 mt-4">
          <article class="ui-kpi-card">
            <div class="ui-kpi-label">
              Форточки
            </div>
            <div class="ui-kpi-value !text-lg">
              {{ climateForm.ventMinPercent }}-{{ climateForm.ventMaxPercent }}%
            </div>
            <div class="ui-kpi-hint">
              Диапазон открытия
            </div>
          </article>

          <article class="ui-kpi-card">
            <div class="ui-kpi-label">
              Водный узел
            </div>
            <div class="ui-kpi-value !text-lg">
              {{ waterForm.tanksCount }} бака
            </div>
            <div class="ui-kpi-hint">
              {{ waterTopologyLabel }}
            </div>
          </article>

          <article class="ui-kpi-card">
            <div class="ui-kpi-label">
              Коррекция pH / EC
            </div>
            <div class="ui-kpi-value !text-lg">
              pH {{ waterForm.targetPh.toFixed(1) }} · EC {{ waterForm.targetEc.toFixed(1) }}
            </div>
            <div class="ui-kpi-hint">
              Параметры узла коррекции
            </div>
          </article>

          <article class="ui-kpi-card">
            <div class="ui-kpi-label">
              Досветка
            </div>
            <div class="ui-kpi-value !text-lg">
              {{ lightingForm.luxDay }} lux
            </div>
            <div class="ui-kpi-hint">
              {{ lightingForm.scheduleStart }}-{{ lightingForm.scheduleEnd }}
            </div>
          </article>
        </div>
      </section>

      <section class="grid gap-4 xl:grid-cols-2">
        <article class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
          <div class="flex items-center justify-between gap-3">
            <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
              Климат
            </h3>
            <label class="inline-flex items-center gap-2 text-xs text-[color:var(--text-muted)]">
              <input
                v-model="climateForm.enabled"
                type="checkbox"
                class="rounded border-[color:var(--border-muted)]"
                :disabled="!canConfigureAutomation"
              />
              Автоклимат
            </label>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label class="text-xs text-[color:var(--text-muted)]">
              Температура день
              <input
                v-model.number="climateForm.dayTemp"
                type="number"
                min="10"
                max="35"
                step="0.5"
                class="input-field mt-1 w-full"
                :disabled="!canConfigureAutomation"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Температура ночь
              <input
                v-model.number="climateForm.nightTemp"
                type="number"
                min="10"
                max="35"
                step="0.5"
                class="input-field mt-1 w-full"
                :disabled="!canConfigureAutomation"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Влажность день
              <input
                v-model.number="climateForm.dayHumidity"
                type="number"
                min="30"
                max="90"
                class="input-field mt-1 w-full"
                :disabled="!canConfigureAutomation"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Влажность ночь
              <input
                v-model.number="climateForm.nightHumidity"
                type="number"
                min="30"
                max="90"
                class="input-field mt-1 w-full"
                :disabled="!canConfigureAutomation"
              />
            </label>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label class="text-xs text-[color:var(--text-muted)]">
              Min форточек (%)
              <input
                v-model.number="climateForm.ventMinPercent"
                type="number"
                min="0"
                max="100"
                class="input-field mt-1 w-full"
                :disabled="!canConfigureAutomation"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Max форточек (%)
              <input
                v-model.number="climateForm.ventMaxPercent"
                type="number"
                min="0"
                max="100"
                class="input-field mt-1 w-full"
                :disabled="!canConfigureAutomation"
              />
            </label>
          </div>
        </article>

        <article class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
          <div class="flex items-center justify-between gap-3">
            <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
              Вода и узел коррекции
            </h3>
            <Badge :variant="waterForm.tanksCount === 3 ? 'info' : 'success'">
              {{ waterForm.tanksCount }} бака
            </Badge>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label class="text-xs text-[color:var(--text-muted)]">
              Тип системы
              <select
                v-model="waterForm.systemType"
                class="input-select mt-1 w-full"
                :disabled="!canConfigureAutomation"
              >
                <option value="drip">drip</option>
                <option value="substrate_trays">substrate_trays</option>
                <option value="nft">nft</option>
              </select>
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              target pH
              <input
                v-model.number="waterForm.targetPh"
                type="number"
                min="4"
                max="9"
                step="0.1"
                class="input-field mt-1 w-full"
                :disabled="!canConfigureAutomation"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              target EC
              <input
                v-model.number="waterForm.targetEc"
                type="number"
                min="0.1"
                max="10"
                step="0.1"
                class="input-field mt-1 w-full"
                :disabled="!canConfigureAutomation"
              />
            </label>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label class="text-xs text-[color:var(--text-muted)]">
              Интервал (мин)
              <input
                v-model.number="waterForm.intervalMinutes"
                type="number"
                min="5"
                max="1440"
                class="input-field mt-1 w-full"
                :disabled="!canConfigureAutomation"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Длительность (сек)
              <input
                v-model.number="waterForm.durationSeconds"
                type="number"
                min="1"
                max="3600"
                class="input-field mt-1 w-full"
                :disabled="!canConfigureAutomation"
              />
            </label>
            <label class="text-xs text-[color:var(--text-muted)]">
              Полив вручную (сек)
              <input
                v-model.number="waterForm.manualIrrigationSeconds"
                type="number"
                min="1"
                max="3600"
                class="input-field mt-1 w-full"
                :disabled="!canOperateAutomation"
              />
            </label>
          </div>
        </article>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
          Досветка
        </h3>

        <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
          <label class="text-xs text-[color:var(--text-muted)]">
            Lux day
            <input
              v-model.number="lightingForm.luxDay"
              type="number"
              min="0"
              max="120000"
              class="input-field mt-1 w-full"
              :disabled="!canConfigureAutomation"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Lux night
            <input
              v-model.number="lightingForm.luxNight"
              type="number"
              min="0"
              max="120000"
              class="input-field mt-1 w-full"
              :disabled="!canConfigureAutomation"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Hours on
            <input
              v-model.number="lightingForm.hoursOn"
              type="number"
              min="0"
              max="24"
              step="0.5"
              class="input-field mt-1 w-full"
              :disabled="!canConfigureAutomation"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            Manual intensity
            <input
              v-model.number="lightingForm.manualIntensity"
              type="number"
              min="0"
              max="100"
              class="input-field mt-1 w-full"
              :disabled="!canOperateAutomation"
            />
          </label>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            Операционные команды
          </h3>
          <div class="text-xs text-[color:var(--text-muted)]">
            Быстрые действия оператора
          </div>
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
            <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
              Применение профиля автоматики
            </h3>
            <p class="text-xs text-[color:var(--text-dim)] mt-1">
              Команда отправляется как `GROWTH_CYCLE_CONFIG` (`mode=adjust`).
            </p>
          </div>
          <div class="text-xs text-[color:var(--text-muted)]">
            <span v-if="lastAppliedAt">Последнее применение: {{ formatDateTime(lastAppliedAt) }}</span>
            <span v-else>Профиль ещё не применялся</span>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            :disabled="!canConfigureAutomation || isApplyingProfile"
            @click="applyAutomationProfile"
          >
            {{ isApplyingProfile ? 'Отправка профиля...' : 'Применить профиль автоматики' }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :disabled="isApplyingProfile"
            @click="resetToRecommended"
          >
            Восстановить рекомендуемые значения
          </Button>
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

      <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
        <AutomationEngine :zone-id="zoneId" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import AIPredictionsSection from '@/Components/AIPredictionsSection.vue'
import AutomationEngine from '@/Components/AutomationEngine.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import {
  type ZoneAutomationTabProps,
  useZoneAutomationTab,
} from '@/composables/useZoneAutomationTab'

const props = defineProps<ZoneAutomationTabProps>()

const {
  canConfigureAutomation,
  canOperateAutomation,
  climateForm,
  waterForm,
  lightingForm,
  quickActions,
  isApplyingProfile,
  lastAppliedAt,
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
  formatDateTime,
} = useZoneAutomationTab(props)

const zoneId = toRef(props, 'zoneId')
</script>
