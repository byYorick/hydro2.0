<template>
  <AppLayout>
    <div class="space-y-4">
      <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-5">
        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div class="flex-1 min-w-0">
            <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">зона выращивания</p>
            <div class="flex items-center gap-3 mt-1">
              <div class="text-2xl font-semibold truncate">{{ zone.name }}</div>
              <Badge :variant="variant" class="shrink-0" data-testid="zone-status-badge">{{ translateStatus(zone.status) }}</Badge>
            </div>
            <div class="text-sm text-[color:var(--text-dim)] mt-1 space-y-1">
              <div v-if="zone.description" class="truncate">{{ zone.description }}</div>
              <div v-if="activeGrowCycle?.recipeRevision" class="flex items-center gap-2 text-xs uppercase tracking-[0.12em]">
                <span class="text-[color:var(--text-dim)]">Рецепт</span>
                <span class="text-[color:var(--accent-cyan)] font-semibold">
                  {{ activeGrowCycle.recipeRevision.recipe.name }}
                </span>
                <span v-if="activeGrowCycle?.currentPhase" class="text-[color:var(--text-dim)]">
                  фаза {{ activeGrowCycle.currentPhase.phase_index + 1 }}
                </span>
              </div>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2 justify-end">
            <template v-if="canOperateZone">
              <Button size="sm" variant="secondary" @click="onToggle" :disabled="loading.toggle" class="flex-1 sm:flex-none min-w-[140px]" :data-testid="toggleStatus === 'PAUSED' ? 'zone-resume-btn' : 'zone-pause-btn'">
                <template v-if="loading.toggle">
                  <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
                </template>
                <span class="hidden sm:inline">{{ toggleStatus === 'PAUSED' ? 'Возобновить' : 'Приостановить' }}</span>
                <span class="sm:hidden">{{ toggleStatus === 'PAUSED' ? '▶' : '⏸' }}</span>
              </Button>
              <Button size="sm" variant="outline" @click="openActionModal('FORCE_IRRIGATION')" :disabled="loading.irrigate" class="flex-1 sm:flex-none" data-testid="force-irrigation-button">
                <template v-if="loading.irrigate">
                  <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
                </template>
                <span class="hidden sm:inline">Полить сейчас</span>
                <span class="sm:hidden">💧</span>
              </Button>
              <Button size="sm" @click="onNextPhase" :disabled="loading.nextPhase" class="flex-1 sm:flex-none" data-testid="next-phase-button">
                <template v-if="loading.nextPhase">
                  <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
                </template>
                <span class="hidden sm:inline">Следующая фаза</span>
                <span class="sm:hidden">⏭</span>
              </Button>
              <Button
                v-if="!activeCycle"
                size="sm"
                class="flex-1 sm:flex-none"
                :disabled="loading.cycleConfig"
                @click="onRunCycle"
              >
                Запустить цикл выращивания
              </Button>
              <Button
                v-else
                size="sm"
                variant="outline"
                class="flex-1 sm:flex-none"
                :disabled="loading.cycleConfig"
                @click="onRunCycle"
              >
                Настройки цикла
              </Button>
              <Button
                v-if="activeGrowCycle?.status === 'RUNNING'"
                size="sm"
                variant="secondary"
                class="flex-1 sm:flex-none"
                :disabled="loading.cyclePause"
                @click="onCyclePause"
              >
                <template v-if="loading.cyclePause">
                  <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
                </template>
                Пауза
              </Button>
              <Button
                v-if="activeGrowCycle"
                size="sm"
                variant="danger"
                class="flex-1 sm:flex-none"
                :disabled="loading.cycleAbort"
                @click="onCycleAbort"
              >
                <template v-if="loading.cycleAbort">
                  <LoadingState loading size="sm" :container-class="'inline-flex mr-2'" />
                </template>
                Стоп
              </Button>
              <div
                v-if="growthCycleCommandStatus"
                class="flex items-center gap-1 text-[10px] text-[color:var(--text-dim)] w-full"
              >
                <div
                  class="w-1.5 h-1.5 rounded-full"
                  :class="{
                    'bg-[color:var(--accent-amber)] animate-pulse': ['QUEUED', 'SENT', 'ACCEPTED', 'pending', 'executing'].includes(growthCycleCommandStatus || ''),
                    'bg-[color:var(--accent-green)]': ['DONE', 'completed', 'ack'].includes(growthCycleCommandStatus || ''),
                    'bg-[color:var(--accent-red)]': ['FAILED', 'TIMEOUT', 'SEND_FAILED', 'failed'].includes(growthCycleCommandStatus || '')
                  }"
                ></div>
                <span>{{ getCommandStatusText(growthCycleCommandStatus) }}</span>
              </div>
            </template>
            <Button size="sm" variant="outline" @click="modals.open('simulation')" class="flex-1 sm:flex-none">
              <span class="hidden sm:inline">Симуляция</span>
              <span class="sm:hidden">🧪</span>
            </Button>
          </div>
        </div>
      </div>

      <!-- Одна колонка: все элементы последовательно -->
      <div class="space-y-4">
        <!-- Целевые значения телеметрии -->
        <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
          <ZoneTargets v-if="targets && (targets.ph || targets.ec || targets.temp || targets.humidity)" :telemetry="telemetry" :targets="targets" />
          <div v-else class="text-center py-6">
            <div class="text-4xl mb-2">🎯</div>
            <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
              Целевые значения не настроены
            </div>
            <div class="text-xs text-[color:var(--text-muted)]">
              Настройте целевые значения для отслеживания параметров зоны
            </div>
          </div>
        </div>
        <!-- Прогресс цикла выращивания -->
        <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
          <StageProgress
            v-if="activeGrowCycle"
            :grow-cycle="activeGrowCycle"
            :phase-progress="computedPhaseProgress"
            :phase-days-elapsed="computedPhaseDaysElapsed"
            :phase-days-total="computedPhaseDaysTotal"
            :started-at="activeGrowCycle.started_at"
          />
          <div v-else-if="activeGrowCycle || activeCycle || zone.status === 'RUNNING'" class="text-center py-6">
            <div class="text-4xl mb-2">🌱</div>
            <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
              Цикл выращивания активен
            </div>
            <div class="text-xs text-[color:var(--text-muted)] space-y-1">
              <div v-if="zone.status">
                Статус зоны: <span class="font-semibold">{{ translateStatus(zone.status) }}</span>
              </div>
              <div v-if="activeGrowCycle?.status">
                Статус цикла: <span class="font-semibold">{{ translateStatus(activeGrowCycle.status) }}</span>
              </div>
              <div v-if="activeGrowCycle?.started_at">
                Запущен: {{ formatTimeShort(new Date(activeGrowCycle.started_at)) }}
              </div>
              <div class="mt-2 text-[color:var(--text-dim)]">
                Привяжите рецепт для детального отслеживания прогресса фаз
              </div>
            </div>
          </div>
          <div v-else class="text-center py-6">
            <div class="text-4xl mb-2">🌱</div>
            <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
              Цикл выращивания не запущен
            </div>
            <div class="text-xs text-[color:var(--text-muted)]">
              Привяжите рецепт и запустите цикл выращивания для отслеживания прогресса
            </div>
          </div>
        </div>
        <!-- Графики телеметрии pH и EC -->
        <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
          <div class="mb-3">
            <div class="text-sm font-semibold text-[color:var(--text-primary)]">Графики телеметрии</div>
            <div class="text-xs text-[color:var(--text-muted)] mt-1">pH и EC</div>
          </div>
          
          <div v-if="chartDataPh.length > 0 || chartDataEc.length > 0">
            <!-- Мульти-серии график pH + EC -->
            <MultiSeriesTelemetryChart
              title="pH и EC"
              :series="multiSeriesData"
              :time-range="chartTimeRange"
              @time-range-change="onChartTimeRangeChange"
            />
          </div>
          <div v-else-if="showSeparateCharts" class="space-y-3">
            <!-- Отдельные графики как fallback или опционально -->
            <ZoneTelemetryChart 
              title="pH" 
              :data="chartDataPh" 
              series-name="pH"
              :time-range="chartTimeRange"
              @time-range-change="onChartTimeRangeChange"
            />
            <ZoneTelemetryChart 
              title="EC" 
              :data="chartDataEc" 
              series-name="EC"
              :time-range="chartTimeRange"
              @time-range-change="onChartTimeRangeChange"
            />
          </div>
          <div v-else class="text-center py-6">
            <!-- Сообщение если нет данных для графиков -->
            <div class="text-4xl mb-2">📊</div>
            <div class="text-sm font-medium text-[color:var(--text-primary)] mb-1">
              Нет данных для графиков
            </div>
            <div class="text-xs text-[color:var(--text-muted)]">
              Данные телеметрии появятся после начала работы датчиков в зоне
            </div>
          </div>
        </div>
        <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
          <ZoneDevicesVisualization
            :zone-name="zone.name"
            :zone-status="zone.status"
            :devices="devices"
            :can-manage="canManageDevices"
            @attach="showAttachNodesModal = true"
            @configure="(device) => openNodeConfig(device.id, device)"
          />
        </div>
        <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
          <UnassignedNodeErrorsWidget :zone-id="zone.id" :limit="5" />
        </div>
        <!-- AI Прогнозы -->
        <div class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
          <AIPredictionsSection
            :zone-id="zone.id"
            :targets="targets"
            :horizon-minutes="60"
            :auto-refresh="true"
            :default-expanded="true"
          />
        </div>
        <Card>
            <div class="flex items-center justify-between mb-2">
              <div class="text-sm font-semibold">Рецепт</div>
              <template v-if="canManageRecipe">
                <Button
                  size="sm"
                  :variant="activeGrowCycle ? 'secondary' : 'primary'"
                  @click="activeGrowCycle ? onCycleChangeRecipe() : onRunCycle()"
                  data-testid="recipe-attach-btn"
                >
                  {{ activeGrowCycle ? 'Сменить ревизию' : 'Запустить цикл' }}
                </Button>
              </template>
            </div>
            <div v-if="activeGrowCycle?.recipeRevision?.recipe" class="text-sm text-[color:var(--text-muted)]">
              <div class="font-semibold">
                {{ activeGrowCycle.recipeRevision.recipe.name }}
              </div>
              <div class="text-xs text-[color:var(--text-dim)]">
                Фаза {{ (activeGrowCycle?.currentPhase?.phase_index ?? 0) + 1 }}
                из {{ activeGrowCycle?.phases?.length || 0 }}
                <span v-if="activeGrowCycle?.currentPhase?.name">
                  — {{ activeGrowCycle.currentPhase.name }}
                </span>
              </div>
              <div class="mt-2 flex flex-wrap items-center gap-2">
                <Badge :variant="cycleStatusVariant" class="text-[10px] px-2 py-0.5">
                  {{ cycleStatusLabel }}
                </Badge>
                <span v-if="phaseTimeLeftLabel" class="text-[11px] text-[color:var(--text-dim)]">
                  {{ phaseTimeLeftLabel }}
                </span>
              </div>
            </div>
            <div v-else class="space-y-2">
              <div class="text-sm text-[color:var(--text-dim)]">
                Цикл выращивания не запущен
              </div>
              <template v-if="canManageRecipe">
                <div class="text-xs text-[color:var(--text-dim)]">
                  Запустите цикл выращивания, чтобы применить рецепт и отслеживать фазы
                </div>
              </template>
            </div>
          </Card>
      </div>

      <!-- Cycles (расписание подсистем) -->
      <Card>
        <div class="text-sm font-semibold mb-3">Циклы</div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
          <div v-for="cycle in cyclesList" :key="cycle.type" class="text-xs text-[color:var(--text-dim)] p-3 rounded border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] hover:border-[color:var(--border-strong)] transition-colors">
            <div class="font-semibold text-sm mb-1 text-[color:var(--text-primary)] flex items-center justify-between gap-2">
              <span>{{ translateCycleType(cycle.type) }}</span>
              <span
                class="px-1.5 py-0.5 rounded-full text-[10px]"
                :class="cycle.required ? 'bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)]' : 'bg-[color:var(--bg-elevated)] text-[color:var(--text-dim)]'"
              >
                {{ cycle.required ? 'Обязательно' : 'Опционально' }}
              </span>
            </div>

            <!-- Таргеты текущей фазы (baseline рецепта) -->
            <div class="text-[11px] mb-2 space-y-0.5 text-[color:var(--text-muted)]">
              <div v-if="cycle.recipeTargets && cycle.type === 'PH_CONTROL' && typeof cycle.recipeTargets.min === 'number' && typeof cycle.recipeTargets.max === 'number'">
                pH: {{ cycle.recipeTargets.min }}–{{ cycle.recipeTargets.max }}
              </div>
              <div v-else-if="cycle.recipeTargets && cycle.type === 'EC_CONTROL' && typeof cycle.recipeTargets.min === 'number' && typeof cycle.recipeTargets.max === 'number'">
                EC: {{ cycle.recipeTargets.min }}–{{ cycle.recipeTargets.max }}
              </div>
              <div v-else-if="cycle.recipeTargets && cycle.type === 'CLIMATE' && typeof cycle.recipeTargets.temperature === 'number' && typeof cycle.recipeTargets.humidity === 'number'">
                Климат: t={{ cycle.recipeTargets.temperature }}°C, RH={{ cycle.recipeTargets.humidity }}%
              </div>
              <div v-else-if="cycle.recipeTargets && cycle.type === 'LIGHTING' && typeof cycle.recipeTargets.hours_on === 'number'">
                Свет: {{ cycle.recipeTargets.hours_on }}ч / пауза {{ typeof cycle.recipeTargets.hours_off === 'number' ? cycle.recipeTargets.hours_off : (24 - cycle.recipeTargets.hours_on) }}ч
              </div>
              <div v-else-if="cycle.recipeTargets && cycle.type === 'IRRIGATION' && typeof cycle.recipeTargets.interval_minutes === 'number' && typeof cycle.recipeTargets.duration_seconds === 'number'">
                Полив: каждые {{ cycle.recipeTargets.interval_minutes }} мин, {{ cycle.recipeTargets.duration_seconds }} с
              </div>
              <div v-else class="text-[color:var(--text-dim)]">
                Таргеты для этой фазы не заданы
              </div>
            </div>

            <div class="text-xs mb-1">Стратегия: {{ translateStrategy(cycle.strategy || 'periodic') }}</div>
            <div class="text-xs mb-2">Интервал: {{ cycle.interval ? formatInterval(cycle.interval) : 'Не настроено' }}</div>
            
            <!-- Последний запуск с индикатором -->
            <div class="mb-2">
              <div class="text-xs text-[color:var(--text-dim)] mb-1">Последний запуск:</div>
              <div class="flex items-center gap-2">
                <div v-if="cycle.last_run" class="w-2 h-2 rounded-full bg-[color:var(--accent-green)]"></div>
                <div v-else class="w-2 h-2 rounded-full bg-[color:var(--text-dim)]"></div>
                <span class="text-xs text-[color:var(--text-muted)]">{{ formatTimeShort(cycle.last_run) }}</span>
              </div>
            </div>
            
            <!-- Следующий запуск с прогресс-баром -->
            <div class="mb-2">
              <div class="text-xs text-[color:var(--text-dim)] mb-1">Следующий запуск:</div>
              <div v-if="cycle.next_run" class="space-y-1">
                <div class="flex items-center gap-2">
                  <div class="w-2 h-2 rounded-full bg-[color:var(--accent-amber)] animate-pulse"></div>
                  <span class="text-xs text-[color:var(--text-muted)]">{{ formatTimeShort(cycle.next_run) }}</span>
                </div>
                <!-- Прогресс-бар до следующего запуска -->
                <div v-if="cycle.last_run && cycle.interval" class="w-full h-1.5 bg-[color:var(--border-muted)] rounded-full overflow-hidden">
                  <div 
                    class="h-full bg-[color:var(--accent-amber)] transition-all duration-300"
                    :style="{ width: `${getProgressToNextRun(cycle)}%` }"
                  ></div>
                </div>
                <div v-if="cycle.last_run && cycle.interval" class="text-xs text-[color:var(--text-dim)]">
                  {{ getTimeUntilNextRun(cycle) }}
                </div>
              </div>
              <div v-else class="text-xs text-[color:var(--text-dim)]">Не запланирован</div>
            </div>
          </div>
        </div>
      </Card>

      <!-- Cycle Control Panel -->
      <CycleControlPanel
        v-if="activeGrowCycle"
        :cycle="activeGrowCycle"
        :grow-cycle="activeGrowCycle"
        :phase-progress="computedPhaseProgress"
        :phase-days-elapsed="computedPhaseDaysElapsed"
        :phase-days-total="computedPhaseDaysTotal"
        :can-manage="canManageCycle"
        :loading="loading.cyclePause || loading.cycleResume || loading.cycleHarvest || loading.cycleAbort"
        @pause="onCyclePause"
        @resume="onCycleResume"
        @harvest="onCycleHarvest"
        @abort="onCycleAbort"
      />

      <!-- Automation Engine -->
      <AutomationEngine :zone-id="zoneId" />

      <!-- Events (история событий) -->
      <Card>
        <div class="text-sm font-semibold mb-2">События</div>
        <div v-if="events.length > 0" class="space-y-1 max-h-[400px] overflow-y-auto" data-testid="zone-events-list">
          <div
            v-for="e in events"
            :key="e.id"
            :data-testid="`zone-event-item-${e.id}`"
            class="text-sm text-[color:var(--text-muted)] flex items-start gap-2 py-1 border-b border-[color:var(--border-muted)] last:border-0"
          >
            <Badge
              :variant="
                e.kind === 'ALERT' ? 'danger' :
                e.kind === 'WARNING' ? 'warning' :
                e.kind === 'INFO' ? 'info' : 'neutral'
              "
              class="text-xs shrink-0"
            >
              {{ translateEventKind(e.kind) }}
            </Badge>
            <div class="flex-1 min-w-0">
              <div class="text-xs text-[color:var(--text-dim)]">
                {{ new Date(e.occurred_at).toLocaleString('ru-RU') }}
              </div>
              <div class="text-sm">{{ e.message }}</div>
            </div>
          </div>
        </div>
        <div v-else class="text-sm text-[color:var(--text-dim)]">Нет событий</div>
      </Card>
    </div>
    
    <!-- Digital Twin Simulation Modal -->
    <ZoneSimulationModal
      :show="showSimulationModal"
      :zone-id="zoneId"
      :default-recipe-id="activeGrowCycle?.recipeRevision?.recipe_id"
      @close="modals.close('simulation')"
    />
    
    <!-- Модальное окно для действий с параметрами -->
    <ZoneActionModal
      v-if="showActionModal"
      :show="showActionModal"
      :action-type="currentActionType"
      :zone-id="zoneId"
      @close="modals.close('action')"
      @submit="onActionSubmit"
    />
    
    <!-- Модальное окно привязки узлов -->
    <AttachNodesModal
      v-if="showAttachNodesModal"
      :show="showAttachNodesModal"
      :zone-id="zoneId"
      @close="showAttachNodesModal = false"
      @attached="onNodesAttached"
    />
    
    <!-- Модальное окно настройки узла -->
    <NodeConfigModal
      v-if="showNodeConfigModal && selectedNodeId"
      :show="showNodeConfigModal"
      :node-id="selectedNodeId"
      :node="selectedNode"
      @close="modals.close('nodeConfig')"
      @published="onNodeConfigPublished"
    />
    
    <!-- Модальное окно запуска/корректировки цикла выращивания -->
    <GrowthCycleWizard
      v-if="showGrowthCycleModal && zoneId"
      :show="showGrowthCycleModal"
      :zone-id="zoneId"
      :zone-name="zone.name"
      :current-phase-targets="currentPhase?.targets || null"
      :active-cycle="activeCycle"
      @close="modals.close('growthCycle')"
      @submit="onGrowthCycleWizardSubmit"
    />

    <ConfirmModal
      :open="harvestModal.open"
      title="Зафиксировать сбор"
      message=" "
      confirm-text="Подтвердить"
      :loading="loading.cycleHarvest"
      @close="closeHarvestModal"
      @confirm="confirmHarvest"
    >
      <div class="space-y-3 text-sm text-[color:var(--text-muted)]">
        <div>Зафиксировать сбор урожая и завершить цикл?</div>
        <div>
          <label class="text-xs text-[color:var(--text-dim)]">Метка партии (опционально)</label>
          <input v-model="harvestModal.batchLabel" class="input-field mt-1 w-full" placeholder="Например: Batch-042" />
        </div>
      </div>
    </ConfirmModal>

    <ConfirmModal
      :open="abortModal.open"
      title="Аварийная остановка"
      message=" "
      confirm-text="Остановить"
      confirm-variant="danger"
      :loading="loading.cycleAbort"
      @close="closeAbortModal"
      @confirm="confirmAbort"
    >
      <div class="space-y-3 text-sm text-[color:var(--text-muted)]">
        <div>Остановить цикл? Это действие нельзя отменить.</div>
        <div>
          <label class="text-xs text-[color:var(--text-dim)]">Причина (опционально)</label>
          <textarea v-model="abortModal.notes" class="input-field mt-1 w-full h-20 resize-none" placeholder="Короткое описание причины"></textarea>
        </div>
      </div>
    </ConfirmModal>

    <ConfirmModal
      :open="changeRecipeModal.open"
      title="Сменить рецепт"
      message=" "
      confirm-text="Подтвердить"
      :confirm-disabled="!changeRecipeModal.recipeRevisionId"
      :loading="loading.cycleChangeRecipe"
      @close="closeChangeRecipeModal"
      @confirm="confirmChangeRecipe"
    >
      <div class="space-y-3 text-sm text-[color:var(--text-muted)]">
        <div>Введите ID ревизии рецепта и выберите режим применения.</div>
        <div>
          <label class="text-xs text-[color:var(--text-dim)]">ID ревизии рецепта</label>
          <input v-model="changeRecipeModal.recipeRevisionId" class="input-field mt-1 w-full" placeholder="Например: 42" />
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="btn btn-outline h-9 px-3 text-xs"
            :class="changeRecipeModal.applyMode === 'now' ? 'border-[color:var(--accent-green)]' : ''"
            @click="changeRecipeModal.applyMode = 'now'"
          >
            Применить сейчас
          </button>
          <button
            type="button"
            class="btn btn-outline h-9 px-3 text-xs"
            :class="changeRecipeModal.applyMode === 'next_phase' ? 'border-[color:var(--accent-green)]' : ''"
            @click="changeRecipeModal.applyMode = 'next_phase'"
          >
            Со следующей фазы
          </button>
        </div>
      </div>
    </ConfirmModal>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import { useHistory } from '@/composables/useHistory'
