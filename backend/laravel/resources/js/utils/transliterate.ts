/**
 * Утилита для транслитерации русского текста в латиницу
 */

/**
 * Таблица транслитерации русских букв в латиницу
 */
const transliterationMap: Record<string, string> = {
  'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
  'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
  'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
  'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
  'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
  'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
  'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
  'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
  'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
  'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
}

/**
 * Транслитерирует русский текст в латиницу
 * @param text - Исходный текст (может содержать русские буквы)
 * @returns Транслитерированный текст
 */
export function transliterate(text: string): string {
  return text
    .split('')
    .map(char => transliterationMap[char] || char)
    .join('')
}

/**
 * Генерирует UID на основе названия с префиксом
 * @param name - Название (может быть на русском)
 * @param prefix - Префикс для UID (по умолчанию 'gh-')
 * @returns Сгенерированный UID в формате: prefix-transliterated-name
 */
export function generateUid(name: string, prefix: string = 'gh-'): string {
  if (!name || name.trim().length === 0) {
    return `${prefix}untitled`
  }

  // Транслитерируем название
  let transliterated = transliterate(name.trim())

  // Приводим к нижнему регистру
  transliterated = transliterated.toLowerCase()

  // Убираем все символы, кроме букв, цифр и дефисов
  transliterated = transliterated.replace(/[^a-z0-9-]/g, '-')

  // Убираем множественные дефисы
  transliterated = transliterated.replace(/-+/g, '-')

  // Убираем дефисы в начале и конце
  transliterated = transliterated.replace(/^-+|-+$/g, '')

  // Если после обработки ничего не осталось, используем значение по умолчанию
  if (transliterated.length === 0) {
    transliterated = 'untitled'
  }

  // Ограничиваем длину (оставляем место для префикса)
  const maxLength = 50 - prefix.length
  if (transliterated.length > maxLength) {
    transliterated = transliterated.substring(0, maxLength)
    // Убираем возможный дефис в конце после обрезки
    transliterated = transliterated.replace(/-+$/, '')
  }

  return `${prefix}${transliterated}`
}

