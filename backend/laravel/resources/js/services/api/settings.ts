/**
 * Settings / user preferences API client.
 *
 * Эндпоинты:
 *   GET   /settings/preferences  — текущие preferences пользователя
 *   PATCH /settings/preferences  — частичное обновление
 */
import { apiGet, apiPatchVoid } from './_client'

export type UserPreferences = Record<string, unknown>

export const settingsApi = {
  getPreferences(): Promise<UserPreferences> {
    return apiGet<UserPreferences>('/settings/preferences')
  },

  updatePreferences(patch: UserPreferences): Promise<void> {
    return apiPatchVoid('/settings/preferences', patch)
  },
}