import ZoneTargets from '@/Components/ZoneTargets.vue'
import StageProgress from '@/Components/StageProgress.vue'
import ZoneDevicesVisualization from '@/Components/ZoneDevicesVisualization.vue'
import LoadingState from '@/Components/LoadingState.vue'
import UnassignedNodeErrorsWidget from '@/Components/UnassignedNodeErrorsWidget.vue'
import AIPredictionsSection from '@/Components/AIPredictionsSection.vue'
import ZoneSimulationModal from '@/Components/ZoneSimulationModal.vue'
import ZoneActionModal from '@/Components/ZoneActionModal.vue'
import GrowthCycleWizard from '@/Components/GrowCycle/GrowthCycleWizard.vue'
import AttachNodesModal from '@/Components/AttachNodesModal.vue'
import NodeConfigModal from '@/Components/NodeConfigModal.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import AutomationEngine from '@/Components/AutomationEngine.vue'
import CycleControlPanel from '@/Components/GrowCycle/CycleControlPanel.vue'
import { translateStatus, translateEventKind, translateCycleType, translateStrategy } from '@/utils/i18n'
import { formatTimeShort, formatInterval } from '@/utils/formatTime'
import { logger } from '@/utils/logger'

// Используем logger напрямую (logger уже проверен и доступен)
import { useCommands } from '@/composables/useCommands'
import { useTelemetry } from '@/composables/useTelemetry'
import { useZones } from '@/composables/useZones'
import { useApi } from '@/composables/useApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { useErrorHandler } from '@/composables/useErrorHandler'
import { useOptimisticUpdate, createOptimisticZoneUpdate } from '@/composables/useOptimisticUpdate'
import { useZonesStore } from '@/stores/zones'
import { useOptimizedUpdates, useTelemetryBatch } from '@/composables/useOptimizedUpdates'
import { useToast } from '@/composables/useToast'
import { useModal } from '@/composables/useModal'
import { useLoading } from '@/composables/useLoading'
import { useTheme } from '@/composables/useTheme'
import { extractData } from '@/utils/apiHelpers'
import { usePageProps } from '@/composables/usePageProps'
import { DEBOUNCE_DELAY, ANIMATION_DELAY, TOAST_TIMEOUT } from '@/constants/timeouts'
import { ERROR_MESSAGES } from '@/constants/messages'
import type { Zone, Device, ZoneTelemetry, ZoneTargets as ZoneTargetsType, Cycle, CommandType } from '@/types'
import type { ZoneEvent } from '@/types/ZoneEvent'

