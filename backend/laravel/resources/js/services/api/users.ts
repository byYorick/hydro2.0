/**
 * Users administration API client.
 *
 * Endpoints:
 *   GET    /api/users                 — список пользователей
 *   POST   /settings/users            — создать
 *   PATCH  /settings/users/:id        — обновить
 *   DELETE /settings/users/:id        — удалить
 *
 * Note: read live из `/api/users`, а write идут в `/settings/users/*`.
 * Это backend-контракт, фронтенд только его отражает.
 */
import type { User } from '@/types'
import { apiGet, apiPost, apiPatch, apiDelete } from './_client'

export interface UserPayload {
  name: string
  email: string
  password?: string
  role: string
}

export const usersApi = {
  list(): Promise<User[]> {
    return apiGet<User[]>('/users')
  },

  create(payload: UserPayload): Promise<User> {
    return apiPost<User>('/settings/users', payload)
  },

  update(userId: number, payload: UserPayload): Promise<User> {
    return apiPatch<User>(`/settings/users/${userId}`, payload)
  },

  delete(userId: number): Promise<void> {
    return apiDelete<void>(`/settings/users/${userId}`)
  },
}
