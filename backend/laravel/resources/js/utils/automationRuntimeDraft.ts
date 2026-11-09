import type { AutomationRuntimeSettingItem, AutomationRuntimeSettingSection } from '@/types/SystemSettings'
import type { SettingsDraftValue } from '@/utils/settingsDraft'

export type RuntimeDraft = Record<string, SettingsDraftValue>

export function runtimeItems(sections: AutomationRuntimeSettingSection[]): AutomationRuntimeSettingItem[] {
  return sections.flatMap(section => section.items).filter(item => item.editable)
}

export function runtimeFieldError(item: AutomationRuntimeSettingItem, value: SettingsDraftValue): string | null {
  if (item.type === 'bool') return typeof value === 'boolean' ? null : 'Выберите: включено или выключено.'
  if (item.type === 'int' || item.type === 'float') {
    if (value === undefined || value === '' || typeof value === 'boolean' || String(value).trim() === '') return 'Введите число.'
    const number = Number(value)
    if (!Number.isFinite(number)) return 'Введите конечное число.'
    if (item.type === 'int' && !Number.isInteger(number)) return 'Введите целое число.'
    if (item.min !== undefined && number < item.min) return `Минимум: ${item.min}.`
    if (item.max !== undefined && number > item.max) return `Максимум: ${item.max}.`
  }
  if (item.options?.length && !item.options.includes(String(value))) return 'Выберите значение из списка.'
  return null
}

export function normalizeRuntimeValue(item: AutomationRuntimeSettingItem, value: SettingsDraftValue): SettingsDraftValue {
  if (item.type === 'bool') return value
  if (item.type === 'int' || item.type === 'float') return Number(value)
  return String(value ?? '').trim()
}

export function isRuntimeFieldDirty(item: AutomationRuntimeSettingItem, value: SettingsDraftValue): boolean {
  if (runtimeFieldError(item, value)) return true
  return !Object.is(normalizeRuntimeValue(item, value), item.value)
}

export function buildRuntimePatch(sections: AutomationRuntimeSettingSection[], draft: RuntimeDraft): RuntimeDraft {
  const patch: RuntimeDraft = {}
  for (const item of runtimeItems(sections)) {
    const error = runtimeFieldError(item, draft[item.key])
    if (error) throw new Error(`${item.label}: ${error}`)
    if (isRuntimeFieldDirty(item, draft[item.key])) patch[item.key] = normalizeRuntimeValue(item, draft[item.key])
  }
  return patch
}
