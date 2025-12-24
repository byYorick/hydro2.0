/**
 * Composable для унификации работы с Inertia формами
 * Предоставляет стандартные callbacks для onSuccess, onError, onFinish
 */
import { useForm, type UseFormReturn } from '@inertiajs/vue3'
import { router } from '@inertiajs/vue3'
import { useToast } from './useToast'
import { ERROR_MESSAGES, SUCCESS_MESSAGES } from '@/constants/messages'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { ToastHandler } from './useApi'

export interface UseInertiaFormOptions<T extends Record<string, unknown>> {
  /**
   * Функция для показа Toast уведомлений (опционально)
   * Если не передана, будет использован useToast
   */
  showToast?: ToastHandler

  /**
   * Сообщение об успехе (опционально)
   * Если не передано, будет использовано SUCCESS_MESSAGES.SAVED
   */
  successMessage?: string

  /**
   * Сообщение об ошибке (опционально)
   * Если не передано, будет использовано сообщение из ошибки валидации
   */
  errorMessage?: string

  /**
   * Должен ли показываться Toast при успехе (по умолчанию true)
   */
  showSuccessToast?: boolean

  /**
   * Должен ли показываться Toast при ошибке (по умолчанию true)
   */
  showErrorToast?: boolean

  /**
   * Должен ли выполняться reset формы при успехе (по умолчанию false)
   */
  resetOnSuccess?: boolean

  /**
   * Какие поля формы сбрасывать при успехе (опционально)
   * Если не указано, но resetOnSuccess=true, будет сброшена вся форма
   */
  resetFieldsOnSuccess?: (keyof T)[]

  /**
   * Функция, вызываемая при успехе (опционально)
   */
  onSuccess?: (page: any) => void

  /**
   * Функция, вызываемая при ошибке (опционально)
   */
  onError?: (errors: Record<string, string>) => void

  /**
   * Функция, вызываемая после завершения (опционально)
   */
  onFinish?: () => void

  /**
   * Callback для обновления store после успеха (рекомендуется)
   * Вместо reloadOnSuccess используйте этот callback для обновления данных
   */
  onStoreUpdate?: (data: any) => void

  /**
   * Должен ли выполняться reload после успеха (deprecated)
   * @deprecated Используйте onStoreUpdate для обновления store напрямую
   * Можно передать массив ключей для partial reload (only)
   */
  reloadOnSuccess?: boolean | string[]

  /**
   * Сохранять ли прокрутку (по умолчанию true)
   */
  preserveScroll?: boolean

  /**
   * Сохранять ли состояние (по умолчанию false)
   */
  preserveState?: boolean
}

/**
 * Создает обертку над useForm с унифицированными callbacks
 */