const ZoneTelemetryChart = defineAsyncComponent(() => import('@/Pages/Zones/ZoneTelemetryChart.vue'))
const MultiSeriesTelemetryChart = defineAsyncComponent(() => import('@/Components/MultiSeriesTelemetryChart.vue'))

interface PageProps {
  zone?: Zone
  zoneId?: number
  telemetry?: ZoneTelemetry
  targets?: ZoneTargetsType
  devices?: Device[]
  events?: ZoneEvent[]
  cycles?: Record<string, Cycle>
  current_phase?: any
  active_cycle?: any
  active_grow_cycle?: any
  auth?: {
    user?: {
      role?: string
    }
  }
}

const page = usePage<PageProps>()

// Modal states using useModal composable
const modals = useModal<{
  simulation: boolean
  action: boolean
  growthCycle: boolean
  attachNodes: boolean
  nodeConfig: boolean
}>({
  simulation: false,
  action: false,
  growthCycle: false,
  attachNodes: false,
  nodeConfig: false,
})

const showSimulationModal = computed(() => modals.isModalOpen('simulation'))
const showActionModal = computed(() => modals.isModalOpen('action'))
const showGrowthCycleModal = computed(() => modals.isModalOpen('growthCycle'))
const showAttachNodesModal = computed(() => modals.isModalOpen('attachNodes'))
const showNodeConfigModal = computed(() => modals.isModalOpen('nodeConfig'))

const currentActionType = ref<CommandType>('FORCE_IRRIGATION')
const selectedNodeId = ref<number | null>(null)
const selectedNode = ref<any>(null)

