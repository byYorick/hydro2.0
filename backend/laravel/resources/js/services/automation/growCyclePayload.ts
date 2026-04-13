/**
 * Построение payload'а для создания grow cycle.
 *
 * Чистая функция без Vue-зависимостей — вход/выход только данные.
 * Используется Growth Cycle Wizard при submit (POST /zones/{id}/grow-cycles).
 */

import type { WaterFormState } from '@/composables/zoneAutomationTypes'

export interface CreateGrowCyclePayloadInput {
  waterForm: WaterFormState
  recipeRevisionId: number
  plantId: number
  plantingAt?: string
  expectedHarvestAt?: string
  startImmediately: boolean
}

export interface CreateGrowCyclePayload {
  recipe_revision_id: number
  plant_id: number
  planting_at?: string
  start_immediately: boolean
  irrigation: {
    system_type: WaterFormState['systemType']
    interval_minutes: number
    duration_seconds: number
    clean_tank_fill_l?: number
    nutrient_tank_target_l?: number
    irrigation_batch_l?: number
  }
  settings: {
    expected_harvest_at?: string
  }
}

export function buildCreateGrowCyclePayload(
  input: CreateGrowCyclePayloadInput,
): CreateGrowCyclePayload {
  const { waterForm } = input
  const isTwoTank = waterForm.tanksCount === 2

  return {
    recipe_revision_id: input.recipeRevisionId,
    plant_id: input.plantId,
    planting_at: input.plantingAt,
    start_immediately: input.startImmediately,
    irrigation: {
      system_type: waterForm.systemType,
      interval_minutes: waterForm.intervalMinutes,
      duration_seconds: waterForm.durationSeconds,
      clean_tank_fill_l: isTwoTank ? waterForm.cleanTankFillL : undefined,
      nutrient_tank_target_l: isTwoTank ? waterForm.nutrientTankTargetL : undefined,
      irrigation_batch_l: isTwoTank ? waterForm.irrigationBatchL : undefined,
    },
    settings: {
      expected_harvest_at: input.expectedHarvestAt || undefined,
    },
  }
}
