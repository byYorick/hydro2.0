import { describe, it, expect, vi } from 'vitest'
import { useFormValidation } from '../useFormValidation'
import { useForm } from '@inertiajs/vue3'

describe('useFormValidation (P3-3)', () => {
  it('should detect errors in form', () => {
    const form = useForm({ name: '', email: '' })
    // @ts-ignore - для теста устанавливаем ошибки напрямую
    form.errors = { name: 'Name is required' }
    
    const { hasErrors, getError } = useFormValidation(form)

    expect(hasErrors.value).toBe(true)
    expect(getError('name')).toBe('Name is required')
  })

  it('should return first error', () => {
    const form = useForm({ name: '', email: '' })
    // @ts-ignore
    form.errors = {
      name: 'Name is required',
      email: 'Email is invalid'
    }
    
    const { firstError } = useFormValidation(form)

    expect(firstError.value).toBe('Name is required')
  })

  it('should check if specific field has error', () => {
    const form = useForm({ name: '', email: '' })
    // @ts-ignore
    form.errors = { name: 'Name is required' }
    
    const { hasError } = useFormValidation(form)

    expect(hasError('name')).toBe(true)
    expect(hasError('email')).toBe(false)
  })

  it('should return error classes for field with error', () => {
    const form = useForm({ name: '', email: '' })
    // @ts-ignore
    form.errors = { name: 'Name is required' }
    
    const { getErrorClasses } = useFormValidation(form)

    const classes = getErrorClasses('name', 'base-class')
    expect(classes).toContain('border-[color:var(--accent-red)]')
    expect(classes).toContain('bg-[color:var(--badge-danger-bg)]')
  })

  it('should return normal classes for field without error', () => {
    const form = useForm({ name: '', email: '' })
    // @ts-ignore
    form.errors = {}
    
    const { getErrorClasses } = useFormValidation(form)

    const classes = getErrorClasses('name', 'base-class')
    expect(classes).toContain('border-[color:var(--border-muted)]')
    expect(classes).toContain('bg-[color:var(--bg-elevated)]')
  })

  it('should clear error for specific field', () => {
    const form = useForm({ name: '', email: '' })
    // @ts-ignore
    form.errors = { name: 'Name is required' }
    const clearErrorsSpy = vi.spyOn(form, 'clearErrors')
    
    const { clearError } = useFormValidation(form)

    clearError('name')
    expect(clearErrorsSpy).toHaveBeenCalledWith('name')
  })

  it('should clear all errors', () => {
    const form = useForm({ name: '', email: '' })
    // @ts-ignore
    form.errors = { name: 'Name is required', email: 'Email is invalid' }
    const clearErrorsSpy = vi.spyOn(form, 'clearErrors')
    
    const { clearAllErrors } = useFormValidation(form)

    clearAllErrors()
    expect(clearErrorsSpy).toHaveBeenCalled()
  })

  it('should validate number range correctly', () => {
    const form = useForm({})
    const { validateNumberRange } = useFormValidation(form)

    expect(validateNumberRange(5, 1, 10, 'Value')).toBeNull()
    expect(validateNumberRange(0, 1, 10, 'Value')).toContain('должен быть от 1 до 10')
    expect(validateNumberRange(11, 1, 10, 'Value')).toContain('должен быть от 1 до 10')
    expect(validateNumberRange(null, 1, 10, 'Value')).toContain('обязательно')
  })

  it('should validate minimum length', () => {
    const form = useForm({})
    const { validateMinLength } = useFormValidation(form)

    expect(validateMinLength('test', 3, 'Field')).toBeNull()
    expect(validateMinLength('te', 3, 'Field')).toContain('минимум 3 символов')
    expect(validateMinLength(null, 3, 'Field')).toContain('минимум 3 символов')
  })

  it('should validate email format', () => {
    const form = useForm({})
    const { validateEmail } = useFormValidation(form)

    expect(validateEmail('test@example.com')).toBeNull()
    expect(validateEmail('invalid-email')).toContain('Некорректный формат')
    expect(validateEmail(null)).toContain('обязателен')
  })
})