// Loading states using useLoading composable
interface LoadingState {
  toggle: boolean
  irrigate: boolean
  nextPhase: boolean
  cycleConfig: boolean
  cyclePause: boolean
  cycleResume: boolean
  cycleHarvest: boolean
  cycleAbort: boolean
  cycleChangeRecipe: boolean
}

const { loading, setLoading, startLoading, stopLoading } = useLoading<LoadingState>({
  toggle: false,
  irrigate: false,
  nextPhase: false,
  cycleConfig: false,
  cyclePause: false,
  cycleResume: false,
  cycleHarvest: false,
  cycleAbort: false,
  cycleChangeRecipe: false,
})

const { showToast } = useToast()

// Инициализация composables с Toast
const { sendZoneCommand, reloadZoneAfterCommand, updateCommandStatus, pendingCommands } = useCommands(showToast)
const { fetchHistory } = useTelemetry(showToast)
const { fetchZone, reloadZone } = useZones(showToast)
const { api } = useApi(showToast)
const { subscribeToZoneCommands } = useWebSocket(showToast)
const { handleError } = useErrorHandler(showToast)
const { performUpdate } = useOptimisticUpdate()
const zonesStore = useZonesStore()

// zoneId должен определяться из URL или props напрямую, без зависимости от zone
// Извлекаем ID из URL (например, /zones/25 -> 25)
const zoneId = computed(() => {
  // Сначала пробуем из props
  if (page.props.zoneId) {
    const id = page.props.zoneId
    return typeof id === 'string' ? parseInt(id) : id
  }
  
  // Пробуем из zone props
  if (page.props.zone?.id) {
    const id = page.props.zone.id
    return typeof id === 'string' ? parseInt(id) : id
  }
  
  // Извлекаем из URL как fallback
  const pathMatch = window.location.pathname.match(/\/zones\/(\d+)/)
  if (pathMatch && pathMatch[1]) {
    return parseInt(pathMatch[1])
  }
  
  return null
})

const zone = computed<Zone>(() => {
  const zoneIdValue = zoneId.value
  
  // Сначала проверяем store - там может быть более актуальное состояние
  if (zoneIdValue) {
    const storeZone = zonesStore.zoneById(zoneIdValue)
    if (storeZone && storeZone.id) {
      return storeZone
    }
  }
  
  // Если в store нет, используем props
  const rawZoneData = (page.props.zone || {}) as any
  
  const zoneData = { ...rawZoneData }
  
  // Убеждаемся, что у объекта есть id
  if (!zoneData.id && zoneIdValue) {
    zoneData.id = zoneIdValue
  }
  
  // Если zoneData все еще пустой, возвращаем минимальный объект
  if (!zoneData.id) {
    return {
      id: zoneIdValue || undefined,
    } as Zone
  }
  
  return zoneData as Zone
})

// История просмотров
const { addToHistory } = useHistory()

// Добавляем зону в историю просмотров
watch(zone, (newZone) => {
  if (newZone?.id) {
    addToHistory({
      id: newZone.id,
      type: 'zone',
      name: newZone.name || `Зона ${newZone.id}`,
      url: `/zones/${newZone.id}`
    })
  }
}, { immediate: true })

// Телеметрия, цели и устройства из props
// Оптимизированное обновление телеметрии
const telemetryRef = ref<ZoneTelemetry>(page.props.telemetry || { ph: null, ec: null, temperature: null, humidity: null } as ZoneTelemetry)

// Используем batch updates для оптимизации частых обновлений телеметрии
const { addUpdate, flush } = useTelemetryBatch((updates) => {
  // Применяем обновления пакетом
  const currentZoneId = zoneId.value
  updates.forEach((metrics, zoneIdStr) => {
    if (zoneIdStr === String(currentZoneId)) {
      const current = { ...telemetryRef.value }
      metrics.forEach((value, metric) => {
        switch (metric) {
          case 'ph':
            current.ph = value
            break
          case 'ec':
            current.ec = value
            break
          case 'temperature':
            current.temperature = value
            break
          case 'humidity':
            current.humidity = value
            break
        }
      })
      telemetryRef.value = current
    }
  })
}) // Использует DEBOUNCE_DELAY.NORMAL по умолчанию

const telemetry = computed(() => telemetryRef.value)
const { targets: targetsProp, devices: devicesProp, events: eventsProp, cycles: cyclesProp, current_phase: currentPhaseProp, active_cycle: activeCycleProp, active_grow_cycle: activeGrowCycleProp } = usePageProps<PageProps>(['targets', 'devices', 'events', 'cycles', 'current_phase', 'active_cycle', 'active_grow_cycle'])

// Сырые targets (исторический формат, для Back-compat) + нормализованный current_phase
const targets = computed(() => (targetsProp.value || {}) as ZoneTargetsType)
const currentPhase = computed(() => {
  if (currentPhaseProp.value) {
    return currentPhaseProp.value as any
  }
  return null
})

const activeCycle = computed(() => (activeCycleProp.value || null) as any)
const activeGrowCycle = computed(() => (activeGrowCycleProp.value || zone.value?.activeGrowCycle || null) as any)
const devices = computed(() => (devicesProp.value || []) as Device[])
const events = computed(() => (eventsProp.value || []) as ZoneEvent[])
const cycles = computed(() => (cyclesProp.value || {}) as Record<string, Cycle>)

// События цикла (теперь загружаются внутри CycleControlPanel)
const userRole = computed(() => page.props.auth?.user?.role || 'viewer')
const canOperateZone = computed(() => ['admin', 'operator', 'agronomist'].includes(userRole.value))
const canManageDevices = computed(() => ['admin', 'operator'].includes(userRole.value))
const canManageRecipe = computed(() => ['admin', 'operator', 'agronomist'].includes(userRole.value))
const canManageCycle = computed(() => ['admin', 'operator', 'agronomist'].includes(userRole.value))

// Вычисление прогресса фазы/рецепта на основе нормализованного current_phase (UTC)
// ВАЖНО: все вычисления в UTC, отображение форматируется в локальное время
const computedPhaseProgress = computed(() => {
  const phase = currentPhase.value
  if (!phase) {
    logger.debug('[Zones/Show] computedPhaseProgress: phase is null')
    return null
  }
  
  if (!phase.phase_started_at || !phase.phase_ends_at) {
    logger.debug('[Zones/Show] computedPhaseProgress: missing dates', {
      phase_started_at: phase.phase_started_at,
      phase_ends_at: phase.phase_ends_at,
    })
    return null
  }

  // Все даты в UTC (ISO8601 с 'Z' или без, но интерпретируем как UTC)
  const now = new Date() // Текущее время в UTC (Date всегда в UTC внутренне)
  const phaseStart = new Date(phase.phase_started_at)
  const phaseEnd = new Date(phase.phase_ends_at)

  // Проверяем валидность дат
  if (isNaN(phaseStart.getTime()) || isNaN(phaseEnd.getTime())) {
    logger.debug('[Zones/Show] computedPhaseProgress: invalid dates', {
      phase_started_at: phase.phase_started_at,
      phase_ends_at: phase.phase_ends_at,
      phaseStartTime: phaseStart.getTime(),
      phaseEndTime: phaseEnd.getTime(),
    })
    return null
  }

  const totalMs = phaseEnd.getTime() - phaseStart.getTime()
  if (totalMs <= 0) {
    logger.debug('[Zones/Show] computedPhaseProgress: totalMs <= 0', { totalMs })
    return null
  }

  const elapsedMs = now.getTime() - phaseStart.getTime()
  
  logger.debug('[Zones/Show] computedPhaseProgress: calculation', {
    now: now.toISOString(),
    phaseStart: phaseStart.toISOString(),
    phaseEnd: phaseEnd.toISOString(),
    elapsedMs,
    totalMs,
    progress: elapsedMs > 0 ? (elapsedMs / totalMs) * 100 : 0,
  })
  
  if (elapsedMs <= 0) return 0
  if (elapsedMs >= totalMs) return 100

  return Math.min(100, Math.max(0, (elapsedMs / totalMs) * 100))
})

const computedPhaseDaysElapsed = computed(() => {
  const phase = currentPhase.value
  if (!phase || !phase.phase_started_at) return null

  // Все вычисления в UTC
  const now = new Date()
  const phaseStart = new Date(phase.phase_started_at)
  
  if (isNaN(phaseStart.getTime())) {
    return null
  }

  const elapsedMs = now.getTime() - phaseStart.getTime()
  if (elapsedMs <= 0) return 0

  const elapsedDays = elapsedMs / (1000 * 60 * 60 * 24)
  return Math.floor(elapsedDays)
})

const computedPhaseDaysTotal = computed(() => {
  const phase = currentPhase.value
  if (!phase || !phase.duration_hours) return null

  return Math.ceil(phase.duration_hours / 24)
})

// Единый статус цикла зоны и человекочитаемое время до конца фазы
const cycleStatusLabel = computed(() => {
  if (activeGrowCycle.value) {
    const status = activeGrowCycle.value.status
    if (status === 'RUNNING') return 'Цикл активен'
    if (status === 'PAUSED') return 'Цикл на паузе'
    if (status === 'PLANNED') return 'Цикл запланирован'
  }
  if (activeCycle.value) {
    return 'Цикл активен'
  }
  return 'Цикл не запущен'
})

