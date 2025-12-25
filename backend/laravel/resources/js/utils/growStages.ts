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
 * Маппинг по индексу фазы (для рецептов с фиксированным порядком)
 */
const DEFAULT_STAGE_BY_PHASE_INDEX: GrowStage[] = [
  'planting',    // фаза 0
  'rooting',     // фаза 1
  'veg',         // фаза 2
  'flowering',   // фаза 3
  'harvest',     // фаза 4+
]

/**
 * Определяет стадию на основе названия фазы
 * 
 * @param phaseName - Название фазы (может быть на русском или английском)
 * @returns Стадия или null, если не удалось определить
 */
export function getStageByPhaseName(phaseName: string | null | undefined): GrowStage | null {
  if (!phaseName) return null
  
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
  
  return null
}

/**
 * Определяет стадию на основе индекса фазы
 * 
 * @param phaseIndex - Индекс фазы (0-based)
 * @param totalPhases - Общее количество фаз
 * @returns Стадия
 */
export function getStageByPhaseIndex(phaseIndex: number, totalPhases: number): GrowStage {
  if (phaseIndex < 0) return 'planting'
  if (phaseIndex >= DEFAULT_STAGE_BY_PHASE_INDEX.length) {
    // Для фаз после последней стадии возвращаем последнюю
    return DEFAULT_STAGE_BY_PHASE_INDEX[DEFAULT_STAGE_BY_PHASE_INDEX.length - 1]
  }
  return DEFAULT_STAGE_BY_PHASE_INDEX[phaseIndex]
}

/**
 * Определяет стадию для фазы (комбинированный подход)
 * Сначала пытается определить по названию, затем по индексу
 * 
 * @param phaseName - Название фазы
 * @param phaseIndex - Индекс фазы
 * @param totalPhases - Общее количество фаз
 * @returns Стадия
 */
export function getStageForPhase(
  phaseName: string | null | undefined,
  phaseIndex: number,
  totalPhases: number
): GrowStage {
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
 * @returns Информация о стадии или null
 */
export function getStageInfo(stage: GrowStage | null): GrowStageInfo | null {
  if (!stage) return null
  return GROW_STAGES[stage] || null
}

/**
 * Получить цвет стадии
 * 
 * @param stage - Стадия или null
 * @returns CSS переменная цвета или null
 */
export function getStageColor(stage: GrowStage | null): string | null {
  const info = getStageInfo(stage)
  return info?.color || null
}

/**
 * Получить лейбл стадии
 * 
 * @param stage - Стадия или null
 * @returns Лейбл стадии или пустая строка
 */
export function getStageLabel(stage: GrowStage | null): string {
  const info = getStageInfo(stage)
  return info?.label || ''
}

/**
 * Получить иконку стадии
 * 
 * @param stage - Стадия или null
 * @returns Иконка стадии или пустая строка
 */
export function getStageIcon(stage: GrowStage | null): string {
  const info = getStageInfo(stage)
  return info?.icon || ''
}

/**
 * Получить порядок стадии (для сортировки)
 * 
 * @param stage - Стадия или null
 * @returns Порядок стадии или -1
 */
export function getStageOrder(stage: GrowStage | null): number {
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
 * @returns Следующая стадия или null, если текущая стадия последняя
 */
export function getNextStage(currentStage: GrowStage | null): GrowStage | null {
  if (!currentStage) return 'planting'
  
  const currentOrder = getStageOrder(currentStage)
  if (currentOrder < 0 || currentOrder >= GROW_STAGES_ORDERED.length - 1) {
    return null
  }
  
  return GROW_STAGES_ORDERED[currentOrder + 1]
}

/**
 * Получить предыдущую стадию
 * 
 * @param currentStage - Текущая стадия
 * @returns Предыдущая стадия или null, если текущая стадия первая
 */
export function getPrevStage(currentStage: GrowStage | null): GrowStage | null {
  if (!currentStage) return null
  
  const currentOrder = getStageOrder(currentStage)
  if (currentOrder <= 0) {
    return null
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
export function calculateCycleProgress(
  currentPhaseIndex: number,
  phases: Array<{ duration_hours: number }>,
  startedAt: string | null | undefined,
  phaseProgress: number | null
): number {
  if (!startedAt || !phases || phases.length === 0) {
    return 0
  }
  
  if (currentPhaseIndex < 0 || currentPhaseIndex >= phases.length) {
    return 0
  }
  
  // Вычисляем общее время цикла
  const totalHours = phases.reduce((sum, phase) => sum + (phase.duration_hours || 0), 0)
  
  if (totalHours === 0) {
    return 0
  }
  
  // Вычисляем прошедшее время до текущей фазы
  let completedHours = 0
  for (let i = 0; i < currentPhaseIndex; i++) {
    const phase = phases[i]
    if (phase && typeof phase.duration_hours === 'number') {
      completedHours += phase.duration_hours
    }
  }
  
  // Добавляем прогресс текущей фазы
  const currentPhase = phases[currentPhaseIndex]
  if (!currentPhase) {
    return 0
  }
  
  const currentPhaseDurationHours = currentPhase.duration_hours || 0
  const currentPhaseProgress = (phaseProgress || 0) / 100
  const currentPhaseCompleted = currentPhaseDurationHours * currentPhaseProgress
  
  const totalCompleted = completedHours + currentPhaseCompleted
  
  return Math.min(100, Math.max(0, (totalCompleted / totalHours) * 100))
}
