/**
 * Роль пользователя
 */
export type UserRole = 'admin' | 'operator' | 'viewer' | 'agronomist' | 'engineer'

/**
 * Модель пользователя
 */
export interface User {
  id: number
  name: string
  email: string
  role?: UserRole
  preferences?: {
    alert_toast_suppression_sec?: number
    [key: string]: unknown
  }
  email_verified_at?: string | null
  created_at?: string
  updated_at?: string
}