const cycleStatusVariant = computed<'success' | 'neutral' | 'warning'>(() => {
  if (activeGrowCycle.value) {
    const status = activeGrowCycle.value.status
    if (status === 'RUNNING') return 'success'
    if (status === 'PAUSED') return 'warning'
    if (status === 'PLANNED') return 'neutral'
  }
  if (activeCycle.value) {
    return 'success'
  }
  return 'neutral'
})

const phaseTimeLeftLabel = computed(() => {
  const phase = currentPhase.value
  if (!phase || !phase.phase_ends_at) {
    return ''
  }

  // Все вычисления в UTC
  const now = new Date()
  const endsAt = new Date(phase.phase_ends_at)
  
  if (isNaN(endsAt.getTime())) {
    return ''
  }

  const diffMs = endsAt.getTime() - now.getTime()

  if (diffMs <= 0) {
    return 'Фаза завершена'
  }

  const minutes = Math.floor(diffMs / 60000)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (days > 0) {
    return `До конца фазы: ${days} дн.`
  }
  if (hours > 0) {
    return `До конца фазы: ${hours} ч`
  }
  return `До конца фазы: ${minutes} мин`
})

// Список циклов для отображения:
// объединяем расписание из API (/cycles) с таргетами текущей фазы рецепта и (в будущем) фактическим active_cycle
const cyclesList = computed(() => {
  const phaseTargets = (currentPhase.value?.targets || {}) as any
  const active = (activeCycle.value?.subsystems || {}) as any

  const serverCycles = cycles.value || {}

  const base = [
    {
      key: 'ph',
      type: 'PH_CONTROL',
      required: true,
      recipeTargets: phaseTargets.ph || null,
      activeTargets: active.ph?.targets || null,
      enabled: active.ph?.enabled ?? true,
      strategy: serverCycles.PH_CONTROL?.strategy || 'periodic',
      interval: serverCycles.PH_CONTROL?.interval ?? 300,
      last_run: serverCycles.PH_CONTROL?.last_run || null,
      next_run: serverCycles.PH_CONTROL?.next_run || null,
    },
    {
      key: 'ec',
      type: 'EC_CONTROL',
      required: true,
      recipeTargets: phaseTargets.ec || null,
      activeTargets: active.ec?.targets || null,
      enabled: active.ec?.enabled ?? true,
      strategy: serverCycles.EC_CONTROL?.strategy || 'periodic',
      interval: serverCycles.EC_CONTROL?.interval ?? 300,
      last_run: serverCycles.EC_CONTROL?.last_run || null,
      next_run: serverCycles.EC_CONTROL?.next_run || null,
    },
    {
      key: 'irrigation',
      type: 'IRRIGATION',
      required: true,
      recipeTargets: phaseTargets.irrigation || null,
      activeTargets: active.irrigation?.targets || null,
      enabled: active.irrigation?.enabled ?? true,
      strategy: serverCycles.IRRIGATION?.strategy || 'periodic',
      interval: serverCycles.IRRIGATION?.interval ?? null,
      last_run: serverCycles.IRRIGATION?.last_run || null,
      next_run: serverCycles.IRRIGATION?.next_run || null,
    },
    {
      key: 'lighting',
      type: 'LIGHTING',
      required: false,
      recipeTargets: phaseTargets.lighting || null,
      activeTargets: active.lighting?.targets || null,
      enabled: active.lighting?.enabled ?? false,
      strategy: serverCycles.LIGHTING?.strategy || 'periodic',
      interval: serverCycles.LIGHTING?.interval ?? null,
      last_run: serverCycles.LIGHTING?.last_run || null,
      next_run: serverCycles.LIGHTING?.next_run || null,
    },
    {
      key: 'climate',
      type: 'CLIMATE',
      required: false,
      recipeTargets: phaseTargets.climate || null,
      activeTargets: active.climate?.targets || null,
      enabled: active.climate?.enabled ?? false,
      strategy: serverCycles.CLIMATE?.strategy || 'periodic',
      interval: serverCycles.CLIMATE?.interval ?? 300,
      last_run: serverCycles.CLIMATE?.last_run || null,
      next_run: serverCycles.CLIMATE?.next_run || null,
    },
  ]

  return base as Array<
    {
      key: string
      type: string
      required: boolean
      recipeTargets: any
      activeTargets: any
      enabled: boolean
    } & Cycle & {
      last_run?: string | null
      next_run?: string | null
      interval?: number | null
    }
  >
})

// Функции для вычисления прогресса до следующего запуска
function getProgressToNextRun(cycle: Cycle & { last_run?: string | null; next_run?: string | null; interval?: number | null }): number {
  if (!cycle.last_run || !cycle.next_run || !cycle.interval) return 0
  
  const now = new Date().getTime()
  const lastRun = new Date(cycle.last_run).getTime()
  const nextRun = new Date(cycle.next_run).getTime()
  
  if (now >= nextRun) return 100
  if (now <= lastRun) return 0
  
  const total = nextRun - lastRun
  const elapsed = now - lastRun
  return Math.min(100, Math.max(0, (elapsed / total) * 100))
}

function getTimeUntilNextRun(cycle: Cycle & { next_run?: string | null }): string {
  if (!cycle.next_run) return ''
  
  const now = new Date().getTime()
  const nextRun = new Date(cycle.next_run).getTime()
  const diff = nextRun - now
  
  if (diff <= 0) return 'Просрочено'
  
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)
  
  if (days > 0) return `Через ${days} дн.`
  if (hours > 0) return `Через ${hours} ч.`
  if (minutes > 0) return `Через ${minutes} мин.`
  return 'Скоро'
}

// Функции для отображения статуса команд
const growthCycleCommandStatus = computed(() => {
  const activeStatuses = ['QUEUED', 'SENT', 'ACCEPTED', 'DONE', 'FAILED', 'TIMEOUT', 'SEND_FAILED', 'pending', 'executing', 'completed', 'failed', 'ack']
  const matching = pendingCommands.value
    .filter((cmd) => cmd.type === 'GROWTH_CYCLE_CONFIG' && cmd.zoneId === zoneId.value && activeStatuses.includes(cmd.status))
    .sort((a, b) => b.timestamp - a.timestamp)
  return matching[0]?.status || null
})

function getCommandStatusText(status: string | null): string {
  if (!status) return ''
  const texts: Record<string, string> = {
    'QUEUED': 'В очереди',
    'SENT': 'Отправлено',
    'ACCEPTED': 'Принято',
    'DONE': 'Выполнено',
    'FAILED': 'Ошибка',
    'TIMEOUT': 'Таймаут',
    'SEND_FAILED': 'Ошибка отправки',
    'pending': 'Ожидание...',
    'executing': 'Выполняется...',
    'completed': 'Выполнено',
    'ack': 'Выполнено',
    'failed': 'Ошибка'
  }
  return texts[status] || status
}

// Графики: загрузка данных истории
const chartTimeRange = ref<'1H' | '24H' | '7D' | '30D' | 'ALL'>('24H')
const chartDataPh = ref<Array<{ ts: number; value: number }>>([])
const chartDataEc = ref<Array<{ ts: number; value: number }>>([])
const showSeparateCharts = ref(false) // Опция для показа отдельных графиков

