import type { BadgeVariant } from '@/Components/Badge.vue'

export type CycleStatusLabelStyle = 'long' | 'short' | 'sentence'
export type CycleStatusVariantStyle = 'default' | 'center'

const LABELS_BY_STYLE: Record<CycleStatusLabelStyle, Record<string, string>> = {
  long: {
    PLANNED: 'Запланирован',
    RUNNING: 'Запущен',
    PAUSED: 'Приостановлен',
    HARVESTED: 'Собран',
    ABORTED: 'Прерван',
    AWAITING_CONFIRM: 'Ожидает подтверждения',
  },
  short: {
    PLANNED: 'План',
    RUNNING: 'Активен',
    PAUSED: 'Пауза',
    HARVESTED: 'Собран',
    ABORTED: 'Прерван',
    AWAITING_CONFIRM: 'Ожидание',
  },
  sentence: {
    PLANNED: 'Цикл запланирован',
    RUNNING: 'Цикл активен',
    PAUSED: 'Цикл на паузе',
    HARVESTED: 'Цикл собран',
    ABORTED: 'Цикл прерван',
    AWAITING_CONFIRM: 'Цикл ожидает подтверждения',
  },
}

const VARIANTS_BY_STYLE: Record<CycleStatusVariantStyle, Record<string, BadgeVariant>> = {
  default: {
    PLANNED: 'neutral',
    RUNNING: 'success',
    PAUSED: 'warning',
    HARVESTED: 'success',
    ABORTED: 'danger',
    AWAITING_CONFIRM: 'warning',
  },
  center: {
    PLANNED: 'info',
    RUNNING: 'success',
    PAUSED: 'warning',
    HARVESTED: 'success',
    ABORTED: 'danger',
    AWAITING_CONFIRM: 'warning',
  },
}

export function getCycleStatusLabel(status: string, style: CycleStatusLabelStyle = 'long'): string {
  return LABELS_BY_STYLE[style]?.[status] ?? status
}

export function getCycleStatusVariant(status: string, style: CycleStatusVariantStyle = 'default'): BadgeVariant {
  return VARIANTS_BY_STYLE[style]?.[status] ?? 'neutral'
}