export function useInertiaForm<T extends Record<string, unknown>>(
  initialData: T,
  options: UseInertiaFormOptions<T> = {}
) {
  const {
    showToast: providedShowToast,
    successMessage,
    errorMessage,
    showSuccessToast = true,
    showErrorToast = true,
    resetOnSuccess = false,
    resetFieldsOnSuccess,
    onSuccess: customOnSuccess,
    onError: customOnError,
    onFinish: customOnFinish,
    onStoreUpdate,
    reloadOnSuccess = false,
    preserveScroll = true,
    preserveState = false,
  } = options

  // Используем useToast, если не передан showToast
  const { showToast: defaultShowToast } = useToast()
  const showToast = providedShowToast || defaultShowToast

  // Создаем форму через useForm
  const form = useForm<T>(initialData)

  /**
   * Унифицированный обработчик успеха
   */
  function handleSuccess(page: any): void {
    // Показываем Toast при успехе
    if (showSuccessToast) {
      const message = successMessage || SUCCESS_MESSAGES.SAVED
      showToast(message, 'success', TOAST_TIMEOUT.NORMAL)
    }

    // Сбрасываем форму при успехе, если нужно
    if (resetOnSuccess) {
      if (resetFieldsOnSuccess && resetFieldsOnSuccess.length > 0) {
        form.reset(...resetFieldsOnSuccess)
      } else {
        form.reset()
      }
    }

    // Обновляем store через callback (рекомендуемый способ)
    if (onStoreUpdate) {
      try {
        onStoreUpdate(page.props || page)
      } catch (error) {
        // eslint-disable-next-line no-console
        console.error('[useInertiaForm] Error in onStoreUpdate callback:', error)
      }
    }

    // Выполняем reload, если нужно (deprecated - используйте onStoreUpdate)
    if (reloadOnSuccess) {
      // eslint-disable-next-line no-console
      console.warn('[useInertiaForm] reloadOnSuccess is deprecated. Use onStoreUpdate callback instead.')
      if (Array.isArray(reloadOnSuccess)) {
        router.reload({ only: reloadOnSuccess, preserveScroll, preserveState })
      } else {
        router.reload({ preserveScroll, preserveState })
      }
    }

    // Вызываем пользовательский callback
    if (customOnSuccess) {
      customOnSuccess(page)
    }
  }

  /**
   * Унифицированный обработчик ошибок
   */
  function handleError(errors: Record<string, string>): void {
    // Показываем Toast при ошибке
    if (showErrorToast) {
      const message =
        errorMessage ||
        (Object.keys(errors).length > 0
          ? ERROR_MESSAGES.VALIDATION
          : ERROR_MESSAGES.UNKNOWN)
      showToast(message, 'error', TOAST_TIMEOUT.LONG)
    }

    // Вызываем пользовательский callback
    if (customOnError) {
      customOnError(errors)
    }
  }

  /**
   * Унифицированный обработчик завершения
   */
  function handleFinish(): void {
    // Вызываем пользовательский callback
    if (customOnFinish) {
      customOnFinish()
    }
  }

  /**
   * Обертка для form.submit с унифицированными callbacks
   */
  function submit(
    method: 'get' | 'post' | 'put' | 'patch' | 'delete',
    url: string,
    options: {
      preserveScroll?: boolean
      preserveState?: boolean
      only?: string[]
      onSuccess?: (page: any) => void
      onError?: (errors: Record<string, string>) => void
      onFinish?: () => void
    } = {}
  ) {
    const {
      preserveScroll: optionPreserveScroll = preserveScroll,
      preserveState: optionPreserveState = preserveState,
      only,
      onSuccess: optionOnSuccess,
      onError: optionOnError,
      onFinish: optionOnFinish,
    } = options

    // Объединяем callbacks
    const combinedOnSuccess = optionOnSuccess
      ? (page: any) => {
          handleSuccess(page)
          optionOnSuccess(page)
        }
      : handleSuccess

    const combinedOnError = optionOnError
      ? (errors: Record<string, string>) => {
          handleError(errors)
          optionOnError(errors)
        }
      : handleError

    const combinedOnFinish = optionOnFinish
      ? () => {
          handleFinish()
          optionOnFinish()
        }
      : handleFinish

    // Создаем опции для submit
    const submitOptions: any = {
      preserveScroll: optionPreserveScroll,
      preserveState: optionPreserveState,
      onSuccess: combinedOnSuccess,
      onError: combinedOnError,
      onFinish: combinedOnFinish,
    }

    if (only) {
      submitOptions.only = only
    }

    // Вызываем соответствующий метод формы
    switch (method) {
      case 'get':
        form.get(url, submitOptions)
        break
      case 'post':
        form.post(url, submitOptions)
        break
      case 'put':
        form.put(url, submitOptions)
        break
      case 'patch':
        form.patch(url, submitOptions)
        break
      case 'delete':
        form.delete(url, submitOptions)
        break
    }
  }

  return {
    form,
    submit,
    handleSuccess,
    handleError,
    handleFinish,
  }
}

