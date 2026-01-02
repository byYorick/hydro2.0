/**
 * Vue Error Handlers - централизованная обработка ошибок Vue
 * 
 * Настраивает глобальные обработчики ошибок и предупреждений Vue
 * без перезагрузки страницы и с безопасным логированием
 * 
 * Использование:
 *   import { setupVueErrorHandlers } from '@/utils/vueErrorHandlers'
 *   setupVueErrorHandlers(vueApp)
 */
import type { App } from 'vue'
import { logger } from './logger'

/**
 * Обработчик ошибок Vue без перезагрузки страницы
 * Игнорирует отмененные запросы Inertia.js
 */
function createErrorHandler(_vueApp: App): (err: unknown, instance: any, info: string) => void {
  return (err, instance, info) => {
    // Игнорируем отмененные запросы Inertia.js
    if (
      (err as any)?.code === 'ERR_CANCELED' ||
      (err as any)?.name === 'CanceledError' ||
      (err as any)?.message === 'canceled'
    ) {
      return
    }
    
    // Извлекаем только безопасные свойства для избежания циклических ссылок
    const safeError = err instanceof Error ? {
      message: err.message || String(err),
      name: err.name,
      stack: err.stack ? err.stack.split('\n').slice(0, 10).join('\n') : undefined, // Ограничиваем stack
      code: (err as any).code,
    } : {
      message: String(err),
      type: typeof err,
    }
    
    const safeInstance = instance ? {
      componentName: instance.$options?.name || instance.$options?.__name || 'Unknown',
      tag: instance.$vnode?.tag || instance.$el?.tagName || undefined,
    } : undefined
    
    // Логируем только безопасные данные
    logger.error('[VUE ERROR]', { 
      error: safeError,
      info: typeof info === 'string' ? info : undefined,
      instance: safeInstance,
    })
    // НЕ вызываем location.reload() или router.reload() здесь
    // Ошибки должны обрабатываться через ErrorBoundary компонент
  }
}

/**
 * Обработчик предупреждений Vue с безопасным логированием
 */
function createWarnHandler(): (msg: string, instance: any, trace: string) => void {
  return (msg, instance, trace) => {
    // Извлекаем только безопасные свойства для избежания циклических ссылок
    const safeInstance = instance ? {
      $options: instance.$options ? {
        name: instance.$options.name,
        __name: instance.$options.__name,
      } : undefined,
    } : undefined
    
    logger.warn('[VUE WARN]', { 
      message: msg,
      trace: trace || undefined,
      instance: safeInstance,
    })
  }
}

/**
 * Настраивает глобальные обработчики ошибок и предупреждений Vue
 * 
 * @param vueApp - Экземпляр Vue приложения
 */
export function setupVueErrorHandlers(vueApp: App): void {
  vueApp.config.errorHandler = createErrorHandler(vueApp)
  vueApp.config.warnHandler = createWarnHandler()
}
