/**
 * Ziggy Safe Install - безопасная установка ZiggyVue плагина
 * 
 * Обеспечивает корректную установку ZiggyVue для Vue 3 с проверкой версии
 * и обработкой ошибок при отсутствии Ziggy
 * 
 * Использование:
 *   import { installZiggy } from '@/utils/ziggy'
 *   await installZiggy(vueApp)
 */
import type { App } from 'vue'
import { logger } from './logger'

/**
 * Устанавливает версию Vue явно для корректной работы ZiggyVue
 * ZiggyVue проверяет версию Vue через parseInt(vueApp.version)
 * Если версия не установлена или undefined, parseInt вернет NaN, и ZiggyVue попытается использовать Vue 2 API
 * Vue 3 не имеет метода mixin, что приводит к ошибке "can't access property 'extend' of undefined"
 */
function ensureVueVersion(vueApp: App): void {
  if (!vueApp.version || typeof vueApp.version !== 'string') {
    // Устанавливаем версию Vue явно в формате строки "3.x.x"
    // parseInt("3.4.0") вернет 3, что больше 2, и ZiggyVue будет использовать Vue 3 API
    Object.defineProperty(vueApp, 'version', {
      value: '3.4.0',
      writable: false,
      configurable: false,
      enumerable: true,
    })
  }
}

/**
 * Безопасно устанавливает ZiggyVue плагин для Vue 3
 * 
 * @param vueApp - Экземпляр Vue приложения
 * @returns Promise, который разрешается после установки (или если Ziggy недоступен)
 */
export async function installZiggy(vueApp: App): Promise<void> {
  // Устанавливаем версию Vue СИНХРОННО перед любым использованием ZiggyVue
  ensureVueVersion(vueApp)
  
  try {
    // Динамический импорт для безопасной загрузки ZiggyVue
    // Путь относительно resources/js (app.js находится в resources/js)
    const ziggyModule = await import('../../../vendor/tightenco/ziggy/dist/index.esm.js')
    const ZiggyVue = ziggyModule.ZiggyVue || ziggyModule.default?.ZiggyVue || ziggyModule.default
    
    // Проверяем версию Vue перед использованием ZiggyVue
    const vueVersion = parseInt(vueApp.version || '0')
    if (vueVersion <= 2) {
      logger.error('[ziggy] Vue version is too old for ZiggyVue', {
        version: vueApp.version,
        parsed: vueVersion,
        note: 'ZiggyVue requires Vue 3. Setting version to 3.4.0',
      })
      ensureVueVersion(vueApp)
    }
    
    if (ZiggyVue && typeof ZiggyVue.install === 'function') {
      // Передаем vueApp и конфигурацию Ziggy в install()
      // ZiggyVue.install принимает два параметра: app и config
      // Если config не передан, ZiggyVue попытается найти Ziggy глобально
      ZiggyVue.install(vueApp, typeof Ziggy !== 'undefined' ? Ziggy : undefined)
      logger.debug('[ziggy] ZiggyVue installed successfully')
    } else if (ZiggyVue && typeof ZiggyVue === 'function') {
      // Если ZiggyVue - это функция, используем её как плагин
      vueApp.use(ZiggyVue)
      logger.debug('[ziggy] ZiggyVue installed as function plugin')
    } else {
      logger.warn('[ziggy] ZiggyVue is not a valid Vue plugin', { ZiggyVue })
    }
  } catch (err) {
    // Если Ziggy не установлен или не доступен, продолжаем без него
    logger.warn('[ziggy] ZiggyVue not available, continuing without it', { 
      err: err instanceof Error ? err.message : String(err) 
    })
  }
}

