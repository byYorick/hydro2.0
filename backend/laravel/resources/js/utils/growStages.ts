/**
 * ЕДИНСТВЕННЫЙ ИСТОЧНИК ИСТИНЫ для стадий цикла выращивания
 * 
 * Этот файл определяет все стадии, их цвета, лейблы и правила маппинга.
 * Все компоненты должны использовать функции из этого модуля для работы со стадиями.
 * 
 * ИСПОЛЬЗОВАНИЕ:
 *   import { getStageForPhase, getStageInfo, GROW_STAGES } from '@/utils/growStages'
 * 
 * ЗАПРЕЩЕНО:
 *   - Хардкодить стадии в компонентах
 *   - Создавать собственные маппинги стадий
 *   - Использовать строковые литералы вместо типов из этого модуля
 */

/**
 * Типы стадий цикла выращивания
 */
export type GrowStage = 'planting' | 'rooting' | 'veg' | 'flowering' | 'harvest'

/**
 * Информация о стадии (цвет, лейбл, иконка)
 */
export interface GrowStageInfo {
  id: GrowStage
  label: string
  color: string
  icon?: string
  order: number // Порядок стадии для сортировки
}

/**
 * ЕДИНСТВЕННЫЙ источник информации о стадиях
 * Используется во всех компонентах для отображения стадий
 */
export const GROW_STAGES: Record<GrowStage, GrowStageInfo> = {
  planting: {
    id: 'planting',
    label: 'Посадка',
    color: 'var(--accent-lime)',
    icon: '🌱',
    order: 0,
  },
  rooting: {
    id: 'rooting',
    label: 'Укоренение',
    color: 'var(--accent-cyan)',
    icon: '🌿',
    order: 1,
  },
  veg: {
    id: 'veg',
    label: 'Вегетация',
    color: 'var(--accent-green)',
    icon: '🌳',
    order: 2,
  },
  flowering: {
    id: 'flowering',
    label: 'Цветение',
    color: 'var(--accent-amber)',
    icon: '🌸',
    order: 3,
  },
  harvest: {
    id: 'harvest',
    label: 'Сбор урожая',
    color: 'var(--accent-red)',
    icon: '🍎',
    order: 4,
  },
}

/**
 * Массив стадий в правильном порядке
 */
export const GROW_STAGES_ORDERED: GrowStage[] = [
  'planting',
  'rooting',
  'veg',
  'flowering',
  'harvest',
]

/**
 * Маппинг названий фаз к стадиям
 * Поддерживает русский и английский языки, различные варианты написания
 */
const PHASE_TO_STAGE_MAPPING: Record<string, GrowStage> = {
  // Посадка
  'посадка': 'planting',
  'посев': 'planting',
  'germination': 'planting',
  'germ': 'planting',
  'seed': 'planting',
  'семена': 'planting',
  'sowing': 'planting',
  
  // Укоренение
  'укоренение': 'rooting',
  'rooting': 'rooting',
  'root': 'rooting',
  'seedling': 'rooting',
  'рассада': 'rooting',
  'ростки': 'rooting',
  'sprouting': 'rooting',
  
  // Вега
  'вега': 'veg',
  'вегетация': 'veg',
  'vegetative': 'veg',
  'veg': 'veg',
  'growth': 'veg',
  'рост': 'veg',
  'вегетативный': 'veg',
  'vegetation': 'veg',
  
  // Цветение
  'цветение': 'flowering',
  'flowering': 'flowering',
  'flower': 'flowering',
  'bloom': 'flowering',
  'blooming': 'flowering',
  'цвет': 'flowering',
  'floral': 'flowering',
  
  // Сбор
  'сбор': 'harvest',
  'harvest': 'harvest',
  'finishing': 'harvest',
  'finish': 'harvest',
  'созревание': 'harvest',
  'урожай': 'harvest',
  'harvesting': 'harvest',
}

/**
 * Определяет стадию на основе названия фазы
 * 
 * @param phaseName - Название фазы (может быть на русском или английском)
 * @returns Стадия или undefined, если не удалось определить
 */
