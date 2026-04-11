/**
 * Internal re-export of apiClient for domain-specific API modules.
 *
 * This is the ONLY place outside `services/api/` that is allowed to import
 * `@/utils/apiClient`. Everything else must go through a typed domain client
 * (e.g. `api.zones.getById(id)`).
 *
 * The lint rule `no-restricted-imports` (see .eslintrc.cjs) enforces this boundary.
 */
import apiClient, { type ToastHandler } from '@/utils/apiClient'
import { extractData } from '@/utils/apiHelpers'
import type { AxiosRequestConfig } from 'axios'

export { apiClient }
export type { ToastHandler }

/**
 * GET request that automatically unwraps `{ data: T }` envelopes.
 *
 * Use this when the backend returns a typed payload. If the endpoint is known
 * to wrap in `{ data: ... }` we handle both shapes transparently.
 */
export async function apiGet<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const response = await apiClient.get<unknown>(url, config)
  const data = extractData<T>(response.data)
  if (data === null || data === undefined) {
    throw new Error(`[api] GET ${url}: empty response payload`)
  }
  return data
}

/**
 * POST request that automatically unwraps `{ data: T }` envelopes.
 */
export async function apiPost<T>(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  const response = await apiClient.post<unknown>(url, body, config)
  const data = extractData<T>(response.data)
  if (data === null || data === undefined) {
    throw new Error(`[api] POST ${url}: empty response payload`)
  }
  return data
}

/**
 * PATCH request that automatically unwraps `{ data: T }` envelopes.
 */
export async function apiPatch<T>(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  const response = await apiClient.patch<unknown>(url, body, config)
  const data = extractData<T>(response.data)
  if (data === null || data === undefined) {
    throw new Error(`[api] PATCH ${url}: empty response payload`)
  }
  return data
}

/**
 * PUT request that automatically unwraps `{ data: T }` envelopes.
 */
export async function apiPut<T>(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  const response = await apiClient.put<unknown>(url, body, config)
  const data = extractData<T>(response.data)
  if (data === null || data === undefined) {
    throw new Error(`[api] PUT ${url}: empty response payload`)
  }
  return data
}

/**
 * DELETE request.
 * Returns the parsed body if present, otherwise void.
 */
export async function apiDelete<T = void>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const response = await apiClient.delete<unknown>(url, config)
  return extractData<T>(response.data) as T
}

/**
 * POST with no body expected in response (204/empty payload allowed).
 * Use for endpoints like `/publish`, `/ack` where the caller only cares
 * about success/failure, not data.
 */
export async function apiPostVoid(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<void> {
  await apiClient.post(url, body, config)
}

/**
 * PATCH with no body expected in response.
 */
export async function apiPatchVoid(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<void> {
  await apiClient.patch(url, body, config)
}
