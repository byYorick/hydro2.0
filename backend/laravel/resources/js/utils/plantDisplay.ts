export interface DisplayRange {
  min?: number | string | null
  max?: number | string | null
}

export function formatRange(range: DisplayRange | undefined): string {
  if (!range) {
    return '—'
  }
  const min = range.min ?? ''
  const max = range.max ?? ''
  if (min === '' && max === '') {
    return '—'
  }
  if (min !== '' && max !== '') {
    return `${min} – ${max}`
  }
  return min !== '' ? `от ${min}` : `до ${max}`
}

export function formatCurrency(value: number | string | null | undefined, currency = 'RUB'): string {
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  const numeric = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(numeric)) {
    return '—'
  }
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(numeric)
}

export function formatDuration(hours: number | null | undefined): string {
  if (!hours) {
    return '-'
  }
  if (hours < 24) {
    return `${hours} ч`
  }
  const days = Math.floor(hours / 24)
  const remainder = hours % 24
  if (remainder === 0) {
    return `${days} дн`
  }
  return `${days} дн ${remainder} ч`
}

export function formatTargetRange(target: { min?: number; max?: number } | number | undefined | null): string {
  if (target === undefined || target === null) {
    return '-'
  }
  if (typeof target === 'number') {
    return target.toString()
  }
  const min = target.min ?? ''
  const max = target.max ?? ''
  if (min === '' && max === '') {
    return '-'
  }
  if (min !== '' && max !== '') {
    return `${min}–${max}`
  }
  return min !== '' ? `от ${min}` : `до ${max}`
}

export function formatIrrigationInterval(seconds: number | undefined | null): string {
  if (!seconds) {
    return '-'
  }
  if (seconds < 60) {
    return `${seconds} сек`
  }
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const secs = seconds % 60
    if (secs === 0) {
      return `${minutes} мин`
    }
    return `${minutes} мин ${secs} сек`
  }
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  if (mins === 0) {
    return `${hours} ч`
  }
  return `${hours} ч ${mins} мин`
}

export function hasTargetValue(target: unknown): boolean {
  if (target === null || target === undefined) {
    return false
  }
  if (typeof target === 'number') {
    return true
  }
  if (typeof target === 'object') {
    const range = target as DisplayRange
    return (range.min !== null && range.min !== undefined) || (range.max !== null && range.max !== undefined)
  }
  return false
}

export function hasPhaseTargets(targets: unknown): boolean {
  if (!targets || typeof targets !== 'object') {
    return false
  }
  return Object.values(targets).some(value => hasTargetValue(value))
}
