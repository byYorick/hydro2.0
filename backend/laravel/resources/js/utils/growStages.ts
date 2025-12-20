/**
 * Стадии цикла выращивания
 */
export type GrowStage = 'planting' | 'rooting' | 'veg' | 'flowering' | 'harvest'

export interface GrowStageInfo {
  id: GrowStage
  label: string
  color: string
  icon?: string
}

/**
 * Информация о стадиях
 */
export const GROW_STAGES: Record<GrowStage, GrowStageInfo> = {
  planting: {
    id: 'planting',
    label: 'Посадка',
    color: 'var(--accent-lime)',
    icon: '🌱',
  },
  rooting: {
    id: 'rooting',
    label: 'Укоренение',
    color: 'var(--accent-cyan)',
    icon: '🌿',
  },
  veg: {
    id: 'veg',
    label: 'Вега',
    color: 'var(--accent-green)',
    icon: '🌳',
  },
  flowering: {
    id: 'flowering',
    label: 'Цветение',
    color: 'var(--accent-amber)',
    icon: '🌸',
  },
  harvest: {
    id: 'harvest',
    label: 'Сбор',
    color: 'var(--accent-red)',
    icon: '🍎',
  },
}

/**
 * Маппинг названий фаз к стадиям
 * Можно расширить для кастомных рецептов
 */
const PHASE_TO_STAGE_MAPPING: Record<string, GrowStage> = {
  // Посадка
  'посадка': 'planting',
  'посев': 'planting',
  'germination': 'planting',
  'germ': 'planting',
  'seed': 'planting',
  'семена': 'planting',
  
  // Укоренение
  'укоренение': 'rooting',
  'rooting': 'rooting',
  'root': 'rooting',
  'seedling': 'rooting',
  'рассада': 'rooting',
  'ростки': 'rooting',
  
  // Вега
  'вега': 'veg',
  'вегетация': 'veg',
  'vegetative': 'veg',
  'veg': 'veg',
  'growth': 'veg',
  'рост': 'veg',
  'вегетативный': 'veg',
  
  // Цветение
  'цветение': 'flowering',
  'flowering': 'flowering',
  'flower': 'flowering',
  'bloom': 'flowering',
  'blooming': 'flowering',
  'цвет': 'flowering',
  
  // Сбор
  'сбор': 'harvest',
  'harvest': 'harvest',
  'finishing': 'harvest',
  'finish': 'harvest',
  'созревание': 'harvest',
  'урожай': 'harvest',
}

/**
 * Маппинг по индексу фазы (для рецептов с фиксированным порядком)
 * Можно настроить в зависимости от типа рецепта
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
 */
export function getStageInfo(stage: GrowStage | null): GrowStageInfo | null {
  if (!stage) return null
  return GROW_STAGES[stage] || null
}

/**
 * Вычисляет общий прогресс цикла на основе фаз рецепта
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
    completedHours += phases[i]?.duration_hours || 0
  }
  
  // Добавляем прогресс текущей фазы
  const currentPhase = phases[currentPhaseIndex]
  const currentPhaseProgress = (phaseProgress || 0) / 100
  const currentPhaseCompleted = (currentPhase?.duration_hours || 0) * currentPhaseProgress
  
  const totalCompleted = completedHours + currentPhaseCompleted
  
  return Math.min(100, Math.max(0, (totalCompleted / totalHours) * 100))
}
