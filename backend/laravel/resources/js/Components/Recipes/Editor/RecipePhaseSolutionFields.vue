<template>
  <div class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2">
    <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
      Раствор
    </div>
    <div :class="phase.day_night_enabled ? 'space-y-3' : 'max-w-sm space-y-2'">
      <!-- pH -->
      <div>
        <div class="text-sm font-extrabold text-[color:var(--text-primary)] mb-1 tracking-widest uppercase">
          pH
        </div>
        <div class="flex flex-wrap gap-3">
          <div :class="phase.day_night_enabled ? 'w-full min-w-0 sm:min-w-[280px] sm:flex-1 max-w-sm' : 'w-full max-w-sm'">
            <div
              v-if="phase.day_night_enabled"
              class="text-[10px] text-[color:var(--text-dim)] uppercase tracking-wider mb-1"
            >
              ☀ день
            </div>
            <div class="target-row">
              <div class="target-row__side">
                <span class="target-row__label">мин</span><input
                  v-model.number="phase.ph_min"
                  type="number"
                  step="0.1"
                  class="target-row__input hide-spin"
                />
              </div>
              <div class="target-row__center">
                <button
                  type="button"
                  class="target-row__btn"
                  @click="phase.ph_target = +((phase.ph_target ?? 0) - 0.1).toFixed(1); onPhTargetChange(phase)"
                >
                  &minus;
                </button>
                <input
                  v-model.number="phase.ph_target"
                  type="number"
                  step="0.1"
                  class="target-row__input target-row__input--main hide-spin"
                  @input="onPhTargetChange(phase)"
                />
                <button
                  type="button"
                  class="target-row__btn"
                  @click="phase.ph_target = +((phase.ph_target ?? 0) + 0.1).toFixed(1); onPhTargetChange(phase)"
                >
                  +
                </button>
              </div>
              <div class="target-row__side">
                <span class="target-row__label">макс</span><input
                  v-model.number="phase.ph_max"
                  type="number"
                  step="0.1"
                  class="target-row__input hide-spin"
                />
              </div>
            </div>
          </div>
          <div
            v-if="phase.day_night_enabled"
            class="w-full min-w-0 sm:min-w-[280px] sm:flex-1 max-w-sm"
          >
            <div class="text-[10px] text-[color:var(--text-dim)] uppercase tracking-wider mb-1">
              ☾ ночь
            </div>
            <div class="target-row">
              <div class="target-row__side">
                <span class="target-row__label">мин</span><input
                  v-model.number="phase.day_night.ph.night_min"
                  type="number"
                  step="0.1"
                  class="target-row__input hide-spin"
                />
              </div>
              <div class="target-row__center">
                <button
                  type="button"
                  class="target-row__btn"
                  @click="phase.day_night.ph.night = +((phase.day_night.ph.night ?? 0) - 0.1).toFixed(1); onPhNightTargetChange(phase)"
                >
                  &minus;
                </button>
                <input
                  v-model.number="phase.day_night.ph.night"
                  type="number"
                  step="0.1"
                  class="target-row__input target-row__input--main hide-spin"
                  @input="onPhNightTargetChange(phase)"
                />
                <button
                  type="button"
                  class="target-row__btn"
                  @click="phase.day_night.ph.night = +((phase.day_night.ph.night ?? 0) + 0.1).toFixed(1); onPhNightTargetChange(phase)"
                >
                  +
                </button>
              </div>
              <div class="target-row__side">
                <span class="target-row__label">макс</span><input
                  v-model.number="phase.day_night.ph.night_max"
                  type="number"
                  step="0.1"
                  class="target-row__input hide-spin"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
      <!-- EC -->
      <div>
        <div class="text-sm font-extrabold text-[color:var(--text-primary)] mb-1 tracking-widest uppercase">
          EC
        </div>
        <div class="flex flex-wrap gap-3">
          <div :class="phase.day_night_enabled ? 'w-full min-w-0 sm:min-w-[280px] sm:flex-1 max-w-sm' : 'w-full max-w-sm'">
            <div
              v-if="phase.day_night_enabled"
              class="text-[10px] text-[color:var(--text-dim)] uppercase tracking-wider mb-1"
            >
              ☀ день
            </div>
            <div class="target-row">
              <div class="target-row__side">
                <span class="target-row__label">мин</span><input
                  v-model.number="phase.ec_min"
                  type="number"
                  step="0.1"
                  class="target-row__input hide-spin"
                />
              </div>
              <div class="target-row__center">
                <button
                  type="button"
                  class="target-row__btn"
                  @click="phase.ec_target = +((phase.ec_target ?? 0) - 0.1).toFixed(1); onEcTargetChange(phase)"
                >
                  &minus;
                </button>
                <input
                  v-model.number="phase.ec_target"
                  type="number"
                  step="0.1"
                  class="target-row__input target-row__input--main hide-spin"
                  @input="onEcTargetChange(phase)"
                />
                <button
                  type="button"
                  class="target-row__btn"
                  @click="phase.ec_target = +((phase.ec_target ?? 0) + 0.1).toFixed(1); onEcTargetChange(phase)"
                >
                  +
                </button>
              </div>
              <div class="target-row__side">
                <span class="target-row__label">макс</span><input
                  v-model.number="phase.ec_max"
                  type="number"
                  step="0.1"
                  class="target-row__input hide-spin"
                />
              </div>
            </div>
          </div>
          <div
            v-if="phase.day_night_enabled"
            class="w-full min-w-0 sm:min-w-[280px] sm:flex-1 max-w-sm"
          >
            <div class="text-[10px] text-[color:var(--text-dim)] uppercase tracking-wider mb-1">
              ☾ ночь
            </div>
            <div class="target-row">
              <div class="target-row__side">
                <span class="target-row__label">мин</span><input
                  v-model.number="phase.day_night.ec.night_min"
                  type="number"
                  step="0.1"
                  class="target-row__input hide-spin"
                />
              </div>
              <div class="target-row__center">
                <button
                  type="button"
                  class="target-row__btn"
                  @click="phase.day_night.ec.night = +((phase.day_night.ec.night ?? 0) - 0.1).toFixed(1); onEcNightTargetChange(phase)"
                >
                  &minus;
                </button>
                <input
                  v-model.number="phase.day_night.ec.night"
                  type="number"
                  step="0.1"
                  class="target-row__input target-row__input--main hide-spin"
                  @input="onEcNightTargetChange(phase)"
                />
                <button
                  type="button"
                  class="target-row__btn"
                  @click="phase.day_night.ec.night = +((phase.day_night.ec.night ?? 0) + 0.1).toFixed(1); onEcNightTargetChange(phase)"
                >
                  +
                </button>
              </div>
              <div class="target-row__side">
                <span class="target-row__label">макс</span><input
                  v-model.number="phase.day_night.ec.night_max"
                  type="number"
                  step="0.1"
                  class="target-row__input hide-spin"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RecipePhaseFormState } from '@/composables/recipeEditorShared'
const phase = defineModel<RecipePhaseFormState>('phase', { required: true })

import { onPhTargetChange, onEcTargetChange, onPhNightTargetChange, onEcNightTargetChange } from '@/composables/recipePhaseFields'
</script>
