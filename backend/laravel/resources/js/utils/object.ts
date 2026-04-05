/**
 * Утилиты для работы с объектами.
 */

/**
 * Читает значение из вложенного объекта по dot-notation пути.
 * Возвращает null если путь не существует или промежуточное значение не объект.
 *
 * @example readByPath({ a: { b: 42 } }, 'a.b') // → 42
 * @example readByPath({ a: null }, 'a.b')       // → null
 */
export function readByPath(source: unknown, path: string): unknown {
  if (!source || typeof source !== 'object') {
    return null
  }

  return path.split('.').reduce<unknown>((acc, segment) => {
    if (!acc || typeof acc !== 'object' || Array.isArray(acc)) {
      return null
    }
    return (acc as Record<string, unknown>)[segment]
  }, source)
}
