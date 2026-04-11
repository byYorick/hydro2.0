/**
 * Чистые helper-функции для AutomationProcessDiagram.vue.
 * Вынесены отдельно, чтобы облегчить unit-тестирование и разгрузить
 * основной компонент.
 */

export function formatUpdatedAt(value: string | null | undefined): string {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function formatIrrStateValue(value: boolean | null | undefined): string {
  if (value === true) return 'Вкл'
  if (value === false) return 'Выкл'
  return '—'
}

export function clampPercent(value: unknown): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 0
  return Math.max(0, Math.min(100, parsed))
}

export function tankFillY(levelPercent: number): number {
  const normalized = clampPercent(levelPercent)
  return 70 + 250 * (1 - normalized / 100)
}

export function tankFillHeight(levelPercent: number): number {
  const normalized = clampPercent(levelPercent)
  return 250 * (normalized / 100)
}

export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '-'
  }
  return Number(value).toFixed(digits)
}

const ELEMENT_TITLE_MAP: Record<string, string> = {
  clean: 'Бак чистой воды',
  nutrient: 'Бак рабочего раствора',
  buffer: 'Буферный бак',
  pipes: 'Линии потока',
  correction: 'Контур коррекции',
  correction_node: 'Узел коррекции',
  valve_in: 'Входной клапан',
  valve_out: 'Выходной клапан',
  pump_in: 'Насос набора',
  pump: 'Главный насос',
  circulation: 'Насос рециркуляции',
  pump_correction: 'Насос дозирования',
}

export function elementTitle(element: string): string {
  return ELEMENT_TITLE_MAP[element] ?? element
}
