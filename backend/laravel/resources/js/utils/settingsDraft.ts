export type SettingsDraftValue = string | number | boolean | undefined

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
