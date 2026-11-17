import type { SystemSettingsField } from '@/types/SystemSettings'
import { runtimeFieldError } from './automationRuntimeDraft'
import { isValidHHMM } from '@/services/automation/parsingUtils'

export type SettingsDraftValue = string | number | boolean | undefined

export function settingsFieldError(field: SystemSettingsField, value: SettingsDraftValue): string | null {
  if (field.type === 'json') {
    try {
      const parsed = JSON.parse(String(value ?? ''))
      return parsed !== null && typeof parsed === 'object' ? null : 'Введите список или объект JSON.'
    } catch { return 'Проверьте формат JSON.' }
  }
  if (field.type === 'string' && (typeof value !== 'string' || value.trim() === '')) return 'Введите значение.'
  if (field.type === 'string' && field.path.endsWith('_hhmm') && !isValidHHMM(String(value ?? ''))) {
    return 'Укажите время ЧЧ:ММ от 00:00 до 23:59.'
  }
  return runtimeFieldError({
    ...field, key: field.path, value: undefined, editable: true, input_type: field.type,
    type: ({ integer: 'int', number: 'float', boolean: 'bool' } as Record<string, string>)[field.type] ?? field.type,
  }, value)
}

export function normalizeSettingsFieldValue(field: SystemSettingsField, value: SettingsDraftValue): unknown {
  const error = settingsFieldError(field, value)
  if (error) throw new Error(`${field.label}: ${error}`)
  if (field.type === 'json') return JSON.parse(String(value))
  if (field.type === 'integer' || field.type === 'number') return Number(value)
  if (field.type === 'string') return String(value).trim()
  return value
}

export function isSettingsFieldDirty(field: SystemSettingsField, value: SettingsDraftValue, saved: unknown): boolean {
  if (settingsFieldError(field, value)) return true
  return JSON.stringify(normalizeSettingsFieldValue(field, value)) !== JSON.stringify(saved)
}

/**
 * Поверхностное сравнение черновиков настроек.
 *
 * Формы настроек синхронизируют локальный draft с `modelValue` через два watcher-а.
 * Без такой проверки они переизлучают одно и то же значение по кругу и Vue падает
 * с «Maximum recursive updates exceeded».
 */
export function isSameSettingsDraft(
  a: Record<string, SettingsDraftValue>,
  b: Record<string, SettingsDraftValue>,
): boolean {
  const aKeys = Object.keys(a)
  const bKeys = Object.keys(b)

  if (aKeys.length !== bKeys.length) {
    return false
  }

  return aKeys.every((key) => Object.is(a[key], b[key]))
}