export function getStageByPhaseName(phaseName: string | null | undefined): GrowStage | undefined {
  if (!phaseName) return undefined
  
  const normalized = phaseName.toLowerCase().trim()
  
  // Прямой маппинг
  if (PHASE_TO_STAGE_MAPPING[normalized]) {
    return PHASE_TO_STAGE_MAPPING[normalized]
  }
  
  // Поиск по ключевым словам
  for (const [key, stage] of Object.entries(PHASE_TO_STAGE_MAPPING)) {
    if (normalized.includes(key) || key.includes(normalized)) {
      return stage
    }
  }
  
  return undefined
}

/**
 * Определяет стадию на основе индекса фазы
 * 
 * @param phaseIndex - Индекс фазы (0-based)
 * @param totalPhases - Общее количество фаз
 * @returns Стадия или undefined
 */
function getStageMapForTotalPhases(totalPhases: number): GrowStage[] {
  if (totalPhases >= GROW_STAGES_ORDERED.length) {
    return GROW_STAGES_ORDERED
  }
  if (totalPhases === 4) {
    return ['planting', 'veg', 'veg', 'flowering']
  }
  if (totalPhases === 3) {
    return ['planting', 'veg', 'flowering']
  }
  if (totalPhases === 2) {
    return ['planting', 'veg']
  }
  return ['veg']
}

export function getStageByPhaseIndex(phaseIndex: number, totalPhases?: number): GrowStage | undefined {
  if (phaseIndex < 0) return undefined

  if (typeof totalPhases === 'number' && totalPhases > 0) {
    const stageMap = getStageMapForTotalPhases(totalPhases)
    if (phaseIndex >= stageMap.length) {
      return stageMap[stageMap.length - 1]
    }
    return stageMap[phaseIndex]
  }

  if (phaseIndex === 0) return 'planting'
  if (phaseIndex === 1 || phaseIndex === 2) return 'veg'
  if (phaseIndex === 3) return 'flowering'
  return 'veg'
}

/**
 * Определяет стадию для фазы (комбинированный подход)
 * Сначала пытается определить по названию, затем по индексу
 * 
 * @param phaseName - Название фазы
 * @param phaseIndex - Индекс фазы
 * @param totalPhases - Общее количество фаз
 * @returns Стадия или undefined
 */
export function getStageForPhase(
  phaseName: string | null | undefined,
  phaseIndex: number,
  totalPhases?: number
): GrowStage | undefined {
  // Сначала пытаемся определить по названию
  const stageByName = getStageByPhaseName(phaseName)
  if (stageByName) {
    return stageByName
  }
  
  // Если не получилось, используем индекс
  return getStageByPhaseIndex(phaseIndex, totalPhases)
}

/**
 * Получить информацию о стадии
 * 
 * @param stage - Стадия или null
 * @returns Информация о стадии или undefined
 */
export function getStageInfo(stage: GrowStage | null | undefined): GrowStageInfo | undefined {
  if (!stage || !GROW_STAGES[stage]) return undefined
  return GROW_STAGES[stage]
}

/**
 * Получить цвет стадии
 * 
 * @param stage - Стадия или null
 * @returns CSS переменная цвета или undefined
 */
export function getStageColor(stage: GrowStage | null | undefined): string | undefined {
  const info = getStageInfo(stage)
  return info?.color
}

/**
 * Получить лейбл стадии
 * 
 * @param stage - Стадия или null
 * @returns Лейбл стадии или undefined
 */
export function getStageLabel(stage: GrowStage | null | undefined): string | undefined {
  const info = getStageInfo(stage)
  return info?.label
}

/**
 * Получить иконку стадии
 * 
 * @param stage - Стадия или null
 * @returns Иконка стадии или undefined
 */
export function getStageIcon(stage: GrowStage | null | undefined): string | undefined {
  const info = getStageInfo(stage)
  return info?.icon
}

/**
 * Получить порядок стадии (для сортировки)
 * 
 * @param stage - Стадия или null
 * @returns Порядок стадии или -1
 */
export function getStageOrder(stage: GrowStage | null | undefined): number {
  const info = getStageInfo(stage)
  return info?.order ?? -1
}

/**
 * Проверить, является ли стадия валидной
 * 
 * @param stage - Стадия для проверки
 * @returns true, если стадия валидна
 */
export function isValidStage(stage: string | null | undefined): stage is GrowStage {
  if (!stage) return false
  return stage in GROW_STAGES
}