const { theme } = useTheme()
const resolveCssColor = (variable: string, fallback: string): string => {
  if (typeof window === 'undefined') {
    return fallback
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

const chartPalette = computed(() => {
  theme.value
  return {
    ph: resolveCssColor('--accent-cyan', '#3b82f6'),
    ec: resolveCssColor('--accent-green', '#10b981'),
  }
})

// Мульти-серии данные для комбинированного графика
const multiSeriesData = computed(() => {
  return [
    {
      name: 'ph',
      label: 'pH',
      color: chartPalette.value.ph,
      data: chartDataPh.value,
      currentValue: telemetry.value.ph,
      yAxisIndex: 0,
      targetRange: targets.value.ph ? {
        min: targets.value.ph.min,
        max: targets.value.ph.max,
      } : undefined,
    },
    {
      name: 'ec',
      label: 'EC',
      color: chartPalette.value.ec,
      data: chartDataEc.value,
      currentValue: telemetry.value.ec,
      yAxisIndex: 1, // Используем правую ось Y для EC
      targetRange: targets.value.ec ? {
        min: targets.value.ec.min,
        max: targets.value.ec.max,
      } : undefined,
    },
  ]
})

// Загрузка данных истории для графиков через useTelemetry
async function loadChartData(metric: 'PH' | 'EC', timeRange: string): Promise<Array<{ ts: number; value: number }>> {
  if (!zoneId.value) return []
  
  const now = new Date()
  let from: Date | null = null
  switch (timeRange) {
    case '1H':
      from = new Date(now.getTime() - 60 * 60 * 1000)
      break
    case '24H':
      from = new Date(now.getTime() - 24 * 60 * 60 * 1000)
      break
    case '7D':
      from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
      break
    case '30D':
      from = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
      break
    case 'ALL':
      from = null
      break
  }
  
  try {
    const params: { from?: string; to: string } = { to: now.toISOString() }
    if (from) params.from = from.toISOString()
    
    return await fetchHistory(zoneId.value, metric, params)
  } catch (err) {
    logger.error(`Failed to load ${metric} history:`, err)
    return []
  }
}

async function onChartTimeRangeChange(newRange: string): Promise<void> {
  chartTimeRange.value = newRange as '1H' | '24H' | '7D' | '30D' | 'ALL'
  chartDataPh.value = await loadChartData('PH', newRange)
  chartDataEc.value = await loadChartData('EC', newRange)
}

// Watch для отслеживания изменений zone props (отключен для производительности)
// watch(() => page.props.zone, (newZone: any, oldZone: any) => {
//   logInfo('[Zones/Show] Zone props changed')
// }, { deep: true, immediate: true })

// Сохраняем функцию отписки для очистки при размонтировании
let unsubscribeZoneCommands: (() => void) | null = null

// Регистрируем onUnmounted синхронно перед async onMounted
onUnmounted(() => {
  // Отписываемся от WebSocket канала при размонтировании
  if (unsubscribeZoneCommands) {
    unsubscribeZoneCommands()
    unsubscribeZoneCommands = null
  }
  flush()
})

onMounted(async () => {
  logger.info('[Show.vue] Компонент смонтирован', { zoneId: zoneId.value })

  // Инициализируем зону в store из props для синхронизации
  if (zoneId.value && zone.value?.id) {
    zonesStore.upsert(zone.value, true) // silent: true, так как это начальная инициализация
    logger.debug('[Zones/Show] Zone initialized in store from props', { zoneId: zoneId.value })
  }

  const params = new URLSearchParams(window.location.search)
  if (params.get('start_cycle') === '1') {
    modals.open('growthCycle')
  }

  // Загрузить данные для графиков
  chartDataPh.value = await loadChartData('PH', chartTimeRange.value)
  chartDataEc.value = await loadChartData('EC', chartTimeRange.value)
  
  // Подписаться на WebSocket канал команд зоны и сохранить функцию отписки
  if (zoneId.value) {
    unsubscribeZoneCommands = subscribeToZoneCommands(zoneId.value, (commandEvent) => {
      // Обновляем статус команды через useCommands
      updateCommandStatus(commandEvent.commandId, commandEvent.status, commandEvent.message)
      
      // Если команда завершена, обновляем зону
      // Проверяем новые и старые статусы для обратной совместимости
      const finalStatuses = ['DONE', 'FAILED', 'TIMEOUT', 'SEND_FAILED', 'completed', 'failed']
      if (finalStatuses.includes(commandEvent.status)) {
        reloadZoneAfterCommand(zoneId.value, ['zone', 'cycles'])
      }
    })

    // Подписаться на обновления цикла через канал зоны
    const echo = window.Echo
    if (echo) {
      const channel = echo.private(`hydro.zones.${zoneId.value}`)
      channel.listen('.App\\Events\\GrowCycleUpdated', (event: any) => {
        logger.info('[Zones/Show] GrowCycleUpdated event received', event)
        // Обновляем зону для получения актуального состояния цикла
        reloadZone(zoneId.value, ['zone', 'active_grow_cycle'])
      })
      
      // Сохраняем функцию отписки
      const originalUnsubscribe = unsubscribeZoneCommands
      unsubscribeZoneCommands = () => {
        if (originalUnsubscribe) originalUnsubscribe()
        channel.stopListening('.App\\Events\\GrowCycleUpdated')
      }
    }
  }
  
  // Автоматическая синхронизация через события stores
  const { useStoreEvents } = await import('@/composables/useStoreEvents')
  const { subscribeWithCleanup } = useStoreEvents()
  
  // Слушаем события обновления зоны для автоматического обновления
  subscribeWithCleanup('zone:updated', (updatedZone: any) => {
    if (updatedZone.id === zoneId.value) {
      // Если есть обновление телеметрии, применяем его оптимизированно
      if (updatedZone.telemetry) {
        const tel = updatedZone.telemetry
        if (tel.ph !== null && tel.ph !== undefined) {
          addUpdate(String(zoneId.value), 'ph', tel.ph)
        }
        if (tel.ec !== null && tel.ec !== undefined) {
          addUpdate(String(zoneId.value), 'ec', tel.ec)
        }
        if (tel.temperature !== null && tel.temperature !== undefined) {
          addUpdate(String(zoneId.value), 'temperature', tel.temperature)
        }
        if (tel.humidity !== null && tel.humidity !== undefined) {
          addUpdate(String(zoneId.value), 'humidity', tel.humidity)
        }
      } else {
        // Обновляем зону через Inertia partial reload только если нет телеметрии
        reloadZone(zoneId.value, ['zone'])
      }
    }
  })
  
})

/**
 * Получить параметры по умолчанию для команды цикла на основе targets/recipe
 */
function getDefaultCycleParams(cycleType: string): Record<string, unknown> {
  const params: Record<string, unknown> = {}
  
  switch (cycleType) {
    case 'IRRIGATION':
      // Используем длительность полива из targets или рецепта
      if (targets.value.irrigation_duration_sec) {
        // Важно: это может приходить либо из текущей фазы рецепта, либо из агрегированных targets зоны
        params.duration_sec = targets.value.irrigation_duration_sec
      } else {
        params.duration_sec = 10
      }
      break
      
    case 'PH_CONTROL':
      // Используем целевой pH из targets или рецепта
      if (typeof targets.value.ph_min === 'number' && typeof targets.value.ph_max === 'number') {
        // Бэкенд отдаёт цели текущей фазы в виде плоских snake_case полей (ph_min, ph_max, ...)
        params.target_ph = (targets.value.ph_min + targets.value.ph_max) / 2
      } else if (typeof targets.value.ph_min === 'number' || typeof targets.value.ph_max === 'number') {
        // Если есть только одна граница — используем её как целевое значение
        params.target_ph = (targets.value.ph_min ?? targets.value.ph_max) as number
      } else if ((targets.value as any).ph?.min && (targets.value as any).ph?.max) {
        // Back-compat: старый формат с вложенным объектом ph { min, max }
        const ph = (targets.value as any).ph
        params.target_ph = (ph.min + ph.max) / 2
      } else if (typeof (targets.value as any).ph === 'number') {
        // Back-compat: старый формат с одним числовым значением pH
        params.target_ph = (targets.value as any).ph
      } else {
        params.target_ph = 6.0
      }
      break
      
    case 'EC_CONTROL':
      // Используем целевой EC из targets или рецепта
      if (typeof targets.value.ec_min === 'number' && typeof targets.value.ec_max === 'number') {
        params.target_ec = (targets.value.ec_min + targets.value.ec_max) / 2
      } else if (typeof targets.value.ec_min === 'number' || typeof targets.value.ec_max === 'number') {
        params.target_ec = (targets.value.ec_min ?? targets.value.ec_max) as number
      } else if ((targets.value as any).ec?.min && (targets.value as any).ec?.max) {
        // Back-compat: старый формат с вложенным объектом ec { min, max }
        const ec = (targets.value as any).ec
        params.target_ec = (ec.min + ec.max) / 2
      } else if (typeof (targets.value as any).ec === 'number') {
        params.target_ec = (targets.value as any).ec
      } else {
        params.target_ec = 1.5
      }
      break
      
    case 'CLIMATE':
      // Используем целевые параметры климата из targets или рецепта
      // Температура
      if (typeof targets.value.temp_min === 'number' && typeof targets.value.temp_max === 'number') {
        params.target_temp = (targets.value.temp_min + targets.value.temp_max) / 2
      } else if (typeof targets.value.temp_min === 'number' || typeof targets.value.temp_max === 'number') {
        params.target_temp = (targets.value.temp_min ?? targets.value.temp_max) as number
      } else if ((targets.value as any).temp_air) {
        // Back-compat: старый формат, когда приходило одно значение temp_air
        params.target_temp = (targets.value as any).temp_air
      } else {
        params.target_temp = 22
      }
      
      // Влажность
      if (typeof targets.value.humidity_min === 'number' && typeof targets.value.humidity_max === 'number') {
        params.target_humidity = (targets.value.humidity_min + targets.value.humidity_max) / 2
      } else if (typeof targets.value.humidity_min === 'number' || typeof targets.value.humidity_max === 'number') {
        params.target_humidity = (targets.value.humidity_min ?? targets.value.humidity_max) as number
      } else if ((targets.value as any).humidity_air) {
        // Back-compat: старый формат, когда приходило одно значение humidity_air
        params.target_humidity = (targets.value as any).humidity_air
      } else {
        params.target_humidity = 60
      }
      break
      
    case 'LIGHTING':
      // Используем параметры освещения из targets или рецепта
      if (targets.value.light_hours) {
        params.duration_hours = targets.value.light_hours
      } else {
        params.duration_hours = 12
      }
      
      params.intensity = 80 // Интенсивность по умолчанию
      break
  }
  
  return params
}

async function onRunCycle(): Promise<void> {
  if (!zoneId.value) {
    logger.warn('[onRunCycle] zoneId is missing')
    showToast('Ошибка: зона не найдена', 'error', TOAST_TIMEOUT.NORMAL)
    return
  }

  // Открываем модал для запуска/корректировки агрегированного цикла
  modals.open('growthCycle')
}

const variant = computed<'success' | 'neutral' | 'warning' | 'danger'>(() => {
  switch (zone.value.status) {
    case 'RUNNING': return 'success'
    case 'PAUSED': return 'neutral'
    case 'WARNING': return 'warning'
    case 'ALARM': return 'danger'
    default: return 'neutral'
  }
})

const toggleStatus = computed(() => {
  return activeGrowCycle.value?.status || zone.value.status
})

async function onToggle(): Promise<void> {
  if (!zoneId.value) return
  
  const currentCycle = activeGrowCycle.value
  if (!currentCycle?.id) {
    showToast('Нет активного цикла для паузы или возобновления', 'error', TOAST_TIMEOUT.NORMAL)
    return
  }
  
  const currentStatus = toggleStatus.value
  const isPaused = currentStatus === 'PAUSED'
  const newStatus = isPaused ? 'RUNNING' : 'PAUSED'
  const action = isPaused ? 'resume' : 'pause'
  const actionText = isPaused ? 'возобновлен' : 'приостановлен'
  
  setLoading('toggle', true)
  
  // Создаем оптимистичное обновление
  const optimisticUpdate = createOptimisticZoneUpdate(
    zonesStore,
    zoneId.value,
    { activeGrowCycle: { ...currentCycle, status: newStatus } }
  )
  
  try {
    // Применяем оптимистичное обновление и выполняем операцию на сервере
    await performUpdate(
      `zone-toggle-${zoneId.value}-${Date.now()}`,
      {
        applyUpdate: optimisticUpdate.applyUpdate,
        rollback: optimisticUpdate.rollback,
        syncWithServer: async () => {
          await api.post(`/api/grow-cycles/${currentCycle.id}/${action}`, {})
          return await fetchZone(zoneId.value, true)
        },
        onSuccess: async (updatedZone) => {
          showToast(`Цикл успешно ${actionText}`, 'success', TOAST_TIMEOUT.NORMAL)
          if (updatedZone?.id) {
            zonesStore.upsert(updatedZone, false)
          }
        },
        onError: async (error) => {
          logger.error('Failed to toggle zone:', error)
          let errorMessage = ERROR_MESSAGES.UNKNOWN
          
          // Проверяем, если это ошибка 422 (Cycle is not paused/running), синхронизируем статус
          const is422Error = error && typeof error === 'object' && 'response' in error && 
                           (error as any).response?.status === 422
          
          if (error && typeof error === 'object' && 'message' in error) {
            errorMessage = String(error.message)
          } else if (is422Error && error && typeof error === 'object' && 'response' in error) {
            const response = (error as any).response
            if (response?.data?.message) {
              errorMessage = String(response.data.message)
            }
          }
          
          showToast(`Ошибка при изменении статуса цикла: ${errorMessage}`, 'error', TOAST_TIMEOUT.LONG)
          
          // При ошибке 422 откладываем синхронизацию, чтобы избежать rate limiting
          // Используем setTimeout с задержкой и reloadZone, который делает fallback к Inertia reload
          if (is422Error) {
            logger.info('[Zones/Show] Status mismatch detected, will sync zone from server with delay', {
              zoneId: zoneId.value,
              currentStatus,
              action,
            })
            
            // Откладываем синхронизацию на 2 секунды, чтобы избежать rate limiting
            setTimeout(() => {
              if (zoneId.value) {
                logger.info('[Zones/Show] Syncing zone status from server after delay', {
                  zoneId: zoneId.value,
                })
                // Используем reloadZone вместо fetchZone - он делает fallback к Inertia reload при ошибке
                reloadZone(zoneId.value, ['zone']).catch((syncError) => {
                  logger.error('[Zones/Show] Failed to sync zone status after validation error:', syncError)
                  // Если и reloadZone не помог, просто логируем ошибку
                  // Пользователь может обновить страницу вручную
                })
              }
            }, 2000)
          }
        },
        showLoading: false, // Управляем loading вручную
        timeout: 10000, // 10 секунд таймаут
      }
    )
  } catch (err) {
    // Ошибка уже обработана в onError callback
    logger.error('Failed to toggle zone (unhandled):', err)
  } finally {
    setLoading('toggle', false)
  }
}

function openActionModal(actionType: CommandType): void {
  currentActionType.value = actionType
  showActionModal.value = true
}

async function onActionSubmit({ actionType, params }: { actionType: CommandType; params: Record<string, unknown> }): Promise<void> {
  if (!zoneId.value) return
  
  setLoading('cycleConfig', true)
  
  try {
    await sendZoneCommand(zoneId.value, actionType, params)
    const actionNames: Record<CommandType, string> = {
      'FORCE_IRRIGATION': 'Полив',
      'FORCE_PH_CONTROL': 'Коррекция pH',
      'FORCE_EC_CONTROL': 'Коррекция EC',
      'FORCE_CLIMATE': 'Управление климатом',
      'FORCE_LIGHTING': 'Управление освещением'
    } as Record<CommandType, string>
    const actionName = actionNames[actionType] || 'Действие'
    showToast(`${actionName} запущено успешно`, 'success', TOAST_TIMEOUT.NORMAL)
    // Обновляем зону и cycles через Inertia partial reload
    reloadZoneAfterCommand(zoneId.value, ['zone', 'cycles'])
  } catch (err) {
    logger.error(`Failed to execute ${actionType}:`, err)
    let errorMessage = ERROR_MESSAGES.UNKNOWN
    if (err && typeof err === 'object' && 'message' in err) errorMessage = String(err.message)
    const actionName = actionNames[actionType] || 'Действие'
    showToast(`Ошибка при выполнении "${actionName}": ${errorMessage}`, 'error', TOAST_TIMEOUT.LONG)
  } finally {
    setLoading('cycleConfig', false)
  }
}

async function onGrowthCycleWizardSubmit({ zoneId, recipeId, startedAt, expectedHarvestAt }: { zoneId: number; recipeId: number; startedAt: string; expectedHarvestAt?: string }): Promise<void> {
  // Новый wizard уже создал цикл через API, нужно только обновить данные
  reloadZoneAfterCommand(zoneId, ['zone', 'cycles', 'active_grow_cycle'])
}

async function onGrowthCycleSubmit({ mode, subsystems }: { mode: 'start' | 'adjust'; subsystems: Record<string, { enabled: boolean; targets: any }> }): Promise<void> {
  if (!zoneId.value) return
  
  setLoading('irrigate', true)
  
  try {
    // Отправляем команду GROWTH_CYCLE_CONFIG с mode и subsystems
    await sendZoneCommand(zoneId.value, 'GROWTH_CYCLE_CONFIG' as CommandType, {
      mode,
      subsystems
    })
    
    const modeText = mode === 'start' ? 'запущен' : 'скорректирован'
    showToast(`Цикл выращивания успешно ${modeText}`, 'success', TOAST_TIMEOUT.NORMAL)
    
    // Обновляем зону и cycles через Inertia partial reload
    reloadZoneAfterCommand(zoneId.value, ['zone', 'cycles'])
  } catch (err) {
    logger.error(`Failed to execute GROWTH_CYCLE_CONFIG:`, err)
    let errorMessage = ERROR_MESSAGES.UNKNOWN
    
    // Обработка ошибок валидации с бэкенда (422)
    if (err && typeof err === 'object' && 'response' in err) {
      const response = (err as any).response
      if (response?.status === 422 && response?.data) {
        // Пытаемся извлечь детальное сообщение об ошибке
        if (response.data.message) {
          errorMessage = String(response.data.message)
        } else if (response.data.errors && typeof response.data.errors === 'object') {
          // Если есть объект errors, собираем все сообщения
          const errorMessages = Object.values(response.data.errors).flat()
          errorMessage = errorMessages.length > 0 ? String(errorMessages[0]) : ERROR_MESSAGES.VALIDATION
        } else if (response.data.code === 'VALIDATION_ERROR') {
          errorMessage = response.data.message || ERROR_MESSAGES.VALIDATION
        }
      } else if (response?.data?.message) {
        errorMessage = String(response.data.message)
      }
    } else if (err && typeof err === 'object' && 'message' in err) {
      errorMessage = String(err.message)
    }
    
    showToast(`Ошибка при выполнении цикла выращивания: ${errorMessage}`, 'error', TOAST_TIMEOUT.LONG)
  } finally {
    setLoading('irrigate', false)
  }
}

function openNodeConfig(nodeId: number, node: any): void {
  selectedNodeId.value = nodeId
  selectedNode.value = node
  modals.open('nodeConfig')
}

async function onNodesAttached(nodeIds: number[]): Promise<void> {
  if (!zoneId.value) return
  
  try {
    // Обновляем зону через API вместо reload
    const { fetchZone } = useZones(showToast)
    const updatedZone = await fetchZone(zoneId.value, true) // forceRefresh = true
    
    if (updatedZone?.id) {
      zonesStore.upsert(updatedZone)
      logger.debug('[Zones/Show] Zone updated in store after nodes attachment', { zoneId: updatedZone.id })
    }
  } catch (error) {
    logger.error('[Zones/Show] Failed to update zone after nodes attachment, falling back to reload', { zoneId: zoneId.value, error })
    // Fallback к частичному reload при ошибке
    reloadZone(zoneId.value, ['zone', 'devices'])
  }
}

function onNodeConfigPublished(): void {
  // Конфигурация уже обновлена в store через NodeConfigModal
  // Дополнительное обновление не требуется, так как данные приходят через WebSocket
  logger.debug('[Zones/Show] Node config published, store already updated')
}

async function onNextPhase(): Promise<void> {
  if (!activeGrowCycle.value?.id) return

  setLoading('nextPhase', true)
  try {
    const response = await api.post(`/api/grow-cycles/${activeGrowCycle.value.id}/advance-phase`)
    if (response.data?.status === 'ok') {
      showToast('Фаза успешно изменена', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadZone(zoneId.value, ['zone', 'active_grow_cycle'])
    }
  } catch (err) {
    logger.error('Failed to change phase:', err)
    handleError(err)
  } finally {
    setLoading('nextPhase', false)
  }
}

// Методы для работы с циклами (события теперь загружаются в CycleControlPanel)

async function onCyclePause(): Promise<void> {
  if (!activeGrowCycle.value?.id) return

  setLoading('cyclePause', true)
  try {
    const response = await api.post(`/api/grow-cycles/${activeGrowCycle.value.id}/pause`)
    if (response.data?.status === 'ok') {
      showToast('Цикл приостановлен', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadZone(zoneId.value, ['zone', 'active_grow_cycle'])
    }
  } catch (err) {
    logger.error('Failed to pause cycle:', err)
    handleError(err)
  } finally {
    setLoading('cyclePause', false)
  }
}

async function onCycleResume(): Promise<void> {
  if (!activeGrowCycle.value?.id) return

  setLoading('cycleResume', true)
  try {
    const response = await api.post(`/api/grow-cycles/${activeGrowCycle.value.id}/resume`)
    if (response.data?.status === 'ok') {
      showToast('Цикл возобновлен', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadZone(zoneId.value, ['zone', 'active_grow_cycle'])
    }
  } catch (err) {
    logger.error('Failed to resume cycle:', err)
    handleError(err)
  } finally {
    setLoading('cycleResume', false)
  }
}

const harvestModal = reactive<{ open: boolean; batchLabel: string }>({
  open: false,
  batchLabel: '',
})

const abortModal = reactive<{ open: boolean; notes: string }>({
  open: false,
  notes: '',
})

const changeRecipeModal = reactive<{ open: boolean; recipeRevisionId: string; applyMode: 'now' | 'next_phase' }>({
  open: false,
  recipeRevisionId: '',
  applyMode: 'now',
})

function closeHarvestModal() {
  harvestModal.open = false
  harvestModal.batchLabel = ''
}

function closeAbortModal() {
  abortModal.open = false
  abortModal.notes = ''
}

function closeChangeRecipeModal() {
  changeRecipeModal.open = false
  changeRecipeModal.recipeRevisionId = ''
  changeRecipeModal.applyMode = 'now'
}

function onCycleHarvest(): void {
  if (!activeGrowCycle.value?.id) return
  harvestModal.open = true
}

async function confirmHarvest(): Promise<void> {
  if (!activeGrowCycle.value?.id) return

  setLoading('cycleHarvest', true)
  try {
    const response = await api.post(`/api/grow-cycles/${activeGrowCycle.value.id}/harvest`, {
      batch_label: harvestModal.batchLabel || undefined,
    })
    if (response.data?.status === 'ok') {
      showToast('Урожай зафиксирован, цикл закрыт', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadZone(zoneId.value, ['zone', 'active_grow_cycle'])
      closeHarvestModal()
    }
  } catch (err) {
    logger.error('Failed to harvest cycle:', err)
    handleError(err)
  } finally {
    setLoading('cycleHarvest', false)
  }
}

function onCycleAbort(): void {
  if (!activeGrowCycle.value?.id) return
  abortModal.open = true
}

async function confirmAbort(): Promise<void> {
  if (!activeGrowCycle.value?.id) return

  setLoading('cycleAbort', true)
  try {
    const response = await api.post(`/api/grow-cycles/${activeGrowCycle.value.id}/abort`, {
      notes: abortModal.notes || undefined,
    })
    if (response.data?.status === 'ok') {
      showToast('Цикл аварийно остановлен', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadZone(zoneId.value, ['zone', 'active_grow_cycle'])
      closeAbortModal()
    }
  } catch (err) {
    logger.error('Failed to abort cycle:', err)
    handleError(err)
  } finally {
    setLoading('cycleAbort', false)
  }
}

function onCycleChangeRecipe(): void {
  if (!activeGrowCycle.value?.id) return
  changeRecipeModal.open = true
}

async function confirmChangeRecipe(): Promise<void> {
  if (!activeGrowCycle.value?.id) return

  const revisionIdNum = parseInt(changeRecipeModal.recipeRevisionId)
  if (isNaN(revisionIdNum)) {
    showToast('Неверный ID ревизии', 'error', TOAST_TIMEOUT.NORMAL)
    return
  }

  setLoading('cycleChangeRecipe', true)
  try {
    const response = await api.post(`/api/grow-cycles/${activeGrowCycle.value.id}/change-recipe-revision`, {
      recipe_revision_id: revisionIdNum,
      apply_mode: changeRecipeModal.applyMode,
    })
    if (response.data?.status === 'ok') {
      showToast('Ревизия рецепта обновлена', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadZone(zoneId.value, ['zone', 'active_grow_cycle'])
      await loadCycleEvents()
      closeChangeRecipeModal()
    }
  } catch (err) {
    logger.error('Failed to change recipe revision:', err)
    handleError(err)
  } finally {
    setLoading('cycleChangeRecipe', false)
  }
}

// Вспомогательные функции для отображения циклов
function getCycleStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    PLANNED: 'Запланирован',
    RUNNING: 'Запущен',
    PAUSED: 'Приостановлен',
    HARVESTED: 'Собран',
    ABORTED: 'Прерван',
  }
  return labels[status] || status
}

function getCycleStatusVariant(status: string): 'success' | 'neutral' | 'warning' | 'danger' {
  const variants: Record<string, 'success' | 'neutral' | 'warning' | 'danger'> = {
    PLANNED: 'neutral',
    RUNNING: 'success',
    PAUSED: 'warning',
    HARVESTED: 'success',
    ABORTED: 'danger',
  }
  return variants[status] || 'neutral'
}

function getCycleEventVariant(type: string): 'success' | 'neutral' | 'warning' | 'danger' {
  if (type.includes('HARVESTED') || type.includes('STARTED') || type.includes('RESUMED')) {
    return 'success'
  }
  if (type.includes('ABORTED') || type.includes('CRITICAL')) {
    return 'danger'
  }
  if (type.includes('PAUSED') || type.includes('WARNING')) {
    return 'warning'
  }
  return 'neutral'
}

function getCycleEventTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    CYCLE_CREATED: 'Создан цикл',
    CYCLE_STARTED: 'Запущен цикл',
    CYCLE_PAUSED: 'Приостановлен',
    CYCLE_RESUMED: 'Возобновлен',
    CYCLE_HARVESTED: 'Собран урожай',
    CYCLE_ABORTED: 'Прерван',
    CYCLE_RECIPE_REBASED: 'Рецепт изменен',
    PHASE_TRANSITION: 'Смена фазы',
    RECIPE_PHASE_CHANGED: 'Изменена фаза',
    ZONE_COMMAND: 'Ручное вмешательство',
    ALERT_CREATED: 'Критическое предупреждение',
  }
  return labels[type] || type
}

function getCycleEventMessage(event: any): string {
  const details = event.details || event.payload || {}
  const type = event.type

  if (type === 'CYCLE_HARVESTED') {
    return `Урожай собран${details.batch_label ? ` (партия: ${details.batch_label})` : ''}`
  }
  if (type === 'CYCLE_ABORTED') {
    return `Цикл прерван${details.reason ? `: ${details.reason}` : ''}`
  }
  if (type === 'PHASE_TRANSITION' || type === 'RECIPE_PHASE_CHANGED') {
    return `Фаза ${details.from_phase ?? ''} → ${details.to_phase ?? ''}`
  }
  if (type === 'ZONE_COMMAND') {
    return `Ручное вмешательство: ${details.command_type || 'команда'}`
  }
  if (type === 'ALERT_CREATED') {
    return `Критическое предупреждение: ${details.message || details.code || 'alert'}`
  }

  return getCycleEventTypeLabel(type)
}

// События цикла теперь загружаются внутри CycleControlPanel
</script>
