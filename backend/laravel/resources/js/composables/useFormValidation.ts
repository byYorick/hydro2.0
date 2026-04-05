/**
 * Composable для улучшенной валидации и обработки ошибок форм
 */
import { computed } from 'vue'
import type { InertiaForm } from '@inertiajs/vue3'
import type { FormDataKeys } from '@inertiajs/core'
import {
  validateEmail,
  validateMinLength,
  validateNumberRange,
} from '@/utils/validation'

export { validateEmail, validateMinLength, validateNumberRange }

/**
 * Улучшенная обработка ошибок формы
 */
export function useFormValidation<T extends Record<string, unknown>>(
  form: InertiaForm<T>
) {
  /**
   * Проверяет, есть ли ошибки в форме
   */
  const hasErrors = computed<boolean>(() => {
    return Object.keys(form.errors).length > 0
  })

  /**
   * Получает первую ошибку из формы
   */
  const firstError = computed<string | null>(() => {
    const errors = form.errors
    const firstKey = Object.keys(errors)[0]
    return firstKey ? errors[firstKey] : null
  })

  /**
   * Получает ошибку для конкретного поля
   */
  function getError(field: FormDataKeys<T>): string | null {
    return form.errors[field] || null
  }

  /**
   * Проверяет, есть ли ошибка для конкретного поля
   */
  function hasError(field: FormDataKeys<T>): boolean {
    return !!form.errors[field]
  }

  /**
   * Получает классы для поля с ошибкой
   */
  function getErrorClasses(field: FormDataKeys<T>, baseClasses: string = ''): string {
    const errorClasses = 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]'
    const normalClasses = 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]'
    
    return hasError(field) 
      ? `${baseClasses} ${errorClasses}`.trim()
      : `${baseClasses} ${normalClasses}`.trim()
  }

  /**
   * Очищает ошибки для конкретного поля
   */
  function clearError(field: FormDataKeys<T>): void {
    form.clearErrors(field)
  }

  /**
   * Очищает все ошибки
   */
  function clearAllErrors(): void {
    form.clearErrors()
  }

  return {
    hasErrors,
    firstError,
    getError,
    hasError,
    getErrorClasses,
    clearError,
    clearAllErrors,
    validateNumberRange,
    validateMinLength,
    validateEmail,
  }
}