/**
 * Получить следующую стадию
 * 
 * @param currentStage - Текущая стадия
 * @returns Следующая стадия или undefined, если текущая стадия последняя
 */
export function getNextStage(currentStage: GrowStage | null | undefined): GrowStage | undefined {
  if (!currentStage || !isValidStage(currentStage)) return undefined

  const currentOrder = getStageOrder(currentStage)
  if (currentOrder < 0 || currentOrder >= GROW_STAGES_ORDERED.length - 1) {
    return undefined
  }

  return GROW_STAGES_ORDERED[currentOrder + 1]
}

/**
 * Получить предыдущую стадию
 * 
 * @param currentStage - Текущая стадия
 * @returns Предыдущая стадия или undefined, если текущая стадия первая
 */
export function getPrevStage(currentStage: GrowStage | null | undefined): GrowStage | undefined {
  if (!currentStage || !isValidStage(currentStage)) return undefined

  const currentOrder = getStageOrder(currentStage)
  if (currentOrder <= 0) {
    return undefined
  }

  return GROW_STAGES_ORDERED[currentOrder - 1]
}

/**
 * Вычисляет общий прогресс цикла на основе фаз рецепта
 * 
 * @param currentPhaseIndex - Индекс текущей фазы
 * @param phases - Массив фаз с длительностью
 * @param startedAt - Дата начала цикла
 * @param phaseProgress - Прогресс текущей фазы (0-100)
 * @returns Прогресс цикла в процентах (0-100)
 */
type CycleProgressInput = {
  recipe?: { phases?: Array<{ duration_hours: number }> }
  started_at?: string | null
  current_phase_index?: number | null
  phase_progress?: number | null
}

function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, value))
}

function calculateProgressFromElapsed(
  phases: Array<{ duration_hours: number }>,
  startedAt: string
): number {
  const startedAtDate = new Date(startedAt)
  if (Number.isNaN(startedAtDate.getTime())) {
    return 0
  }

  let remainingHours = (Date.now() - startedAtDate.getTime()) / (1000 * 60 * 60)
  if (remainingHours <= 0) {
    return 0
  }

  const perPhaseProgress = phases.map((phase) => {
    const durationHours = phase?.duration_hours || 0
    if (durationHours <= 0) {
      return 0
    }

    if (remainingHours >= durationHours) {
      remainingHours -= durationHours
      return 100
    }

    const progress = (remainingHours / durationHours) * 100
    remainingHours = 0
    return clampPercent(progress)
  })

  const sum = perPhaseProgress.reduce((total, value) => total + value, 0)
  return clampPercent(sum / phases.length)
}

export function calculateCycleProgress(
  input: CycleProgressInput
): number
export function calculateCycleProgress(
  currentPhaseIndex: number,
  phases: Array<{ duration_hours: number }>,
  startedAt: string | null | undefined,
  phaseProgress: number | null
): number
export function calculateCycleProgress(
  arg1: CycleProgressInput | number,
  arg2?: Array<{ duration_hours: number }>,
  arg3?: string | null,
  arg4?: number | null
): number {
  if (typeof arg1 === 'object' && arg1 !== null && !Array.isArray(arg1)) {
    const phases = arg1.recipe?.phases || []
    const startedAt = arg1.started_at
    const currentPhaseIndex = arg1.current_phase_index ?? -1
    const phaseProgress = arg1.phase_progress ?? null
    return calculateCycleProgress(currentPhaseIndex, phases, startedAt, phaseProgress)
  }

  const currentPhaseIndex = arg1 as number
  const phases = arg2 || []
  const startedAt = arg3
  const phaseProgress = arg4

  if (!startedAt || phases.length === 0) {
    return 0
  }

  if (currentPhaseIndex < 0 || currentPhaseIndex >= phases.length) {
    return 0
  }

  if (typeof phaseProgress === 'number') {
    const perPhaseProgress = phases.map((_, index) => {
      if (index < currentPhaseIndex) return 100
      if (index > currentPhaseIndex) return 0
      return clampPercent(phaseProgress)
    })

    const sum = perPhaseProgress.reduce((total, value) => total + value, 0)
    return clampPercent(sum / phases.length)
  }

  return calculateProgressFromElapsed(phases, startedAt)
}
