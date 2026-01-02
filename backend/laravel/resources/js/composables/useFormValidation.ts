/**
 * Composable для улучшенной валидации и обработки ошибок форм
 */
import { computed, type Ref } from 'vue'
import type { Errors as FormErrors } from '@inertiajs/core'
import type { UseFormReturn } from '@inertiajs/vue3'

/**
 * Улучшенная обработка ошибок формы
 */
export function useFormValidation<T extends Record<string, unknown>>(
  form: UseFormReturn<T>
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
  function getError(field: keyof T): string | null {
    return form.errors[field as string] || null
  }

  /**
   * Проверяет, есть ли ошибка для конкретного поля
   */
  function hasError(field: keyof T): boolean {
    return !!form.errors[field as string]
  }

  /**
   * Получает классы для поля с ошибкой
   */
  function getErrorClasses(field: keyof T, baseClasses: string = ''): string {
    const errorClasses = 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]'
    const normalClasses = 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]'
    
    return hasError(field) 
      ? `${baseClasses} ${errorClasses}`.trim()
      : `${baseClasses} ${normalClasses}`.trim()
  }

  /**
   * Очищает ошибки для конкретного поля
   */
  function clearError(field: keyof T): void {
    form.clearErrors(field as string)
  }

  /**
   * Очищает все ошибки
   */
  function clearAllErrors(): void {
    form.clearErrors()
  }

  /**
   * Валидирует числовое значение в диапазоне
   */
  function validateNumberRange(
    value: number | null | undefined,
    min: number,
    max: number,
    fieldName: string
  ): string | null {
    if (value === null || value === undefined) {
      return `${fieldName} обязательно для заполнения`
    }
    if (value < min || value > max) {
      return `${fieldName} должен быть от ${min} до ${max}`
    }
    return null
  }

  /**
   * Валидирует строку на минимальную длину
   */
  function validateMinLength(
    value: string | null | undefined,
    minLength: number,
    fieldName: string
  ): string | null {
    if (!value || value.length < minLength) {
      return `${fieldName} должен содержать минимум ${minLength} символов`
    }
    return null
  }

  /**
   * Валидирует email
   */
  function validateEmail(email: string | null | undefined): string | null {
    if (!email) {
      return 'Email обязателен для заполнения'
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(email)) {
      return 'Некорректный формат email'
    }
    return null
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
